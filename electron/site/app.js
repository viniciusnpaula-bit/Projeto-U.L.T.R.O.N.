import { RealTransport } from './src/real.js';
import { criarOrbe, criarCampo, estadoDoOrbe } from './src/orb.js';

/* Uma tela só. Nada aqui inventa estado: tudo desenhado vem do núcleo. */
const $ = id => document.getElementById(id);
const hudActions = Object.freeze({
  browser: 'Abra o navegador', spotify: 'Abra o Spotify', media: 'Pause ou retome a música',
  volume: 'Aumente o volume do PC', rocket: 'Abra o Rocket League', game: 'Ative o modo jogo',
  minimize: 'Minimize tudo',
});
const THEMES = ['ultron', 'jarvis', 'amber', 'emerald'];
const state = {
  connected: false, paused: false, history: [], commands: new Map(),
  pending: null, status: {}, lastResponse: '', sessionCount: 0,
  turns: [],          // bat-papo de voz: {role, text, source, at}
  turnKeys: new Set(),
  writing: 0,         // turnos que vieram do campo de texto nesta sessão
};
const transport = new RealTransport({ onEvent: handleEvent });

/* ── cena ────────────────────────────────────────────────────────────────── */
const orb = criarOrbe($('orbCanvas'));
const campo = criarCampo($('field'));
const orbMem = {};
let orbTimer = null, orbBusy = false;
orb.iniciar();
campo.iniciar();

function aplicarEstado(status) {
  const e = estadoDoOrbe(status, orbMem, performance.now());
  orb.definir(e);
  $('stateWord').textContent = e.rotulo;
  $('stateHint').textContent = e.dica;
  $('chamber').dataset.state = e.rotulo.toLowerCase();
  if ($('orbState')) $('orbState').textContent = e.rotulo;
}
async function orbTick() {
  if (orbBusy) return;
  orbBusy = true;
  try { aplicarEstado(await window.ultron.status()); } catch { aplicarEstado(null); } finally { orbBusy = false; }
}
function orbLoop(on) {
  if (on && !orbTimer) { orbTimer = setInterval(orbTick, 220); orbTick(); }
  if (!on) { clearInterval(orbTimer); orbTimer = null; }
}

/* ── tema ────────────────────────────────────────────────────────────────── */
function applyTheme(theme) {
  const selected = THEMES.includes(theme) ? theme : 'ultron';
  document.documentElement.dataset.theme = selected;
  try { localStorage.setItem('ultron-theme', selected); } catch {}
  document.querySelectorAll('.swatch').forEach(node => node.setAttribute('aria-checked', String(node.dataset.theme === selected)));
  publishHudSnapshot();
}

/* ── HUD flutuante ───────────────────────────────────────────────────────── */
function publishHudSnapshot() {
  if (!window.ultron?.publishHudSnapshot) return;
  window.ultron.publishHudSnapshot({
    core: typeof state.status.core_running === 'boolean' ? (state.status.core_running ? 'Online' : 'Parado') : 'Indisponível',
    api: typeof state.status.api_running === 'boolean' ? (state.status.api_running ? 'Conectada' : 'Parada') : 'Indisponível',
    microphone: $('micVal')?.textContent || 'Indisponível',
    response: state.lastResponse || 'Indisponível',
    theme: document.documentElement.dataset.theme || 'ultron',
  }).catch(() => {});
}

/* ── utilidades ──────────────────────────────────────────────────────────── */
function toast(message) {
  const node = $('toast');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove('show'), 3200);
}

