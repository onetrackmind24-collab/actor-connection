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
      attrs: {}, focus() {}, scrollIntoView() {}, appendChild() {},
      setAttribute(name,value) {this.attrs[name]=value;}, removeAttribute(name) {delete this.attrs[name];},
    };
  }
  const context = {
    document: {getElementById: id => nodes[id], querySelectorAll: () => []},
    AbortController, setTimeout, clearTimeout,
    URLSearchParams, location: {search: ''},
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
  f.context.fetch=async()=>({ok:false,status:404,json:async()=>({error:'Puzzle expired or unknown'})});
  await f.context.resumeRound('saved');
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
  console.log('PASS recovery, deadlines, search feedback, keyboard selection and stale suggestions');
}

run().catch(error => {console.error(error); process.exitCode = 1;});
