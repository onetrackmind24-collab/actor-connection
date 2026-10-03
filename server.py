#!/usr/bin/env python3
import json, os, time, urllib.parse, urllib.request, threading, secrets, datetime, sqlite3, statistics
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from collections import deque

ROOT=Path(__file__).resolve().parent
CACHE_DIR=ROOT/'cache'; CACHE_DIR.mkdir(exist_ok=True)
TMDB='https://api.themoviedb.org/3'
TOKEN=os.environ.get('TMDB_API_TOKEN','').strip()
TARGET_NAME=os.environ.get('WEEKLY_TARGET','Denzel Washington').strip()
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
ACTIVE_PUZZLES_FILE=ROOT/'active_puzzles.json'
TTL=60*60*24*30
PUZZLE_TTL=60*60*6
DEV_DIAGNOSTICS=os.environ.get('DEV_DIAGNOSTICS','').strip().lower() in {'1','true','yes'}
USED_STARTERS_FILE=ROOT/'used_starters.json'
ELIGIBILITY_FILE=ROOT/'eligibility_overrides.json'
RESULTS_DB=Path(os.environ.get('RESULTS_DB', str(ROOT/'game_results.sqlite3')))
RESULTS_LOCK=threading.Lock()


def load_active_puzzles():
    try:
        data=json.loads(ACTIVE_PUZZLES_FILE.read_text())
        if not isinstance(data,dict): return {}
        cutoff=time.time()-PUZZLE_TTL
        return {str(k):v for k,v in data.items() if isinstance(v,dict) and float(v.get('created',0))>=cutoff and not v.get('finished')}
    except Exception:
        return {}

def save_active_puzzles():
    # Atomic replace avoids leaving a half-written session file if the process stops mid-write.
    try:
        tmp=ACTIVE_PUZZLES_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(PUZZLES,separators=(',',':')))
        tmp.replace(ACTIVE_PUZZLES_FILE)
    except Exception:
        pass

# Active rounds survive a server restart during the six-hour puzzle window.
PUZZLES.update(load_active_puzzles())

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
    try:
        data=json.loads(ELIGIBILITY_FILE.read_text())
        return data if isinstance(data,dict) else {}
    except Exception:
        return {}

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

def learned_cut(difficulty,start_id,target_id):
    with sqlite3.connect(RESULTS_DB) as db:
        matchup=db.execute('SELECT degrees FROM game_results WHERE solved=1 AND start_id=? AND target_id=?',(str(start_id),str(target_id))).fetchall()
        if len(matchup) >= 10:
            return _median_cut(matchup), {'source':'matchup_median','samples':len(matchup)}
        cohort=db.execute('SELECT degrees FROM game_results WHERE solved=1 AND difficulty=?',(difficulty,)).fetchall()
        if len(cohort) >= 25:
            return _median_cut(cohort), {'source':'difficulty_median','samples':len(cohort)}
    seed={'beginner':2,'intermediate':3,'expert':3}.get(difficulty,3)
    return seed, {'source':'seed','samples':max(len(matchup),len(cohort))}

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
    # TMDB movie cast means an acting credit in a movie. It does NOT reliably
    # identify end-credit-only/cameo timing, so those edge cases require the
    # curated override file instead of pretending the provider proves them.
    return {'eligible':True,'reason':'provider_movie_cast'}

def eligible_cast(mid):
    return [a for a in cast(mid) if eligibility_for(mid,a)['eligible']]

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
}
DEMO_BY_ID={str(v['id']):v for v in DEMO_PEOPLE.values()}
DEMO_NAME_BY_ID={str(v['id']):k for k,v in DEMO_PEOPLE.items()}
DEMO_MODE=not bool(TOKEN)

def cache_file(key):
    safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in key)
    return CACHE_DIR/(safe+'.json')

def cached(key, loader):
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
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)

def person(name):
    if DEMO_MODE: return DEMO_PEOPLE.get(name,{})
    key='person_'+name.lower()
    def load():
        d=tmdb('/search/person',{'query':name,'include_adult':'false','language':'en-US','page':1})
        rows=[x for x in d.get('results',[]) if x.get('known_for_department')=='Acting'] or d.get('results',[])
        return rows[0] if rows else {}
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
        mid=str(m.get('id'))
        movie_cast=eligible_cast(mid)
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

def score_for(degrees, cut=3, hints_used=0, deep_cut_bonus=0):
    # The Cut is the expected competent-player route, not the mathematical shortest path.
    # Route efficiency stays primary; Deep Cut bonuses are capped so obscure detours cannot farm points.
    if degrees is None or degrees < 1 or degrees > 6: return 0
    base=max(25, 100 + (cut-degrees)*25)
    hint_penalty=0 if hints_used <= 0 else (10 if hints_used == 1 else 20)
    return max(0, base + min(25, max(0, deep_cut_bonus)) - hint_penalty)

