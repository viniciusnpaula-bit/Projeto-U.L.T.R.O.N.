const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ultron', Object.freeze({
  health: () => ipcRenderer.invoke('api:health'),
  status: () => ipcRenderer.invoke('api:status'),
  events: () => ipcRenderer.invoke('api:events'),
  command: text => ipcRenderer.invoke('api:command', text),
  microphone: paused => ipcRenderer.invoke('api:microphone', paused),
  microphones: () => ipcRenderer.invoke('api:microphones'),
  conversation: () => ipcRenderer.invoke('api:conversation'),
  updateInfo: () => ipcRenderer.invoke('update:info'),
  updateCheck: () => ipcRenderer.invoke('update:check'),
  updateApply: restartAfter => ipcRenderer.invoke('update:apply', restartAfter === true),
  updateLaunch: () => ipcRenderer.invoke('update:launch'),
  updateRollback: () => ipcRenderer.invoke('update:rollback'),
  setZoom: enabled => ipcRenderer.invoke('view:zoom', enabled === true),
  selectMicrophone: deviceId => ipcRenderer.invoke('api:microphone-device', deviceId),
  confirmation: (requestId, approved, pin) => ipcRenderer.invoke('api:confirmation', requestId, approved, pin),
  emergencyStop: () => ipcRenderer.invoke('api:emergency-stop'),
  shutdown: () => ipcRenderer.invoke('api:shutdown'),
  toggleHud: () => ipcRenderer.invoke('hud:toggle'),
  publishHudSnapshot: snapshot => ipcRenderer.invoke('hud:publish', snapshot),
  onHudVisibility: callback => {
    const listener = (_event, visible) => callback(visible === true);
    ipcRenderer.on('hud:visibility', listener);
    return () => ipcRenderer.removeListener('hud:visibility', listener);
  },
  onHudAction: callback => {
    const listener = (_event, request) => callback(request);
    ipcRenderer.on('hud:run-action', listener);
    return () => ipcRenderer.removeListener('hud:run-action', listener);
  },
  hudActionResult: (requestId, accepted) => ipcRenderer.send('hud:action-result', requestId, accepted === true),
  version: '1.9.4',
}));
