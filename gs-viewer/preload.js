const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electron', {
    selectFile: () => ipcRenderer.invoke('select-file'),
    handleDrop: (filePath) => ipcRenderer.invoke('handle-drop', filePath)
})
