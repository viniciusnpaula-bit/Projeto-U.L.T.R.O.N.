const API_PREFIX = '/api/v1';
const REQUEST_TIMEOUT_MS = 12000;
const MAX_COMMAND_LENGTH = 4000;

function createApiClient({ baseUrl, token, fetchImpl = fetch }) {
  let url;
  try {
    url = new URL(baseUrl);
  } catch {
    throw new TypeError('URL da API local inválida.');
  }
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new TypeError('A API do ULTRON deve usar uma URL local válida.');
  }
  if (typeof token !== 'string' || token.length < 32 || typeof fetchImpl !== 'function') {
    throw new TypeError('Configuração da API local inválida.');
  }
  const origin = url.origin;

  async function request(method, route, data) {
    const controller = new AbortController();
    const headers = { Accept: 'application/json', 'X-ULTRON-Token': token };
    const init = { method, headers, signal: controller.signal };
    if (data !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(data);
    }
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetchImpl(`${origin}${API_PREFIX}${route}`, init);
      const raw = await response.text();
      let result;
      try {
        result = raw ? JSON.parse(raw) : {};
      } catch {
        throw new Error('Resposta inválida da API local.');
      }
      if (!response.ok) {
        throw new Error(`A API local recusou a solicitação (${response.status}).`);
      }
      return result;
    } catch (error) {
      if (error.message.startsWith('A API local recusou') ||
          error.message === 'Resposta inválida da API local.') throw error;
      if (error.name === 'AbortError') throw new Error('Tempo limite da API local excedido.');
      throw new Error('Não foi possível conectar à API local.');
    } finally {
      clearTimeout(timer);
    }
  }

  return Object.freeze({
    health: () => request('GET', '/health'),
    status: () => request('GET', '/status'),
    events: () => request('GET', '/events'),
    updateInfo: () => request('GET', '/update'),
    updateCheck: () => request('GET', '/update/check'),
    updateApply: restartAfter => request('POST', '/update/apply', { restart_after: restartAfter === true }),
    updateLaunch: () => request('POST', '/update/launch', {}),
    updateRollback: () => request('POST', '/update/rollback', {}),
    command: text => {
      if (typeof text !== 'string' || !text.trim() || text.length > MAX_COMMAND_LENGTH) {
        throw new TypeError('O comando deve conter de 1 a 4000 caracteres.');
      }
      return request('POST', '/commands', { text });
    },
    microphone: paused => {
      if (typeof paused !== 'boolean') throw new TypeError('Estado do microfone inválido.');
      return request('POST', '/microphone', { paused });
    },
    conversation: () => request('GET', '/conversation'),
    microphones: () => request('GET', '/microphones'),
    selectMicrophone: deviceId => {
      if (deviceId !== null && (typeof deviceId !== 'string' || deviceId.length > 512)) {
        throw new TypeError('Dispositivo de microfone inválido.');
      }
      return request('POST', '/microphone/device', { device_id: deviceId });
    },
    confirmation: (requestId, approved, pin) => {
      if (typeof requestId !== 'string' || !requestId || typeof approved !== 'boolean' ||
          (pin !== undefined && typeof pin !== 'string')) {
        throw new TypeError('Resposta de confirmação inválida.');
      }
      const body = { request_id: requestId, approved };
      if (pin !== undefined) body.pin = pin;
      return request('POST', '/confirmations', body);
    },
    emergencyStop: () => request('POST', '/emergency-stop', {}),
    shutdown: () => request('POST', '/shutdown', {}),
  });
}

module.exports = { createApiClient };
