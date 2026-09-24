// Run with: node tests/account-cache.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadCache() {
  const storage = new Map();
  const source = fs.readFileSync(path.join(__dirname, '../src/utils/cache.ts'), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports,
    require(name) {
      if (name === '@react-native-async-storage/async-storage') return { default: {
        getItem: async key => storage.get(key) ?? null,
        setItem: async (key, value) => { storage.set(key, value); },
        removeItem: async key => { storage.delete(key); },
      } };
      if (name === 'expo-image') return { Image: {} };
      throw new Error(`Unexpected dependency: ${name}`);
    },
  });
  return { ...exports, storage };
}

for (const kind of ['userProfile', 'feedDeck']) {
  test(`${kind}: switching accounts cannot read another account or legacy cache`, async () => {
    const c = loadCache();
    c.storage.set('@user_profile', JSON.stringify({ owner: 'legacy' }));
    c.storage.set('@feed_cards_v1', JSON.stringify({ owner: 'legacy' }));
    const accountAKey = c.CACHE_KEYS[kind]('A');
    const accountBKey = c.CACHE_KEYS[kind]('B');
    await c.cacheSet(accountAKey, { owner: 'A' });
    assert.equal(await c.cacheGet(accountBKey), null);
    await c.cacheSet(accountBKey, { owner: 'B' });
    // A request started by A completes after B has signed in.
    await c.cacheSet(accountAKey, { owner: 'A', delayed: true });
    assert.equal((await c.cacheGet(accountBKey)).owner, 'B');
    assert.equal((await c.cacheGet(accountAKey)).delayed, true);
  });
}

test('unknown account does not read or write a shared anonymous cache', async () => {
  const c = loadCache();
  for (const kind of ['userProfile', 'feedDeck']) {
    const key = c.CACHE_KEYS[kind](null);
    await c.cacheSet(key, { private: true });
    assert.equal(await c.cacheGet(key), null);
  }
  assert.equal(c.storage.size, 0);
});

test('conversation cache read/write/remove contract is preserved', async () => {
  const c = loadCache();
  const key = c.CACHE_KEYS.chatThread('chat1');
  await c.cacheSet(key, { messages: [{ id: 'm1' }] });
  assert.equal((await c.cacheGet(key)).messages[0].id, 'm1');
  await c.cacheRemove(key);
  assert.equal(await c.cacheGet(key), null);
});
