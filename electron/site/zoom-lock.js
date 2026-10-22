// Zoom da interface: DESLIGADO por padrão.
//
// A câmara do ULTRON é desenhada para 100% (núcleo em canvas, colunas fixas).
// Aqui fechamos todas as portas do zoom do Chromium:
//   * Ctrl + roda / Ctrl + "+" / Ctrl + "-" / Ctrl + "0" viram no-op;
//   * o fator de zoom é reafirmado a cada carregamento (o Electron guarda o último
//     por origem — um Ctrl+roda esquecido reabria a janela ampliada);
//   * o main process também chama setZoomFactor(1) e limita o visual zoom a 1.
//
// Para reativar no futuro (ex.: acessibilidade): `window.ultron.setZoom(true)`
// libera o menu de zoom e o Ctrl+roda; o usuário pode então escolher o tamanho.
(() => {
  const ZOOM_KEYS = new Set(['+', '=', '-', '_', '0']);
  let zoomsEnabled = false;

  function travarZooms() {
    const webFrame = window.require?.('electron')?.webFrame;
    if (webFrame) webFrame.setZoomFactor(1);
    document.documentElement.style.zoom = '';
  }

  // 1) teclado: Ctrl/Cmd + (+ - 0) nunca chegam ao Chromium
  window.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    if (ZOOM_KEYS.has(event.key)) {
      if (zoomsEnabled && event.key === '0') return;   // voltar a 100% é permitido
      event.preventDefault();
      event.stopPropagation();
      if (!zoomsEnabled) travarZooms();
    }
  }, { capture: true });

  // 2) roda do mouse com Ctrl (pinch em trackpad também chega como ctrl+wheel)
  window.addEventListener('wheel', event => {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      if (!zoomsEnabled) travarZooms();
    }
  }, { passive: false, capture: true });

  // 3) gesto de pinça no trackpad (mais confiável em alguns drivers)
  document.addEventListener('gesturestart', event => { if (!zoomsEnabled) event.preventDefault(); });
  document.addEventListener('gesturechange', event => { if (!zoomsEnabled) event.preventDefault(); });

  // 4) o menu de contexto do Chromium permite "recarregar" mas nunca ampliar
  window.addEventListener('contextmenu', event => {
    if (event.ctrlKey) event.preventDefault();
  });

  // 5) reafirma 100% ao carregar e ao voltar o foco (fator persistido pelo Electron)
  window.addEventListener('DOMContentLoaded', travarZooms);
  window.addEventListener('focus', () => { if (!zoomsEnabled) travarZooms(); });

  // 6) ponte para o main process
  window.ultron?.setZoom?.(false).catch?.(() => {});
  window.setUltronZoom = enabled => {
    zoomsEnabled = enabled === true;
    window.ultron?.setZoom?.(zoomsEnabled).catch?.(() => {});
    if (!zoomsEnabled) travarZooms();
    return zoomsEnabled;
  };
})();
