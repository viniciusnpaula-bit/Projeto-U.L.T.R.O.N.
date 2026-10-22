const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { app, BrowserWindow, ipcMain, screen } = require('electron');
const { createApiClient } = require('./api');

const api = createApiClient({ baseUrl: process.env.ULTRON_API_URL, token: process.env.ULTRON_API_TOKEN });
const quickActions = Object.freeze({
  browser: 'Abra o navegador', spotify: 'Abra o Spotify', media: 'Pause ou retome a música',
  volume: 'Aumente o volume do PC', rocket: 'Abra o Rocket League', game: 'Ative o modo jogo', minimize: 'Minimize tudo',
});
let mainWindow;
let miniWindow;
let lastHudSnapshot = null;
let nextActionRequest = 0;
const pendingActions = new Map();
let quitting = false;
let zoomsEnabled = false;

function isSender(event, window) {
  return Boolean(window && !window.isDestroyed() && event.sender === window.webContents &&
    (!event.senderFrame || event.senderFrame === window.webContents.mainFrame));
}

function registerApiHandlers() {
  const methods = {
    'api:health': () => api.health(), 'api:status': () => api.status(), 'api:events': () => api.events(),
    'api:conversation': () => api.conversation(),
    'api:command': (_event, text) => api.command(text), 'api:microphone': (_event, paused) => api.microphone(paused),
    'api:confirmation': (_event, requestId, approved, pin) => api.confirmation(requestId, approved, pin),
    'api:emergency-stop': () => api.emergencyStop(), 'api:shutdown': () => api.shutdown(),
  };
  for (const [channel, handler] of Object.entries(methods)) ipcMain.handle(channel, handler);
  ipcMain.handle('api:microphones', event => {
    if (!isSender(event, mainWindow)) throw new TypeError('Janela do ULTRON inválida.');
    return api.microphones();
  });
  ipcMain.handle('api:microphone-device', (event, deviceId) => {
    if (!isSender(event, mainWindow) || (deviceId !== null && typeof deviceId !== 'string')) {
      throw new TypeError('Solicitação de microfone inválida.');
    }
    return api.selectMicrophone(deviceId);
  });

  // zoom desligado de propósito: a interface é desenhada para 100% e o Electron
  // reabre sempre com o último fator de zoom aplicado.
  ipcMain.handle('view:zoom', (event, enabled) => {
    if (!isSender(event, mainWindow)) return false;
    zoomsEnabled = enabled === true;
    if (!zoomsEnabled && mainWindow) {
      mainWindow.webContents.setZoomFactor(1);
      mainWindow.webContents.setZoomLevel(0);
    }
    if (mainWindow) mainWindow.webContents.setVisualZoomLevelLimits(1, 1);
    return zoomsEnabled;
  });

  ipcMain.handle('update:info', event => {
    if (!isSender(event, mainWindow)) return null;
    return api.updateInfo();
  });
  ipcMain.handle('update:check', event => {
    if (!isSender(event, mainWindow)) return null;
    return api.updateCheck();
  });
  ipcMain.handle('update:apply', (event, restartAfter) => {
    if (!isSender(event, mainWindow)) return null;
    return api.updateApply(restartAfter === true);
  });
  ipcMain.handle('update:launch', async event => {
    if (!isSender(event, mainWindow)) return false;
    const launched = await api.updateLaunch();
    if (launched) setTimeout(() => app.quit(), 400);
    return launched === true;
  });
  ipcMain.handle('update:rollback', event => {
    if (!isSender(event, mainWindow)) return false;
    return api.updateRollback();
  });

  ipcMain.handle('hud:toggle', event => {
    if (!isSender(event, mainWindow)) return false;
    if (miniWindow && !miniWindow.isDestroyed()) { miniWindow.close(); return false; }
    createMiniWindow();
    return true;
  });
  ipcMain.handle('hud:snapshot', event => isSender(event, miniWindow) ? lastHudSnapshot : null);
  ipcMain.handle('hud:publish', (event, snapshot) => {
    if (!isSender(event, mainWindow) || !snapshot || typeof snapshot !== 'object') return false;
    const theme = ['ultron', 'jarvis', 'amber', 'emerald'].includes(snapshot.theme) ? snapshot.theme : 'ultron';
    const clean = value => typeof value === 'string' ? value.slice(0, 500) : 'Indisponível';
    lastHudSnapshot = Object.freeze({ core: clean(snapshot.core), api: clean(snapshot.api), microphone: clean(snapshot.microphone), response: clean(snapshot.response), theme });
    if (miniWindow && !miniWindow.isDestroyed()) miniWindow.webContents.send('hud:snapshot', lastHudSnapshot);
    return true;
  });
  ipcMain.handle('hud:return', event => {
    if (!isSender(event, miniWindow)) return false;
    miniWindow.close();
    if (mainWindow && !mainWindow.isDestroyed()) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.show(); mainWindow.focus(); }
    return true;
  });
  ipcMain.handle('hud:action', async (event, actionId) => {
    if (!isSender(event, miniWindow) || !Object.hasOwn(quickActions, actionId) || !mainWindow || mainWindow.isDestroyed()) return false;
    const requestId = ++nextActionRequest;
    return new Promise(resolve => {
      const timeout = setTimeout(() => { pendingActions.delete(requestId); resolve(false); }, 15000);
      pendingActions.set(requestId, accepted => { clearTimeout(timeout); pendingActions.delete(requestId); resolve(accepted === true); });
      mainWindow.webContents.send('hud:run-action', { requestId, actionId });
    });
  });
  ipcMain.on('hud:action-result', (event, requestId, accepted) => {
    if (!isSender(event, mainWindow) || !Number.isSafeInteger(requestId)) return;
    pendingActions.get(requestId)?.(accepted);
  });
}

