const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const { exec } = require('child_process')
const util = require('util')
const execPromise = util.promisify(exec)

function createWindow () {
    const win = new BrowserWindow({
        width: 960,
        height: 540,
        resizable: false,
        autoHideMenuBar: true,
        icon: path.join(__dirname, 'assets', 'icon.ico'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        }
    })

    win.loadFile('index.html')
}

app.whenReady().then(() => {
    createWindow()
})

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit()
    }
})

// 处理文件选择
ipcMain.handle('select-file', async () => {
    const result = await dialog.showOpenDialog({
        properties: ['openFile'],
        filters: [{ name: 'GS Files', extensions: ['gs', 'GS'] }]
    })
    
    if (!result.canceled && result.filePaths.length > 0) {
        return handleGSFile(result.filePaths[0])
    }
})

// 处理拖放文件
ipcMain.handle('handle-drop', async (event, filePath) => {
    return handleGSFile(filePath)
})

// 处理GS文件
async function handleGSFile(filePath) {
    try {
        const { stdout } = await execPromise(`"${path.join(__dirname, 'assets', 'gs2png.exe')}" -b64 "${filePath}"`)
        return stdout
    } catch (error) {
        console.error('Error:', error)
        return JSON.stringify({ error: error.message })
    }
}
