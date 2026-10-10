#!/usr/bin/env python3
import weakref
from contextlib import nullcontext
import re, json, os, time, urllib.parse, urllib.request, threading, secrets, datetime, sqlite3, statistics, unicodedata
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from collections import deque
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
# Keep all mutable state on an explicitly configured persistent volume.
STATE_DIR=Path(os.environ.get('GAME_DATA_DIR',str(ROOT))).expanduser().resolve()
STATE_DIR.mkdir(parents=True,exist_ok=True)
CACHE_DIR=STATE_DIR/'cache'; CACHE_DIR.mkdir(exist_ok=True)
TMDB='https://api.themoviedb.org/3'
TOKEN=os.environ.get('TMDB_API_TOKEN','').strip()
TARGET_OVERRIDE=os.environ.get('WEEKLY_TARGET','').strip()
WEEKLY_TARGETS=('Matt Damon','Tom Hanks','Morgan Freeman','Denzel Washington',
                'Michael Caine','Clint Eastwood','Jack Nicholson',
                'Scarlett Johansson','Angelina Jolie')
WEEKLY_ZONE=ZoneInfo('America/New_York')
WEEKLY_EPOCH=datetime.date(2026,10,5)

def weekly_target(now=None):
    now=now or datetime.datetime.now(WEEKLY_ZONE)
    if now.tzinfo is None: raise ValueError('Weekly clock must include a timezone')
    local=now.astimezone(WEEKLY_ZONE)
    monday=local.date()-datetime.timedelta(days=local.weekday())
    index=(monday-WEEKLY_EPOCH).days//7
    end=datetime.datetime.combine(monday+datetime.timedelta(days=7),datetime.time(),tzinfo=WEEKLY_ZONE)
    return {'name':TARGET_OVERRIDE or WEEKLY_TARGETS[index%len(WEEKLY_TARGETS)],
            'week_start':monday.isoformat(),'changes_at':None if TARGET_OVERRIDE else end.isoformat(),
            'rotation_enabled':not bool(TARGET_OVERRIDE)}
# Demo fallback pool. Live mode discovers a much larger candidate catalog from the provider.
# A candidate is NEVER served until the route verifier proves a <=6 route.
PUZZLE_CANDIDATES={
    'beginner':['Tom Hanks','Julia Roberts','Steve Martin'],
    'intermediate':['George Clooney','Paul Giamatti','Jeff Bridges'],
    'expert':['Michael Shannon','John C. Reilly','Steve Buscemi']
}
PUZZLE_CURSOR={'beginner':0,'intermediate':0,'expert':0}
LOCK=threading.Lock()
MEM={}
PUZZLES={}
ROUND_LOCKS=weakref.WeakValueDictionary()
ROUND_LOCKS_GUARD=threading.Lock()
STATE_WRITE_LOCK=threading.Lock()

def round_lock(puzzle_id):
    pid=str(puzzle_id or '')
    if not pid or pid not in PUZZLES: return nullcontext()
    with ROUND_LOCKS_GUARD:
        lock=ROUND_LOCKS.get(pid)
        if lock is None:
            lock=threading.RLock();ROUND_LOCKS[pid]=lock
        return lock

ACTIVE_PUZZLES_FILE=STATE_DIR/'active_puzzles.json'
TTL=60*60*24*30
PUZZLE_TTL=60*60*6
DEV_DIAGNOSTICS=os.environ.get('DEV_DIAGNOSTICS','').strip().lower() in {'1','true','yes'}
USED_STARTERS_FILE=STATE_DIR/'used_starters.json'
ELIGIBILITY_FILE=STATE_DIR/'eligibility_overrides.json'
RESULTS_DB=Path(os.environ.get('RESULTS_DB', str(STATE_DIR/'game_results.sqlite3')))
RESULTS_LOCK=threading.Lock()
RESULTS_DB.parent.mkdir(parents=True,exist_ok=True)
# Seed curated data only once; never overwrite persisted user/game state.
for state_name in ('eligibility_overrides.json','used_starters.json'):
    destination=STATE_DIR/state_name
    source=ROOT/state_name
    if destination!=source and not destination.exists() and source.exists():
        destination.write_bytes(source.read_bytes())


def load_active_puzzles():
    try:
        data=json.loads(ACTIVE_PUZZLES_FILE.read_text())
        if not isinstance(data,dict): return {}
        cutoff=time.time()-PUZZLE_TTL
        return {str(k):v for k,v in data.items() if isinstance(v,dict) and float(v.get('created',0))>=cutoff and (not v.get('finished') or isinstance(v.get('final_result'),dict))}
    except Exception:
        return {}

def save_active_puzzles():
    # Atomic replace avoids leaving a half-written session file if the process stops mid-write.
    try:
        with STATE_WRITE_LOCK:
            tmp=ACTIVE_PUZZLES_FILE.with_suffix('.tmp')
            tmp.write_text(json.dumps(PUZZLES,separators=(',',':')))
            tmp.replace(ACTIVE_PUZZLES_FILE)
    except Exception:
        pass

# Active rounds survive a server restart during the six-hour puzzle window.
PUZZLES.update(load_active_puzzles())


CHALLENGES_FILE=STATE_DIR/'challenges.json'
CHALLENGE_TTL=7*24*60*60
CHALLENGE_LOCK=threading.RLock()
def load_challenges():
    try:
        data=json.loads(CHALLENGES_FILE.read_text())
        return {k:v for k,v in data.items() if isinstance(v,dict) and v.get('expires',0)>time.time()}
    except (OSError,ValueError,AttributeError): return {}
CHALLENGES=load_challenges()

def challenge_preview(token):
    with CHALLENGE_LOCK:
        item=CHALLENGES.get(token)
        if not item or item['expires']<=time.time(): return None
        return {**{k:item[k] for k in ('start','target','difficulty','hints_enabled','benchmark','expires')},
                'scoring_version':item.get('scoring_version',1)}

def create_challenge(puzzle_id,puzzle,result):
    with CHALLENGE_LOCK:
        for token,item in CHALLENGES.items():
            if item.get('source_puzzle_id')==puzzle_id and item['expires']>time.time(): return token
        token=secrets.token_urlsafe(24)
        item={k:puzzle[k] for k in ('start','target','difficulty','comparison_route','cut')}
        item.update({'scoring_version':result.get('scoring_version',2),
                     'hints_enabled':puzzle.get('hints_enabled',True),
                     'cut_meta':puzzle.get('cut_meta',{}),'route_status':puzzle.get('route_status'),
                     'route_search':puzzle.get('route_search',{}),
                     'source_puzzle_id':puzzle_id,'expires':time.time()+CHALLENGE_TTL,
                     'benchmark':{'points':result['points'],'solved':result['solved'],'degrees':result['degrees']}})
        updated={k:v for k,v in CHALLENGES.items() if v['expires']>time.time()}
        updated[token]=json.loads(json.dumps(item))
        tmp=CHALLENGES_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(updated,separators=(',',':')));tmp.replace(CHALLENGES_FILE)
        CHALLENGES.clear();CHALLENGES.update(updated)
        return token

def start_challenge(token):
    with CHALLENGE_LOCK:
        item=CHALLENGES.get(token)
        if not item or item['expires']<=time.time(): return None
        item=json.loads(json.dumps(item))
    pid=secrets.token_urlsafe(12)
    puzzle={k:item[k] for k in ('start','target','difficulty','comparison_route','cut','cut_meta','route_status','route_search','hints_enabled')}
    puzzle.update({'scoring_version':item.get('scoring_version',1),'created':time.time(),'live_route':[],'current_actor':puzzle['start'],
                   'hints_used':0,'backtracks_used':0,'finished':False,
                   'challenge_token':token,'challenge_benchmark':item['benchmark']})
    PUZZLES[pid]=puzzle;save_active_puzzles()
    return {'puzzle_id':pid,'verified':True,**{k:puzzle[k] for k in ('start','target','difficulty','hints_enabled','challenge_token','challenge_benchmark')}}

def compare_challenge(result,benchmark):
    if result['solved'] and not benchmark['solved']: status='win'
    elif not result['solved'] and benchmark['solved']: status='loss'
    elif not result['solved']: status='tie'
    else: status='win' if result['points']>benchmark['points'] else ('loss' if result['points']<benchmark['points'] else 'tie')
    return {'status':status,'opponent_points':benchmark['points'],'opponent_solved':benchmark['solved']}

def load_used_starters():
    try:
        data=json.loads(USED_STARTERS_FILE.read_text())
        return set(data if isinstance(data,list) else [])
    except Exception:
        return set()

def save_used_starters(names):
    try: USED_STARTERS_FILE.write_text(json.dumps(sorted(names),indent=2))
    except Exception: pass

USED_STARTERS=load_used_starters()

def load_eligibility_overrides():
    """Curated exceptions for credits the provider cannot classify to our rules.

    Keys are movie IDs, then person IDs. Values contain eligible (bool), reason,
    and optional source/note. Provider cast credits are allowed by default; a
    curated deny wins everywhere: validation, graph search, hints and scoring.
    """
    # Bundled rules update on deployment; disk-backed custom rules remain intact.
    merged={}
    for path in dict.fromkeys([ROOT/'eligibility_overrides.json',ELIGIBILITY_FILE]):
        try:
            data=json.loads(path.read_text())
            if isinstance(data,dict):
                for mid,rules in data.items():
                    if isinstance(rules,dict): merged.setdefault(str(mid),{}).update(rules)
        except (OSError,ValueError): pass
    return merged

ELIGIBILITY_OVERRIDES=load_eligibility_overrides()