function secureLocalWindow(window, file) {
  window.webContents.on('will-navigate', (event, url) => {
    if (url !== pathToFileURL(file).href) event.preventDefault();
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
}

function createMiniWindow() {
  if (miniWindow && !miniWindow.isDestroyed()) { miniWindow.show(); miniWindow.focus(); return miniWindow; }
  const file = path.join(__dirname, 'site', 'mini-hud.html');
  const area = screen.getPrimaryDisplay().workArea;
  const width = Math.min(390, area.width);
  const height = Math.min(650, area.height);
  miniWindow = new BrowserWindow({
    width, height, x: area.x + area.width - width - 18, y: area.y + 18,
    minWidth: width, maxWidth: width, minHeight: Math.min(420, height), maxHeight: height,
    frame: false, resizable: false, alwaysOnTop: true, skipTaskbar: true,
    backgroundColor: '#07080b', autoHideMenuBar: true, icon: path.join(__dirname, 'assets', 'ULTRON.ico'),
    webPreferences: { preload: path.join(__dirname, 'mini-preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  secureLocalWindow(miniWindow, file);
  miniWindow.on('closed', () => {
    miniWindow = null;
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('hud:visibility', false);
  });
  miniWindow.loadFile(file);
  miniWindow.webContents.once('did-finish-load', () => {
    miniWindow?.webContents.send('hud:snapshot', lastHudSnapshot);
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('hud:visibility', true);
  });
  return miniWindow;
}

function createWindow() {
  const indexFile = path.join(__dirname, 'site', 'index.html');
  mainWindow = new BrowserWindow({
    width: 1440, height: 900, minWidth: 980, minHeight: 640, backgroundColor: '#05070d', autoHideMenuBar: true,
    icon: path.join(__dirname, 'assets', 'ULTRON.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'), contextIsolation: true,
      sandbox: true, nodeIntegration: false, zoomFactor: 1,
    },
  });
  secureLocalWindow(mainWindow, indexFile);
  mainWindow.on('close', event => {
    if (!quitting && miniWindow && !miniWindow.isDestroyed()) { event.preventDefault(); mainWindow.hide(); }
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  mainWindow.loadFile(indexFile);
}

app.whenReady().then(() => {
  app.setAppUserModelId('com.ultron.desktop');
  registerApiHandlers();
  createWindow();
  app.on('before-quit', () => { quitting = true; });
  app.on('activate', () => {
    if (mainWindow && !mainWindow.isDestroyed()) { mainWindow.show(); mainWindow.focus(); }
    else createWindow();
  });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
