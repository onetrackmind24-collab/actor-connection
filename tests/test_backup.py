import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

import backup_state as backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / 'source'
        self.data.mkdir()
        states = {
            'active_puzzles.json': {'round': {'hints_used': 2, 'created': 123}},
            'challenges.json': {'invite': {'expires': 456, 'benchmark': {'points': -20}}},
            'used_starters.json': ['John C. Reilly'],
            'eligibility_overrides.json': {'movie': {'actor': {'eligible': False}}},
        }
        for name, value in states.items():
            (self.data / name).write_text(json.dumps(value))
        self.db = sqlite3.connect(self.data / backup.DATABASE)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE game_results (puzzle_id TEXT, points INTEGER, route_json TEXT, hints_used INTEGER)')
        self.db.execute("INSERT INTO game_results VALUES ('round',-20,'[]',2)")
        self.db.commit()
        self.archive = self.root / 'backup.zip'
        self.destination = self.root / 'restored'

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def create(self, **kwargs):
        return backup.create_backup(self.data, self.archive, server_stopped=True, **kwargs)

    def test_round_trip_includes_committed_wal_results_and_preserves_state(self):
        self.assertTrue(Path(str(self.data / backup.DATABASE) + '-wal').exists())
        self.create()
        backup.restore_backup(self.archive, self.destination)
        for name in backup.JSON_FILES:
            self.assertEqual((self.destination / name).read_bytes(), (self.data / name).read_bytes())
        with sqlite3.connect(self.destination / backup.DATABASE) as db:
            self.assertEqual(db.execute('SELECT * FROM game_results').fetchall(), [('round', -20, '[]', 2)])
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)

    def test_absent_optional_state_uses_explicit_empty_defaults(self):
        for name in backup.JSON_FILES:
            if name != 'active_puzzles.json':
                (self.data / name).unlink()
        self.create()
        backup.restore_backup(self.archive,self.destination)
        self.assertEqual(json.loads((self.destination/'challenges.json').read_text()),{})
        self.assertEqual(json.loads((self.destination/'used_starters.json').read_text()),[])
        with zipfile.ZipFile(self.archive) as bundle:
            manifest=json.loads(bundle.read(backup.MANIFEST))
        self.assertEqual(set(manifest['absent_state_files']),set(backup.JSON_FILES)-{'active_puzzles.json'})

    def test_creation_requires_server_stopped_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'server-stopped'):
            backup.create_backup(self.data, self.archive)
        self.assertFalse(self.archive.exists())

    def test_existing_backup_and_restore_directory_are_never_overwritten(self):
        self.create()
        original = self.archive.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(self.archive.read_bytes(), original)
        self.destination.mkdir()
        sentinel = self.destination / 'keep.txt'
        sentinel.write_text('original')
        with self.assertRaises(FileExistsError):
            backup.restore_backup(self.archive, self.destination)
        self.assertEqual(sentinel.read_text(), 'original')
        self.assertEqual(list(self.destination.iterdir()), [sentinel])

    def test_invalid_source_json_does_not_publish_a_backup(self):
        for content in ('broken JSON', '[]'):
            (self.data / 'active_puzzles.json').write_text(content)
            with self.assertRaises(ValueError):
                self.create()
            self.assertFalse(self.archive.exists())

    def test_corrupt_database_is_rejected(self):
        invalid = self.root / 'invalid.sqlite3'
        invalid.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            self.create(results_db=invalid)
        self.assertFalse(self.archive.exists())

    def test_modified_backup_is_rejected_before_creating_restore_directory(self):
        self.create()
        with zipfile.ZipFile(self.archive) as source:
            members = {name: source.read(name) for name in source.namelist()}
        members['active_puzzles.json'] = b'{}'
        altered = self.root / 'altered.zip'
        with zipfile.ZipFile(altered, 'w') as target:
            for name, value in members.items():
                target.writestr(name, value)
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            backup.restore_backup(altered, self.destination)
        self.assertFalse(self.destination.exists())

    def test_unexpected_archive_paths_cannot_escape_restore_directory(self):
        self.create()
        with zipfile.ZipFile(self.archive, 'a') as bundle:
            bundle.writestr('../escaped.txt', 'bad')
        with self.assertRaisesRegex(ValueError, 'unexpected files'):
            backup.restore_backup(self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.root / 'escaped.txt').exists())


if __name__ == '__main__':
    unittest.main()