def init_results_db():
    with sqlite3.connect(RESULTS_DB) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT, puzzle_id TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL, difficulty TEXT NOT NULL,
            start_id TEXT NOT NULL, start_name TEXT NOT NULL, target_id TEXT NOT NULL, target_name TEXT NOT NULL,
            solved INTEGER NOT NULL, gave_up INTEGER NOT NULL, degrees INTEGER, cut INTEGER NOT NULL,
            hints_used INTEGER NOT NULL, deep_cut_bonus INTEGER NOT NULL, hint_penalty INTEGER NOT NULL,
            points INTEGER NOT NULL, elapsed_seconds REAL, route_json TEXT NOT NULL,
            backtracks_used INTEGER NOT NULL DEFAULT 0, backtrack_penalty INTEGER NOT NULL DEFAULT 0
        )""")
        # Lightweight migration for existing development databases.
        cols={r[1] for r in db.execute('PRAGMA table_info(game_results)').fetchall()}
        if 'backtracks_used' not in cols: db.execute('ALTER TABLE game_results ADD COLUMN backtracks_used INTEGER NOT NULL DEFAULT 0')
        if 'backtrack_penalty' not in cols: db.execute('ALTER TABLE game_results ADD COLUMN backtrack_penalty INTEGER NOT NULL DEFAULT 0')
        db.execute('CREATE INDEX IF NOT EXISTS idx_results_matchup ON game_results(start_id,target_id,solved)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_results_difficulty ON game_results(difficulty,solved)')
        db.commit()

init_results_db()

def _median_cut(rows):
    vals=[int(r[0]) for r in rows if r[0] is not None and 1 <= int(r[0]) <= 6]
    if not vals: return None
    med=float(statistics.median(vals))
    return max(1,min(6,int(med+0.5)))

def learned_cut(start_id,target_id):
    """Use real matchup behavior only after enough exact-match solves exist."""
    with sqlite3.connect(RESULTS_DB) as db:
        matchup=db.execute(
            'SELECT degrees FROM game_results WHERE solved=1 AND start_id=? AND target_id=?',
            (str(start_id),str(target_id))
        ).fetchall()
    if len(matchup) >= 10:
        return _median_cut(matchup), {'source':'matchup_median','samples':len(matchup)}
    return None, {'source':'provisional','samples':len(matchup)}

def save_game_result(puzzle_id,puzzle,verified,solved,gave_up,hints_used,deep_bonus,hint_penalty,points,elapsed_seconds=None,backtrack_penalty=0):
    row=(str(puzzle_id),int(time.time()),puzzle['difficulty'],str(puzzle['start']['id']),puzzle['start']['name'],str(puzzle['target']['id']),puzzle['target']['name'],int(bool(solved)),int(bool(gave_up)),len(verified) if solved else None,int(puzzle.get('cut',3)),int(hints_used),int(deep_bonus),int(hint_penalty),int(points),float(elapsed_seconds) if elapsed_seconds is not None else None,json.dumps(verified,separators=(',',':')),int(puzzle.get('backtracks_used',0)),int(backtrack_penalty))
    with RESULTS_LOCK, sqlite3.connect(RESULTS_DB) as db:
        db.execute("""INSERT OR IGNORE INTO game_results (puzzle_id,created_at,difficulty,start_id,start_name,target_id,target_name,solved,gave_up,degrees,cut,hints_used,deep_cut_bonus,hint_penalty,points,elapsed_seconds,route_json,backtracks_used,backtrack_penalty) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",row)
        db.commit()

def result_stats():
    with sqlite3.connect(RESULTS_DB) as db:
        total=db.execute('SELECT COUNT(*) FROM game_results').fetchone()[0]
        solved=db.execute('SELECT COUNT(*) FROM game_results WHERE solved=1').fetchone()[0]
        avg=db.execute('SELECT AVG(degrees) FROM game_results WHERE solved=1').fetchone()[0]
    return {'attempts':total,'solved':solved,'average_degrees':round(avg,2) if avg is not None else None}

def eligibility_for(mid, actor):
    aid=str(actor.get('id','')); mid=str(mid)
    rule=(ELIGIBILITY_OVERRIDES.get(mid) or {}).get(aid)
    if rule is not None:
        if isinstance(rule,bool):
            return {'eligible':rule,'reason':'curated_override'}
        return {'eligible':bool(rule.get('eligible',False)),
                'reason':rule.get('reason','curated_override'),
                'source':rule.get('source'), 'note':rule.get('note')}

    # TMDB's /movie/{id}/credits `cast` array is the authoritative default for
    # an acting/on-screen movie appearance. Do NOT require a nonblank character
    # field: valid voice and acting credits can have incomplete role metadata.
    # Crew-only credits live in the separate `crew` array and never reach this
    # function through cast(). Known edge cases (for example an ineligible
    # end-credit-only appearance) are handled with eligibility_overrides.json.
    role=str(actor.get('character') or '').lower().replace('–','-').replace('—','-')
    annotations=re.findall(r'[\(\[]([^\)\]]*)[\)\]]',role)
    if role.strip() in {'cameo','cameo appearance','post-credits scene','mid-credits scene','end-credits scene'}:
        annotations.append(role)
    for annotation in annotations:
        if re.search(r'\b(?:post|mid|end|after)[ -]credits?\b',annotation):
            return {'eligible':False,'reason':'end_credit_only_label'}
        if re.search(r'\bcameo\b',annotation):
            return {'eligible':False,'reason':'cameo_label'}
    return {'eligible':True,'reason':'provider_movie_cast'}

def eligible_cast(mid):
    return [a for a in cast(mid) if eligibility_for(mid,a)['eligible']]

def movie_credit_for_actor(actor_id, movie_id):
    """Return an eligible current-actor movie cast credit, or None."""
    aid=str(actor_id); mid=str(movie_id)
    if not eligibility_for(mid,{'id':aid})['eligible']: return None
    movie=next((m for m in movies(aid) if str(m.get('id'))==mid), None)
    if movie is not None and (not eligibility_for(mid,dict(movie,id=aid))['eligible'] or connection_actor(mid,aid) is None): return None
    return movie

def connection_actor(movie_id, actor_id):
    """Return an eligible movie-cast row for actor_id, or None.

    This is the only movie-side eligibility gate used by gameplay, autocomplete,
    graph expansion, hints, and curated-route validation.
    """
    aid=str(actor_id); mid=str(movie_id)
    return next((a for a in cast(mid)
                 if str(a.get('id'))==aid and eligibility_for(mid,a)['eligible']), None)

def validate_connection(current_actor_id, movie_id, next_actor_id):
    """Canonical Actor -> Movie -> Actor validation.

    Rule: the current actor must have the movie in their movie CAST credits; the
    connecting actor must appear in that movie's CAST array and pass explicit
    eligibility overrides; the two people must be different. Crew-only credits
    never qualify because cast() reads only TMDB's cast array.
    """
    current=str(current_actor_id); nxt=str(next_actor_id); mid=str(movie_id)
    if not current or not nxt or not mid or current==nxt:
        return None
    movie=movie_credit_for_actor(current,mid)
    if not movie:
        return None
    actor=connection_actor(mid,nxt)
    if not actor:
        return None
    return {'movie':movie,'actor':actor}

def valid_connection_candidates(current_actor_id, movie_id):
    """Eligible connecting actors for a movie, using the same rule as /api/move."""
    current=str(current_actor_id); mid=str(movie_id)
    if not movie_credit_for_actor(current,mid):
        return []
    return [a for a in cast(mid)
            if str(a.get('id'))!=current and eligibility_for(mid,a)['eligible']]

def set_eligibility_override(mid, aid, eligible, reason, source=None, note=None):
    """Internal curation helper; not exposed as a public HTTP endpoint."""
    mid,aid=str(mid),str(aid)
    rule={'eligible':bool(eligible),'reason':str(reason)}
    if source: rule['source']=str(source)
    if note: rule['note']=str(note)
    ELIGIBILITY_OVERRIDES.setdefault(mid,{})[aid]=rule
    ELIGIBILITY_FILE.write_text(json.dumps(ELIGIBILITY_OVERRIDES,indent=2,sort_keys=True))
    return rule
