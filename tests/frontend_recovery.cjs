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
      focus() {}, scrollIntoView() {}, appendChild() {}, setAttribute() {},
    };
  }
  const context = {
    document: {getElementById: id => nodes[id], querySelectorAll: () => []},
    URLSearchParams, location: {search: ''},
    sessionStorage: {getItem: () => null, removeItem() {}},
    clearInterval() {}, setInterval() { return 1; },
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
  console.log('PASS dropped move recovery, failed back recovery, blocked retries and stale hint recovery');
}

run().catch(error => {console.error(error); process.exitCode = 1;});
