const test = require('node:test');
const assert = require('node:assert/strict');
const { createApiClient } = require('../api');

const TOKEN = 't'.repeat(48);

test('named API actions call only the current ULTRON routes with the run token', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return Response.json({ ok: true });
  };
  const api = createApiClient({
    baseUrl: 'http://127.0.0.1:43873', token: TOKEN, fetchImpl,
  });

  await api.health();
  await api.status();
  await api.events();
  await api.command('olá');
  await api.microphone(true);
  await api.confirmation('request-1', true, '1234');
  await api.emergencyStop();
  await api.shutdown();

  assert.deepEqual(calls.map(({ url, init }) => [url, init.method, init.body || null]), [
    ['http://127.0.0.1:43873/api/v1/health', 'GET', null],
    ['http://127.0.0.1:43873/api/v1/status', 'GET', null],
    ['http://127.0.0.1:43873/api/v1/events', 'GET', null],
    ['http://127.0.0.1:43873/api/v1/commands', 'POST', '{"text":"olá"}'],
    ['http://127.0.0.1:43873/api/v1/microphone', 'POST', '{"paused":true}'],
    ['http://127.0.0.1:43873/api/v1/confirmations', 'POST',
      '{"request_id":"request-1","approved":true,"pin":"1234"}'],
    ['http://127.0.0.1:43873/api/v1/emergency-stop', 'POST', '{}'],
    ['http://127.0.0.1:43873/api/v1/shutdown', 'POST', '{}'],
  ]);
  for (const { init } of calls) {
    assert.equal(init.headers['X-ULTRON-Token'], TOKEN);
    assert.ok(init.signal instanceof AbortSignal);
  }
  assert.equal('request' in api, false);
});

test('API client rejects non-loopback configuration and malformed inputs', async () => {
  assert.throws(() => createApiClient({ baseUrl: 'http://0.0.0.0:8000', token: TOKEN }));
  assert.throws(() => createApiClient({ baseUrl: 'http://127.0.0.1:8000', token: 'short' }));
  const api = createApiClient({
    baseUrl: 'http://127.0.0.1:43873', token: TOKEN,
    fetchImpl: async () => Response.json({ ok: true }),
  });
  assert.throws(() => api.command('x'.repeat(4001)));
  assert.throws(() => api.microphone('yes'));
  assert.throws(() => api.confirmation('', true));
});

test('API transport errors never expose the run token', async () => {
  const api = createApiClient({
    baseUrl: 'http://127.0.0.1:43873', token: TOKEN,
    fetchImpl: async () => { throw new Error(`connection failed: ${TOKEN}`); },
  });
  await assert.rejects(api.status(), error => !error.message.includes(TOKEN));
});