# Zero-setup demo graph. If no external movie-data credential is configured,
# the server automatically uses this verified sample graph so the game is playable.
DEMO_PEOPLE={
 'Michael Shannon':{'id':'p1','name':'Michael Shannon','profile_path':None},
 'Russell Crowe':{'id':'p2','name':'Russell Crowe','profile_path':None},
 'Denzel Washington':{'id':'p3','name':'Denzel Washington','profile_path':None},
 'Henry Cavill':{'id':'p4','name':'Henry Cavill','profile_path':None},
 'Tom Hanks':{'id':'p5','name':'Tom Hanks','profile_path':None},
 'Julia Roberts':{'id':'p6','name':'Julia Roberts','profile_path':None},
 'George Clooney':{'id':'p7','name':'George Clooney','profile_path':None},
 'Matt Damon':{'id':'p8','name':'Matt Damon','profile_path':None},
 'Paul Giamatti':{'id':'p9','name':'Paul Giamatti','profile_path':None},
 'Steve Martin':{'id':'p10','name':'Steve Martin','profile_path':None},
 'Queen Latifah':{'id':'p11','name':'Queen Latifah','profile_path':None},
 'John C. Reilly':{'id':'p12','name':'John C. Reilly','profile_path':None},
 'Luis Guzman':{'id':'p13','name':'Luis Guzman','profile_path':None},
 'Jeff Bridges':{'id':'p14','name':'Jeff Bridges','profile_path':None},
 'John Goodman':{'id':'p15','name':'John Goodman','profile_path':None},
 'Steve Buscemi':{'id':'p16','name':'Steve Buscemi','profile_path':None},
 'Morgan Freeman':{'id':'p17','name':'Morgan Freeman','profile_path':None},
 'Michael Caine':{'id':'p18','name':'Michael Caine','profile_path':None},
 'Clint Eastwood':{'id':'p19','name':'Clint Eastwood','profile_path':None},
 'Jack Nicholson':{'id':'p20','name':'Jack Nicholson','profile_path':None},
 'Scarlett Johansson':{'id':'p21','name':'Scarlett Johansson','profile_path':None},
 'Angelina Jolie':{'id':'p22','name':'Angelina Jolie','profile_path':None},

}
DEMO_MOVIES={
 'm1':{'id':'m1','title':'Man of Steel','release_date':'2013-06-14','popularity':100,'poster_path':None,'actors':['Michael Shannon','Russell Crowe','Henry Cavill']},
 'm2':{'id':'m2','title':'Virtuosity','release_date':'1995-08-04','popularity':90,'poster_path':None,'actors':['Russell Crowe','Denzel Washington']},
 'm3':{'id':'m3','title':'Philadelphia','release_date':'1993-12-22','popularity':95,'poster_path':None,'actors':['Tom Hanks','Denzel Washington']},
 'm4':{'id':'m4','title':'The Pelican Brief','release_date':'1993-12-17','popularity':90,'poster_path':None,'actors':['Julia Roberts','Denzel Washington']},
 'm5':{'id':'m5','title':"Ocean's Eleven",'release_date':'2001-12-07','popularity':95,'poster_path':None,'actors':['George Clooney','Matt Damon']},
 'm6':{'id':'m6','title':'Courage Under Fire','release_date':'1996-07-12','popularity':85,'poster_path':None,'actors':['Matt Damon','Denzel Washington']},
 'm7':{'id':'m7','title':'Cinderella Man','release_date':'2005-06-03','popularity':80,'poster_path':None,'actors':['Paul Giamatti','Russell Crowe']},
 'm8':{'id':'m8','title':'Bringing Down the House','release_date':'2003-03-07','popularity':80,'poster_path':None,'actors':['Steve Martin','Queen Latifah']},
 'm9':{'id':'m9','title':'The Bone Collector','release_date':'1999-11-05','popularity':90,'poster_path':None,'actors':['Denzel Washington','Queen Latifah','Luis Guzman']},
 'm10':{'id':'m10','title':'Boogie Nights','release_date':'1997-10-10','popularity':90,'poster_path':None,'actors':['John C. Reilly','Luis Guzman']},
 'm11':{'id':'m11','title':'The Big Lebowski','release_date':'1998-03-06','popularity':95,'poster_path':None,'actors':['Jeff Bridges','John Goodman','Steve Buscemi']},
 'm12':{'id':'m12','title':'Flight','release_date':'2012-11-02','popularity':90,'poster_path':None,'actors':['Denzel Washington','John Goodman']},
 'm13':{'id':'m13','title':'Glory','release_date':'1989-12-15','popularity':90,'poster_path':None,'actors':['Denzel Washington','Morgan Freeman']},
}
# Offline fixtures for the additional live-validated Morgan Freeman bridges.
# Popularity values are synthetic demo data, not provider measurements.
DEMO_MOVIES['m14']={'id':'m14','title':'Batman Begins','release_date':'','popularity':50,'poster_path':None,'actors':['Morgan Freeman','Michael Caine']}
DEMO_MOVIES['m15']={'id':'m15','title':'Unforgiven','release_date':'','popularity':50,'poster_path':None,'actors':['Morgan Freeman','Clint Eastwood']}
DEMO_MOVIES['m16']={'id':'m16','title':'The Bucket List','release_date':'','popularity':50,'poster_path':None,'actors':['Morgan Freeman','Jack Nicholson']}
DEMO_MOVIES['m17']={'id':'m17','title':'Lucy','release_date':'','popularity':50,'poster_path':None,'actors':['Morgan Freeman','Scarlett Johansson']}
DEMO_MOVIES['m18']={'id':'m18','title':'Wanted','release_date':'','popularity':50,'poster_path':None,'actors':['Morgan Freeman','Angelina Jolie']}
# Glory cast verified against https://www.sonypictures.com/movies/glory
DEMO_BY_ID={str(v['id']):v for v in DEMO_PEOPLE.values()}
DEMO_NAME_BY_ID={str(v['id']):k for k,v in DEMO_PEOPLE.items()}
DEMO_MODE=not bool(TOKEN)

SEARCH_CONTEXT=threading.local()

def check_search_budget():
    deadline=getattr(SEARCH_CONTEXT,'deadline',None)
    if deadline is not None and time.monotonic()>=deadline:
        raise TimeoutError('Hint search exceeded its time budget')

def cache_file(key):
    safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in key)
    return CACHE_DIR/(safe+'.json')

def cached(key, loader):
    check_search_budget()
    now=time.time()
    with LOCK:
        if key in MEM and now-MEM[key][0] < TTL: return MEM[key][1]
    f=cache_file(key)
    if f.exists() and now-f.stat().st_mtime < TTL:
        try:
            data=json.loads(f.read_text())
            with LOCK: MEM[key]=(now,data)
            return data
        except Exception: pass
    data=loader()
    try: f.write_text(json.dumps(data))
    except Exception: pass
    with LOCK: MEM[key]=(now,data)
    return data

def tmdb(path, params=None):
    if not TOKEN: raise RuntimeError('Server is missing TMDB_API_TOKEN')
    url=TMDB+path
    if params: url += '?' + urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+TOKEN,'accept':'application/json','User-Agent':'ActorConnectionPrototype/0.3'})
    check_search_budget()
    deadline=getattr(SEARCH_CONTEXT,'deadline',None)
    timeout=min(20,max(0.1,deadline-time.monotonic())) if deadline is not None else 20
    with urllib.request.urlopen(req,timeout=timeout) as r:
        result=json.load(r)
    check_search_budget()
    return result

def person(name):
    if DEMO_MODE: return DEMO_PEOPLE.get(name,{})
    key='person_v3_'+name.lower()
    def load():
        d=tmdb('/search/person',{'query':name,'include_adult':'false','language':'en-US','page':1})
        rows=d.get('results',[])
        exact=[x for x in rows if _name_key(x.get('name'))==_name_key(name)]
        acting=[x for x in rows if x.get('known_for_department')=='Acting']
        # A performer may be best known as a director/writer. Their movie CAST
        # credits decide eligibility; their primary occupation is not a ban.
        preferred=[x for x in exact if x.get('known_for_department')=='Acting'] or exact or acting or rows
        return preferred[0] if preferred else {}
    return cached(key,load)

def movies(pid):
    if DEMO_MODE:
        name=DEMO_NAME_BY_ID.get(str(pid))
        return [{k:v for k,v in m.items() if k!='actors'} for m in DEMO_MOVIES.values() if name in m['actors']]
    def load():
        d=tmdb(f'/person/{pid}/movie_credits',{'language':'en-US'})
        rows=[x for x in d.get('cast',[]) if x.get('release_date')]
        rows.sort(key=lambda x:x.get('popularity',0),reverse=True)
        return rows
    return cached('movies_'+str(pid),load)

def cast(mid):
    if DEMO_MODE:
        m=DEMO_MOVIES.get(str(mid),{})
        return [DEMO_PEOPLE[n] for n in m.get('actors',[]) if n in DEMO_PEOPLE]
    return cached('cast_'+str(mid),lambda:tmdb(f'/movie/{mid}/credits',{'language':'en-US'}).get('cast',[]))

def _neighbors(pid, movie_limit=None, cast_limit=None, stats=None):
    """Yield unique actor neighbors with the movie that connects them.

    Limits are explicit search-envelope controls. None means all provider-returned
    movie credits/cast members are considered for that expansion.
    """
    actor_movies=movies(pid)
    if movie_limit is not None: actor_movies=actor_movies[:movie_limit]
    emitted=set()
    for m in actor_movies:
        check_search_budget()
        mid=str(m.get('id'))
        movie_cast=valid_connection_candidates(pid,mid)
        if cast_limit is not None: movie_cast=movie_cast[:cast_limit]
        if stats is not None:
            stats['movies_scanned'] += 1
            stats['cast_rows_scanned'] += len(movie_cast)
        for a in movie_cast:
            aid=str(a.get('id'))
            if aid==str(pid) or aid in emitted: continue
            emitted.add(aid)
            yield aid, {'movie':{'id':m.get('id'),'title':m.get('title'),'poster_path':m.get('poster_path')},
                        'actor':{'id':a.get('id'),'name':a.get('name'),'profile_path':a.get('profile_path')}}

def _bounded_bfs(start,target,max_depth,movie_limit,cast_limit):
    """Breadth-first search inside a declared envelope; shortest only inside it."""
    stats={'actors_expanded':0,'movies_scanned':0,'cast_rows_scanned':0,
           'movie_limit':movie_limit,'cast_limit':cast_limit,'max_depth':max_depth}
    if str(start)==str(target): return [],stats
    q=deque([(str(start),[])])
    seen={str(start)}
    while q:
        check_search_budget()
        pid,path=q.popleft()
        if len(path)>=max_depth: continue
        stats['actors_expanded'] += 1
        for aid,step in _neighbors(pid,movie_limit,cast_limit,stats):
            if aid in seen: continue
            np=path+[step]
            if aid==str(target): return np,stats
            seen.add(aid)
            if len(np)<max_depth: q.append((aid,np))
    return None,stats

def find_path_with_meta(start,target,max_depth=6):
    """Find a verified route and describe exactly what the search proves.

    Demo mode searches the entire bundled graph, so BFS proves global shortest
    distance in that graph. Live mode widens in stages. A live result is always
    a verified route, but never falsely advertised as globally shortest because
    provider/API practical limits make an exhaustive movie-universe proof costly.
    """
    if DEMO_MODE:
        path,stats=_bounded_bfs(start,target,max_depth,None,None)
        return path,{'status':'proven_shortest','scope':'complete_demo_graph','stats':stats}

    # Fast first pass, then progressively wider passes. This improves route quality
    # without making every puzzle generation pay the cost of a huge graph crawl.
    stages=[(40,35),(80,60),(140,100)]
    best=None; best_stats=None
    for movie_limit,cast_limit in stages:
        path,stats=_bounded_bfs(start,target,max_depth,movie_limit,cast_limit)
        if path is not None and (best is None or len(path)<len(best)):
            best,best_stats=path,stats
            # One degree is mathematically unbeatable; no wider pass can improve it.
            if len(best)==1: break
        # If we found a route, keep widening once more to look for a shorter route,
        # but avoid automatically exploding API work through every remaining stage.
        if best is not None and (movie_limit,cast_limit)!=(stages[0]): break
    return best,{'status':'verified_route','scope':'adaptive_live_graph','stats':best_stats or stats}

