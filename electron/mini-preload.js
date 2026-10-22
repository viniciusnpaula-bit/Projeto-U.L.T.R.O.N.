const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ultron', Object.freeze({
  getHudSnapshot: () => ipcRenderer.invoke('hud:snapshot'),
  onHudSnapshot: callback => {
    const listener = (_event, snapshot) => callback(snapshot);
    ipcRenderer.on('hud:snapshot', listener);
    return () => ipcRenderer.removeListener('hud:snapshot', listener);
  },
  returnToMain: () => ipcRenderer.invoke('hud:return'),
  runHudAction: actionId => ipcRenderer.invoke('hud:action', actionId),
  version: '1.9.4',
}));
