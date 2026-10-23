import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import backup_state
from automatic_backups import AutomaticBackups, SnapshotGate


class AutomaticBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        for name, kind in backup_state.JSON_FILES.items():
            (self.data / name).write_text(json.dumps(kind()))
        self.db = self.data / backup_state.DATABASE
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE game_results (puzzle_id TEXT, points INTEGER, route_json TEXT, hints_used INTEGER)')
            db.execute("INSERT INTO game_results VALUES ('original',25,'[]',0)")
        self.gate = SnapshotGate()
        self.manager = AutomaticBackups(self.data, self.db, self.gate, enabled=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_daily_backup_survives_restart_and_does_not_duplicate(self):
        archive = self.manager.maybe_backup()
        self.assertIsNotNone(archive)
        backup_state.read_backup(archive)
        self.assertEqual(self.manager.status()['local_status'], 'verified')
        self.assertEqual(self.manager.status()['off_server_status'], 'not_configured')
        self.assertIsNone(self.manager.maybe_backup())
        fresh = AutomaticBackups(self.data, self.db, self.gate, enabled=True)
        self.assertIsNone(fresh.maybe_backup())
        self.assertEqual(fresh.status()['local_status'], 'verified')
        self.assertEqual(len(fresh.archives()), 1)

    def test_due_backup_refreshes_and_manifest_truthfully_records_quiesced_writes(self):
        first = self.manager.maybe_backup()
        self.manager.last_success -= self.manager.interval_seconds + 301
        self.assertEqual(self.manager.status()['local_status'], 'stale')
        second = self.manager.maybe_backup()
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        with backup_state.zipfile.ZipFile(second) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
        self.assertFalse(manifest['server_stopped_confirmed'])
        self.assertTrue(manifest['writes_quiesced_confirmed'])
        self.assertEqual(manifest['kind'], 'automatic-local')

    def test_retention_keeps_seven_verified_automatic_copies_and_named_checkpoint(self):
        self.manager.interval_seconds = 0
        self.manager.folder.mkdir()
        named = self.manager.folder / 'production-2026-10-22.zip'
        backup_state.create_backup(self.data, named, server_stopped=True)
        named_bytes = named.read_bytes()
        unknown = self.manager.folder / 'keep.txt'
        unknown.write_text('keep')
        for _ in range(9):
            self.assertIsNotNone(self.manager.maybe_backup())
        self.assertEqual(len(self.manager.archives()), 7)
        self.assertEqual(named.read_bytes(), named_bytes)
        self.assertEqual(unknown.read_text(), 'keep')
        for archive in self.manager.archives():
            backup_state.read_backup(archive)

    def test_corrupt_automatic_file_is_preserved_without_blocking_new_backups(self):
        self.manager.folder.mkdir()
        bad = self.manager.folder / 'automatic-20990101T000000000000Z-12345678.zip'
        bad.write_bytes(b'corrupt')
        self.assertIsNotNone(self.manager.maybe_backup())
        self.assertEqual(bad.read_bytes(), b'corrupt')
        self.assertTrue(self.manager.status()['retention_warning'])
        self.assertEqual(self.manager.status()['local_status'], 'verified')

    def test_failure_does_not_prune_or_claim_success_and_retry_recovers(self):
        archive = self.manager.maybe_backup()
        original = archive.read_bytes()
        self.manager.interval_seconds = 0
        with patch('automatic_backups.create_backup', side_effect=OSError('disk full')):
            self.assertIsNone(self.manager.maybe_backup())
        self.assertIsNotNone(self.manager.status()['last_failure_at'])
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(len(self.manager.archives()), 1)
        self.assertIsNotNone(self.manager.maybe_backup())
        self.assertIsNone(self.manager.status()['last_failure_at'])

    def test_disabled_backup_never_creates_files(self):
        self.manager.enabled = False
        self.assertIsNone(self.manager.start())
        self.assertIsNone(self.manager.maybe_backup())
        self.assertFalse(self.manager.folder.exists())

    def test_snapshot_waits_for_complete_request_and_new_requests_wait_for_snapshot(self):
        request_started = threading.Event()
        release_request = threading.Event()
        snapshot_started = threading.Event()
        release_snapshot = threading.Event()
        next_request = threading.Event()
        def operation():
            with self.gate.operation():
                request_started.set()
                release_request.wait(3)
        def snapshot():
            with self.gate.snapshot():
                snapshot_started.set()
                release_snapshot.wait(3)
        def following():
            with self.gate.operation():
                next_request.set()
        first = threading.Thread(target=operation)
        writer = threading.Thread(target=snapshot)
        second = threading.Thread(target=following)
        first.start()
        self.assertTrue(request_started.wait(1))
        writer.start()
        try:
            self.assertFalse(snapshot_started.wait(.05))
            release_request.set()
            self.assertTrue(snapshot_started.wait(1))
            second.start()
            self.assertFalse(next_request.wait(.05))
            release_snapshot.set()
            self.assertTrue(next_request.wait(1))
        finally:
            release_request.set(); release_snapshot.set()
            first.join(3); writer.join(3)
            if second.ident is not None:
                second.join(3)

    def test_gate_timeout_and_exception_release_requests(self):
        with self.gate.operation():
            with self.assertRaises(TimeoutError):
                with self.gate.snapshot(timeout=.01):
                    self.fail('Snapshot entered during a request')
        with self.assertRaises(ValueError):
            with self.gate.snapshot():
                raise ValueError('test')
        with self.gate.operation():
            self.assertEqual(self.gate.requests, 1)

    def test_requests_still_run_concurrently(self):
        barrier = threading.Barrier(3)
        def request():
            with self.gate.operation():
                barrier.wait(timeout=2)
                barrier.wait(timeout=2)
        a = threading.Thread(target=request); b = threading.Thread(target=request)
        a.start(); b.start()
        barrier.wait(timeout=2)
        self.assertEqual(self.gate.requests, 2)
        barrier.wait(timeout=2)
        a.join(2); b.join(2)

    def test_cross_file_snapshot_includes_complete_request_not_half_a_write(self):
        started = threading.Event(); finish = threading.Event()
        def request():
            with self.gate.operation():
                (self.data / 'active_puzzles.json').write_text('{"revision":1}')
                started.set()
                finish.wait(2)
                (self.data / 'challenges.json').write_text('{"revision":1}')
        worker = threading.Thread(target=request); worker.start()
        self.assertTrue(started.wait(1))
        timer = threading.Timer(.05, finish.set); timer.start()
        try:
            archive = self.manager.maybe_backup()
            self.assertIsNotNone(archive)
            payload = backup_state.read_backup(archive)
            self.assertEqual(json.loads(payload['active_puzzles.json']), {'revision': 1})
            self.assertEqual(json.loads(payload['challenges.json']), {'revision': 1})
        finally:
            finish.set(); worker.join(3); timer.join(3)


if __name__ == '__main__':
    unittest.main()