def find_path(start,target,max_depth=6):
    return find_path_with_meta(start,target,max_depth)[0]

def public_person(p):
    return {'id':p.get('id'),'name':p.get('name'),'profile_path':p.get('profile_path')}

def cleanup_puzzles():
    cutoff=time.time()-PUZZLE_TTL
    with LOCK:
        stale=[pid for pid,p in PUZZLES.items() if p.get('created',0)<cutoff]
        for pid in stale: PUZZLES.pop(pid,None)

def score_for(degrees, cut=3, hints_used=0, deep_cut_bonus=0, backtrack_penalty=0, six_hint_rule=True):
    # The Cut is the expected competent-player route, not the mathematical shortest path.
    # Route efficiency stays primary; Deep Cut bonuses are capped so obscure detours cannot farm points.
    if degrees is None or degrees < 1 or degrees > 6: return 0
    base=max(25, 100 + (cut-degrees)*25)
    hint_penalty=0 if hints_used <= 0 else (10 if hints_used == 1 else 20)
    # A six-connection solve with hints has no positive scoring base.
    # Deep Cuts still earn free backs, but cannot cancel this penalty.
    if six_hint_rule and degrees == 6 and hints_used > 0:
        return -hint_penalty - max(0, backtrack_penalty)
    return max(0, base + min(25, max(0, deep_cut_bonus)) - hint_penalty - max(0, backtrack_penalty))

def connection_deep_cut(movie, movie_cast, current_id, next_id):
    """Estimate how non-obvious a *connection* is, not how famous an actor is.

    This is deliberately conservative.  A buried credit in a less prominent/older movie can
    earn a Deep Cut, while a top-billed role in a famous movie normally earns nothing.
    The returned values are the game scale: 0 / 5 / 10 / 15.
    """
    by_id={str(a.get('id')):a for a in movie_cast}
    # Excluded/missing credits cannot earn obscurity points from fallback billing.
    if str(current_id) not in by_id or str(next_id) not in by_id: return 0
    cur=by_id[str(current_id)]; nxt=by_id[str(next_id)]
    def billing(a):
        if a.get('order') is not None:
            try: return int(a.get('order'))
            except Exception: pass
        # Demo data is intentionally tiny and ordered by its bundled cast list.
        for i,x in enumerate(movie_cast):
            if str(x.get('id'))==str(a.get('id')): return i
        return 99
    buried=max(billing(cur), billing(nxt))
    # Deep Cut is about an obscure connection, not merely an older or currently
    # low-popularity movie. If both actors are top-billed, the link is too prominent
    # to earn an obscurity bonus.
    if buried <= 3:
        return 0
    popularity=float(movie.get('popularity') or 0)
    year=0
    try: year=int((movie.get('release_date') or '')[:4])
    except Exception: pass
    age=max(0, datetime.datetime.now().year-year) if year else 0
    difficulty=0
    if buried >= 15: difficulty += 3
    elif buried >= 8: difficulty += 2
    elif buried >= 4: difficulty += 1
    if popularity and popularity < 8: difficulty += 2
    elif popularity and popularity < 20: difficulty += 1
    if age >= 35: difficulty += 1
    if difficulty >= 5: return 15
    if difficulty >= 3: return 10
    if difficulty >= 2: return 5
    return 0

def deep_cut_for_route(start_id, verified):
    cur=str(start_id); details=[]; total=0
    for step in verified:
        mid=str(step['movie']['id']); nxt=str(step['actor']['id'])
        movie=next((m for m in movies(cur) if str(m.get('id'))==mid), step['movie'])
        movie_cast=eligible_cast(mid)
        bonus=connection_deep_cut(movie,movie_cast,cur,nxt)
        from_name=next((a.get('name','') for a in movie_cast if str(a.get('id'))==cur),'')
        details.append({'movie':step['movie']['title'],'from_actor':from_name,'actor':step['actor']['name'],'bonus':bonus})
        total += bonus; cur=nxt
    return min(25,total), details

def provisional_cut_for_route(route, start_id=None):
    """Estimate competent-player route length from the verified route itself.

    The verified route is the floor, not automatically The Cut. Obscure links can
    raise the expectation by one or two degrees, but the provisional Cut can never
    drift more than two above the verified route. Direct, prominent connections stay
    at 1 instead of inheriting a generic difficulty seed.
    """
    distance=max(1,min(6,len(route or [])))
    obscure_steps=0
    deep_points=0
    details=[]
    if start_id is not None and route:
        try:
            deep_points,details=deep_cut_for_route(start_id,route)
            obscure_steps=sum(1 for d in details if int(d.get('bonus',0) or 0)>0)
        except Exception:
            # Cut generation must never make an otherwise valid puzzle fail to load.
            deep_points,details,obscure_steps=0,[],0

    uplift=0
    if obscure_steps==1:
        uplift=1
        # A single genuinely buried connection can justify a larger gap.
        if deep_points>=15: uplift=2
    elif obscure_steps>=2:
        uplift=2

    cut=max(1,min(6,distance+uplift))
    return cut,{
        'source':'provisional_route_model',
        'samples':0,
        'verified_distance':distance,
        'obscure_steps':obscure_steps,
        'deep_points_on_reference_route':deep_points,
        'uplift':uplift
    }

def cut_for(difficulty, route, start_id=None, target_id=None):
    # The Cut models expected competent-player performance, not difficulty labels.
    # Exact matchup data wins once we have enough real solves; until then, derive a
    # provisional Cut from the verified route and how obscure its connections are.
    if start_id is not None and target_id is not None:
        learned,meta=learned_cut(start_id,target_id)
        if learned is not None:
            return learned,meta
    cut,meta=provisional_cut_for_route(route,start_id)
    if start_id is not None and target_id is not None:
        _,learn_meta=learned_cut(start_id,target_id)
        meta['samples']=learn_meta.get('samples',0)
    return cut,meta

def live_candidate_catalog(max_pages=20):
    """Return a broad, cached pool of working film actors for live puzzle generation.

    We intentionally do not use a tiny hand-written name list in live mode. Provider
    popularity is used only as a recognizability signal; route verification remains the
    hard gate before anybody can be served.
    """
    if DEMO_MODE:
        return [{'name':n,'popularity':0,'known_for':[]} for n in DEMO_PEOPLE]
    def load():
        # Keep startup cheap: /person/popular already includes a small known_for sample.
        # The old code fetched a full filmography for every popular person (up to ~100
        # extra provider calls) before a difficulty button could even respond.
        out=[]; seen=set()
        for page in range(1,max_pages+1):
            data=tmdb('/person/popular',{'page':page})
            for x in data.get('results',[]):
                if x.get('known_for_department')!='Acting' or not x.get('name'): continue
                pid=str(x.get('id'))
                if not pid or pid in seen: continue
                seen.add(pid)
                known_movies=[k for k in (x.get('known_for') or []) if k.get('media_type')=='movie']
                if not known_movies or not x.get('profile_path'): continue
                out.append({'id':x.get('id'),'name':x['name'],'profile_path':x.get('profile_path'),
                            'popularity':float(x.get('popularity') or 0),'known_for':known_movies})
        return out
    return cached(f'candidate_catalog_{max_pages}',load)

