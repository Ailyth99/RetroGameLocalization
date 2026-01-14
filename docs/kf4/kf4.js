const go = new Go();
let wasmLoaded = false;

//游戏版本数据
const GAME_VERSIONS = {
    "SLPS_250.57": { offset: 0x3A6EE0, offsetFOV: 0x1C09C8, name: "汉化版/日版 (JP)", canFOV: true },
    "SLUS_203.18": { offset: 0x3A85E0, offsetFOV: 0x1C2108, name: "美版 (US)", canFOV: true }, 
    "SLES_509.20": { offset: 0x3EA5A0, offsetFOV: 0, name: "欧版 (EU)", canFOV: false }
};
const OFFSET_ELF_JP = 0x3136E0;
const CHUNK_SIZE = 4096;
const WRITE_CHUNK_SIZE = 128 * 1024 * 1024; //按照128MB下载分块

//加载 WASM
WebAssembly.instantiateStreaming(fetch("kf4_patcher.wasm"), go.importObject).then((result) => {
    go.run(result.instance);
    wasmLoaded = true;
    console.log("✅ WASM Core Loaded Successfully");
}).catch(err => {
    alert("WASM加载失败");
});

let currentFile = null;
let detected = null;

const dropArea = document.getElementById('dropArea');
const fileInput = document.getElementById('fileInput');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
    dropArea.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); }, false);
});

dropArea.addEventListener('dragenter', () => dropArea.classList.add('dragover'), false);
dropArea.addEventListener('dragover', () => dropArea.classList.add('dragover'), false);
dropArea.addEventListener('dragleave', () => dropArea.classList.remove('dragover'), false);
dropArea.addEventListener('drop', e => { 
    dropArea.classList.remove('dragover'); 
    if (e.dataTransfer.files.length) processFiles(e.dataTransfer.files);
}, false);

fileInput.addEventListener('change', e => processFiles(e.target.files));

function processFiles(files) {
    if (!wasmLoaded) return;
    currentFile = files[0];
    document.getElementById('fileNameDisplay').innerText = currentFile.name;
    const verDisplay = document.getElementById('versionDisplay');
    verDisplay.innerText = "识别中...";
    verDisplay.style.color = "var(--accent-color)";

    const reader = new FileReader();
    reader.onload = e => analyzeHeader(new Uint8Array(e.target.result));
    reader.readAsArrayBuffer(currentFile.slice(0, 2 * 1024 * 1024)); // 读取前 2MB 用于识别
}

function analyzeHeader(data) {
    const magic = String.fromCharCode(...data.slice(1, 4));
    if (magic === "ELF") {
        detected = { offset: OFFSET_ELF_JP, name: "ELF 文件 (日版)", canFOV: false };
        finalizeLoad(detected);
    } else {
        const text = new TextDecoder().decode(data);
        const match = text.match(/BOOT2\s*=\s*cdrom0:\\([A-Z]{4}_[0-9]{3}\.[0-9]{2})/i);
        if (match && GAME_VERSIONS[match[1].toUpperCase()]) {
            detected = GAME_VERSIONS[match[1].toUpperCase()];
            finalizeLoad(detected);
        } else {
            alert("无法自动识别版本。请确保上传的是有效的国王密令4 ISO镜像。");
            document.getElementById('versionDisplay').innerText = "识别失败";
        }
    }
}

async function finalizeLoad(info) {
    document.getElementById('versionDisplay').innerText = info.name;
    
    const paramChunk = new Uint8Array(await currentFile.slice(info.offset, info.offset + CHUNK_SIZE).arrayBuffer());
    const rates = kf4_AnalyzeChunk(paramChunk);
    
    if (rates.error) {
        alert("分析失败");
        return;
    }

    document.getElementById('settingsCard').style.opacity = "1";
    document.getElementById('settingsCard').style.pointerEvents = "auto";
    document.getElementById('patchBtn').disabled = false;

    const ids = ["0", "24", "48", "72", "96", "144", "168", "192", "216", "240"];
    ids.forEach(off => {
        if (rates[off] !== undefined) document.getElementById("p_" + off).value = rates[off].toFixed(2);
    });

    const fovSect = document.getElementById('fovSection');
    if (info.canFOV) {
        fovSect.style.opacity = "1"; fovSect.style.pointerEvents = "auto";
        document.getElementById('fovNotice').innerText = "已匹配到视野修改点。";
        const fovData = new Uint8Array(await currentFile.slice(info.offsetFOV, info.offsetFOV + 2).arrayBuffer());
        const fovLabel = kf4_AnalyzeFOV(fovData);
        const radio = document.querySelector(`input[name="fov"][value="${fovLabel}"]`);
        if (radio) radio.checked = true;
    } else {
        fovSect.style.opacity = "0.3"; fovSect.style.pointerEvents = "none";
        document.getElementById('fovNotice').innerText = "该版本暂不支持视角修改功能。";
    }
}