def connection_deep_cut(movie, movie_cast, current_id, next_id):
    """Estimate how non-obvious a *connection* is, not how famous an actor is.

    This is deliberately conservative.  A buried credit in a less prominent/older movie can
    earn a Deep Cut, while a top-billed role in a famous movie normally earns nothing.
    The returned values are the game scale: 0 / 5 / 10 / 15.
    """
    by_id={str(a.get('id')):a for a in movie_cast}
    cur=by_id.get(str(current_id),{}); nxt=by_id.get(str(next_id),{})
    def billing(a):
        if a.get('order') is not None:
            try: return int(a.get('order'))
            except Exception: pass
        # Demo data is intentionally tiny and ordered by its bundled cast list.
        for i,x in enumerate(movie_cast):
            if str(x.get('id'))==str(a.get('id')): return i
        return 99
    buried=max(billing(cur), billing(nxt))
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
        details.append({'movie':step['movie']['title'],'actor':step['actor']['name'],'bonus':bonus})
        total += bonus; cur=nxt
    return min(25,total), details

def cut_for(difficulty, route, start_id=None, target_id=None):
    # The Cut is expected competent-player performance, not mathematical shortest path.
    if start_id is not None and target_id is not None:
        return learned_cut(difficulty,start_id,target_id)
    seed={'beginner':2, 'intermediate':3, 'expert':3}.get(difficulty,3)
    return seed, {'source':'seed','samples':0}

def live_candidate_catalog(max_pages=5):
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
                known_movies=[k for k in (x.get('known_for') or []) if k.get('media_type')=='movie']
                if len(known_movies) < 2 or not x.get('profile_path'): continue
                known_movies=[k for k in (x.get('known_for') or []) if k.get('media_type')=='movie']
                if not known_movies or not x.get('profile_path'): continue
                out.append({'id':x.get('id'),'name':x['name'],'profile_path':x.get('profile_path'),
                            'popularity':float(x.get('popularity') or 0),'known_for':known_movies})
        return out
    return cached(f'candidate_catalog_{max_pages}',load)

def candidate_names_for(difficulty):
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
    return [x['name'] for x in band if x['name']!=TARGET_NAME]