def candidate_names_for(difficulty,target_name=None):
    target_name=target_name or weekly_target()['name']
    if DEMO_MODE:
        return list(PUZZLE_CANDIDATES[difficulty])
    catalog=live_candidate_catalog()
    # Popularity is a starting recognizability heuristic, not the final difficulty model.
    # Beginner favors familiar faces; Expert favors the lower half of a still-recognizable
    # catalog. Route verification and, later, player data determine actual playability.
    ranked=sorted(catalog,key=lambda x:x.get('popularity',0),reverse=True)
    n=len(ranked)
    if difficulty=='beginner': band=ranked[:max(30,n//3)]
    elif difficulty=='intermediate': band=ranked[max(15,n//5):max(50,(n*3)//4)]
    else: band=ranked[max(30,n//2):] or ranked
    return [x['name'] for x in band if x['name']!=target_name]



# Fast, curated alpha routes. These are resolved against the live provider before
# a puzzle is served, so the game still validates real movie credits. They keep
# difficulty selection responsive while the broader graph search remains as a fallback.
CURATED_ALPHA_ROUTES={
    # Alpha starter pools intentionally avoid direct co-stars of the weekly target.
    # Each route is still resolved against live TMDB credits before it can be served.
    'beginner':[
        ('Tom Hanks',[('Apollo 13','Ed Harris'),('Gone Baby Gone','Morgan Freeman')]),
        ('Julia Roberts',[("Ocean's Eleven",'Brad Pitt'),('Se7en','Morgan Freeman')]),
        ('George Clooney',[("Ocean's Eleven",'Brad Pitt'),('Se7en','Morgan Freeman')]),
        ('Leonardo DiCaprio',[('Once Upon a Time... in Hollywood','Brad Pitt'),('Se7en','Morgan Freeman')]),
        ('Samuel L. Jackson',[('Pulp Fiction','Bruce Willis'),('RED','Morgan Freeman')]),
        ('Nicolas Cage',[('The Rock','Ed Harris'),('Gone Baby Gone','Morgan Freeman')]),
        ('Ryan Gosling',[('The Big Short','Brad Pitt'),('Se7en','Morgan Freeman')]),
        ('Emma Stone',[('Zombieland','Woody Harrelson'),('Now You See Me','Morgan Freeman')]),
        ('Chris Evans',[('Avengers: Endgame','Scarlett Johansson'),('Lucy','Morgan Freeman')]),
        ('Robert Downey Jr.',[('Iron Man 2','Scarlett Johansson'),('Lucy','Morgan Freeman')]),
        ('Harrison Ford',[('The Fugitive','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Sandra Bullock',[('The Proposal','Ryan Reynolds'),("Hitman's Wife's Bodyguard",'Morgan Freeman')]),
        ('Mark Wahlberg',[('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Adam Sandler',[('Anger Management','Jack Nicholson'),('The Bucket List','Morgan Freeman')]),
        ('Bradley Cooper',[('American Hustle','Christian Bale'),('The Dark Knight Rises','Morgan Freeman')]),
        ('Jennifer Lawrence',[('American Hustle','Christian Bale'),('The Dark Knight Rises','Morgan Freeman')]),
        ('Johnny Depp',[('Charlie and the Chocolate Factory','Helena Bonham Carter'),('The Dark Knight Rises','Morgan Freeman')]),
        ('Will Ferrell',[('The Other Guys','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Robin Williams',[('Insomnia','Al Pacino'),('Heat','Robert De Niro'),('Last Vegas','Morgan Freeman')]),
        ('Kevin Bacon',[('A Few Good Men','Tom Cruise'),('Oblivion','Morgan Freeman')]),
    ],
    'intermediate':[
        ('Paul Giamatti',[('Cinderella Man','Russell Crowe'),('Virtuosity','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('John C. Reilly',[('Boogie Nights','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Steve Buscemi',[('The Big Lebowski','John Goodman'),('Flight','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Stanley Tucci',[('The Devil Wears Prada','Meryl Streep'),('Lions for Lambs','Tom Cruise'),('Oblivion','Morgan Freeman')]),
        ('J.K. Simmons',[('The Accountant','Ben Affleck'),('The Sum of All Fears','Morgan Freeman')]),
        ('John Turturro',[('The Big Lebowski','John Goodman'),('Flight','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Sam Rockwell',[('Iron Man 2','Scarlett Johansson'),('Lucy','Morgan Freeman')]),
        ('Willem Dafoe',[('Spider-Man','J.K. Simmons'),('The Accountant','Ben Affleck'),('The Sum of All Fears','Morgan Freeman')]),
        ('Edward Norton',[('The Italian Job','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Jeff Goldblum',[('Jurassic Park','Samuel L. Jackson'),('Pulp Fiction','Bruce Willis'),('RED','Morgan Freeman')]),
        ('Chris Cooper',[('Adaptation.','Nicolas Cage'),('The Rock','Ed Harris'),('Gone Baby Gone','Morgan Freeman')]),
        ('Richard Jenkins',[('Step Brothers','Will Ferrell'),('The Other Guys','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('David Strathairn',[('Lincoln','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Stephen Root',[('No Country for Old Men','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Jeff Bridges',[('The Big Lebowski','John Goodman'),('Flight','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Paul Rudd',[('Anchorman: The Legend of Ron Burgundy','Will Ferrell'),('The Other Guys','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Philip Seymour Hoffman',[('Boogie Nights','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Don Cheadle',[("Ocean's Eleven",'Brad Pitt'),('Se7en','Morgan Freeman')]),
        ('Laura Dern',[('Jurassic Park','Samuel L. Jackson'),('Pulp Fiction','Bruce Willis'),('RED','Morgan Freeman')]),
        ('Woody Allen',[('Antz','Gene Hackman'),('Unforgiven','Morgan Freeman')]),
    ],
    'expert':[
        ('Michael Shannon',[('Man of Steel','Russell Crowe'),('Virtuosity','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('David Morse',[('The Negotiator','Samuel L. Jackson'),('Pulp Fiction','Bruce Willis'),('RED','Morgan Freeman')]),
        ('William H. Macy',[('Boogie Nights','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Clifton Collins Jr.',[('Capote','Philip Seymour Hoffman'),('Boogie Nights','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Stephen Tobolowsky',[('Groundhog Day','Bill Murray'),("Charlie's Angels",'Drew Barrymore'),('Batman Forever','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Luis Guzman',[('Boogie Nights','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('John Hawkes',[('Lincoln','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Richard Jenkins',[('Step Brothers','Will Ferrell'),('The Other Guys','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('David Strathairn',[('Lincoln','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Stephen Root',[('No Country for Old Men','Tommy Lee Jones'),('High Crimes','Morgan Freeman')]),
        ('Paul Giamatti',[('Cinderella Man','Russell Crowe'),('Virtuosity','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('John C. Reilly',[('Boogie Nights','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Steve Buscemi',[('The Big Lebowski','John Goodman'),('Flight','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('John Turturro',[('The Big Lebowski','John Goodman'),('Flight','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('Willem Dafoe',[('Spider-Man','J.K. Simmons'),('The Accountant','Ben Affleck'),('The Sum of All Fears','Morgan Freeman')]),
        ('Chris Cooper',[('Adaptation.','Nicolas Cage'),('The Rock','Ed Harris'),('Gone Baby Gone','Morgan Freeman')]),
        ('Stanley Tucci',[('The Devil Wears Prada','Meryl Streep'),('Lions for Lambs','Tom Cruise'),('Oblivion','Morgan Freeman')]),
        ('Jeff Goldblum',[('Jurassic Park','Samuel L. Jackson'),('Pulp Fiction','Bruce Willis'),('RED','Morgan Freeman')]),
        ('Edward Norton',[('The Italian Job','Mark Wahlberg'),('2 Guns','Denzel Washington'),('Glory','Morgan Freeman')]),
        ('J.K. Simmons',[('The Accountant','Ben Affleck'),('The Sum of All Fears','Morgan Freeman')]),
    ],
}

def _title_key(value):
    value=unicodedata.normalize('NFKD',str(value or ''))
    return ''.join(ch.lower() for ch in value if ch.isalnum() and not unicodedata.combining(ch))

def _name_key(value):
    value=unicodedata.normalize('NFKD',str(value or ''))
    return ''.join(ch.lower() for ch in value if ch.isalnum() and not unicodedata.combining(ch))

def resolve_curated_route(start_person, steps, target_name=None):
    """Resolve and validate a short named route using the live provider.

    This is intentionally small and deterministic: each movie must be in the
    current actor's movie credits and the named next actor must be in that
    movie's eligible cast. If anything fails, return None and let normal graph
    search handle the candidate instead.
    """
    current=public_person(start_person)
    route=[]
    for movie_title,next_actor_name in steps:
        wanted=_title_key(movie_title)
        movie=next((m for m in movies(current['id']) if _title_key(m.get('title'))==wanted),None)
        if not movie:
            return None
        movie_cast=valid_connection_candidates(current['id'],movie.get('id'))
        next_actor=next((a for a in movie_cast if _name_key(a.get('name',''))==_name_key(next_actor_name)),None)
        if not next_actor:
            return None
        route.append({'movie':{'id':movie.get('id'),'title':movie.get('title'),'poster_path':movie.get('poster_path')},
                      'actor':public_person(next_actor)})
        current=public_person(next_actor)
    return route if route and str(current.get('name','')).casefold()==(target_name or weekly_target()['name']).casefold() else None

def has_direct_movie_connection(actor_id, target_id):
    """One cheap provider query to keep alpha starters from being direct co-stars.

    The game still accepts any legitimate direct connection a player discovers; this
    filter is only for starter selection so every test round is not a one-move puzzle.
    """
    if str(actor_id)==str(target_id):
        return True
    if DEMO_MODE:
        for m in movies(actor_id):
            if str(target_id) in {str(a.get('id')) for a in eligible_cast(m.get('id'))}:
                return True
        return False
    key=f'direct_{actor_id}_{target_id}'
    def load():
        d=tmdb('/discover/movie',{'with_people':f'{actor_id},{target_id}','include_adult':'false','page':1})
        return bool(d.get('total_results',0) or d.get('results'))
    return bool(cached(key,load))

def expand_verified_starter(candidate, route, difficulty, target, seconds=6):
    """Try co-stars of a verified route's first film, never a name allowlist.

    Only the first edge changes; the already validated tail stays intact. Missing
    photos do not disqualify an actor. A small budget protects round-start latency.
    """
    if not route: return candidate,route
    previous=getattr(SEARCH_CONTEXT,'deadline',None)
    deadline=time.monotonic()+seconds
    SEARCH_CONTEXT.deadline=min(previous,deadline) if previous is not None else deadline
    try:
        first=route[0]; mid=first['movie']['id']; next_id=str(first['actor']['id'])
        cast_rows=eligible_cast(mid)
        # Billing is a starter recognizability heuristic, not an eligibility rule.
        if difficulty=='beginner': pool=cast_rows[:10]
        elif difficulty=='expert': pool=cast_rows[10:] or cast_rows
        else: pool=cast_rows
        pool=list(pool);secrets.SystemRandom().shuffle(pool)
        for actor in pool:
            check_search_budget()
            aid=str(actor.get('id'))
            if not actor.get('name') or aid in {next_id,str(target['id'])}: continue
            if actor['name'] in USED_STARTERS: continue
            if has_direct_movie_connection(aid,target['id']): continue
            connection=validate_connection(aid,mid,next_id)
            if connection:
                return public_person(actor),[{'movie':first['movie'],'actor':public_person(connection['actor'])}]+route[1:]
    except (TimeoutError,OSError):
        # An unavailable discovery service cannot invalidate the verified seed.
        pass
    finally:
        SEARCH_CONTEXT.deadline=previous
    return candidate,route

def generate_puzzle(difficulty='expert', hints_enabled=True):
    previous=getattr(SEARCH_CONTEXT,'deadline',None)
    deadline=time.monotonic()+60
    SEARCH_CONTEXT.deadline=min(previous,deadline) if previous is not None else deadline
    try:
        return _generate_puzzle(difficulty,hints_enabled)
    except TimeoutError as error:
        raise RuntimeError('Could not verify a puzzle within the search limit. Retry or choose another level.') from error
    finally:
        SEARCH_CONTEXT.deadline=previous

def _generate_puzzle(difficulty='expert', hints_enabled=True):
    cleanup_puzzles()
    difficulty=(difficulty or 'expert').lower()
    if difficulty not in PUZZLE_CANDIDATES: difficulty='expert'
    target_name=weekly_target()['name']
    target=person(target_name)
    if not target: raise RuntimeError('Weekly target could not be loaded')
    # First try the tiny curated alpha pool for this difficulty BEFORE building
    # the broad live candidate catalog.  The catalog is only needed as fallback;
    # building it on every cold deploy can add a long delay to a button tap.

    # First try the tiny curated alpha pool for this difficulty. This avoids an
    # expensive six-degree graph crawl on the request that follows a button tap.
    # Every step is still checked against live provider credits before serving.
    curated=CURATED_ALPHA_ROUTES.get(difficulty,[])
    target_bridges={
        'Michael Caine':[('Batman Begins','Michael Caine')],
        'Clint Eastwood':[('Unforgiven','Clint Eastwood')],
        'Jack Nicholson':[('The Bucket List','Jack Nicholson')],
        'Scarlett Johansson':[('Lucy','Scarlett Johansson')],
        'Angelina Jolie':[('Wanted','Angelina Jolie')],
        'Denzel Washington':[('Glory','Denzel Washington')],
        'Matt Damon':[('Invictus','Matt Damon')],
        'Tom Hanks':[('Gone Baby Gone','Ed Harris'),('Apollo 13','Tom Hanks')]
    }
    if target_name in target_bridges:
        adapted=[]
        for starter,steps in curated:
            extended=steps+target_bridges[target_name]
            # Stop at the first target appearance; never force a redundant detour.
            hit=next(i for i,(_,name) in enumerate(extended) if name==target_name)
            adapted.append((starter,extended[:hit+1]))
        curated=adapted
    # Prefer a fresh starter, but if the remaining fresh entries fail provider
    # resolution, immediately recycle a known-good curated starter instead of
    # dropping into the expensive live graph crawl. This keeps repeated alpha
    # games fast even after the no-repeat pool has been used up.
    fresh=[x for x in curated if x[0] not in USED_STARTERS]
    # Shuffle copies while keeping unseen starters ahead of recycled ones.
    # Failed fresh entries are tried only once before the catalog fallback.
    recycled=[x for x in curated if x[0] in USED_STARTERS]
    rng=secrets.SystemRandom()
    rng.shuffle(fresh)
    rng.shuffle(recycled)
    curated_passes=[fresh,recycled]
    for curated_order in curated_passes:
      for candidate_name,steps in curated_order:
        candidate=person(candidate_name)
        if not candidate or str(candidate.get('id'))==str(target.get('id')):
            continue
        # For the current alpha pool, do not serve a starter who already shares
        # a movie with the weekly target; otherwise every round collapses to Cut 1.
        if has_direct_movie_connection(candidate.get('id'),target.get('id')):
            continue
        route=resolve_curated_route(candidate,steps,target_name)
        min_len=2 if DEMO_MODE else {'beginner':2,'intermediate':2,'expert':3}.get(difficulty,2)
        if not route or not (min_len <= len(route) <= 6):
            continue
        candidate,route=expand_verified_starter(candidate,route,difficulty,target)
        USED_STARTERS.add(candidate['name']); save_used_starters(USED_STARTERS)
        puzzle_id=secrets.token_urlsafe(12)
        cut,cut_meta=cut_for(difficulty, route, candidate.get('id'), target.get('id'))
        route_meta={'status':'verified_route','scope':'verified_cast_route','stats':{'steps':len(route)}}
        PUZZLES[puzzle_id]={
            'created':time.time(),'difficulty':difficulty,'hints_enabled':bool(hints_enabled),
            'start':public_person(candidate),'target':public_person(target),
            'comparison_route':route,'route_status':'verified_route','route_search':route_meta,
            'cut':cut,'cut_meta':cut_meta,'hints_used':0,'backtracks_used':0,
            'live_route':[], 'current_actor':public_person(candidate), 'finished':False
        }
        save_active_puzzles()
        return {
            'puzzle_id':puzzle_id,'difficulty':difficulty,'hints_enabled':bool(hints_enabled),
            'start':public_person(candidate),'target':public_person(target),'verified':True
        }

    # Only pay for the broader candidate catalog if every curated route failed.
    names=candidate_names_for(difficulty,target_name)
    if not names: raise RuntimeError('No starting-actor candidates available')
    start_at=PUZZLE_CURSOR[difficulty] % len(names)
    # Rotate candidates, but serve only after a route is verified under the same graph rules.
    # Do not repeat a starting actor until the eligible pool for this difficulty is exhausted.
    # A short mathematical route does not disqualify Expert; recognizability is a separate concern.
    def eligible_route(candidate):
        if not candidate or str(candidate.get('id'))==str(target.get('id')): return None
        if has_direct_movie_connection(candidate.get('id'),target.get('id')): return None
        route,route_meta=find_path_with_meta(candidate.get('id'),target.get('id'),6)
        min_len=2 if DEMO_MODE else {'beginner':2,'intermediate':2,'expert':3}.get(difficulty,2)
        if route is None or not (min_len <= len(route) <= 6): return None
        return route,route_meta

    ordered=[names[(start_at+i)%len(names)] for i in range(len(names))]
    fresh=[n for n in ordered if n not in USED_STARTERS]
    recycled=[n for n in ordered if n in USED_STARTERS]
    passes=[fresh,recycled]
    for pass_names in passes:
      for candidate_name in pass_names:
        idx=names.index(candidate_name); candidate=person(candidate_name)
        result=eligible_route(candidate)
        if result is not None:
            route,route_meta=result
            PUZZLE_CURSOR[difficulty]=(idx+1)%len(names)
            USED_STARTERS.add(candidate_name); save_used_starters(USED_STARTERS)
            puzzle_id=secrets.token_urlsafe(12)
            route_status=route_meta['status']
            cut,cut_meta=cut_for(difficulty, route, candidate.get('id'), target.get('id'))
            PUZZLES[puzzle_id]={
                'created':time.time(),'difficulty':difficulty,'hints_enabled':bool(hints_enabled),
                'start':public_person(candidate),'target':public_person(target),
                'comparison_route':route,'route_status':route_status,'route_search':route_meta,
                'cut':cut,'cut_meta':cut_meta,'hints_used':0,'backtracks_used':0,
                'live_route':[], 'current_actor':public_person(candidate), 'finished':False
            }
            save_active_puzzles()
            return {
                'puzzle_id':puzzle_id,
                'difficulty':difficulty,'hints_enabled':bool(hints_enabled),
                'start':public_person(candidate),
                'target':public_person(target),
                'verified':True,
                # Answer data intentionally stays server-side until the round is submitted.
            }
    raise RuntimeError('No candidate in this difficulty pool passed the <=6 verification gate')


def route_allowed_by_overrides(start_id, route):
    """Recheck both actors against cached/provider credits without a graph crawl."""
    current={'id':start_id}
    for step in route:
        mid=str(step['movie']['id']); actor=step['actor']
        if not validate_connection(current['id'],mid,actor['id']):
            return False
        current=actor
    return True

def known_finish_route(puzzle, current, max_depth):
    """Search only already accepted edges and the verified comparison route.

    Reverse played edges let an off-route player return toward a verified finish.
    This is a normal connection using the same film, not a free backtrack.
    """
    graph={}
    for route in (puzzle.get('comparison_route') or [], puzzle.get('live_route') or []):
        previous=puzzle['start']
        for step in route:
            actor=step['actor']
            if not route_allowed_by_overrides(previous['id'],[step]):
                previous=actor
                continue
            graph.setdefault(str(previous['id']),[]).append((str(actor['id']),step))
            reverse={'movie':step['movie'],'actor':previous}
            graph.setdefault(str(actor['id']),[]).append((str(previous['id']),reverse))
            previous=actor
    target=str(puzzle['target']['id'])
    queue=deque([(str(current),[])])
    seen={str(current)}
    while queue:
        actor,path=queue.popleft()
        if actor==target: return path
        if len(path)>=max_depth: continue
        for neighbor,step in graph.get(actor,[]):
            if neighbor not in seen:
                seen.add(neighbor); queue.append((neighbor,path+[step]))
    return None

def known_bridge_path(puzzle,current,target,depth):
    """Try shared-film joins to verified route actors before broad graph search."""
    current=str(current); target=str(target)
    hubs=[puzzle['target']]+[step['actor'] for step in reversed(puzzle.get('comparison_route') or [])]+[puzzle['start']]
    current_movies=movies(current)
    seen=set()
    for hub in hubs:
        check_search_budget()
        aid=str(hub['id'])
        if aid==current or aid in seen: continue
        seen.add(aid)
        tail=known_finish_route(puzzle,aid,depth-1)
        if tail is None: continue
        hub_movies={str(m['id']) for m in movies(aid)}
        for movie in current_movies:
            check_search_budget()
            mid=str(movie['id'])
            if mid not in hub_movies: continue
            connection=validate_connection(current,mid,aid)
            if not connection: continue
            m=connection['movie']
            step={'movie':{'id':m['id'],'title':m.get('title'),'poster_path':m.get('poster_path')},
                  'actor':public_person(connection['actor'])}
            return [step]+tail
    return None

def bounded_hint_path(current, target, depth, seconds=8, puzzle=None):
    previous=getattr(SEARCH_CONTEXT,'deadline',None)
    SEARCH_CONTEXT.deadline=time.monotonic()+seconds
    try:
        if puzzle is not None and depth>0:
            shortcut=known_bridge_path(puzzle,current,target,depth)
            if shortcut: return shortcut
        return find_path(current,target,depth)
    except (TimeoutError, OSError):
        return None
    finally:
        SEARCH_CONTEXT.deadline=previous

def route_revision_error(puzzle,body):
    if 'route_revision' not in body: return None
    expected=body['route_revision']
    if type(expected) is not int or expected<0:
        return ({'error':'Invalid route revision'},400)
    if expected!=int(puzzle.get('route_revision',0)):
        return ({'error':'Your round changed. Recover current progress before retrying.','round_changed':True},409)
    return None

def resumable_round(puzzle_id, puzzle):
    """Expose only player-owned progress; keep comparison answers and The Cut hidden."""
    played=list(puzzle.get('live_route') or [])
    deep,_=deep_cut_for_route(puzzle['start']['id'],played)
    return {'puzzle_id':puzzle_id,'verified':True,'difficulty':puzzle['difficulty'],'hints_enabled':puzzle.get('hints_enabled',True),
            'start':puzzle['start'],'target':puzzle['target'],
            'current_actor':puzzle['current_actor'],'live_route':played,
            'degrees':len(played),'route_revision':int(puzzle.get('route_revision',0)),'hints_used':int(puzzle.get('hints_used',0)),
            'backtracks_used':int(puzzle.get('backtracks_used',0)),
            'free_backs':1+(deep//10),'challenge_token':puzzle.get('challenge_token'),'challenge_benchmark':puzzle.get('challenge_benchmark'),
            'elapsed_seconds':max(0,int(time.time()-float(puzzle['created'])))}

PUBLIC_FILES={'/':'index.html','/index.html':'index.html','/assets/make-the-cut-logo.png':'assets/make-the-cut-logo.png'}

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        # Static files must be explicitly public; never serve arbitrary project state.
        return str(ROOT/PUBLIC_FILES.get(urllib.parse.urlparse(path).path,'index.html'))
    def do_HEAD(self):
        if urllib.parse.urlparse(self.path).path not in PUBLIC_FILES:
            return self.send_error(404)
        return super().do_HEAD()
    def send_json(self,obj,status=200):
        data=json.dumps(obj).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        with round_lock(query.get('puzzle_id',[''])[0]):
            return self.handle_get()
    def handle_get(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        try:
            if u.path=='/api/status': return self.send_json({'ready':True,'build':'2026-10-10-keyboard-search-v27','mode':'demo' if DEMO_MODE else 'live','cache_entries':len(list(CACHE_DIR.glob('*.json'))),'weekly_target':weekly_target()['name'],'weekly_schedule':weekly_target(),'eligibility_overrides':sum(len(v) for v in ELIGIBILITY_OVERRIDES.values()),'storage':{'data_directory_configured':bool(os.environ.get('GAME_DATA_DIR')),'results_in_data_directory':RESULTS_DB.resolve().is_relative_to(STATE_DIR)},'results':result_stats()})
            if u.path=='/api/round':
                pid=q.get('puzzle_id',[''])[0]; cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if puzzle.get('finished'):
                    result=puzzle.get('final_result')
                    if result is None: return self.send_json({'error':'Round already finished'},409)
                    return self.send_json(resumable_round(pid,puzzle) | {'finished':True,'final_result':result})
                return self.send_json(resumable_round(pid,puzzle))
            if u.path=='/api/challenge':
                preview=challenge_preview(q.get('token',[''])[0])
                if preview is None: return self.send_json({'error':'Challenge expired or unknown'},404)
                return self.send_json(preview)
            if u.path=='/api/puzzle' and 'challenge' in q:
                round_data=start_challenge(q['challenge'][0])
                if round_data is None: return self.send_json({'error':'Challenge expired or unknown'},404)
                return self.send_json(round_data)
            if u.path=='/api/puzzle': return self.send_json(generate_puzzle(q.get('difficulty',['expert'])[0], hints_enabled=q.get('hints',['on'])[0].lower()!='off'))
            if u.path=='/api/person': return self.send_json(person(q.get('name',[''])[0]))
            if u.path=='/api/autocomplete/movies':
                pid=q.get('puzzle_id',[''])[0]; term=q.get('q',[''])[0].strip().lower()
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if not term: return self.send_json([])
                current=str(puzzle['current_actor']['id'])
                hits=[m for m in movies(current) if _title_key(term) in _title_key(m.get('title','')) and eligibility_for(m.get('id'),dict(m,id=current))['eligible']]
                return self.send_json([{'id':m.get('id'),'title':m.get('title'),'release_date':m.get('release_date'),'poster_path':m.get('poster_path')} for m in hits[:12]])
            if u.path=='/api/autocomplete/actors':
                pid=q.get('puzzle_id',[''])[0]; mid=q.get('movie_id',[''])[0]; term=q.get('q',[''])[0].strip().lower()
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if not term or not mid: return self.send_json([])
                current=str(puzzle['current_actor']['id'])
                # Autocomplete and move validation deliberately share the exact same
                # canonical connection rule so the UI can never offer a choice that
                # /api/move subsequently rejects for eligibility reasons.
                hits=[a for a in valid_connection_candidates(current,mid)
                      if _name_key(term) in _name_key(a.get('name',''))]
                # Issue a short-lived server-side offer token for each autocomplete result.
                # If the UI offers a connection and the player selects it, /api/move
                # accepts that exact server-approved offer without re-querying provider data.
                movie=movie_credit_for_actor(current,mid)
                offered=puzzle.setdefault('offered_connections',{})
                out=[]
                for a in hits[:12]:
                    token=secrets.token_urlsafe(12)
                    offered[token]={
                        'current_actor_id':current,
                        'movie_id':str(mid),
                        'next_actor_id':str(a.get('id')),
                        'movie':{'id':movie.get('id'),'title':movie.get('title'),'poster_path':movie.get('poster_path')} if movie else {'id':mid,'title':''},
                        'actor':public_person(a),
                        'created':time.time()
                    }
                    out.append(public_person(a) | {'character':a.get('character',''),'connection_token':token})
                # Keep only the newest offers to avoid unbounded session growth.
                if len(offered)>100:
                    keep=sorted(offered.items(),key=lambda kv:kv[1].get('created',0),reverse=True)[:60]
                    puzzle['offered_connections']=dict(keep)
                save_active_puzzles()
                return self.send_json(out)
            if u.path.startswith('/api/person/') and u.path.endswith('/movies'):
                if not DEV_DIAGNOSTICS: return self.send_json({'error':'Not found'},404)
                return self.send_json(movies(u.path.split('/')[3]))
            if u.path.startswith('/api/movie/') and u.path.endswith('/cast'):
                if not DEV_DIAGNOSTICS: return self.send_json({'error':'Not found'},404)
                return self.send_json(cast(u.path.split('/')[3]))
            if u.path=='/api/path':
                if not DEV_DIAGNOSTICS: return self.send_json({'error':'Not found'},404)
                # Development-only diagnostics. The player UI uses /api/hint so it
                # never receives an entire answer route before the round is over.
                pid=q.get('puzzle_id',[''])[0]; a=q.get('from',[''])[0]; depth=min(6,max(1,int(q.get('max',['6'])[0])))
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                b=str(puzzle['target']['id'])
                return self.send_json({'path':find_path(a,b,depth)})
            if u.path=='/api/hint':
                pid=q.get('puzzle_id',[''])[0]; level=min(2,max(1,int(q.get('level',['1'])[0])))
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if 'route_revision' in q:
                    try: expected=int(q['route_revision'][0])
                    except (ValueError,TypeError): return self.send_json({'error':'Invalid route revision'},400)
                    revision_error=route_revision_error(puzzle,{'route_revision':expected})
                    if revision_error: return self.send_json(*revision_error)
                if not puzzle.get('hints_enabled',True): return self.send_json({'error':'Hints are disabled for this round'},403)
                depth=max(0,6-len(puzzle.get('live_route') or []))
                if depth==0 or puzzle.get('finished'): return self.send_json({'error':'No moves remaining'},409)
                a=str(puzzle['current_actor']['id'])
                # Cache the chosen route by current actor so Hint 1 and Hint 2 are guaranteed
                # to refer to the same route even if the graph/cache changes between clicks.
                hint_routes=puzzle.setdefault('hint_routes',{})
                path=hint_routes.get(a)
                if path is not None and (len(path)>depth or not route_allowed_by_overrides(a,path)):
                    hint_routes.pop(a,None); path=None
                if path is None:
                    # Reuse the route already verified at puzzle generation. A fresh
                    # live graph crawl can take minutes even at the starting actor.
                    reference=puzzle.get('comparison_route') or []
                    actors=[str(puzzle['start']['id'])]+[str(step['actor']['id']) for step in reference]
                    for index,actor_id in enumerate(actors[:-1]):
                        suffix=reference[index:]
                        if actor_id==a and len(suffix)<=depth and route_allowed_by_overrides(a,suffix):
                            path=suffix
                            break
                    if path is None:
                        path=known_finish_route(puzzle,a,depth)
                    if path is None:
                        path=bounded_hint_path(a,str(puzzle['target']['id']),depth,puzzle=puzzle)
                    if path: hint_routes[a]=path
                if not path: return self.send_json({'error':'No verified hint route found'},404)
                first=path[0]
                # Hint usage is server-authoritative. A client cannot erase a hint penalty
                # by submitting hints=0 at the end of the round.
                puzzle['hints_used']=max(int(puzzle.get('hints_used',0)), level)
                save_active_puzzles()
                out={'level':level,'movie':first['movie']}
                if level>=2: out['actor']=first['actor']
                return self.send_json(out)
            if u.path not in PUBLIC_FILES:
                return self.send_error(404)
            return super().do_GET()
        except Exception as e: return self.send_json({'error':str(e)},500)
    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            body=json.loads(self.rfile.read(n) or b'{}')
            if not isinstance(body,dict): return self.send_json({'error':'Expected a JSON object'},400)
        except (ValueError,TypeError): return self.send_json({'error':'Invalid JSON request'},400)
        with round_lock(body.get('puzzle_id')):
            return self.handle_post(body)
    def handle_post(self,body):
        try:
            if self.path in {'/api/validate','/api/move'}:
                pid=str(body.get('puzzle_id','')); cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                # Legacy stateless validation remains available only when no puzzle is supplied.
                if not pid and self.path=='/api/validate':
                    current=str(body.get('current_actor_id','')); nxt=str(body.get('next_actor_id','')); mid=str(body.get('movie_id',''))
                    return self.send_json({'valid': validate_connection(current,mid,nxt) is not None})
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if puzzle.get('finished'): return self.send_json({'error':'Round already finished'},409)
                revision_error=route_revision_error(puzzle,body)
                if revision_error: return self.send_json(*revision_error)
                current=str(puzzle['current_actor']['id']); nxt=str(body.get('next_actor_id','')); mid=str(body.get('movie_id',''))
                if len(puzzle['live_route'])>=6: return self.send_json({'error':'Six-degree limit reached'},409)
                token=str(body.get('connection_token','') or '')
                connection=None
                if token:
                    offer=(puzzle.get('offered_connections') or {}).get(token)
                    if offer and str(offer.get('current_actor_id'))==current and str(offer.get('movie_id'))==mid and str(offer.get('next_actor_id'))==nxt and route_allowed_by_overrides(current,[{'movie':{'id':mid},'actor':{'id':nxt}}]):
                        connection={'movie':offer.get('movie') or {},'actor':offer.get('actor') or {}}
                # Backward-compatible fallback for older clients that do not send a token.
                if connection is None:
                    connection=validate_connection(current,mid,nxt)
                if not connection:
                    return self.send_json({'valid':False,'degrees':len(puzzle['live_route']),'reason':'connection_not_authorized'})
                m=connection['movie']; a=connection['actor']
                step={'movie':{'id':m.get('id'),'title':m.get('title') or body.get('movie_title','')},
                      'actor':public_person(a)}
                # Compute against a proposed snapshot; provider failures must not advance the round.
                proposed=dict(puzzle,route_revision=int(puzzle.get('route_revision',0))+1,live_route=puzzle['live_route']+[step],current_actor=step['actor'],hint_routes={},offered_connections={})
                degrees=len(proposed['live_route']); solved=nxt==str(puzzle['target']['id']); remaining=max(0,6-degrees)
                # Early-failure detection: only declare a DEAD END when the search can actually
                # prove there is no finish inside the remaining moves. In demo mode the graph is
                # complete, so a failed BFS is proof. In live provider mode a failed bounded search
                # is only 'unknown' and must never be presented as a mathematical dead end.
                viability='solved' if solved else 'unknown'; finish_route=None
                if not solved and remaining>0:
                    finish_route=known_finish_route(proposed,nxt,remaining)
                    if finish_route:
                        viability='viable'
                        proposed['hint_routes'][nxt]=finish_route
                    elif DEMO_MODE:
                        finish_route,finish_meta=find_path_with_meta(nxt,str(puzzle['target']['id']),remaining)
                        viability='viable' if finish_route is not None else 'dead_end'
                    # Live unknown paths never trigger a blocking graph crawl here.
                elif not solved and remaining==0:
                    viability='dead_end'
                proposed['viability']=viability
                earned_deep,_=deep_cut_for_route(puzzle['start']['id'],proposed['live_route'])
                free_backs=1+(earned_deep//10)
                puzzle.update(proposed)
                save_active_puzzles()
                return self.send_json({'valid':True,'degrees':degrees,'route_revision':proposed['route_revision'],'remaining':remaining,'current_actor':step['actor'],'solved':solved,'limit_reached':degrees>=6,'free_backs':free_backs,'deep_cut_bank':earned_deep,'viability':viability,'dead_end':viability=='dead_end'})
            if self.path=='/api/backtrack':
                pid=str(body.get('puzzle_id','')); cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if puzzle.get('finished'): return self.send_json({'error':'Round already finished'},409)
                revision_error=route_revision_error(puzzle,body)
                if revision_error: return self.send_json(*revision_error)
                if not puzzle['live_route']: return self.send_json({'error':'Already at starting actor'},409)
                proposed=dict(puzzle,route_revision=int(puzzle.get('route_revision',0))+1,live_route=puzzle['live_route'][:-1],hint_routes={},offered_connections={})
                proposed['backtracks_used']=int(proposed.get('backtracks_used',0))+1
                proposed['current_actor']=proposed['live_route'][-1]['actor'] if proposed['live_route'] else proposed['start']
                proposed['hint_routes']={}
                # One back is always free. Every 10 Deep Cut points earned on the CURRENT
                # surviving route earns another free back. Rolled-back Deep Cuts no longer count.
                earned_deep,_=deep_cut_for_route(proposed['start']['id'],proposed['live_route'])
                free_backs=1+(earned_deep//10)
                penalty=max(0,int(proposed['backtracks_used'])-free_backs)*5
                puzzle.update(proposed)
                save_active_puzzles()
                return self.send_json({'ok':True,'route_revision':proposed['route_revision'],'degrees':len(proposed['live_route']),'current_actor':proposed['current_actor'],'backtracks_used':proposed['backtracks_used'],'free_backs':free_backs,'backtrack_penalty':penalty,'deep_cut_bank':earned_deep})
            if self.path=='/api/result':
                pid=str(body.get('puzzle_id','')); cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if puzzle.get('final_result') is not None:
                    return self.send_json(puzzle['final_result'])
                # Final scoring consumes only the server-owned route. Client-submitted route
                # data is intentionally ignored so browser state cannot manufacture a solve.
                verified=list(puzzle.get('live_route') or [])
                if len(verified)>6: return self.send_json({'error':'Route exceeds six degrees'},400)
                cur=str(puzzle['current_actor']['id'])
                solved=cur==str(puzzle['target']['id'])
                gave_up=bool(body.get('gave_up',False))
                exhausted=len(verified)>=6
                if not (solved or gave_up or exhausted):
                    return self.send_json({'error':'Round is still active'},409)
                comparison=puzzle['comparison_route']
                proven=puzzle.get('route_status')=='proven_shortest'
                deep_bonus, deep_details = deep_cut_for_route(puzzle['start']['id'],verified) if solved else (0,[])
                hints_used=min(2,max(0,int(puzzle.get('hints_used',0) or 0)))
                hint_penalty=0 if hints_used==0 else (10 if hints_used==1 else 20)
                quick_cut_bonus=max(0,(int(puzzle.get('cut',3))-len(verified))*25) if solved else 0
                free_backs=1+(deep_bonus//10)
                backtracks_used=int(puzzle.get('backtracks_used',0))
                backtrack_penalty=max(0,backtracks_used-free_backs)*5
                scoring_version=int(puzzle.get('scoring_version',2))
                points=score_for(len(verified),puzzle.get('cut',3),hints_used,deep_bonus,backtrack_penalty,scoring_version>=2) if solved else 0
                # The browser timer is display-only. Persist elapsed time from the server's
                # puzzle creation timestamp so a modified client cannot submit a fake time.
                elapsed=max(0.0, time.time()-float(puzzle.get('created',time.time())))
                result={'hints_enabled':puzzle.get('hints_enabled',True),'gave_up':gave_up,'solved':solved,'degrees':len(verified),'points':points,'cut':puzzle.get('cut',3),'cut_source':puzzle.get('cut_meta',{}).get('source','seed'),'cut_samples':puzzle.get('cut_meta',{}).get('samples',0),'quick_cut_bonus':quick_cut_bonus,'deep_cut_bonus':deep_bonus,'deep_cut_details':deep_details,'hint_penalty':hint_penalty,'hints_used':hints_used,'backtracks_used':backtracks_used,'free_backs':free_backs,'backtrack_penalty':backtrack_penalty,'elapsed_seconds':round(elapsed,3),'comparison_degrees':len(comparison) if comparison is not None else None,'comparison_route':comparison,'comparison_label':'Shortest verified route' if proven else 'Verified comparison route','shortest_proven':proven,'search_scope':puzzle.get('route_search',{}).get('scope','complete_demo_graph' if DEMO_MODE else 'adaptive_live_graph'),'search_stats':puzzle.get('route_search',{}).get('stats',{})}
                result['scoring_version']=scoring_version
                if scoring_version>=2 and solved and len(verified)==6 and hints_used:
                    result['scoring_note']='Six connections with hints: bonuses do not offset the hint penalty. Paid backtracks also subtract points.'
                if puzzle.get('challenge_benchmark') is not None:
                    result['challenge_outcome']=compare_challenge(result,puzzle['challenge_benchmark'])
                result['challenge_token']=create_challenge(pid,puzzle,result)
                save_game_result(pid,puzzle,verified,solved,gave_up,hints_used,deep_bonus,hint_penalty,points,elapsed,backtrack_penalty)
                puzzle['finished']=True
                puzzle['final_result']=result
                save_active_puzzles()
                return self.send_json(result)
            return self.send_json({'error':'Not found'},404)
        except Exception as e: return self.send_json({'error':str(e)},500)

if __name__=='__main__':
    port=int(os.environ.get('PORT','8787'))
    host=os.environ.get('HOST','0.0.0.0')
    print(f'Actor Connection listening on {host}:{port}')
    print('Data mode:', 'zero-setup demo' if DEMO_MODE else 'live movie database')
    print('Disk cache:', CACHE_DIR)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