async function applyPatch() {
    if (!currentFile) return;

    const config = {};
    ["0", "24", "48", "72", "96", "144", "168", "192", "216", "240"].forEach(o => {
        config[o] = parseFloat(document.getElementById("p_" + o).value) || 1.0;
    });

    const fovMap = { "1.0": [0x80, 0x3F], "1.25": [0xA0, 0x3F], "1.5": [0xC0, 0x3F], "1.75": [0xE0, 0x3F] };
    const selFov = document.querySelector('input[name="fov"]:checked').value;
    const fovBytes = new Uint8Array(fovMap[selFov] || [0x80, 0x3F]);

    const overlay = document.getElementById('globalOverlay');
    const pBar = document.getElementById('globalProgressBar');
    const pPct = document.getElementById('globalProgressPercent');
    const sText = document.getElementById('statusText');

    try {
        const paramBuf = await currentFile.slice(detected.offset, detected.offset + CHUNK_SIZE).arrayBuffer();
        const patchedParams = kf4_PatchChunk(new Uint8Array(paramBuf), config);

        const name = currentFile.name;
        const lastIdx = name.lastIndexOf('.');
        const saveName = lastIdx !== -1 ? name.substring(0, lastIdx) + "_patched" + name.substring(lastIdx) : name + "_patched";

        overlay.style.display = 'flex';
        sText.innerText = "WRITING... (STAGE 1/2)";

        if (window.showSaveFilePicker) {
            const handle = await window.showSaveFilePicker({ suggestedName: saveName, types: [{ description: 'ISO Image', accept: {'application/octet-stream': ['.iso', '.bin', '.elf']} }] });
            const writable = await handle.createWritable();
            const total = currentFile.size;
            let wrote = 0;

            const stepWrite = async (blob) => {
                await writable.write(blob);
                wrote += blob.size;
                const p = ((wrote / total) * 100).toFixed(1);
                pBar.style.width = p + '%'; pPct.innerText = p + '%';
            };

            if (detected.canFOV) {
                await stepWrite(currentFile.slice(0, detected.offsetFOV));
                await stepWrite(new Blob([fovBytes]));
                await stepWrite(currentFile.slice(detected.offsetFOV + 2, detected.offset));
            } else {
                await stepWrite(currentFile.slice(0, detected.offset));
            }

            await stepWrite(new Blob([patchedParams]));

            let pos = detected.offset + CHUNK_SIZE;
            while (pos < total) {
                const end = Math.min(pos + WRITE_CHUNK_SIZE, total);
                await stepWrite(currentFile.slice(pos, end));
                pos = end;
            }

            sText.innerText = "FINALIZING...";
            pBar.classList.add('processing');
            pPct.innerText = "BUILDING...";
            await new Promise(r => setTimeout(r, 300));
            await writable.close();

            overlay.style.display = 'none';
            pBar.classList.remove('processing');
            alert("修改后的文件保存成功！");
        } 
        else {
            sText.innerText = "GENERATING BLOB...";
            pBar.classList.add('processing');
            const parts = [currentFile.slice(0, detected.offset)]; //移动端暂不强制注入 FOV，防止过于复杂 OOM
            parts.push(patchedParams);
            parts.push(currentFile.slice(detected.offset + CHUNK_SIZE));
            const blob = new Blob(parts, {type: "application/octet-stream"});
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob); a.download = saveName; a.click();
            overlay.style.display = 'none';
        }
    } catch (e) {
        overlay.style.display = 'none';
        if (e.name !== 'AbortError') alert("错误: " + e.message);
    }
}