#!/usr/bin/env python3
"""Offline game-state backups. Run --help; stop the game server before creating one."""
import argparse
from contextlib import closing
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

JSON_FILES = {
    'active_puzzles.json': dict,
    'challenges.json': dict,
    'used_starters.json': list,
    'eligibility_overrides.json': dict,
}
DATABASE = 'game_results.sqlite3'
MANIFEST = 'manifest.json'
FILES = set(JSON_FILES) | {DATABASE}


def check_database(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('Results database integrity check failed')
        columns = {row[1] for row in db.execute('PRAGMA table_info(game_results)')}
        if not {'puzzle_id', 'points', 'route_json', 'hints_used'} <= columns:
            raise ValueError('Results database is missing game-results columns')


def check_json(name, data):
    if not isinstance(json.loads(data), JSON_FILES[name]):
        raise ValueError('Unexpected JSON structure: ' + name)


def read_backup(archive):
    """Validate every member before exposing bytes to the restore operation."""
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or set(names) != FILES | {MANIFEST}:
            raise ValueError('Backup contains missing, duplicate or unexpected files')
        manifest = json.loads(bundle.read(MANIFEST))
        if (not isinstance(manifest, dict) or manifest.get('format_version') != 1
                or not isinstance(manifest.get('files'), dict) or set(manifest['files']) != FILES):
            raise ValueError('Unsupported or incomplete backup manifest')
        payload = {}
        for name in sorted(FILES):
            data = bundle.read(name)
            entry = manifest['files'][name]
            if (not isinstance(entry, dict) or entry.get('size') != len(data)
                    or entry.get('sha256') != hashlib.sha256(data).hexdigest()):
                raise ValueError('Backup integrity mismatch: ' + name)
            if name in JSON_FILES:
                check_json(name, data)
            payload[name] = data
    with tempfile.TemporaryDirectory(prefix='make-the-cut-verify-') as folder:
        database = Path(folder) / DATABASE
        database.write_bytes(payload[DATABASE])
        check_database(database)
    return payload


def create_backup(data_dir, output, *, server_stopped=False, results_db=None):
    if not server_stopped:
        raise ValueError('Stop the game server and pass --server-stopped before creating a backup')
    data_dir, output = Path(data_dir).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Backup output already exists; choose a new filename')
    database = Path(results_db).resolve() if results_db else data_dir / DATABASE
    check_database(database)
    payload = {}
    absent = []
    for name in JSON_FILES:
        try:
            data = (data_dir / name).read_bytes()
        except FileNotFoundError:
            if name == 'active_puzzles.json':
                raise
            # The server treats not-yet-created invitations, starter history
            # and local overrides as empty; retain that explicit empty state.
            absent.append(name)
            data = json.dumps(JSON_FILES[name]()).encode()
        check_json(name, data)
        payload[name] = data
    # SQLite's backup API includes committed WAL data; copying only the main
    # database file can silently omit recent results.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='make-the-cut-backup-', dir=output.parent) as folder:
        database_copy = Path(folder) / DATABASE
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(database_copy)) as target:
            with target:
                source.backup(target)
        payload[DATABASE] = database_copy.read_bytes()
        manifest = {
            'format_version': 1,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'server_stopped_confirmed': True,
            'absent_state_files': absent,
            'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                      for name, data in sorted(payload.items())},
        }
        temporary_archive = Path(folder) / 'state.zip'
        with zipfile.ZipFile(temporary_archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(MANIFEST, json.dumps(manifest, sort_keys=True))
            for name, data in sorted(payload.items()):
                bundle.writestr(name, data)
        temporary_archive.chmod(0o600)
        read_backup(temporary_archive)
        # Publish without replacing an existing backup, including a racing writer.
        os.link(temporary_archive, output)
    return output


def restore_backup(archive, destination):
    payload = read_backup(archive)
    destination = Path(destination).resolve()
    # Restoring into an existing directory could mix old and recovered state.
    destination.mkdir(mode=0o700)
    for name, data in payload.items():
        path = destination / name
        with path.open('xb') as file:
            file.write(data)
        path.chmod(0o600)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='Create a backup with the server stopped')
    create.add_argument('--data-dir', required=True, type=Path)
    create.add_argument('--output', required=True, type=Path)
    create.add_argument('--results-db', type=Path, default=os.environ.get('RESULTS_DB'))
    create.add_argument('--server-stopped', action='store_true')
    verify = commands.add_parser('verify', help='Validate a backup without restoring it')
    verify.add_argument('--backup', required=True, type=Path)
    restore = commands.add_parser('restore', help='Restore into a new directory without overwriting live data')
    restore.add_argument('--backup', required=True, type=Path)
    restore.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'create':
            create_backup(args.data_dir, args.output, server_stopped=args.server_stopped, results_db=args.results_db)
            print('Backup created and verified.')
        elif args.command == 'verify':
            read_backup(args.backup)
            print('Backup integrity verified.')
        else:
            restore_backup(args.backup, args.destination)
            print('Backup restored into the new directory. Original timestamps and expiry windows are unchanged.')
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile, KeyError, TypeError) as error:
        parser.exit(1, 'Backup operation failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
