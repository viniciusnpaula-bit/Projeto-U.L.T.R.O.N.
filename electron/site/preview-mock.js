/* Pré-visualização local da interface: mock do núcleo para ver a tela no navegador.
   Não faz parte do app — o Electron injeta a ponte real (preload.js). */
const verbose = new URLSearchParams(location.search).has('live');
const agora = () => Date.now() / 1000;
const status = () => ({
  core_running: true, api_running: true,
  microphone_paused: false, microphone_capturing: true, microphone_state: 'ouvindo',
  microphone_threshold: 400, microphone_level: 180 + 220 * (0.5 + 0.5 * Math.sin(agora() * 1.7)),
  cpu_percent: 23, ram_percent: 58, disk_percent: 71,
  autostart_installed: true, speaking: false,
});
const fila = [];
window.ultron = {
  health: async () => ({ ok: true }),
  status: async () => status(),
  events: async () => ({ events: fila.splice(0) }),
  command: async text => {
    const id = `op-${Math.random().toString(36).slice(2, 8)}`;
    setTimeout(() => fila.push({
      type: 'command_result', operation_id: id,
      response: text.toLowerCase().includes('abr') ? 'Abrindo agora, senhor.' :
        'Às ordens. Registrei o comando e o núcleo respondeu no canal local.',
    }), 900);
    return { operation_id: id };
  },
  microphone: async paused => ({ paused }),
  conversation: async () => ({ turns: [] }),
  updateInfo: async () => ({ current_version: '1.9.4', auto_check: false, job: null }),
  updateCheck: async () => ({ status: 'ok', current_version: '1.9.4', latest_version: '1.9.4', update_available: false, notes: '' }),
  updateApply: async () => ({ status: 'baixando' }),
  updateLaunch: async () => true,
  updateRollback: async () => true,
  setZoom: async () => false,
  microphones: async () => ({
    devices: [{ id: null, name: 'Padrão do sistema' }, { id: '["WASAPI","Microfone USB",0]', name: 'Microfone USB' }],
    selected_id: null, selected_name: 'Padrão do sistema', selected_available: true, active_name: 'Padrão do sistema',
  }),
  selectMicrophone: async id => ({ selected_name: 'Microfone USB', active_name: 'Microfone USB' }),
  confirmation: async () => true,
  emergencyStop: async () => true,
  shutdown: async () => true,
  toggleHud: async () => true,
  publishHudSnapshot: async () => true,
  onHudVisibility: () => () => {},
  onHudAction: () => () => {},
  hudActionResult: () => {},
};
/* modo ?chat: simula uma conversa de voz chegando, para ver o bat-papo */
if (new URLSearchParams(location.search).has('chat')) {
  const falas = [
    ['user', 'Ei, Ultron, qual é a previsão do tempo para amanhã?'],
    ['assistant', 'Amanhã fica nublado pela manhã, com máxima de 27 graus e chance de chuva à tarde.'],
    ['user', 'Ative o modo jogo.'],
    ['assistant', 'Modo jogo ativado: janelas minimizadas e Rocket League aberto.'],
  ];
  /* mesma linha do tempo para todos, sem aleatoriedade */
  falas.forEach(([role, text], indice) => {
    setTimeout(() => fila.push({ type: 'conversation_turn', role, text, source: 'voz', at: Date.now() / 1000 }), 900 + indice * 1600);
  });
}
if (verbose) {
  /* cliques na prévia: um comando de exemplo após 1,2 s para ver a resposta chegando */
  setTimeout(() => {
    const form = document.getElementById('consoleForm');
    document.getElementById('commandInput').value = 'Ei, Ultron, abra o navegador';
    form.dispatchEvent(new Event('submit', { cancelable: true }));
  }, 1200);
  setTimeout(() => {
    document.querySelector('[data-command="Abra o Rocket League"]')?.click();
  }, 3600);
  setTimeout(() => document.getElementById('openSettings').click(), 5600);
}
