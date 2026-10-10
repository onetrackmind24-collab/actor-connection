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

    def test_curated_selection_tries_fresh_then_recycled_once(self):
        game = self.game
        original = copy.deepcopy(game.CURATED_ALPHA_ROUTES)
        entries = game.CURATED_ALPHA_ROUTES['beginner']
        game.USED_STARTERS.clear()
        game.USED_STARTERS.add(entries[0][0])
        attempted = []
        real_person = game.person

        def observe(name):
            if name != 'Matt Damon':
                attempted.append(name)
            return real_person(name)

        with patch.object(game, 'person', side_effect=observe), \
             patch.object(game, 'has_direct_movie_connection', return_value=False), \
             patch.object(game, 'resolve_curated_route', return_value=None), \
             patch.object(game, 'candidate_names_for', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'No starting-actor'):
                game.generate_puzzle('beginner')
        self.assertEqual(sorted(attempted), sorted(name for name, _ in entries))
        self.assertEqual(attempted[-1], entries[0][0])
        self.assertEqual(game.CURATED_ALPHA_ROUTES, original)

    def test_every_weekly_target_has_a_playable_round_in_each_difficulty(self):
        game = self.game
        for target in game.WEEKLY_TARGETS:
            game.TARGET_OVERRIDE = target
            for difficulty in ('beginner', 'intermediate', 'expert'):
                with self.subTest(target=target, difficulty=difficulty):
                    game.USED_STARTERS.clear()
                    puzzle = game.generate_puzzle(difficulty)
                    stored = game.PUZZLES[puzzle['puzzle_id']]
                    route = stored['comparison_route']
                    self.assertEqual(puzzle['target']['name'], target)
                    self.assertNotEqual(puzzle['start']['id'], puzzle['target']['id'])
                    self.assertTrue(2 <= len(route) <= 6)
                    current = puzzle['start']['id']
                    for step in route:
                        self.assertIsNotNone(game.validate_connection(current, step['movie']['id'], step['actor']['id']))
                        current = step['actor']['id']
                    self.assertEqual(current, puzzle['target']['id'])
                    self.assertFalse(game.has_direct_movie_connection(puzzle['start']['id'], puzzle['target']['id']))

    def test_six_connection_hint_score_stays_negative_through_result_and_challenge(self):
        game = self.game
        for hints, expected in [(1, -10), (2, -20)]:
            for cut in range(2, 7):
                self.assertEqual(game.score_for(6, cut, hints, 25), expected)
                self.assertEqual(game.score_for(6, cut, hints, 25, 5), expected - 5)
        self.assertEqual(game.score_for(6, 3, 0, 0), 25)
        self.assertEqual(game.score_for(5, 3, 2, 25), 55)
        self.assertEqual(game.score_for(5, 3, 2, 25, 100), 0)
        self.round.update(start=game.public_person(game.person('Tom Hanks')),
                          current_actor=game.public_person(game.person('Tom Hanks')),
                          live_route=[], hints_used=2, backtracks_used=0)
        for movie, actor in [('m3','p3'), ('m13','p17'), ('m13','p3'),
                             ('m13','p17'), ('m13','p3'), ('m6','p8')]:
            status, result = self.request('/api/move', {'movie_id':movie, 'next_actor_id':actor})
            self.assertEqual(status, 200)
            self.assertTrue(result['valid'])
        status, result = self.request('/api/result', {})
        self.assertEqual(status, 200)
        self.assertTrue(result['solved'])
        self.assertEqual(result['points'], -20)
        self.assertIn('bonuses do not offset', result['scoring_note'])
        self.assertEqual(self.request('/api/result', {})[1]['points'], -20)
        with sqlite3.connect(game.RESULTS_DB) as db:
            self.assertEqual(db.execute('SELECT points FROM game_results WHERE puzzle_id=?', (self.pid,)).fetchone()[0], -20)
        self.assertEqual(game.compare_challenge({'solved':True,'points':-10}, {'solved':True,'points':-20})['status'], 'win')
        self.assertEqual(game.compare_challenge({'solved':True,'points':-20}, {'solved':False,'points':0})['status'], 'win')

    def test_existing_challenge_keeps_legacy_scoring(self):
        game = self.game
        token = game.create_challenge(self.pid, self.round,
                                      {'points':5, 'solved':True, 'degrees':6, 'scoring_version':1})
        # Challenges created before versioning have no scoring_version field.
        game.CHALLENGES[token].pop('scoring_version')
        challenge = game.start_challenge(token)
        self.assertEqual(game.PUZZLES[challenge['puzzle_id']]['scoring_version'], 1)
        self.assertEqual(game.challenge_preview(token)['scoring_version'], 1)
        self.assertEqual(game.score_for(6, 3, 2, 0, 0, False), 5)
        self.assertEqual(game.score_for(6, 3, 2, 0), -20)

    def test_verified_starter_expands_beyond_seed_pool_without_photos(self):
        game = self.game
        start = game.person('Michael Shannon')
        route = game.resolve_curated_route(start, [('Man of Steel','Russell Crowe'),
                 ('Virtuosity','Denzel Washington'),('Courage Under Fire','Matt Damon')], 'Matt Damon')
        game.USED_STARTERS.clear()
        game.USED_STARTERS.add('Michael Shannon')
        candidate, expanded = game.expand_verified_starter(start, route, 'intermediate', game.person('Matt Damon'))
        self.assertEqual(candidate['name'], 'Henry Cavill')
        self.assertIsNone(candidate['profile_path'])
        self.assertNotIn(candidate['name'], sum(game.PUZZLE_CANDIDATES.values(), []))
        self.assertEqual(expanded[1:], route[1:])
        self.assertTrue(game.route_allowed_by_overrides(candidate['id'], expanded))
        with patch.object(game,'eligible_cast',side_effect=TimeoutError):
            self.assertEqual(game.expand_verified_starter(start, route, 'expert', game.person('Matt Damon')), (start,route))
        self.assertIsNone(getattr(game.SEARCH_CONTEXT,'deadline',None))

    def test_full_cast_rules_and_accent_insensitive_autocomplete(self):
        game = self.game
        current = str(self.round['current_actor']['id'])
        movie = {'id':'rules-film','title':"Léon's Film",'release_date':'2000-01-01'}
        rows = [{'id':current,'name':'Current','character':'Lead'}]
        rows += [{'id':str(100+i),'name':'Performer '+str(i),'character':'Character'} for i in range(40)]
        rows += [{'id':'voice','name':'Voice Actor','character':'Narrator (voice)'},
                 {'id':'self','name':'Self Performer','character':'Self'},
                 {'id':'blank','name':'José O’Neill','character':''},
                 {'id':'cameo','name':'Cameo Actor','character':'Role (cameo)'},
                 {'id':'credits','name':'Credits Actor','character':'Role (post-credits scene)'}]
        with patch.object(game,'movies',return_value=[movie]), patch.object(game,'cast',return_value=rows):
            for aid in ('voice','self','blank','139'):
                status, response = self.request('/api/validate', {'puzzle_id':'','current_actor_id':current,'movie_id':'rules-film','next_actor_id':aid})
                self.assertEqual(status,200)
                self.assertTrue(response['valid'], aid)
            for aid in ('cameo','credits','crew-only',current):
                self.assertIsNone(game.validate_connection(current,'rules-film',aid))
            status, movies = self.request('/api/autocomplete/movies?'+urllib.parse.urlencode({'puzzle_id':self.pid,'q':'Leons'}))
            self.assertEqual(status,200)
            self.assertEqual(movies[0]['id'],'rules-film')
            status, actors = self.request('/api/autocomplete/actors?'+urllib.parse.urlencode({'puzzle_id':self.pid,'movie_id':'rules-film','q':'Jose ONeill'}))
            self.assertEqual(status,200)
            self.assertEqual(actors[0]['id'],'blank')
            self.assertTrue(actors[0]['connection_token'])

    def test_person_lookup_prefers_exact_actor_name(self):
        game = self.game
        game.DEMO_MODE=False
        rows=[{'id':1,'name':'Ann Example Jr.','known_for_department':'Acting'},
              {'id':2,'name':'Ann Example','known_for_department':'Acting'}]
        with patch.object(game,'tmdb',return_value={'results':rows}):
            self.assertEqual(game.person('Ann Example')['id'],2)
        rows[1]['known_for_department']='Directing'
        with patch.object(game,'tmdb',return_value={'results':rows}):
            self.assertEqual(game.person('Ann Example Writer')['id'],1)
            # A new exact query avoids the already cached actor response.
            game.MEM.clear()
            (game.CACHE_DIR / 'person_v3_ann_example.json').unlink(missing_ok=True)
            self.assertEqual(game.person('Ann Example')['id'],2)

    def test_puzzle_search_budget_is_restored_after_failure(self):
        game = self.game
        def fail(*args):
            self.assertIsNotNone(game.SEARCH_CONTEXT.deadline)
            raise TimeoutError('budget expired')
        with patch.object(game,'_generate_puzzle',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'within the search limit'):
                game.generate_puzzle('expert')
        self.assertIsNone(game.SEARCH_CONTEXT.deadline)

    def test_cached_hint_cannot_exceed_remaining_moves_or_charge_for_failure(self):
        game = self.game
        path = self.round['comparison_route']
        actor = str(self.round['current_actor']['id'])
        self.round.update(live_route=[self.first]*5, hints_used=1,
                          hint_routes={actor:path})
        self.assertGreater(len(path),1)
        with patch.object(game,'known_finish_route',return_value=None), \
             patch.object(game,'bounded_hint_path',return_value=None):
            status, response = self.request('/api/hint?'+urllib.parse.urlencode({'puzzle_id':self.pid,'level':2,'route_revision':0}))
        self.assertEqual(status,404)
        self.assertEqual(response['error'],'No verified hint route found')
        self.assertEqual(self.round['hints_used'],1)
        self.assertNotIn(actor,self.round['hint_routes'])

    def test_weekly_rotation_uses_new_york_monday_and_preserves_roster(self):
        self.game.TARGET_OVERRIDE = ''
        utc = datetime.timezone.utc
        self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 10, 12, 3, 59, tzinfo=utc))['name'], 'Matt Damon')
        for day, name in [(12, 'Tom Hanks'), (19, 'Morgan Freeman'), (26, 'Denzel Washington')]:
            self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 10, day, 4, tzinfo=utc))['name'], name)
        self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 11, 2, 5, tzinfo=utc))['name'], 'Michael Caine')


if __name__ == '__main__':
    unittest.main()
