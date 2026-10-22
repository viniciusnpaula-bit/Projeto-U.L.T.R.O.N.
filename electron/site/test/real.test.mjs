import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { RealTransport } from '../src/real.js';

function makeBridge() {
  const calls = [];
  const bridge = {
    health: async () => ({ ok: true }),
    status: async () => ({ core_running: true, microphone_paused: false }),
    events: async () => ({ events: [{ type: 'notification', message: 'Pronto' }] }),
    command: async text => (calls.push(['command', text]), { operation_id: 'op-1' }),
    microphone: async paused => (calls.push(['microphone', paused]), { paused }),
    microphones: async () => ({ devices: [{ id: null, name: 'Padrão do sistema' }] }),
    selectMicrophone: async deviceId => (calls.push(['selectMicrophone', deviceId]), { selected_name: 'Webcam Mic' }),
    confirmation: async (...args) => (calls.push(['confirmation', ...args]), { accepted: true }),
    emergencyStop: async () => ({ stopped: true }),
    shutdown: async () => ({ shutdown_requested: true }),
  };
  return { bridge, calls };
}

test('transport uses only the named API bridge and maps current runtime events', async () => {
  const { bridge, calls } = makeBridge();
  const events = [];
  const transport = new RealTransport({ bridge, onEvent: event => events.push(event) });
  await transport.connect({ poll: false });
  assert.deepEqual(await transport.command('Olá'), { operation_id: 'op-1' });
  await transport.setMicrophonePaused(true);
  assert.equal((await transport.listMicrophones()).devices[0].name, 'Padrão do sistema');
  await transport.selectMicrophone('input-1');
  await transport.confirm('req-1', true, '1234');
  await transport.poll();
  assert.deepEqual(calls, [['command', 'Olá'], ['microphone', true], ['selectMicrophone', 'input-1'], ['confirmation', 'req-1', true, '1234']]);
  assert.ok(events.some(event => event.event === 'NOTIFICATION' && event.data.message === 'Pronto'));
  assert.ok(events.some(event => event.event === 'SYSTEM_STATUS'));
  transport.disconnect();
});

test('microphone settings reuse the secured core bridge and never create renderer capture', async () => {
  const site = new URL('../', import.meta.url);
  const app = await readFile(fileURLToPath(new URL('app.js', site)), 'utf8');
  const html = await readFile(fileURLToPath(new URL('index.html', site)), 'utf8');
  const main = await readFile(fileURLToPath(new URL('../main.js', site)), 'utf8');
  const preload = await readFile(fileURLToPath(new URL('../preload.js', site)), 'utf8');
  assert.match(html, /id="microphoneSelect"/);
  assert.match(html, /id="refreshMicrophones"/);
  assert.match(html, /id="saveMicrophone"/);
  assert.match(app, /transport\.listMicrophones\(\)/);
  assert.match(app, /transport\.selectMicrophone\(id \|\| null\)/);
  assert.doesNotMatch(app, /getUserMedia|SpeechRecognition/);
  assert.match(main, /isSender\(event, mainWindow\).*api\.selectMicrophone/s);
  assert.match(preload, /selectMicrophone: deviceId => ipcRenderer\.invoke\('api:microphone-device', deviceId\)/);
});

test('health failure stays offline and never enables a mock transport', async () => {
  const { bridge } = makeBridge();
  bridge.health = async () => { throw new Error('offline'); };
  const events = [];
  const transport = new RealTransport({ bridge, onEvent: event => events.push(event) });
  await assert.rejects(transport.connect({ poll: false }), /offline/);
  assert.ok(events.some(event => event.event === 'ULTRON_OFFLINE'));
  assert.equal(transport.mode, 'real');
});

test('desktop UI keeps PIN masked and removes manual credentials and microphone subprocesses', async () => {
  const site = new URL('../', import.meta.url);
  const app = await readFile(fileURLToPath(new URL('app.js', site)), 'utf8');
  const html = await readFile(fileURLToPath(new URL('index.html', site)), 'utf8');
  const css = await readFile(fileURLToPath(new URL('style.css', site)), 'utf8');
  assert.match(app, /pin\.type\s*=\s*'password'/);
  assert.match(app, /data\.requires_pin/);
  assert.match(app, /transport\.emergencyStop\(\)/);
  assert.doesNotMatch(app, /voiceListen|voiceSpeak|sessionStorage|MockTransport/);
  assert.doesNotMatch(html, /apiTokenInput|apiUrlInput|corePathInput/);
  assert.match(css, /--red:\s*#f3293f/i);
});

test('theme changes red accents without recoloring the ULTRON logo', async () => {
  const site = new URL('../', import.meta.url);
  const css = await readFile(fileURLToPath(new URL('style.css', site)), 'utf8');
  const html = await readFile(fileURLToPath(new URL('index.html', site)), 'utf8');
  assert.match(html, /<img class="brand-icon" src="icons\/ULTRON-Logo\.png"/);
  assert.match(css, /\.brand-icon\s*\{[^}]*object-fit:\s*cover/s);
  assert.doesNotMatch(css, /:root\[data-theme=.*?\.brand-icon/s);
  assert.match(css, /--red-bright:\s*color-mix\(in srgb, var\(--red\)/);
  assert.match(css, /\.header-clock b\s*\{[^}]*color:\s*var\(--red-bright\)/s);
  assert.match(css, /\.side-mic-toggle\s*\{[^}]*var\(--red-border\)/s);
  assert.match(css, /\.text-btn\s*\{[^}]*color:\s*var\(--red-bright\)/s);
  assert.match(css, /\.command-dock\s*>\s*div:first-child\s*\{[^}]*color:\s*var\(--red-bright\)/s);
  assert.match(css, /\.metric-card \.meter i\s*\{[^}]*var\(--red-soft\)/s);
});
