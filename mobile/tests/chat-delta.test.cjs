// Run with: node tests/chat-delta.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

test('recovered forward pages are drained and returned newest first', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/api/chatApi.ts'), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  const anchors = [];
  vm.runInNewContext(code, {
    exports,
    require(name) {
      if (name === '../security/inputValidation') return { MAX_MESSAGE_LENGTH: 2000 };
      if (name !== './client') throw new Error(`Unexpected dependency: ${name}`);
      return { apiGet: async (url, params) => {
        assert.equal(url, '/chats/chat1/messages');
        anchors.push(params.since_id);
        // Contract produced by recovery when the original anchor was pruned.
        const start = params.since_id === 'pruned' ? 1 : 51;
        return { success: true, data: {
          messages: Array.from({ length: 50 }, (_, i) => ({
            id: `m${start + i}`, chat_id: 'chat1', sender_id: 'A',
            message_type: 'text', content: String(start + i),
            created_at: '2026-09-24T00:00:00Z',
          })),
          has_more: start === 1,
          next_cursor: start === 1 ? 'm50' : null,
        } };
      } };
    },
  });
  const messages = await exports.getMessagesDelta('chat1', 'pruned');
  assert.deepEqual(anchors, ['pruned', 'm50']);
  assert.equal(messages.length, 100);
  assert.equal(new Set(messages.map(m => m.id)).size, 100);
  assert.equal(messages[0].id, 'm100');
  assert.equal(messages[99].id, 'm1');
});
