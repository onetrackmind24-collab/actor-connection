// Run: node tests/frontend_recovery.cjs
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const source = html.split('<script>')[1].split('</script>')[0];

function fixture() {
  const nodes = {};
  for (const match of html.matchAll(/id="([^"]+)"/g)) {
    nodes[match[1]] = {
      value: '', children: [], disabled: false,
      classList: {
        values: new Set(),
        add(...values) { values.forEach(value => this.values.add(value)); },
        remove(...values) { values.forEach(value => this.values.delete(value)); },
        contains(value) { return this.values.has(value); },
        toggle(value, on) { on ? this.add(value) : this.remove(value); },
      },
      attrs: {}, focus() {this.focused=true;}, scrollIntoView() {}, appendChild() {},
      setAttribute(name,value) {this.attrs[name]=value;}, removeAttribute(name) {delete this.attrs[name];},
    };
  }
  const context = {
    document: {getElementById: id => nodes[id], querySelectorAll: () => []},
    AbortController, setTimeout, clearTimeout,
    URL, URLSearchParams, location: {search: '',href:'https://actor-connection.onrender.com/?keep=yes#game'},
    history: {replaceState(state,title,url) {context.updatedUrl=url;}}, window: {scrollTo(){}},
    sessionStorage: {getItem: () => null, removeItem() { context.savedRoundCleared = true; }},
    clearedTimers: 0,
    clearInterval() { context.clearedTimers++; }, setInterval() { return 1; },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  vm.runInContext("puzzleId='test';start={id:1,name:'Start'};target={id:9,name:'Target'};current=start;route=[{actor:start,movie:null}]", context);
  return {nodes, context};
}

function snapshot(degrees, revision, backs = 0) {
  return {
    puzzle_id: 'test', difficulty: 'beginner', start: {id: 1, name: 'Start'},
    target: {id: 9, name: 'Target'}, current_actor: {id: degrees ? 2 : 1, name: degrees ? 'Next' : 'Start'},
    live_route: degrees ? [{movie: {id: 5, title: 'Film'}, actor: {id: 2, name: 'Next'}}] : [],
    degrees, route_revision: revision, hints_used: 0, free_backs: 1,
    backtracks_used: backs, elapsed_seconds: 10, hints_enabled: true,
  };
}
const response = data => ({ok: true, status: 200, json: async () => data});