function hora() {
  return new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function setLed(id, status) {
  const node = $(id);
  if (!node) return;
  node.classList.remove('online', 'warn', 'error');
  if (status) node.classList.add(status);
}

function setMetric(name, value) {
  const node = $(name);
  if (node) node.textContent = value;
}

/* Fita de eventos: cada item tem horário, tipo e texto. Sem ícones decorativos. */
function fita(kind, text) {
  const list = $('tapeList');
  list.querySelector('.tape-empty')?.remove();
  const item = document.createElement('div');
  item.className = `tape-item ${kind}`;
  const time = document.createElement('time');
  time.textContent = hora();
  const body = document.createElement('p');
  body.textContent = String(text || '').slice(0, 400);
  item.append(time, body);
  list.append(item);
  while (list.children.length > 60) list.firstElementChild.remove();
  list.scrollTop = list.scrollHeight;
  state.sessionCount += 1;
  setMetric('sessionCount', String(state.sessionCount));
}

/* A resposta grande fica na câmara; a mesma frase entra na fita. */
function responder(text) {
  const node = $('responseText');
  const clean = String(text || '').trim();
  node.textContent = clean || 'O núcleo recebeu o comando.';
  node.classList.toggle('long', node.textContent.length > 220);
  const reply = $('reply');
  reply.classList.remove('arriving');
  void reply.offsetWidth;      // reinicia a animação de chegada
  reply.classList.add('arriving');
  state.lastResponse = clean.slice(0, 500);
  if ($('orbResponse')) $('orbResponse').textContent = node.textContent;
  publishHudSnapshot();
}

/* ── bat-papo de voz ─────────────────────────────────────────────────────── */

/* Identidade estável por turno: a API e o evento podem trazer a mesma fala. */
function chaveTurno(turno) {
  return `${turno.role}|${Math.round(Number(turno.at) || 0)}|${String(turno.text || '').slice(0, 40)}`;
}

function horaDe(segundos) {
  const d = Number(segundos) ? new Date(Number(segundos) * 1000) : new Date();
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function bolha(turno) {
  const usuario = turno.role === 'user';
  const item = document.createElement('article');
  item.className = `msg ${usuario ? 'user' : 'core'}`;
  item.dataset.key = chaveTurno(turno);

  const head = document.createElement('div');
  head.className = 'msg-head';
  const quem = document.createElement('span');
  quem.textContent = usuario ? (turno.source === 'texto' ? 'você · escrito' : 'você · voz') : 'ultron';
  const ponto = document.createElement('i');
  const time = document.createElement('time');
  time.textContent = horaDe(turno.at);
  head.append(quem, ponto, time);

  const corpo = document.createElement('p');
  corpo.textContent = String(turno.text || '');
  item.append(head, corpo);
  return item;
}

function adicionarTurno(turno, { fresh = true } = {}) {
  if (!turno || !turno.text || (turno.role !== 'user' && turno.role !== 'assistant')) return false;
  const key = chaveTurno(turno);
  if (state.turnKeys.has(key)) return false;
  state.turnKeys.add(key);
  state.turns.push(turno);
  if (state.turns.length > 120) state.turns.shift();

  const lista = $('commsList');
  $('commsEmpty')?.remove();
  const item = bolha(turno);
  if (fresh) item.classList.add('fresh');
  lista.append(item);
  while (lista.children.length > 120) lista.firstElementChild.remove();
  const perto = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 90;
  if (perto || turno.role === 'assistant') lista.scrollTop = lista.scrollHeight;
  $('commsCount').textContent = `${state.turns.length} ${state.turns.length === 1 ? 'fala' : 'falas'}`;
  return true;
}

function renderTurnos(turnos) {
  const lista = $('commsList');
  lista.replaceChildren();
  state.turns = [];
  state.turnKeys.clear();
  if (!turnos?.length) {
    const vazio = document.createElement('div');
    vazio.className = 'comms-empty';
    vazio.id = 'commsEmpty';
    vazio.innerHTML = '<b>Ainda não há conversa.</b><span>Diga “Ei, Ultron” — cada fala reconhecida e cada resposta aparecem aqui.</span>';
    lista.append(vazio);
    $('commsCount').textContent = '0 falas';
    return;
  }
  for (const turno of turnos) adicionarTurno(turno, { fresh: false });
  lista.scrollTop = lista.scrollHeight;
}

async function carregarConversa() {
  try {
    const dados = await transport.conversation();
    renderTurnos(dados?.turns || []);
  } catch { /* a API pode não ter a rota em versões antigas: a fita ainda mostra tudo */ }
}

/* ── relógio ─────────────────────────────────────────────────────────────── */
function updateClock() {
  const now = new Date();
  $('clockTime').textContent = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  $('clockDate').textContent = now.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' }).replace('.', '');
}

/* ── conexão ─────────────────────────────────────────────────────────────── */
function connection(online) {
  if (!online) { state.status.api_running = undefined; state.status.core_running = undefined; }
  state.connected = online && state.status.core_running === true && state.status.api_running === true;
  if ($('sideStatus')) $('sideStatus').textContent = online ? 'CONECTADO' : 'DESCONECTADO';
  if ($('sideInfo')) $('sideInfo').textContent = online ? 'API local autenticada' : 'API local indisponível';
  $('sideDot')?.classList.toggle('offline', !online);
  if ($('heroStatus')) $('heroStatus').textContent = online ? 'API CONECTADA' : 'AGUARDANDO CONEXÃO';
  if ($('systemBadge')) $('systemBadge').textContent = online ? 'API CONECTADA' : 'API INDISPONÍVEL';
  setLed('headerLed', online ? 'online' : 'error');
  publishHudSnapshot();
}

function updateStatus(data) {
  data = state.status = { ...state.status, ...data };
  state.connected = data.api_running === true && data.core_running === true;
  state.paused = data.microphone_paused === true;

  const mic = data.microphone_error ? 'erro' : state.paused ? 'pausado'
    : data.microphone_capturing ? 'capturando'
    : typeof data.microphone_state === 'string' && data.microphone_state ? data.microphone_state.toLowerCase()
    : 'indisponível';
  setMetric('micVal', mic);
  setMetric('coreVal', typeof data.core_running === 'boolean' ? (data.core_running ? 'Online' : 'Parado') : 'Indisponível');
  setMetric('apiVal', typeof data.api_running === 'boolean' ? (data.api_running ? 'Conectada' : 'Parada') : 'Indisponível');
  setMetric('apiServiceVal', $('apiVal').textContent);
  setMetric('systemMicVal', mic);
  setMetric('coreState', data.core_running === true ? 'OPERACIONAL' : data.core_running === false ? 'NÚCLEO PARADO' : 'DESCONHECIDO');
  setMetric('signalCoreText', $('coreVal').textContent);
  setMetric('autostartVal', typeof data.autostart_installed === 'boolean' ? (data.autostart_installed ? 'início automático ativo' : 'início automático desligado') : 'início —');
  if ($('authStatus') && data.api_running) $('authStatus').textContent = 'sessão autenticada';
  if ($('uptime')) $('uptime').textContent = data.core_running && data.api_running ? 'CORE + API ONLINE' : 'AGUARDANDO NÚCLEO';

  setLed('headerLed', state.connected ? 'online' : data.api_running === false ? 'error' : 'warn');
  setLed('coreLed', data.core_running === true ? 'online' : data.core_running === false ? 'error' : 'warn');
  setLed('apiLed', data.api_running === true ? 'online' : data.api_running === false ? 'error' : 'warn');
  setLed('voiceLed', data.microphone_error ? 'error' : state.paused ? 'warn' : data.microphone_capturing ? 'online' : 'warn');

  /* nível do microfone vira uma linha fina sob a linha de comando */
  const threshold = Number(data.microphone_threshold);
  const level = Number(data.microphone_level);
  const hasLevel = Number.isFinite(threshold) && threshold > 0 && Number.isFinite(level) && level >= 0;
  const percent = hasLevel ? Math.min(100, Math.round(level / threshold * 100)) : null;
  const bar = $('micLevelBar');
  const meter = $('micMeter');
  bar.style.width = `${percent ?? 0}%`;
  meter.classList.toggle('live', percent !== null && !state.paused);
  setMetric('micLevelVal', percent === null ? '—' : `${percent}%`);
  if ($('micDetail')) $('micDetail').textContent = data.microphone_error || (state.paused ? 'Escuta pausada' : data.microphone_capturing ? 'Capturando áudio' : data.microphone_state || 'indisponível');

  for (const [valueId, barId, value] of [['cpuVal', 'cpuBar', data.cpu_percent], ['ramVal', 'ramBar', data.ram_percent], ['diskVal', 'diskBar', data.disk_percent]]) {
    const n = value == null || !Number.isFinite(Number(value)) ? null : Math.max(0, Math.min(100, Number(value)));
    setMetric(valueId, n === null ? '—' : `${Math.round(n)}%`);
    const fill = $(barId);
    if (fill) fill.style.width = `${n ?? 0}%`;
  }

  const botao = $('micButton');
  const rotulo = $('micButtonLabel');
  botao.classList.toggle('active', !state.paused && Boolean(data.microphone_capturing));
  botao.setAttribute('aria-pressed', String(state.paused));
  botao.title = state.paused ? 'Retomar escuta contínua' : 'Pausar escuta contínua';
  botao.setAttribute('aria-label', botao.title);
  rotulo.textContent = state.paused ? 'pausado' : 'escutando';
  const live = $('commsLive');
  if (live) {
    const ativo = data.microphone_capturing && !state.paused && !data.microphone_error;
    live.classList.toggle('on', Boolean(ativo));
    live.textContent = ativo ? 'ao vivo' : state.paused ? 'pausado' : 'sem escuta';
    live.title = ativo ? 'Escuta contínua ativa' : state.paused ? 'Escuta pausada' : 'Microfone sem captura';
  }
  const voz = $('voiceStart');
  if (voz) voz.textContent = state.paused ? 'retomar escuta' : 'pausar escuta';
  setMetric('voicePageStatus', data.microphone_error || mic);

  if (state.pending === null) aplicarEstado(data);
  publishHudSnapshot();
}

/* ── confirmação de segurança ────────────────────────────────────────────── */
function confirmation(event) {
  state.pending = event.request_id;
  const data = event.data || {};
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  const modal = document.createElement('div');
  modal.className = 'modal';

  const label = document.createElement('span');
  label.className = 'eyebrow';
  label.textContent = 'o núcleo precisa da sua autorização';
  const title = document.createElement('h2');
  title.textContent = 'Autorizar ação?';
  const message = document.createElement('p');
  message.textContent = data.message || 'O núcleo solicita autorização para continuar.';
  const risk = document.createElement('p');
  risk.className = 'muted';
  risk.textContent = `risco ${String(data.risk || 'não informado').toLowerCase()}`;

  const actions = document.createElement('div');
  actions.className = 'modal-actions';
  const deny = document.createElement('button');
  deny.className = 'ghost';
  deny.textContent = 'cancelar';
  const approve = document.createElement('button');
  approve.className = 'solid';
  approve.textContent = 'confirmar ação';

  let pin = null;
  if (data.requires_pin) {
    const pinLabel = document.createElement('label');
    pinLabel.textContent = 'PIN de segurança';
    pin = document.createElement('input');
    pin.type = 'password';
    pin.autocomplete = 'off';
    pin.inputMode = 'numeric';
    pin.maxLength = 128;
    pinLabel.append(pin);
    modal.append(pinLabel);
  }

  const answer = async approved => {
    approve.disabled = deny.disabled = true;
    try { await transport.confirm(state.pending, approved, approved ? pin?.value : undefined); }
    catch (error) { toast(`Não foi possível registrar a confirmação: ${error.message}`); }
    backdrop.remove();
    state.pending = null;
  };
  deny.onclick = () => answer(false);
  approve.onclick = () => answer(true);
  modal.addEventListener('keydown', ev => { if (ev.key === 'Escape') answer(false); });

  actions.append(deny, approve);
  modal.prepend(label);
  modal.append(title, message, risk, actions);
  backdrop.append(modal);
  document.body.append(backdrop);
  (pin || approve).focus();
}

/* ── eventos do núcleo ───────────────────────────────────────────────────── */
function handleEvent(event) {
  if (event.event === 'ULTRON_ONLINE') {
    connection(true);
    aplicarEstado({ core_running: true, api_running: true });
  }
  if (event.event === 'ULTRON_OFFLINE') connection(false);
  if (event.event === 'SYSTEM_STATUS') updateStatus(event.data || {});
  if (event.event === 'NOTIFICATION') {
    const message = event.data.message || 'Notificação do núcleo.';
    if ($('activityText')) $('activityText').textContent = message;
    fita('notice', message);
  }
  if (event.event === 'CONVERSATION_TURN') {
    const turno = event.data || {};
    if (adicionarTurno({ role: turno.role, text: turno.text, source: turno.source || 'voz', at: turno.at || Date.now() / 1000 })) {
      fita(turno.role === 'user' ? 'user' : 'core', turno.text);
    }
  }
  if (event.event === 'CONFIRMATION_REQUIRED') confirmation(event);
  if (event.event === 'COMMAND_RESULT') {
    const command = state.commands.get(event.request_id) || 'comando por voz';
    state.commands.delete(event.request_id);
    const value = event.data?.response;
    const text = typeof value === 'string' && value ? value : 'O núcleo recebeu o comando.';
    responder(text);
    fita('core', text);
    const escrito = state.writing > 0;
    if (escrito) state.writing -= 1;
    if (escrito) adicionarTurno({ role: 'assistant', text, source: 'texto', at: Date.now() / 1000 });
  }
}

/* ── envio ───────────────────────────────────────────────────────────────── */
async function send(text) {
  text = String(text || '').trim();
  if (!text) return false;
  if (!state.connected) { toast('O núcleo está desconectado.'); fita('notice', 'Núcleo desconectado — comando não enviado.'); return false; }
  fita('user', text);
  state.writing += 1;
  adicionarTurno({ role: 'user', text, source: 'texto', at: Date.now() / 1000 });
  responder('Enviado. Aguardando o núcleo…');
  $('stateWord').textContent = 'PENSANDO';
  orb.definir({ rotulo: 'PENSANDO', energia: 0.5, brilho: 1, dica: 'Processando o comando…' });
  try {
    const result = await transport.command(text);
    state.commands.set(result.operation_id, text);
    return true;
  } catch (error) {
    responder(error.message);
    fita('notice', error.message);
    toast(error.message);
    aplicarEstado(state.status);
    return false;
  }
}

async function toggleMicrophone() {
  try {
    const result = await transport.setMicrophonePaused(!state.paused);
    state.paused = result.paused;
    updateStatus({ core_running: true, microphone_paused: state.paused, microphone_state: state.paused ? 'pausado' : 'ativo' });
    fita('notice', state.paused ? 'Escuta pausada.' : 'Escuta retomada. Diga “Ei, Ultron”.');
  } catch (error) { toast(`Não foi possível alterar o microfone: ${error.message}`); }
}

async function refreshMicrophones() {
  const select = $('microphoneSelect');
  const status = $('microphoneDeviceStatus');
  try {
    const result = await transport.listMicrophones();
    select.replaceChildren();
    if (!result.selected_available) {
      const missing = document.createElement('option');
      missing.value = '__missing__';
      missing.textContent = `indisponível — ${result.selected_name}`;
      select.append(missing);
    }
    for (const device of result.devices || []) {
      const option = document.createElement('option');
      option.value = device.id ?? '';
      option.textContent = device.name;
      select.append(option);
    }
    select.value = result.selected_available ? (result.selected_id ?? '') : '__missing__';
    status.textContent = result.selected_available
      ? `ativo: ${result.active_name || result.selected_name}`
      : `o microfone salvo (“${result.selected_name}”) não está conectado; escolha outra entrada.`;
  } catch (error) {
    status.textContent = `não foi possível listar as entradas: ${error.message}`;
  }
}

async function saveMicrophone() {
  const id = $('microphoneSelect').value;
  if (id === '__missing__') { toast('Escolha uma entrada disponível antes de aplicar.'); return; }
  $('saveMicrophone').disabled = true;
  try {
    const result = await transport.selectMicrophone(id || null);
    $('microphoneDeviceStatus').textContent = `ativo: ${result.active_name || result.selected_name}`;
    toast(`Microfone: ${result.selected_name}.`);
    await refreshMicrophones();
  } catch (error) {
    $('microphoneDeviceStatus').textContent = `não foi possível aplicar: ${error.message}`;
  } finally {
    $('saveMicrophone').disabled = false;
  }
}

async function refreshStatus(show = false) {
  try {
    const [health, status] = await Promise.all([window.ultron.health(), window.ultron.status()]);
    if (!health.ok || !status.core_running) throw new Error('Núcleo local indisponível.');
    connection(true);
    updateStatus(status);
    if (show) toast('Conexão com o núcleo confirmada.');
  } catch (error) {
    connection(false);
    if (show) toast(error.message);
  }
}

/* ── atualização pelo GitHub ─────────────────────────────────────────────── */
const updateUi = { job: null, timer: null, version: '1.9.4' };

function updateLinha(texto, classe = '') {
  const alvo = $('updateState');
  alvo.textContent = texto;
  alvo.className = classe;
}

function mostrarVersao(info) {
  if (!info) return;
  if (info.current_version) {
    updateUi.version = info.current_version;
    $('updateVersion').textContent = info.current_version;
  }
  const check = info.last_check;
  if (check?.available === false || check?.update_available === false) updateLinha('atualizado ✓', 'ok');
  else if (check?.update_available) updateLinha(`nova versão ${check.latest_version} disponível`, 'warn');
  else if (check?.status === 'sem_release') updateLinha('sem release no GitHub');
  else if (check?.status === 'erro') updateLinha(check.message || 'não foi possível verificar', 'err');
}

async function verificarAtualizacao(silencioso = false) {
  const botao = $('updateCheck');
  botao.disabled = true;
  if (!silencioso) updateLinha('consultando o GitHub…');
  try {
    const info = await window.ultron.updateCheck();
    mostrarVersao({ ...info, last_check: info });
    if (info.status === 'sem_release') updateLinha('ainda não há release publicado', 'warn');
    else if (info.status === 'erro') updateLinha(info.message || 'falha ao consultar', 'err');
    else if (info.update_available) {
      updateLinha(`versão ${info.latest_version} disponível (você tem ${info.current_version})`, 'warn');
      $('updateApply').hidden = false;
      $('updateApply').textContent = `Aplicar ${info.latest_version} e reiniciar`;
      if (info.notes) {
        $('updateNotes').hidden = false;
        $('updateNotes').textContent = info.notes;
      }
      if (!silencioso) toast(`Nova versão: ${info.latest_version}`);
    } else {
      updateLinha('você já está na versão mais recente ✓', 'ok');
      $('updateApply').hidden = true;
    }
  } catch (error) {
    updateLinha(`não foi possível verificar (${error.message})`, 'err');
  } finally {
    botao.disabled = false;
  }
}

function acompanharAtualizacao() {
  clearInterval(updateUi.timer);
  updateUi.timer = setInterval(async () => {
    try {
      const info = await window.ultron.updateInfo();
      const job = info?.job;
      if (!job || job.status === 'idle') return;
      updateUi.job = job;
      const pct = Number.isFinite(job.percent) ? ` ${job.percent}%` : '';
      if (job.status === 'baixando' || job.status === 'aplicando') {
        updateLinha(`${job.message || 'baixando'}${pct}`, 'warn');
        $('updateApply').disabled = true;
      } else if (job.status === 'pronto') {
        updateLinha(job.message || 'pronto para aplicar', 'ok');
        $('updateApply').hidden = false;
        $('updateApply').disabled = false;
        $('updateApply').textContent = 'Fechar e aplicar agora';
        $('updateRollback').hidden = false;
        clearInterval(updateUi.timer);
      } else if (job.status === 'erro') {
        updateLinha(job.message || 'falhou', 'err');
        $('updateApply').disabled = false;
        clearInterval(updateUi.timer);
      } else if (job.status === 'atualizado') {
        updateLinha(job.message || 'já está atualizado', 'ok');
        $('updateApply').hidden = true;
        clearInterval(updateUi.timer);
      }
    } catch { /* sem resposta do núcleo: o botão continua disponível */ }
  }, 1200);
}

async function aplicarAtualizacao() {
  const botao = $('updateApply');
  botao.disabled = true;
  // segunda etapa: o pacote já foi verificado e está em staging
  if (updateUi.job?.status === 'pronto') {
    updateLinha('aplicando e reiniciando…', 'warn');
    try { await window.ultron.updateLaunch(); }
    catch (error) { updateLinha(`falha ao aplicar: ${error.message}`, 'err'); botao.disabled = false; }
    return;
  }
  try {
    updateLinha('baixando e verificando o pacote…', 'warn');
    await window.ultron.updateApply(true);
    acompanharAtualizacao();
  } catch (error) {
    updateLinha(`falha ao baixar: ${error.message}`, 'err');
    botao.disabled = false;
  }
}

async function desfazerAtualizacao() {
  try {
    await window.ultron.updateRollback();
    updateLinha('backup restaurado ✓', 'ok');
    toast('Versão anterior restaurada.');
  } catch (error) {
    updateLinha(`não há backup para restaurar`, 'err');
  }
}

/* ── gaveta ──────────────────────────────────────────────────────────────── */
function drawer(open) {
  const painel = $('drawer');
  const fundo = $('drawerBackdrop');
  painel.hidden = !open;
  fundo.hidden = !open;
  painel.setAttribute('aria-hidden', String(!open));
  if (open) {
    refreshMicrophones();
    $('closeDrawer')?.focus();
  } else {
    $('openSettings')?.focus();
  }
}

/* Fecha por qualquer caminho: botão, fundo, Esc e canto superior direito. */
function fecharGaveta() { if (!$('drawer').hidden) drawer(false); }

/* ── ligação dos controles ───────────────────────────────────────────────── */
applyTheme((() => { try { return localStorage.getItem('ultron-theme') || 'ultron'; } catch { return 'ultron'; } })());
document.querySelectorAll('.swatch').forEach(node => node.onclick = () => applyTheme(node.dataset.theme));
document.querySelectorAll('[data-command]').forEach(button => button.onclick = () => send(button.dataset.command));

$('consoleForm').addEventListener('submit', event => {
  event.preventDefault();
  const input = $('commandInput');
  const text = input.value;
  input.value = '';
  send(text);
});
$('commandInput').addEventListener('keydown', event => {
  if (event.key === 'Escape') { event.target.value = ''; event.target.blur(); }
});
$('micButton').onclick = toggleMicrophone;
$('voiceStart').onclick = toggleMicrophone;
$('refreshMicrophones').onclick = () => refreshMicrophones();
$('saveMicrophone').onclick = saveMicrophone;
$('testConnection').onclick = () => refreshStatus(true);
$('updateCheck').onclick = () => verificarAtualizacao(false);
$('updateApply').onclick = aplicarAtualizacao;
$('updateRollback').onclick = desfazerAtualizacao;
$('scrollLatest').onclick = () => { const lista = $('commsList'); lista.scrollTop = lista.scrollHeight; };
$('clearHistory').onclick = () => {
  state.history = [];
  state.sessionCount = 0;
  renderTurnos([]);
  setMetric('sessionCount', '0');
  $('tapeList').replaceChildren(Object.assign(document.createElement('div'), {
    className: 'tape-empty',
    innerHTML: 'Nada ainda nesta sessão.<br><span>O que você disser aparece aqui.</span>',
  }));
  if ($('memoryList')) $('memoryList').replaceChildren();
  if ($('recentList')) $('recentList').replaceChildren();
  toast('Sessão limpa.');
};
$('openSettings').onclick = () => drawer(true);
$('closeDrawer').addEventListener('click', fecharGaveta);
$('drawerBackdrop').addEventListener('click', fecharGaveta);
$('drawerBackdrop').addEventListener('pointerdown', fecharGaveta);
/* a faixa .drawer::before cobre o canto: clicar nela fecha */
$('drawer').addEventListener('click', event => {
  const r = $('drawer').getBoundingClientRect();
  const pertoDoCanto = event.clientX > r.right - 96 && event.clientY < r.top + 96;
  if (pertoDoCanto && !event.target.closest('.drawer-close')) fecharGaveta();
});
/* botões com data-fechar (usados em blocos) também fecham */
document.querySelectorAll('[data-fechar]').forEach(botao => botao.addEventListener('click', fecharGaveta));
$('toggleHud').onclick = () => window.ultron.toggleHud();
window.ultron.onHudVisibility(visible => {
  $('toggleHud').textContent = visible ? 'fechar flutuante' : 'janela flutuante';
  $('toggleHud').title = visible ? 'Fechar painel flutuante' : 'Abrir painel flutuante';
});
window.ultron.onHudAction(async request => {
  if (!request || !Number.isSafeInteger(request.requestId) || !Object.hasOwn(hudActions, request.actionId)) return;
  $('commandInput').focus();
  window.ultron.hudActionResult(request.requestId, await send(hudActions[request.actionId]));
});
$('emergencyStopButton').onclick = async () => {
  if (!window.confirm('Acionar a parada de emergência do ULTRON?')) return;
  try { await transport.emergencyStop(); toast('Parada de emergência enviada ao núcleo.'); fita('notice', 'Parada de emergência acionada.'); }
  catch (error) { toast(`A parada de emergência falhou: ${error.message}`); }
};

/* atalhos: Ctrl+, ajustes · Ctrl+K foca a linha de comando · Esc fecha */
document.addEventListener('keydown', event => {
  if (event.ctrlKey && event.key === ',') { event.preventDefault(); drawer($('drawer').hidden); }
  if (event.ctrlKey && event.key.toLowerCase() === 'k') { event.preventDefault(); $('commandInput').focus(); }
  if (event.key === 'Escape') {
    if (!$('drawer').hidden) { event.preventDefault(); fecharGaveta(); }
  }
});

/* ── ciclo de vida ───────────────────────────────────────────────────────── */
updateClock();
setInterval(updateClock, 1000);
document.addEventListener('visibilitychange', () => orbLoop(!document.hidden));
window.addEventListener('beforeunload', () => { orb.parar(); campo.parar(); transport.disconnect(); });

(async () => {
  try { await transport.connect(); connection(true); }
  catch (error) { connection(false); toast(error.message); fita('notice', 'API local indisponível. Abra pelo ULTRON.exe.'); }
  orbLoop(true);
  carregarConversa();                       // falas que aconteceram antes do painel abrir
  window.ultron?.updateInfo?.().then(info => {
    mostrarVersao(info);
    // a verificação automática existia no estado salvo: mantém o comportamento
    if (info?.auto_check && document.visibilityState === 'visible') verificarAtualizacao(true);
  }).catch(() => {});
  setInterval(carregarConversa, 20000);     // reconcilia se algum evento se perder
  setInterval(() => refreshStatus(), 5000);
})();
