"""Daily private local snapshots for the single-process game server."""
from contextlib import contextmanager
import datetime
import json
from pathlib import Path
import re
import secrets
import threading
import time
import zipfile

from backup_state import create_backup, read_backup

AUTOMATIC_NAME = re.compile(r'automatic-\d{8}T\d{12}Z-[0-9a-f]{8}\.zip')


class SnapshotGate:
    """Requests remain concurrent; a snapshot waits for all writers to finish.

    A pending snapshot briefly holds new requests to avoid starvation. It gives
    up after timeout instead of waiting indefinitely behind a slow provider.
    """
    def __init__(self):
        self.condition = threading.Condition()
        self.requests = 0
        self.snapshot_pending = False

    @contextmanager
    def operation(self):
        with self.condition:
            while self.snapshot_pending:
                self.condition.wait()
            self.requests += 1
        try:
            yield
        finally:
            with self.condition:
                self.requests -= 1
                self.condition.notify_all()

    @contextmanager
    def snapshot(self, timeout=2):
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.snapshot_pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Snapshot gate busy')
                self.condition.wait(remaining)
            self.snapshot_pending = True
            try:
                while self.requests:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Requests still in progress')
                    self.condition.wait(remaining)
            except BaseException:
                self.snapshot_pending = False
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            with self.condition:
                self.snapshot_pending = False
                self.condition.notify_all()


class AutomaticBackups:
    def __init__(self, data_dir, results_db, gate, *, enabled=False,
                 interval_seconds=86400, keep=7):
        self.data_dir = Path(data_dir)
        self.results_db = Path(results_db)
        self.gate = gate
        self.enabled = enabled
        self.interval_seconds = interval_seconds
        self.keep = keep
        self.lock = threading.Lock()
        self.cycle_lock = threading.Lock()
        self.stop = threading.Event()
        self.last_success = None
        self.last_failure = None
        self.retention_warning = False

    @property
    def folder(self):
        return self.data_dir / 'backups'

    def archives(self):
        if self.folder.is_symlink():
            raise ValueError('Backup directory cannot be a symbolic link')
        if not self.folder.exists():
            return []
        return sorted((p for p in self.folder.iterdir()
                       if AUTOMATIC_NAME.fullmatch(p.name) and p.is_file()
                       and not p.is_symlink()), reverse=True)

    def verified_time(self, archive):
        read_backup(archive)
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
        if manifest.get('kind') != 'automatic-local':
            raise ValueError('Archive is not an automatic checkpoint')
        created = datetime.datetime.fromisoformat(manifest['created_at'])
        if created.tzinfo is None:
            raise ValueError('Backup time must include timezone')
        return created.timestamp()

    def status(self):
        with self.lock:
            last = self.last_success
            return {'enabled': self.enabled,
                    'local_status': ('disabled' if not self.enabled else
                        ('failed' if self.last_failure else 'pending') if last is None else
                        'stale' if time.time() - last > self.interval_seconds + 300 else 'verified'),
                    'last_success_at': None if last is None else datetime.datetime.fromtimestamp(last, datetime.timezone.utc).isoformat(),
                    'last_failure_at': self.last_failure,
                    'retention_warning': self.retention_warning,
                    'local_copies_kept': self.keep,
                    'interval_seconds': self.interval_seconds,
                    'off_server_status': 'not_configured'}

    def maybe_backup(self):
        if not self.enabled or not self.cycle_lock.acquire(blocking=False):
            return None
        try:
            now = time.time()
            with self.lock:
                last = self.last_success
            if last is None:
                for existing in self.archives():
                    try:
                        candidate = self.verified_time(existing)
                        if candidate > now + 300:
                            raise ValueError('Backup timestamp is in the future')
                    except Exception:
                        with self.lock:
                            self.retention_warning = True
                        continue
                    last = candidate
                    with self.lock:
                        self.last_success = last
                    break
            if last is not None and now - last < self.interval_seconds:
                return None
            self.folder.mkdir(mode=0o700, exist_ok=True)
            name = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            archive = self.folder / ('automatic-' + name + '-' + secrets.token_hex(4) + '.zip')
            with self.gate.snapshot():
                create_backup(self.data_dir, archive, results_db=self.results_db,
                              writes_quiesced=True, kind='automatic-local')
            created = self.verified_time(archive)
            with self.lock:
                self.last_success = created
                self.last_failure = None
            print('Automatic local backup verified:', archive, flush=True)
            # Only our own generated, verified automatic archives are pruned.
            # Named checkpoints, corrupt files, unknown files and symlinks stay.
            warning = False
            verified = []
            for old in self.archives():
                try:
                    self.verified_time(old)
                    verified.append(old)
                except Exception:
                    warning = True
            for old in verified[self.keep:]:
                try:
                    old.unlink()
                except Exception:
                    warning = True
            with self.lock:
                self.retention_warning = warning
            if warning:
                print('Automatic backup retention needs attention.', flush=True)
            return archive
        except Exception as error:
            with self.lock:
                self.last_failure = datetime.datetime.now(datetime.timezone.utc).isoformat()
            print('Automatic local backup failed:', type(error).__name__, flush=True)
            return None
        finally:
            self.cycle_lock.release()

    def start(self):
        if not self.enabled:
            return None
        def run():
            while not self.stop.is_set():
                self.maybe_backup()
                self.stop.wait(60)
        worker = threading.Thread(target=run, name='automatic-local-backups', daemon=True)
        worker.start()
        return worker
