"""Offline regression checks. Run: python -m unittest discover -s tests -v"""
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch


class GameplayTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {
            'GAME_DATA_DIR': self.data.name, 'TMDB_API_TOKEN': '',
            'WEEKLY_TARGET': 'Matt Damon',
        }):
            spec = importlib.util.spec_from_file_location(
                'game_under_test', Path(__file__).resolve().parents[1] / 'server.py')
            self.game = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.game)
        self.game.Handler.log_message = lambda *args: None
        self.http = self.game.ThreadingHTTPServer(('127.0.0.1', 0), self.game.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'
        puzzle = self.game.generate_puzzle('beginner')
        self.pid = puzzle['puzzle_id']
        self.round = self.game.PUZZLES[self.pid]
        self.first = self.round['comparison_route'][0]

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.data.cleanup()

    def request(self, path, body=None):
        data = None if body is None else json.dumps({'puzzle_id': self.pid, **body}).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    def move(self, revision='current', actor=None):
        return self.request('/api/move', {
            'route_revision': self.round.get('route_revision', 0) if revision == 'current' else revision,
            'movie_id': self.first['movie']['id'],
            'next_actor_id': actor or self.first['actor']['id'],
        })

    def test_stale_backtrack_does_not_consume_another_back(self):
        self.assertEqual(self.move()[0], 200)
        self.assertEqual(self.move(actor=self.round['start']['id'])[0], 200)
        old_revision = self.round['route_revision']
        self.assertEqual(self.request('/api/backtrack', {'route_revision': old_revision})[0], 200)
        before = copy.deepcopy(self.round)
        status, response = self.request('/api/backtrack', {'route_revision': old_revision})
        self.assertEqual(status, 409)
        self.assertTrue(response['round_changed'])
        self.assertEqual(self.round, before)
        self.assertEqual(self.round['backtracks_used'], 1)

    def test_stale_move_and_hint_after_returning_to_same_actor(self):
        self.assertEqual(self.move()[0], 200)
        self.assertEqual(self.move(actor=self.round['start']['id'])[0], 200)
        self.assertEqual(self.move(revision=0)[0], 409)
        status, _ = self.request('/api/hint?' + urllib.parse.urlencode({
            'puzzle_id': self.pid, 'level': 2, 'route_revision': 0}))
        self.assertEqual(status, 409)
        self.assertEqual(self.round['hints_used'], 0)
        status, saved = self.request('/api/round?puzzle_id=' + self.pid)
        self.assertEqual(status, 200)
        self.assertEqual(saved['route_revision'], 2)
        self.assertNotIn('comparison_route', saved)
        self.assertNotIn('cut', saved)

    def test_invalid_revisions_are_rejected(self):
        for value in [True, '0', -1, None]:
            with self.subTest(value=value):
                self.assertEqual(self.move(revision=value)[0], 400)

    def test_calculation_failures_do_not_commit_move_or_back(self):
        before = copy.deepcopy(self.round)
        with patch.object(self.game, 'deep_cut_for_route', side_effect=OSError('provider unavailable')):
            self.assertEqual(self.move()[0], 500)
        self.assertEqual(self.round, before)
        self.assertEqual(self.game.load_active_puzzles()[self.pid], before)
        self.assertEqual(self.move()[0], 200)
        before = copy.deepcopy(self.round)
        with patch.object(self.game, 'deep_cut_for_route', side_effect=OSError('provider unavailable')):
            self.assertEqual(self.request('/api/backtrack', {'route_revision': 1})[0], 500)
        self.assertEqual(self.round, before)
        self.assertEqual(self.game.load_active_puzzles()[self.pid], before)

    def test_result_database_failure_is_retryable_and_finished_round_survives_reload(self):
        with patch.object(self.game, 'save_game_result', side_effect=OSError('database unavailable')):
            self.assertEqual(self.request('/api/result', {'gave_up': True})[0], 500)
        self.assertFalse(self.round.get('finished'))
        self.assertIsNone(self.round.get('final_result'))
        status, result = self.request('/api/result', {'gave_up': True})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/result', {'gave_up': True})[1], result)
        with sqlite3.connect(self.game.RESULTS_DB) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM game_results WHERE puzzle_id=?',
                                        (self.pid,)).fetchone()[0], 1)
        self.game.PUZZLES.clear()
        self.game.PUZZLES.update(self.game.load_active_puzzles())
        status, recovered = self.request('/api/round?puzzle_id=' + self.pid)
        self.assertEqual(status, 200)
        self.assertTrue(recovered['finished'])
        self.assertEqual(recovered['final_result'], result)

    def test_weekly_rotation_uses_new_york_monday_and_preserves_roster(self):
        self.game.TARGET_OVERRIDE = ''
        utc = datetime.timezone.utc
        self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 10, 12, 3, 59, tzinfo=utc))['name'], 'Matt Damon')
        for day, name in [(12, 'Tom Hanks'), (19, 'Morgan Freeman'), (26, 'Denzel Washington')]:
            self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 10, day, 4, tzinfo=utc))['name'], name)
        self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 11, 2, 5, tzinfo=utc))['name'], 'Matt Damon')


if __name__ == '__main__':
    unittest.main()
