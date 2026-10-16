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

    def assert_terminal_route_locked(self):
        before=copy.deepcopy(self.round)
        saved=self.game.ACTIVE_PUZZLES_FILE.read_bytes()
        last=self.round['live_route'][-1]
        previous=self.round['live_route'][-2]['actor'] if len(self.round['live_route'])>1 else self.round['start']
        actions=[('/api/backtrack',{'route_revision':self.round['route_revision']}),
                 ('/api/move',{'route_revision':self.round['route_revision'],'movie_id':last['movie']['id'],'next_actor_id':previous['id']}),
                 ('/api/hint?'+urllib.parse.urlencode({'puzzle_id':self.pid,'level':2,'route_revision':self.round['route_revision']}),None),
                 ('/api/autocomplete/movies?'+urllib.parse.urlencode({'puzzle_id':self.pid,'q':'a'}),None),
                 ('/api/autocomplete/actors?'+urllib.parse.urlencode({'puzzle_id':self.pid,'q':'a','movie_id':last['movie']['id']}),None)]
        for path,body in actions:
            with self.subTest(path=path):
                status,error=self.request(path,body)
                self.assertEqual(status,409)
                self.assertTrue(error['round_changed'])
                self.assertEqual(self.round,before)
                self.assertEqual(self.game.ACTIVE_PUZZLES_FILE.read_bytes(),saved)

    def test_reaching_target_locks_route_before_result_and_survives_reload(self):
        for step in copy.deepcopy(self.round['comparison_route']):
            status,move=self.request('/api/move',{'route_revision':self.round.get('route_revision',0),'movie_id':step['movie']['id'],'next_actor_id':step['actor']['id']})
            self.assertEqual(status,200)
        self.assertTrue(move['solved'])
        self.assertFalse(self.round.get('finished'))
        self.assert_terminal_route_locked()
        self.game.PUZZLES.clear();self.game.PUZZLES.update(self.game.load_active_puzzles())
        self.round=self.game.PUZZLES[self.pid]
        self.assert_terminal_route_locked()
        self.assertEqual(self.request('/api/round?puzzle_id='+self.pid)[1]['current_actor']['id'],self.round['target']['id'])
        status,result=self.request('/api/result',{})
        self.assertEqual(status,200);self.assertTrue(result['solved'])
        self.assertEqual(self.request('/api/result',{})[1],result)

    def test_sixth_unsolved_move_locks_route_before_result(self):
        self.assertNotEqual(self.first['actor']['id'],self.round['target']['id'])
        for index in range(6):
            self.assertEqual(self.move(actor=self.first['actor']['id'] if index%2==0 else self.round['start']['id'])[0],200)
        self.assert_terminal_route_locked()
        status,result=self.request('/api/result',{})
        self.assertEqual(status,200);self.assertFalse(result['solved']);self.assertEqual(result['degrees'],6)
        self.assertEqual(result['points'],0)

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

    def test_failed_round_write_is_not_acknowledged_and_recovery_retries_save(self):
        game=self.game
        original=game.ACTIVE_PUZZLES_FILE.read_bytes()
        replace=Path.replace
        def fail_active(path,target):
            if path==game.ACTIVE_PUZZLES_FILE.with_suffix('.tmp'):
                raise OSError('private filesystem detail')
            return replace(path,target)
        with patch.object(Path,'replace',autospec=True,side_effect=fail_active):
            status,error=self.move()
            self.assertEqual(status,500)
            self.assertNotIn('private filesystem detail',error['error'])
            self.assertEqual(self.round['route_revision'],1)
            self.assertEqual(game.ACTIVE_PUZZLES_FILE.read_bytes(),original)
            self.assertEqual(self.request('/api/round?puzzle_id='+self.pid)[0],500)
        status,recovered=self.request('/api/round?puzzle_id='+self.pid)
        self.assertEqual(status,200)
        self.assertEqual(recovered['degrees'],1)
        self.assertEqual(recovered['route_revision'],1)
        self.assertEqual(len(game.load_active_puzzles()[self.pid]['live_route']),1)
        # Recover the accepted move; do not duplicate it with the old revision.
        self.assertEqual(self.move(revision=0)[0],409)

    def test_result_retry_requires_durable_cached_result_after_write_failure(self):
        game=self.game
        replace=Path.replace
        def fail_active(path,target):
            if path==game.ACTIVE_PUZZLES_FILE.with_suffix('.tmp'):
                raise OSError('temporary write failure')
            return replace(path,target)
        with patch.object(Path,'replace',autospec=True,side_effect=fail_active):
            self.assertEqual(self.request('/api/result',{'gave_up':True})[0],500)
            result=copy.deepcopy(self.round['final_result'])
            self.assertEqual(self.request('/api/result',{'gave_up':True})[0],500)
            self.assertEqual(self.request('/api/round?puzzle_id='+self.pid)[0],500)
        status,retried=self.request('/api/result',{'gave_up':True})
        self.assertEqual(status,200)
        self.assertEqual(retried,result)
        game.PUZZLES.clear();game.PUZZLES.update(game.load_active_puzzles())
        recovered=self.request('/api/round?puzzle_id='+self.pid)[1]
        self.assertEqual(recovered['final_result'],result)
        with sqlite3.connect(game.RESULTS_DB) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM game_results WHERE puzzle_id=?',(self.pid,)).fetchone()[0],1)

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

    def test_short_off_route_hint_joins_movies_and_respects_depth_and_roles(self):
        game=self.game
        game.DEMO_MODE=False
        films={'current':[{'id':'inception','title':'Inception'}],
               'bridge':[{'id':'inception','title':'Inception'},{'id':'departed','title':'The Departed'}],
               'target':[{'id':'departed','title':'The Departed'}]}
        cast={'inception':[{'id':'current','name':'Tom Berenger','character':'Browning'},
                           {'id':'bridge','name':'Leonardo DiCaprio','character':'Cobb'}],
              'departed':[{'id':'bridge','name':'Leonardo DiCaprio','character':'Billy'},
                          {'id':'target','name':'Matt Damon','character':'Colin'}]}
        with patch.object(game,'movies',side_effect=lambda aid:films[str(aid)]), \
             patch.object(game,'cast',side_effect=lambda mid:cast[str(mid)]):
            self.assertIsNone(game.short_hint_path('current','target',1))
            route=game.bounded_hint_path('current','target',2)
            self.assertEqual([s['movie']['id'] for s in route],['inception','departed'])
            cast['departed'][1]['character']='Colin (cameo)'
            self.assertIsNone(game.short_hint_path('current','target',2))
        self.assertIsNone(getattr(game.SEARCH_CONTEXT,'deadline',None))

    def test_short_hint_timeout_keeps_time_for_known_route_fallback(self):
        game=self.game
        route=[self.first]
        with patch.object(game,'short_hint_path',side_effect=TimeoutError('cold credits')), \
             patch.object(game,'known_bridge_path',return_value=route):
            self.assertEqual(game.bounded_hint_path('current','target',3,puzzle=self.round),route)
        self.assertIsNone(getattr(game.SEARCH_CONTEXT,'deadline',None))

    def test_verified_path_is_retained_when_wider_search_times_out(self):
        game=self.game;game.DEMO_MODE=False
        route=[self.first,self.first]
        with patch.object(game,'_bounded_bfs',side_effect=[(route,{'steps':1}),TimeoutError('budget')]):
            found,meta=game.find_path_with_meta('start','target',6)
            self.assertEqual(found,route)
            self.assertEqual(meta['status'],'verified_route')

    def test_obscure_cast_discoveries_are_expert_starters_only(self):
        game=self.game
        game.DEMO_MODE=False
        obscure={'id':'obscure','name':'Unknown Supporting Performer','order':0,'popularity':10000}
        star={'id':'star','name':'Tom Hanks','order':50,'popularity':0}
        character={'id':'character','name':'Stanley Tucci','order':60,'popularity':0}
        self.assertFalse(game.starter_level_allowed(obscure,'beginner'))
        self.assertFalse(game.starter_level_allowed(obscure,'intermediate'))
        self.assertTrue(game.starter_level_allowed(obscure,'expert'))
        self.assertTrue(game.starter_level_allowed(star,'beginner'))
        self.assertTrue(game.starter_level_allowed(character,'intermediate'))
        self.assertFalse(game.starter_level_allowed(character,'beginner'))
        route=[{'movie':{'id':1,'title':'Film'},'actor':{'id':'bridge','name':'Bridge'}}]
        with patch.object(game,'eligible_cast',return_value=[obscure]), \
             patch.object(game,'has_direct_movie_connection',return_value=False), \
             patch.object(game,'validate_connection',return_value={'actor':obscure}):
            for level in ('beginner','intermediate'):
                chosen,_=game.expand_verified_starter(star,route,level,{'id':'target'})
                self.assertEqual(chosen['name'],'Tom Hanks')
            chosen,_=game.expand_verified_starter(star,route,'expert',{'id':'target'})
            self.assertEqual(chosen['name'],obscure['name'])

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

    def test_undated_movie_cast_credit_remains_playable(self):
        game = self.game
        game.DEMO_MODE = False
        current = str(self.round['current_actor']['id'])
        movie = {'id':771,'title':'Undated Film','release_date':'','popularity':0}
        rows = [{'id':current,'name':'Current','character':''},
                {'id':'next','name':'Voice Performer','character':'Narrator (voice)'},
                {'id':'cameo','name':'Cameo Performer','character':'Self (cameo)'}]
        game.MEM['movies_'+current] = (game.time.time(), [])
        def provider(path, params=None):
            if path == '/person/'+current+'/movie_credits':
                return {'cast':[movie, {'title':'Missing ID'}, {'id':772}],
                        'crew':[{'id':773,'title':'Crew Film','release_date':'2000-01-01'}]}
            if path == '/movie/771/credits':
                return {'cast':rows,'crew':[{'id':'crew','name':'Crew Member'}]}
            raise AssertionError(path)
        with patch.object(game,'tmdb',side_effect=provider):
            self.assertEqual(game.movies(current), [movie])
            self.assertIsNotNone(game.validate_connection(current,771,'next'))
            self.assertIsNone(game.validate_connection(current,771,'cameo'))
            self.assertIsNone(game.validate_connection(current,771,'crew'))
            status, matches = self.request('/api/autocomplete/movies?'+urllib.parse.urlencode(
                {'puzzle_id':self.pid,'q':'Undated'}))
            self.assertEqual(status,200)
            self.assertEqual(matches[0]['id'],771)
            status, actors = self.request('/api/autocomplete/actors?'+urllib.parse.urlencode(
                {'puzzle_id':self.pid,'movie_id':771,'q':'Voice'}))
            self.assertEqual(status,200)
            self.assertEqual(actors[0]['id'],'next')
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
        def fail(*args, **kwargs):
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

    def test_repeated_lower_hint_reports_authoritative_usage_and_backtracks(self):
        self.round['backtracks_used']=1
        def ask(level):
            return self.request('/api/hint?'+urllib.parse.urlencode({'puzzle_id':self.pid,'level':level,'route_revision':0}))
        status,actor_hint=ask(2)
        self.assertEqual(status,200)
        status,movie_hint=ask(1)
        self.assertEqual(status,200)
        self.assertEqual(movie_hint['level'],1)
        self.assertEqual(movie_hint['hints_used'],2)
        self.assertEqual(movie_hint['backtracks_used'],1)
        self.assertEqual(actor_hint['movie'],movie_hint['movie'])
        self.assertEqual(self.round['hints_used'],2)
        self.assertEqual(len(self.round['hinted_movie_ids']),1)
        saved=self.game.load_active_puzzles()[self.pid]
        self.assertEqual(saved['hints_used'],2)

    def test_hinted_movie_never_earns_deep_points_or_bonus_backs(self):
        game=self.game
        with patch.object(game,'connection_deep_cut',return_value=15):
            status,h=self.request('/api/hint?'+urllib.parse.urlencode({'puzzle_id':self.pid,'level':1,'route_revision':0}))
            self.assertEqual(status,200)
            first=self.round['comparison_route'][0]
            self.assertEqual(h['movie']['id'],first['movie']['id'])
            self.assertEqual(self.round['hinted_movie_ids'],[str(first['movie']['id'])])
            self.assertEqual(self.move()[1]['free_backs'],1)
            status,restored=self.request('/api/round?puzzle_id='+self.pid)
            self.assertEqual(restored['free_backs'],1)
            loaded=game.load_active_puzzles()[self.pid]
            self.assertEqual(loaded['hinted_movie_ids'],self.round['hinted_movie_ids'])
            self.assertEqual(self.request('/api/backtrack',{'route_revision':1})[0],200)
            self.assertEqual(self.move()[1]['free_backs'],1)
            current=self.round['start']['id']
            points,details=game.deep_cut_for_route(current,self.round['comparison_route'],self.round['hinted_movie_ids'])
            self.assertEqual(details[0]['bonus'],0)
            self.assertTrue(details[0]['hinted_movie'])
            self.assertTrue(all(x['bonus']==15 for x in details[1:] if x['movie']!=first['movie']['title']))
            for step in self.round['comparison_route'][1:]:
                status,move=self.request('/api/move',{'route_revision':self.round['route_revision'],
                    'movie_id':step['movie']['id'],'next_actor_id':step['actor']['id']})
                self.assertEqual(status,200)
            status,result=self.request('/api/result',{})
            self.assertEqual(status,200)
            self.assertTrue(result['solved'])
            self.assertEqual(result['deep_cut_details'][0]['bonus'],0)
            self.assertEqual(result['deep_cut_bonus'],points)
            self.assertEqual(self.request('/api/result',{})[1],result)
            challenge=game.start_challenge(result['challenge_token'])
            self.assertEqual(game.PUZZLES[challenge['puzzle_id']]['hinted_movie_ids'],[])

    def test_rotation_audit_uses_all_targets_without_changing_game_state(self):
        game=self.game
        before=copy.deepcopy(game.PUZZLES)
        used=set(game.USED_STARTERS)
        cursor=copy.deepcopy(game.PUZZLE_CURSOR)
        active_bytes=game.ACTIVE_PUZZLES_FILE.read_bytes()
        used_bytes=game.USED_STARTERS_FILE.read_bytes()
        game.verify_weekly_rotation()
        report=game.rotation_audit_status()
        self.assertEqual(report['status'],'passed')
        self.assertEqual(len(report['checks']),27)
        self.assertEqual({(c['target'],c['difficulty']) for c in report['checks']},
                         {(n,d) for n in game.WEEKLY_TARGETS for d in ('beginner','intermediate','expert')})
        self.assertEqual(game.PUZZLES,before)
        self.assertEqual(game.USED_STARTERS,used)
        self.assertEqual(game.PUZZLE_CURSOR,cursor)
        self.assertEqual(game.ACTIVE_PUZZLES_FILE.read_bytes(),active_bytes)
        self.assertEqual(game.USED_STARTERS_FILE.read_bytes(),used_bytes)
        self.assertEqual(game.TARGET_OVERRIDE,'Matt Damon')
        report['checks'][0]['status']='corrupted'
        self.assertEqual(game.rotation_audit_status()['checks'][0]['status'],'passed')

    def test_two_rotation_cycles_and_old_round_challenge_stay_frozen(self):
        game=self.game
        game.TARGET_OVERRIDE=''
        clock=game.weekly_target
        original_target=self.round['target']['id']
        utc=datetime.timezone.utc
        for week in range(18):
            # Local Monday midnight changes UTC offset after the DST transition.
            day=game.WEEKLY_EPOCH+datetime.timedelta(weeks=week)
            now=datetime.datetime.combine(day,datetime.time(),tzinfo=game.WEEKLY_ZONE)
            before=clock(now-datetime.timedelta(microseconds=1))
            schedule=clock(now)
            self.assertEqual(schedule['name'],game.WEEKLY_TARGETS[week%9])
            self.assertEqual(before['name'],game.WEEKLY_TARGETS[(week-1)%9])
            self.assertTrue(schedule['rotation_enabled'])
            self.assertEqual(schedule['next_name'],game.WEEKLY_TARGETS[(week+1)%9])
            for level in ('beginner','intermediate','expert'):
                with patch.object(game,'weekly_target',return_value=schedule):
                    generated=game.generate_puzzle(level)
                    self.assertEqual(generated['target']['name'],schedule['name'])
                    status,old=self.request('/api/round?puzzle_id='+self.pid)
                    self.assertEqual(status,200)
                    self.assertEqual(old['target']['id'],original_target)
        for step in self.round['comparison_route']:
            status,response=self.request('/api/move',{'route_revision':self.round.get('route_revision',0),
                'movie_id':step['movie']['id'],'next_actor_id':step['actor']['id']})
            self.assertEqual(status,200)
        status,result=self.request('/api/result',{})
        self.assertEqual(status,200)
        self.assertTrue(result['solved'])
        with patch.object(game,'weekly_target',return_value={'name':'Angelina Jolie'}):
            status,preview=self.request('/api/challenge?token='+result['challenge_token'])
            self.assertEqual(status,200)
            self.assertEqual(preview['target']['id'],original_target)
            challenge=game.start_challenge(result['challenge_token'])
            self.assertEqual(challenge['target']['id'],original_target)

    def test_custom_challenge_is_private_persisted_and_playable_without_benchmark(self):
        game=self.game
        before=set(game.PUZZLES)
        created=game.create_custom_challenge(self.round['start']['name'],self.round['target']['name'],False)
        token=created['token']
        self.assertEqual(set(game.PUZZLES),before)
        self.assertNotIn('comparison_route',created)
        self.assertNotIn('cut',created)
        self.assertIn(token,game.load_challenges())
        preview=game.challenge_preview(token)
        self.assertIsNone(preview['benchmark'])
        self.assertEqual(preview['kind'],'custom')
        self.assertFalse(preview['hints_enabled'])
        self.assertNotIn('comparison_route',preview)
        accepted=game.start_challenge(token)
        self.pid=accepted['puzzle_id'];self.round=game.PUZZLES[self.pid]
        self.assertIsNone(self.round['challenge_benchmark'])
        self.assertEqual(self.request('/api/hint?puzzle_id='+self.pid+'&level=1&route_revision=0')[0],403)
        for step in self.round['comparison_route']:
            self.first=step
            self.assertEqual(self.move()[0],200)
        status,result=self.request('/api/result',{})
        self.assertEqual(status,200)
        self.assertTrue(result['solved'])
        self.assertNotIn('challenge_outcome',result)
        self.assertIsNotNone(game.challenge_preview(result['challenge_token'])['benchmark'])

    def test_custom_challenge_rejects_invalid_names_mode_and_unverified_route(self):
        game=self.game;before=copy.deepcopy(game.CHALLENGES)
        names={'start_name':self.round['start']['name'],'target_name':self.round['target']['name']}
        self.assertEqual(self.request('/api/challenge/create',names)[0],400)
        self.assertEqual(self.request('/api/challenge/create',{'mode':'challenge',**names,'hints_enabled':'false'})[0],400)
        for start,target in [('',names['target_name']),('Unknown Actor',names['target_name']),
                             (names['start_name'],names['start_name'])]:
            self.assertEqual(self.request('/api/challenge/create',{'mode':'challenge','start_name':start,'target_name':target})[0],422)
        with patch.object(game,'short_hint_path',return_value=None),patch.object(game,'_bounded_bfs',return_value=(None,{})):
            self.assertEqual(self.request('/api/challenge/create',{'mode':'challenge',**names})[0],422)
        self.assertEqual(game.CHALLENGES,before)

    def test_custom_short_search_timeout_preserves_broader_verification(self):
        game=self.game
        with patch.object(game,'short_hint_path',side_effect=TimeoutError('cold cache')), \
             patch.object(game,'_bounded_bfs',return_value=(self.round['comparison_route'],{})) as fallback:
            created=game.create_custom_challenge(self.round['start']['name'],self.round['target']['name'])
        self.assertTrue(created['verified'])
        fallback.assert_called_once()
        self.assertIsNone(getattr(game.SEARCH_CONTEXT,'deadline',None))

    def test_launch_hides_target_previews_until_play_but_beta_keeps_them(self):
        game=self.game
        created=game.create_custom_challenge(self.round['start']['name'],self.round['target']['name'])
        token=created['token']
        with patch.object(game,'TARGET_PREVIEWS_ENABLED',True):
            self.assertEqual(self.request('/api/status')[1]['weekly_target'],'Matt Damon')
            self.assertIsNotNone(game.challenge_preview(token)['target'])
        with patch.object(game,'TARGET_PREVIEWS_ENABLED',False):
            status=self.request('/api/status')[1]
            self.assertIsNone(status['weekly_target']);self.assertIsNone(status['weekly_schedule'])
            self.assertEqual(set(status['rotation_verification']),{'status'})
            self.assertTrue(game.challenge_preview(token)['target_hidden'])
            self.assertIsNone(game.challenge_preview(token)['target'])
            accepted=game.start_challenge(token)
            self.assertEqual(accepted['target']['name'],self.round['target']['name'])

    def test_weekly_rotation_uses_new_york_monday_and_preserves_roster(self):
        self.game.TARGET_OVERRIDE = ''
        utc = datetime.timezone.utc
        self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 10, 12, 3, 59, tzinfo=utc))['name'], 'Matt Damon')
        for day, name in [(12, 'Tom Hanks'), (19, 'Morgan Freeman'), (26, 'Denzel Washington')]:
            self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 10, day, 4, tzinfo=utc))['name'], name)
        self.assertEqual(self.game.weekly_target(datetime.datetime(2026, 11, 2, 5, tzinfo=utc))['name'], 'Michael Caine')


if __name__ == '__main__':
    unittest.main()
