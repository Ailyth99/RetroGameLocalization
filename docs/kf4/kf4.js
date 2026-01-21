const go = new Go();
let wasmLoaded = false;

const GAME_VERSIONS = {
    "SLPS_250.57": { offset: 0x3A6EE0, offsetFOV: 0x1C09C8, name: "汉化版/日版 (JP)", canFOV: true },
    "SLUS_203.18": { offset: 0x3A85E0, offsetFOV: 0x1C2108, name: "美版 (US)", canFOV: true },
    "SLES_509.20": { offset: 0x3EA5A0, offsetFOV: 0, name: "欧版 (EU)", canFOV: false }
};

const OFFSET_ELF_JP = 0x3136E0;
const CHUNK_SIZE = 4096;
const WRITE_CHUNK_SIZE = 128 * 1024 * 1024;

const loadingBar = document.getElementById('loadingBar');
const loadingText = document.getElementById('loadingText');
const loadingOverlay = document.getElementById('loadingOverlay');

fetch("kf4_patcher.wasm").then(response => {
    const contentLength = response.headers.get('Content-Length');
    const total = parseInt(contentLength, 10);
    let loaded = 0;

    const reader = response.body.getReader();
    const stream = new ReadableStream({
        start(controller) {
            function push() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        controller.close();
                        return;
                    }
                    loaded += value.byteLength;
                    if (total) {
                        const progress = Math.round((loaded / total) * 100);
                        loadingBar.style.width = progress + '%';
                        loadingText.innerText = progress + '%';
                    }
                    controller.enqueue(value);
                    push();
                });
            }
            push();
        }
    });

    return new Response(stream, { headers: { 'Content-Type': 'application/wasm' } });
}).then(response => response.arrayBuffer())
  .then(bytes => WebAssembly.instantiate(bytes, go.importObject))
  .then(result => {
      go.run(result.instance);
      wasmLoaded = true;
      setTimeout(() => {
          loadingOverlay.style.opacity = '0';
          setTimeout(() => loadingOverlay.style.display = 'none', 500);
      }, 300);
  }).catch(err => {
      loadingText.innerText = "ERROR";
      loadingText.style.color = "red";
      alert("核心组件加载失败，请检查网络或文件完整性。");
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

function handleFileInput(input) { processFiles(input.files); }

function processFiles(files) {
    if (!wasmLoaded) return;
    currentFile = files[0];
    document.getElementById('fileNameDisplay').innerText = currentFile.name;
    const verDisplay = document.getElementById('versionDisplay');
    verDisplay.innerText = "识别中...";
    verDisplay.style.color = "var(--accent-color)";

    const reader = new FileReader();
    reader.onload = e => analyzeHeader(new Uint8Array(e.target.result));
    reader.readAsArrayBuffer(currentFile.slice(0, 2 * 1024 * 1024));
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
            alert("无法自动识别版本。请确保上传的是有效的国王密令4 ISO 镜像。");
            document.getElementById('versionDisplay').innerText = "识别失败";
        }
    }
}

async function finalizeLoad(info) {
    document.getElementById('versionDisplay').innerText = info.name;
    
    const paramChunk = new Uint8Array(await currentFile.slice(info.offset, info.offset + CHUNK_SIZE).arrayBuffer());
    const rates = kf4_AnalyzeChunk(paramChunk);
    
    if (rates.error) {
        alert("分析失败：数据不符合特征。");
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
        document.getElementById('fovNotice').innerText = "已匹配视野修改地址";
        const fovData = new Uint8Array(await currentFile.slice(info.offsetFOV, info.offsetFOV + 2).arrayBuffer());
        const fovLabel = kf4_AnalyzeFOV(fovData);
        const radio = document.querySelector(`input[name="fov"][value="${fovLabel}"]`);
        if (radio) radio.checked = true;
    } else {
        fovSect.style.opacity = "0.3"; fovSect.style.pointerEvents = "none";
        document.getElementById('fovNotice').innerText = "该版本不支持视野修改";
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

        if (window.showSaveFilePicker) {
            const handle = await window.showSaveFilePicker({ suggestedName: saveName, types: [{ description: 'ISO Image', accept: {'application/octet-stream': ['.iso', '.bin', '.elf']} }] });
            
            if (handle.name === currentFile.name) {
                alert("安全警告：不要使用原文件名保存，这将导致源文件清空损坏。\n请务必修改文件名保存。");
                return;
            }

            overlay.style.display = 'flex';
            sText.innerText = "WRITING... (STAGE 1/2)";
            
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

            sText.innerText = "FINALIZING... (PLEASE WAIT)";
            pBar.classList.add('processing');
            pPct.innerText = "构建中...";
            await new Promise(r => setTimeout(r, 300));
            await writable.close();

            overlay.style.display = 'none';
            pBar.classList.remove('processing');
            alert("修改后的文件保存成功！");
        } 
        else {
            overlay.style.display = 'flex';
            sText.innerText = "GENERATING BLOB...";
            pBar.classList.add('processing');
            
            const parts = [];
            if (detected.canFOV) {
                parts.push(currentFile.slice(0, detected.offsetFOV));
                parts.push(fovBytes);
                parts.push(currentFile.slice(detected.offsetFOV + 2, detected.offset));
            } else {
                parts.push(currentFile.slice(0, detected.offset));
            }
            parts.push(patchedParams);
            parts.push(currentFile.slice(detected.offset + CHUNK_SIZE));

            const blob = new Blob(parts, {type: "application/octet-stream"});
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob); a.download = saveName; a.click();
            overlay.style.display = 'none';
            pBar.classList.remove('processing');
        }
    } catch (e) {
        overlay.style.display = 'none';
        pBar.classList.remove('processing');
        if (e.name !== 'AbortError') alert("错误: " + e.message);
    }
}