async function run() {
  // One callback after a suspended tab must catch up rather than add one second.
  const clock=fixture();let now=10000,tick;
  clock.context.Date={now:()=>now};clock.context.setInterval=callback=>{tick=callback;return 1};
  clock.context.startRoundTimer(12.5);
  assert.equal(clock.nodes.time.textContent,'00:12');
  now+=90000;tick();assert.equal(clock.nodes.time.textContent,'01:42');
  clock.context.startRoundTimer(3);now+=2000;tick();
  assert.equal(clock.nodes.time.textContent,'00:05');
  // A failed challenge start must not leak its actor pair into a regular round.
  const failedStart=fixture();
  failedStart.context.location.href='https://actor-connection.onrender.com/?challenge=invitation&keep=yes#game';
  failedStart.context.performance={now:()=>0};
  failedStart.context.window.matchMedia=()=>({matches:true});
  failedStart.context.setTimeout=(callback,ms)=>ms>=30000?setTimeout(callback,ms):setImmediate(callback);
  failedStart.context.sessionStorage.setItem=()=>{};
  vm.runInContext("activeChallengeToken='invitation';challengeBenchmark={points:20}",failedStart.context);
  failedStart.nodes.noHints.disabled=true;
  failedStart.context.fetch=async()=>({ok:false,status:503,json:async()=>({error:'Temporary outage'})});
  await failedStart.context.begin('custom');
  assert.equal(failedStart.nodes.retryStart.classList.contains('hidden'),false);
  assert.equal(failedStart.nodes.difficultyOptions.classList.contains('hidden'),true);
  failedStart.context.fetch=async url=>{
    if(url==='/api/status')return response({ready:true});
    assert.equal(url,'/api/puzzle?challenge=invitation');
    return response({puzzle_id:'retried-challenge',difficulty:'custom',verified:true,start:{id:5,name:'Fresh'},target:{id:9,name:'Target'},hints_enabled:false});
  };
  await failedStart.nodes.retryStart.onclick();
  assert.equal(vm.runInContext('puzzleId',failedStart.context),'retried-challenge');
  assert.equal(failedStart.nodes.retryStart.classList.contains('hidden'),true);
  assert.equal(failedStart.nodes.hint1.classList.contains('hidden'),true);
  // Returning to the rules after another start failure clears the invitation.
  failedStart.context.fetch=async()=>({ok:false,status:503,json:async()=>({error:'Temporary outage'})});
  await failedStart.context.begin('custom');
  failedStart.nodes.backToRules.onclick();
  assert.equal(vm.runInContext('activeChallengeToken',failedStart.context),null);
  assert.equal(failedStart.nodes.noHints.disabled,false);
  assert.equal(failedStart.context.updatedUrl,'/?keep=yes#game');
  failedStart.context.fetch=async url=>{
    if(url==='/api/status')return response({ready:true});
    assert(url.startsWith('/api/puzzle?difficulty=beginner&hints='));
    assert(!url.includes('challenge='));
    return response({puzzle_id:'regular-after-failure',difficulty:'beginner',verified:true,start:{id:5,name:'Fresh'},target:{id:9,name:'Target'},hints_enabled:true});
  };
  await failedStart.context.begin('beginner');
  assert.equal(vm.runInContext('puzzleId',failedStart.context),'regular-after-failure');
  const custom=fixture();
  custom.nodes.customStart.value='Jack Nicholson';custom.nodes.customTarget.value='Gedde Watanabe';
  custom.nodes.customNoHints.checked=true;
  let customRequests=0,releaseCustom;
  custom.context.fetch=(url,options)=>{
    customRequests++;assert.equal(url,'/api/challenge/create');
    assert.deepEqual(JSON.parse(options.body),{mode:'challenge',start_name:'Jack Nicholson',target_name:'Gedde Watanabe',hints_enabled:false});
    return new Promise(resolve=>releaseCustom=resolve);
  };
  const creating=custom.nodes.createCustom.onclick();
  assert.equal(custom.nodes.createCustom.disabled,true);
  await custom.nodes.createCustom.onclick();assert.equal(customRequests,1);
  releaseCustom(response({start:{name:'Jack Nicholson'},target:{name:'Gedde Watanabe'},hints_enabled:false,url:'https://actor-connection.onrender.com/?challenge=custom'}));
  await creating;
  assert.equal(custom.nodes.createCustom.disabled,false);
  assert.match(custom.nodes.customPair.textContent,/Gedde Watanabe.*No hints/);
  assert.equal(custom.nodes.playCustom.attrs.href,custom.nodes.customLink.value);
  custom.context.fetch=async()=>({ok:false,status:422,json:async()=>({error:'Pair not verified'})});
  await custom.nodes.createCustom.onclick();
  assert.equal(custom.nodes.customStatus.textContent,'Pair not verified');
  assert.equal(custom.nodes.customReady.classList.contains('hidden'),true);
  custom.context.fetch=async()=>response({start:{name:'Start'},target:{name:'Target'},difficulty:'custom',hints_enabled:true,benchmark:null,scoring_version:2});
  await custom.context.loadChallenge('custom');
  assert.match(custom.nodes.challengeDetails.textContent,/Custom actor challenge/);
  assert.equal(custom.nodes.acceptChallenge.disabled,false);
  custom.context.fetch=async()=>response({start:{name:'Start'},target:null,target_hidden:true,difficulty:'custom',hints_enabled:true,benchmark:null,scoring_version:2});
  await custom.context.loadChallenge('launch');
  assert.equal(custom.nodes.challengeTitle.textContent,'Start → Hidden target');
  const hiddenShare=custom.context.shareSummary({solved:true,degrees:2,points:80,hints_used:0,target_hidden:true,challenge_token:'launch'});
  assert.match(hiddenShare,/Start → Hidden target/);
  assert.equal(hiddenShare.includes('→ Target'),false);
  const weekly=fixture();
  weekly.context.fetch=async()=>response({weekly_schedule:{name:'Matt Damon',rotation_enabled:true,
    next_name:'Tom Hanks',changes_at:'2026-10-12T00:00:00-04:00'}});
  await weekly.context.refreshWeeklyFeature();
  assert.match(weekly.nodes.weeklyFeature.textContent,/Matt Damon/);
  assert.match(weekly.nodes.weeklyLevel.textContent,/Tom Hanks — Oct 12 at midnight New York time/);
  let release;
  weekly.context.fetch=()=>new Promise(resolve=>release=resolve);
  const stale=weekly.context.refreshWeeklyFeature();
  weekly.context.fetch=async()=>response({weekly_schedule:{name:'Tom Hanks',rotation_enabled:false}});
  await weekly.context.refreshWeeklyFeature();
  release(response({weekly_schedule:{name:'Matt Damon',rotation_enabled:true,next_name:'Tom Hanks',changes_at:'2026-10-12T00:00:00-04:00'}}));
  await stale;
  assert.equal(weekly.nodes.weeklyFeature.textContent,'This week’s target: Tom Hanks.');
  weekly.context.fetch=async()=>response({weekly_schedule:null});
  await weekly.context.refreshWeeklyFeature();
  assert.equal(weekly.nodes.weeklyFeature.textContent,'');
  assert.equal(weekly.nodes.weeklyFeature.classList.contains('hidden'),true);
  weekly.context.fetch=async()=>{throw Error('offline')};
  await weekly.context.refreshWeeklyFeature();
  assert.equal(weekly.nodes.weeklyFeature.textContent,'');
  const {nodes, context} = fixture();
  let moveRequests = 0;
  context.fetch = async (url, options) => {
    if (url === '/api/move') {
      moveRequests++;
      assert.equal(JSON.parse(options.body).route_revision, 0);
      throw Error('response lost after server accepted move');
    }
    assert(url.startsWith('/api/round?'));
    return response(snapshot(1, 1));
  };
  await context.chooseMovie({id: 5, title: 'Film'});
  context.chooseActor({id: 2, name: 'Next'});
  await nodes.connect.onclick();
  assert.equal(moveRequests, 1);
  assert.equal(vm.runInContext('degree', context), 1);
  assert.equal(vm.runInContext('routeRevision', context), 1);
  assert.equal(vm.runInContext('route.length', context), 2);
  assert.equal(nodes.currentName.textContent, 'Next');
  assert.equal(nodes.connect.disabled, false);

  let backRequests = 0;
  context.fetch = async url => {
    if (url === '/api/backtrack') backRequests++;
    throw Error('network unavailable');
  };
  await nodes.back.onclick();
  assert.equal(backRequests, 1);
  for (const id of ['connect', 'back', 'hint1', 'hint2', 'giveUp']) assert.equal(nodes[id].disabled, true);
  assert.equal(nodes.retrySync.disabled, false);
  assert.equal(nodes.retrySync.classList.contains('hidden'), false);
  await nodes.back.onclick(); // Guard must ignore queued/programmatic retries, too.
  assert.equal(backRequests, 1);
  context.fetch = async url => {
    assert(url.startsWith('/api/round?'));
    return response(snapshot(0, 2, 1));
  };
  await nodes.retrySync.onclick();
  assert.equal(vm.runInContext('degree', context), 0);
  assert.equal(vm.runInContext('routeRevision', context), 2);
  assert.equal(nodes.retrySync.classList.contains('hidden'), true);
  assert.equal(nodes.connect.disabled, false);

  context.fetch = async url => {
    if (url.startsWith('/api/hint?')) {
      assert(url.includes('route_revision=2'));
      return {ok: false, status: 409, json: async () => ({error: 'Your round changed. Recover current progress before retrying.'})};
    }
    return response(snapshot(1, 3));
  };
  await nodes.hint2.onclick();
  assert.equal(vm.runInContext('routeRevision', context), 3);
  assert.equal(vm.runInContext('hints', context), 0);
  assert.equal(nodes.currentName.textContent, 'Next');
  // A lost hint response must recover charged usage without issuing another hint.
  for(const failure of ['network','invalid-json','server']){
    const level=failure==='network'?1:2;
    const f=fixture();let hintCalls=0,roundCalls=0;
    f.context.fetch=async url=>{
      if(url.startsWith('/api/hint?')){
        hintCalls++;
        if(failure==='server')return {ok:false,status:503,json:async()=>({error:'Temporary outage'})};
        if(failure==='invalid-json')return {ok:true,status:200,json:async()=>{throw Error('truncated JSON')}};
        throw Error('response lost');
      }
      assert(url.startsWith('/api/round?'));roundCalls++;
      return response({...snapshot(0,0),hints_used:level,free_backs:2});
    };
    await f.nodes['hint'+level].onclick();
    assert.equal(hintCalls,1);assert.equal(roundCalls,1);
    assert.equal(vm.runInContext('hints',f.context),level);
    assert.equal(vm.runInContext('freeBacks',f.context),2);
    assert.match(f.nodes.message.innerHTML,/saved hint usage/);
  }
  // Definite search failure adds no penalty and does not need a snapshot.
  {
    const f=fixture();let calls=0;
    f.context.fetch=async url=>{calls++;assert(url.startsWith('/api/hint?'));return {ok:false,status:404,json:async()=>({error:'No verified hint route found'})}};
    await f.nodes.hint1.onclick();assert.equal(calls,1);assert.equal(vm.runInContext('hints',f.context),0);
  }
  // If hint recovery also fails, block moves until the player recovers the round.
  {
    const f=fixture();f.context.fetch=async()=>{throw Error('offline')};
    await f.nodes.hint2.onclick();
    assert.equal(f.nodes.connect.disabled,true);assert.equal(f.nodes.retrySync.disabled,false);
    assert.equal(f.nodes.retrySync.classList.contains('hidden'),false);
  }
  vm.runInContext("activeChallengeToken='expired';challengeBenchmark={points:20}",context);
  nodes.difficultyOptions.classList.add('hidden');nodes.noHints.disabled=true;
  const previousClears = context.clearedTimers;
  context.fetch = async url => {
    if (url === '/api/backtrack') throw Error('request interrupted');
    return {ok: false, status: 404, json: async () => ({error: 'Puzzle expired or unknown'})};
  };
  await nodes.back.onclick();
  assert.equal(context.clearedTimers, previousClears + 1);
  assert.equal(context.savedRoundCleared, true);
  assert.equal(nodes.loadTitle.textContent, 'Choose your level');
  assert.equal(nodes.gameShell.classList.contains('hidden'), true);
  assert.equal(nodes.loading.classList.contains('hidden'), false);
  assert.equal(vm.runInContext('activeChallengeToken',context),null);
  assert.equal(nodes.difficultyOptions.classList.contains('hidden'),false);
  assert.equal(nodes.noHints.disabled,false);
  // A request can stall before headers or while reading the response body.
  for (const stalledBody of [false, true]) {
    const f = fixture();let fireDeadline;let deadlineCleared=false;
    f.context.setTimeout = callback => {fireDeadline=callback;return 123;};
    f.context.clearTimeout = id => {assert.equal(id,123);deadlineCleared=true;};
    f.context.fetch = async (url, options) => {
      const stalled = () => new Promise((resolve,reject) => {
        options.signal.addEventListener('abort',()=>reject(Error('aborted')));
      });
      if(stalledBody)return {ok:true,status:200,json:stalled};
      return stalled();
    };
    const request = f.context.get('/api/status');
    await new Promise(resolve=>setImmediate(resolve));fireDeadline();
    await assert.rejects(request,/took too long/);
    assert.equal(deadlineCleared,true);
  }
  // A stalled puzzle request releases the clapper and difficulty controls.
  {
    const f=fixture();const buttons=[{disabled:false}];let deadline;let puzzleRequests=0;
    f.context.document.querySelectorAll=()=>buttons;
    f.context.performance={now:()=>0};
    f.context.setTimeout=(callback,ms)=>{deadline=callback;return ms;};
    f.context.clearTimeout=()=>{};
    f.context.fetch=async(url,options)=>{
      if(url==='/api/status')return response({ready:true});
      puzzleRequests++;
      return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted'))));
    };
    const starting=f.context.begin('beginner');
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(buttons[0].disabled,true);
    assert.equal(f.nodes.backToRules.disabled,true);
    await f.context.begin('expert');
    assert.equal(puzzleRequests,1);
    deadline();await starting;
    assert.equal(buttons[0].disabled,false);
    assert.equal(f.nodes.backToRules.disabled,false);
    assert.equal(f.nodes.levelClapper.classList.contains('hidden'),true);
    assert.equal(vm.runInContext('startingRound',f.context),false);
    assert.equal(f.nodes.loadTitle.textContent,'Could not start game');
  }
  // Resume failures keep the saved round; an actual expiry clears it.
  const f=fixture();
  f.context.fetch=async()=>{throw Error('offline')};
  await f.context.resumeRound('saved');
  assert.notEqual(f.context.savedRoundCleared,true);
  assert.equal(f.nodes.loadTitle.textContent,'Could not restore your round');
  assert.equal(f.nodes.retryResume.classList.contains('hidden'),false);
  f.context.fetch=async url=>{assert.equal(url,'/api/round?puzzle_id=saved');return response(snapshot(1,3))};
  await f.nodes.retryResume.onclick();
  assert.equal(f.nodes.retryResume.classList.contains('hidden'),true);
  assert.equal(f.nodes.currentName.textContent,'Next');
  vm.runInContext("activeChallengeToken='expired'",f.context);
  f.nodes.difficultyOptions.classList.add('hidden');f.nodes.noHints.disabled=true;
  f.context.fetch=async()=>({ok:false,status:404,json:async()=>({error:'Puzzle expired or unknown'})});
  await f.context.resumeRound('saved');
  assert.equal(vm.runInContext('activeChallengeToken',f.context),null);
  assert.equal(f.nodes.difficultyOptions.classList.contains('hidden'),false);
  assert.equal(f.nodes.noHints.disabled,false);
  assert.equal(f.context.savedRoundCleared,true);
  assert.equal(f.nodes.loadTitle.textContent,'Choose your level');
  // Search failures must not look like an empty cast list.
  {
    const f=fixture();f.nodes.movieInput.value='Film';
    f.context.fetch=async()=>{throw Error('offline')};
    await f.nodes.movieInput.oninput();
    assert.match(f.nodes.message.innerHTML,/Movie search unavailable/);
    f.context.fetch=async()=>response([]);
    await f.nodes.movieInput.oninput();
    assert.match(f.nodes.message.innerHTML,/No matching eligible movie credits/);
    await f.context.chooseMovie({id:5,title:'Film'});
    f.nodes.actorInput.value='Performer';
    f.context.fetch=async()=>{throw Error('offline')};
    await f.nodes.actorInput.oninput();
    assert.match(f.nodes.message.innerHTML,/Actor search unavailable/);
  }
  // Keyboard choice and cancellation must agree with mouse choice and stale-request guards.
  {
    const f=fixture();let prevented=0;
    const key=value=>({key:value,preventDefault(){prevented++;}});
    f.context.showDrop(f.nodes.movieDrop,[{id:5,title:'First'},{id:6,title:'Second'}],'movie');
    f.nodes.movieInput.onkeydown(key('ArrowDown'));
    f.nodes.movieInput.onkeydown(key('ArrowDown'));
    f.nodes.movieInput.onkeydown(key('Enter'));
    assert.equal(vm.runInContext('selectedMovie.id',f.context),6);
    assert.equal(f.nodes.actorInput.disabled,false);
    assert.equal(f.nodes.movieInput.attrs['aria-expanded'],'false');
    f.context.showDrop(f.nodes.actorDrop,[{id:2,name:'Next'},{id:3,name:'Other'}],'actor');
    f.nodes.actorInput.onkeydown(key('ArrowUp'));
    f.nodes.actorInput.onkeydown(key('Enter'));
    assert.equal(vm.runInContext('selectedActor.id',f.context),3);
    assert.equal(f.nodes.actorInput.attrs['aria-expanded'],'false');
    assert.equal(prevented,5);
    let resolveSearch;
    f.context.fetch=()=>new Promise(resolve=>{resolveSearch=resolve;});
    f.nodes.movieInput.value='New query';
    const searching=f.nodes.movieInput.oninput();
    assert.equal(vm.runInContext('selectedActor',f.context),null);
    assert.equal(f.nodes.actorInput.disabled,true);
    assert.equal(f.nodes.actorInput.value,'');
    f.nodes.movieInput.onkeydown(key('Escape'));
    resolveSearch(response([{id:7,title:'Late suggestion'}]));await searching;
    assert.equal(f.nodes.movieDrop.classList.contains('hidden'),true);
    assert.equal(f.nodes.movieInput.attrs['aria-expanded'],'false');
    const searchingAgain=f.nodes.movieInput.oninput();
    await f.context.chooseMovie({id:8,title:'Chosen movie'});
    resolveSearch(response([{id:9,title:'Late movie'}]));await searchingAgain;
    assert.equal(vm.runInContext('selectedMovie.id',f.context),8);
    assert.equal(f.nodes.movieDrop.classList.contains('hidden'),true);
    f.nodes.actorInput.value='Actor';
    const actorSearching=f.nodes.actorInput.oninput();
    await f.context.chooseMovie({id:10,title:'Different film'});
    resolveSearch(response([{id:4,name:'Wrong film actor'}]));await actorSearching;
    assert.equal(vm.runInContext('selectedActor',f.context),null);
    assert.equal(f.nodes.actorDrop.classList.contains('hidden'),true);
  }
  // Completed rounds lock controls and New Game leaves challenge mode without reload.
  {
    const f=fixture();f.context.location.href='https://actor-connection.onrender.com/?challenge=old&keep=yes#game';
    vm.runInContext("seconds=123;activeChallengeToken='old';challengeBenchmark={points:20}",f.context);
    const result={solved:true,degrees:1,cut:3,points:100,hints_used:0,hint_penalty:0,backtracks_used:0,free_backs:1,backtrack_penalty:0,elapsed_seconds:0,comparison_route:[],comparison_degrees:1,challenge_token:'new'};
    await f.context.finishRound(true,false,result);
    assert.equal(vm.runInContext('roundFinished',f.context),true);
    assert.equal(f.nodes.resultTitle.focused,true);
    assert.match(f.nodes.resultText.innerHTML,/00:00/);
    assert.equal(f.nodes.connect.disabled,true);
    let requests=0;f.context.fetch=async()=>{requests++;throw Error('finished action should not run')};
    await f.nodes.back.onclick();assert.equal(requests,0);
    f.nodes.noHints.disabled=true;f.nodes.newGame.onclick();
    assert.equal(vm.runInContext('activeChallengeToken',f.context),null);
    assert.equal(vm.runInContext('challengeBenchmark',f.context),null);
    assert.equal(vm.runInContext('puzzleId',f.context),null);
    assert.equal(f.context.updatedUrl,'/?keep=yes#game');
    assert.equal(f.nodes.loading.classList.contains('hidden'),false);
    assert.equal(f.nodes.difficultyOptions.classList.contains('hidden'),false);
    assert.equal(f.nodes.result.classList.contains('hidden'),true);
    assert.equal(f.nodes.noHints.disabled,false);
    assert.equal(f.nodes.loadTitle.focused,true);
    f.context.performance={now:()=>0};f.context.window.matchMedia=()=>({matches:true});
    f.context.setTimeout=(callback,ms)=>ms>=30000?setTimeout(callback,ms):setImmediate(callback);
    f.context.sessionStorage.setItem=()=>{};
    f.context.fetch=async url=>{
      if(url==='/api/status')return response({ready:true});
      assert(url.startsWith('/api/puzzle?difficulty=beginner&hints='));
      assert(!url.includes('challenge='));
      return response({puzzle_id:'fresh',difficulty:'beginner',verified:true,start:{id:5,name:'Fresh'},target:{id:9,name:'Target'},hints_enabled:true});
    };
    await f.context.begin('beginner');
    assert.equal(vm.runInContext('puzzleId',f.context),'fresh');
    assert.equal(vm.runInContext('roundFinished',f.context),false);
    assert.equal(f.nodes.connect.disabled,false);
    assert.equal(f.nodes.back.disabled,false);
    assert.equal(f.nodes.movieInput.disabled,false);
    assert.equal(f.nodes.movieInput.focused,true);
    await f.context.finishRound(false,false,{...result,solved:false,degrees:6});
    assert.equal(f.nodes.resultTitle.textContent,'Six-connection limit reached');
  }
  console.log('PASS recovery, search/keyboard, completed-round locks and fresh-game replay');
}

run().catch(error => {console.error(error); process.exitCode = 1;});