def generate_puzzle(difficulty='expert'):
    cleanup_puzzles()
    difficulty=(difficulty or 'expert').lower()
    if difficulty not in PUZZLE_CANDIDATES: difficulty='expert'
    target=person(TARGET_NAME)
    if not target: raise RuntimeError('Weekly target could not be loaded')
    names=candidate_names_for(difficulty)
    if not names: raise RuntimeError('No starting-actor candidates available')
    start_at=PUZZLE_CURSOR[difficulty] % len(names)
    # Rotate candidates, but serve only after a route is verified under the same graph rules.
    # Do not repeat a starting actor until the eligible pool for this difficulty is exhausted.
    # A short mathematical route does not disqualify Expert; recognizability is a separate concern.
    def eligible_route(candidate):
        if not candidate or str(candidate.get('id'))==str(target.get('id')): return None
        route,route_meta=find_path_with_meta(candidate.get('id'),target.get('id'),6)
        if route is None or not (1 <= len(route) <= 6): return None
        return route,route_meta

    ordered=[names[(start_at+i)%len(names)] for i in range(len(names))]
    fresh=[n for n in ordered if n not in USED_STARTERS]
    passes=[fresh, ordered] if fresh else [ordered]
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
                'created':time.time(),'difficulty':difficulty,
                'start':public_person(candidate),'target':public_person(target),
                'comparison_route':route,'route_status':route_status,'route_search':route_meta,
                'cut':cut,'cut_meta':cut_meta,'hints_used':0,'backtracks_used':0,
                'live_route':[], 'current_actor':public_person(candidate), 'finished':False
            }
            save_active_puzzles()
            return {
                'puzzle_id':puzzle_id,
                'difficulty':difficulty,
                'start':public_person(candidate),
                'target':public_person(target),
                'verified':True,
                # Answer data intentionally stays server-side until the round is submitted.
            }
    raise RuntimeError('No candidate in this difficulty pool passed the <=6 verification gate')

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        rel=urllib.parse.urlparse(path).path.lstrip('/') or 'index.html'
        return str(ROOT/rel)
    def send_json(self,obj,status=200):
        data=json.dumps(obj).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        try:
            if u.path=='/api/status': return self.send_json({'ready':True,'mode':'demo' if DEMO_MODE else 'live','cache_entries':len(list(CACHE_DIR.glob('*.json'))),'weekly_target':TARGET_NAME,'build':'2026-10-03-fix1','eligibility_overrides':sum(len(v) for v in ELIGIBILITY_OVERRIDES.values()),'results':result_stats()})
            if u.path=='/api/puzzle': return self.send_json(generate_puzzle(q.get('difficulty',['expert'])[0]))
            if u.path=='/api/person': return self.send_json(person(q.get('name',[''])[0]))
            if u.path=='/api/autocomplete/movies':
                pid=q.get('puzzle_id',[''])[0]; term=q.get('q',[''])[0].strip().lower()
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if not term: return self.send_json([])
                current=str(puzzle['current_actor']['id'])
                hits=[m for m in movies(current) if term in str(m.get('title','')).lower()]
                return self.send_json([{'id':m.get('id'),'title':m.get('title'),'release_date':m.get('release_date'),'poster_path':m.get('poster_path')} for m in hits[:12]])
            if u.path=='/api/autocomplete/actors':
                pid=q.get('puzzle_id',[''])[0]; mid=q.get('movie_id',[''])[0]; term=q.get('q',[''])[0].strip().lower()
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if not term or not mid: return self.send_json([])
                current=str(puzzle['current_actor']['id'])
                # Do not expose a cast for an arbitrary movie: it must be one of the current actor's credits.
                if mid not in {str(m.get('id')) for m in movies(current)}: return self.send_json([])
                hits=[a for a in eligible_cast(mid) if str(a.get('id'))!=current and term in str(a.get('name','')).lower()]
                return self.send_json([public_person(a) | {'character':a.get('character','')} for a in hits[:12]])
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
                depth=min(6,max(1,int(q.get('max',['6'])[0])))
                cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                a=str(puzzle['current_actor']['id'])
                # Cache the chosen route by current actor so Hint 1 and Hint 2 are guaranteed
                # to refer to the same route even if the graph/cache changes between clicks.
                hint_routes=puzzle.setdefault('hint_routes',{})
                path=hint_routes.get(a)
                if path is None:
                    path=find_path(a,str(puzzle['target']['id']),depth)
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
            return super().do_GET()
        except Exception as e: return self.send_json({'error':str(e)},500)
    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0')); body=json.loads(self.rfile.read(n) or b'{}')
            if self.path in {'/api/validate','/api/move'}:
                pid=str(body.get('puzzle_id','')); cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                # Legacy stateless validation remains available only when no puzzle is supplied.
                if not pid and self.path=='/api/validate':
                    current=str(body.get('current_actor_id','')); nxt=str(body.get('next_actor_id','')); mid=str(body.get('movie_id',''))
                    ids={str(x.get('id')) for x in eligible_cast(mid)}
                    return self.send_json({'valid': bool(current and nxt and current in ids and nxt in ids and current!=nxt)})
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if puzzle.get('finished'): return self.send_json({'error':'Round already finished'},409)
                current=str(puzzle['current_actor']['id']); nxt=str(body.get('next_actor_id','')); mid=str(body.get('movie_id',''))
                if len(puzzle['live_route'])>=6: return self.send_json({'error':'Six-degree limit reached'},409)
                ids={str(x.get('id')) for x in eligible_cast(mid)}
                if not(current and nxt and current in ids and nxt in ids and current!=nxt):
                    return self.send_json({'valid':False,'degrees':len(puzzle['live_route'])})
                m=next((x for x in movies(current) if str(x.get('id'))==mid),None)
                a=next((x for x in eligible_cast(mid) if str(x.get('id'))==nxt),None)
                step={'movie':{'id':m.get('id') if m else mid,'title':m.get('title') if m else body.get('movie_title','')},'actor':public_person(a or {'id':nxt,'name':body.get('actor_name','')})}
                puzzle['live_route'].append(step); puzzle['current_actor']=step['actor']; puzzle['hint_routes']={}
                degrees=len(puzzle['live_route']); solved=nxt==str(puzzle['target']['id']); remaining=max(0,6-degrees)
                # Early-failure detection: only declare a DEAD END when the search can actually
                # prove there is no finish inside the remaining moves. In demo mode the graph is
                # complete, so a failed BFS is proof. In live provider mode a failed bounded search
                # is only 'unknown' and must never be presented as a mathematical dead end.
                viability='solved' if solved else 'unknown'; finish_route=None
                if not solved and remaining>0:
                    finish_route,finish_meta=find_path_with_meta(nxt,str(puzzle['target']['id']),remaining)
                    if finish_route is not None:
                        viability='viable'
                    elif finish_meta.get('status')=='proven_shortest':
                        viability='dead_end'
                elif not solved and remaining==0:
                    viability='dead_end'
                puzzle['viability']=viability
                save_active_puzzles()
                return self.send_json({'valid':True,'degrees':degrees,'remaining':remaining,'current_actor':step['actor'],'solved':solved,'limit_reached':degrees>=6,'viability':viability,'dead_end':viability=='dead_end'})
            if self.path=='/api/backtrack':
                pid=str(body.get('puzzle_id','')); cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                if puzzle.get('finished'): return self.send_json({'error':'Round already finished'},409)
                if not puzzle['live_route']: return self.send_json({'error':'Already at starting actor'},409)
                puzzle['live_route'].pop()
                puzzle['backtracks_used']=int(puzzle.get('backtracks_used',0))+1
                puzzle['current_actor']=puzzle['live_route'][-1]['actor'] if puzzle['live_route'] else puzzle['start']
                puzzle['hint_routes']={}
                save_active_puzzles()
                # One back is always free. Every 10 Deep Cut points earned on the CURRENT
                # surviving route earns another free back. Rolled-back Deep Cuts no longer count.
                earned_deep,_=deep_cut_for_route(puzzle['start']['id'],puzzle['live_route'])
                free_backs=1+(earned_deep//10)
                penalty=max(0,int(puzzle['backtracks_used'])-free_backs)*5
                return self.send_json({'ok':True,'degrees':len(puzzle['live_route']),'current_actor':puzzle['current_actor'],'backtracks_used':puzzle['backtracks_used'],'free_backs':free_backs,'backtrack_penalty':penalty,'deep_cut_bank':earned_deep})
            if self.path=='/api/result':
                pid=str(body.get('puzzle_id','')); cleanup_puzzles(); puzzle=PUZZLES.get(pid)
                if not puzzle: return self.send_json({'error':'Puzzle expired or unknown'},404)
                # Final scoring consumes only the server-owned route. Client-submitted route
                # data is intentionally ignored so browser state cannot manufacture a solve.
                verified=list(puzzle.get('live_route') or [])
                if len(verified)>6: return self.send_json({'error':'Route exceeds six degrees'},400)
                cur=str(puzzle['current_actor']['id'])
                solved=cur==str(puzzle['target']['id'])
                gave_up=bool(body.get('gave_up',False))
                comparison=puzzle['comparison_route'] if (solved or gave_up) else None
                proven=puzzle.get('route_status')=='proven_shortest'
                deep_bonus, deep_details = deep_cut_for_route(puzzle['start']['id'],verified) if solved else (0,[])
                hints_used=min(2,max(0,int(puzzle.get('hints_used',0) or 0)))
                hint_penalty=0 if hints_used==0 else (10 if hints_used==1 else 20)
                free_backs=1+(deep_bonus//10)
                backtracks_used=int(puzzle.get('backtracks_used',0))
                backtrack_penalty=max(0,backtracks_used-free_backs)*5
                points=max(0,score_for(len(verified),puzzle.get('cut',3),hints_used,deep_bonus)-backtrack_penalty) if solved else 0
                # The browser timer is display-only. Persist elapsed time from the server's
                # puzzle creation timestamp so a modified client cannot submit a fake time.
                elapsed=max(0.0, time.time()-float(puzzle.get('created',time.time())))
                if solved or gave_up:
                    puzzle['finished']=True
                    save_game_result(pid,puzzle,verified,solved,gave_up,hints_used,deep_bonus,hint_penalty,points,elapsed,backtrack_penalty)
                    save_active_puzzles()
                return self.send_json({'solved':solved,'degrees':len(verified),'points':points,'cut':puzzle.get('cut',3),'cut_source':puzzle.get('cut_meta',{}).get('source','seed'),'cut_samples':puzzle.get('cut_meta',{}).get('samples',0),'deep_cut_bonus':deep_bonus,'deep_cut_details':deep_details,'hint_penalty':hint_penalty,'hints_used':hints_used,'backtracks_used':backtracks_used,'free_backs':free_backs,'backtrack_penalty':backtrack_penalty,'elapsed_seconds':round(elapsed,3),'comparison_degrees':len(comparison) if comparison is not None else None,'comparison_route':comparison,'comparison_label':'Shortest verified route' if proven else 'Verified comparison route','shortest_proven':proven,'search_scope':puzzle.get('route_search',{}).get('scope','complete_demo_graph' if DEMO_MODE else 'adaptive_live_graph'),'search_stats':puzzle.get('route_search',{}).get('stats',{})})
            return self.send_json({'error':'Not found'},404)
        except Exception as e: return self.send_json({'error':str(e)},500)

if __name__=='__main__':
    port=int(os.environ.get('PORT','8787'))
    host=os.environ.get('HOST','0.0.0.0')
    print(f'Actor Connection listening on {host}:{port}')
    print('Data mode:', 'zero-setup demo' if DEMO_MODE else 'live movie database')
    print('Disk cache:', CACHE_DIR)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
