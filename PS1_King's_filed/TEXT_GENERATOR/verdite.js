document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('mainCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const refImage = document.getElementById('refImage');
    const canvasWrapper = document.getElementById('canvasWrapper');
    const workspace = document.getElementById('workspace'); 
    const inputs = document.querySelectorAll('input, textarea, select');
    const zoomSlider = document.getElementById('zoomSlider');
    const zoomDisplay = document.getElementById('zoomDisplay');
    const texturePreset = document.getElementById('texturePreset');
    const binaryThreshold = document.getElementById('binaryThreshold');
    const threshVal = document.getElementById('threshVal');
  
      const imgNoiseInput = document.getElementById('imgNoiseInput');
    const noiseImgStatus = document.getElementById('noiseImgStatus');
    let uploadedNoiseImage = null;

    const textureConfigs = {
        preset1: [
            { color: { r:198, g:222, b:198 }, probability: 0.65 }, 
            { color: { r:173, g:173, b:82  }, probability: 0.02 }, 
            { color: { r:132, g:132, b:132 }, probability: 0.04 },
            { color: { r:165, g:165, b:165 }, probability: 0.08 },
            { color: { r:222, g:222, b:222 }, probability: 0.08 },
            { color: { r:233, g:233, b:233 }, probability: 0.08 },
            { color: { r:255, g:255, b:244 }, probability: 0.04 }
        ],
        preset2: [
            { color: { r:239, g:222, b:156 }, probability: 0.70 },
            { color: { r:222, g:206, b:156 }, probability: 0.03 }, 
            { color: { r:239, g:206, b:140 }, probability: 0.03 },
            { color: { r:222, g:222, b:156 }, probability: 0.03 },
            { color: { r:239, g:206, b:156 }, probability: 0.03 },
            { color: { r:255, g:222, b:156 }, probability: 0.03 },
            { color: { r:239, g:239, b:156 }, probability: 0.03 },
            { color: { r:255, g:255, b:165 }, probability: 0.03 },
            { color: { r:239, g:239, b:173 }, probability: 0.03 },
            { color: { r:239, g:222, b:173 }, probability: 0.03 },
            { color: { r:255, g:206, b:173 }, probability: 0.03 }
        ]
    };

    function draw() {
        if(threshVal) threshVal.innerText = binaryThreshold.value;

        const w = parseInt(document.getElementById('canvasW').value) || 256;
        const h = parseInt(document.getElementById('canvasH').value) || 256;
        const size = parseInt(document.getElementById('fontSize').value) || 16;
        const gap = parseInt(document.getElementById('lineGap').value) || 2;
        const startX = parseInt(document.getElementById('offsetX').value) || 0;
        const startY = parseInt(document.getElementById('offsetY').value) || 0;
        const align = document.getElementById('textAlign').value;
        const isBold = document.getElementById('boldCheck').checked;
        const text = document.getElementById('textInput').value;
        const fontManual = document.getElementById('fontManual');
        const fontSelect = document.getElementById('fontSelect');
        const font = (fontManual.value && fontManual.value.trim()) ? fontManual.value.trim() : fontSelect.value;
        
        const useTexture = document.getElementById('textureCheck').checked;
        const currentPreset = texturePreset.value;
        const threshold = parseInt(binaryThreshold.value);

        let logicalW = w;
        let logicalH = h;

        if (uploadedNoiseImage) {
            logicalW = uploadedNoiseImage.width;
            logicalH = uploadedNoiseImage.height;
            if(document.getElementById('canvasW').value != logicalW) document.getElementById('canvasW').value = logicalW;
            if(document.getElementById('canvasH').value != logicalH) document.getElementById('canvasH').value = logicalH;
        }

  
        updateWrapperSize(logicalW, logicalH);

  
        canvas.width = logicalW;
        canvas.height = logicalH;

        ctx.clearRect(0, 0, logicalW, logicalH);
        ctx.imageSmoothingEnabled = false;

        if (uploadedNoiseImage) {
            ctx.drawImage(uploadedNoiseImage, 0, 0);
        } else {
            ctx.font = `${isBold ? 'bold ' : ''}${size}px "${font}"`;
            ctx.fillStyle = "#FFFFFF"; 
            ctx.textBaseline = 'top';
            
            let drawX = (align === 'left') ? startX : (logicalW / 2 + (startX - 8));
            ctx.textAlign = (align === 'left') ? 'left' : 'center';

            const paragraphs = text.split('\n');
            let cursorY = startY;
            const lineHeight = size + gap;
            const maxW = logicalW - (startX * 2);

            paragraphs.forEach(para => {
                let line = '';
                for(let i = 0; i < para.length; i++){
                    const test = line + para[i];
                    if(ctx.measureText(test).width > maxW && i > 0){
                        ctx.fillText(line, Math.floor(drawX), Math.floor(cursorY));
                        line = para[i];
                        cursorY += lineHeight;
                    } else { line = test; }
                }
                ctx.fillText(line, Math.floor(drawX), Math.floor(cursorY));
                cursorY += lineHeight;
            });
        }

        applyTextureProcess(logicalW, logicalH, useTexture, currentPreset, threshold);
    }

    function applyTextureProcess(w, h, useTexture, presetKey, threshold) {
        const imgData = ctx.getImageData(0, 0, w, h);
        const data = imgData.data; 
        const config = textureConfigs[presetKey];
        const defaultColor = config[0].color;

        for(let i = 0; i < data.length; i += 4) {
            const alpha = data[i + 3]; 
            if(alpha > 0) {
                if(alpha < threshold) {
                    data[i + 3] = 0;
                } else {
                    data[i + 3] = 255; 
                    if(useTexture) {
                        const rand = Math.random(); 
                        let cumulativeProbability = 0;
                        let selectedColor = defaultColor;
                        for (const item of config) {
                            cumulativeProbability += item.probability;
                            if (rand < cumulativeProbability) {
                                selectedColor = item.color;
                                break;
                            }
                        }
                        data[i] = selectedColor.r; data[i + 1] = selectedColor.g; data[i + 2] = selectedColor.b;
                    } else {
                        data[i] = defaultColor.r; data[i + 1] = defaultColor.g; data[i + 2] = defaultColor.b;
                    }
                }
            }
        }
        ctx.putImageData(imgData, 0, 0);
    }

    function updateWrapperSize(w, h) {
        const zoom = parseInt(zoomSlider.value) / 100;
        canvasWrapper.style.width = (w * zoom) + 'px';
        canvasWrapper.style.height = (h * zoom) + 'px';
    }

    inputs.forEach(el => el.addEventListener('input', draw));
    
    zoomSlider.addEventListener('input', () => {
        zoomDisplay.innerText = zoomSlider.value + "%";
        draw(); 
    });

    window.resetZoom = function() {
        zoomSlider.value = 100;
        zoomDisplay.innerText = "100%";
        draw();
    }

    workspace.addEventListener('wheel', (e) => {
        e.preventDefault();
        const currentZoom = parseInt(zoomSlider.value);
        const delta = e.deltaY > 0 ? -10 : 10; // 向下滚缩小，向上滚放大
        let newZoom = currentZoom + delta;
        
        newZoom = Math.max(10, Math.min(newZoom, 800));
        
        zoomSlider.value = newZoom;
        zoomDisplay.innerText = newZoom + "%";
        
        draw();
    });

    // Reference Image
    document.getElementById('refInput').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if(file){
            const r = new FileReader();
            r.onload = (evt) => { 
                refImage.src = evt.target.result; 
                refImage.style.display = 'block'; 
                document.getElementById('refControls').style.display = 'flex'; 
            };
            r.readAsDataURL(file);
        }
    });
    
    document.getElementById('refOpacity').addEventListener('input', (e) => {
        refImage.style.opacity = e.target.value / 100;
    });

    window.clearRef = function() { 
        refImage.src = ""; refImage.style.display = 'none';
        document.getElementById('refInput').value = ""; 
        document.getElementById('refControls').style.display = 'none'; 
    }

    // Noise Image
    document.getElementById('imgNoiseInput').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if(file) {
            const img = new Image();
            img.onload = () => {
                uploadedNoiseImage = img;
                document.getElementById('noiseImgStatus').style.display = 'block';
                draw();
            };
            img.src = URL.createObjectURL(file);
        }
    });

    window.clearNoiseImg = function() {
        uploadedNoiseImage = null;
        document.getElementById('imgNoiseInput').value = "";
        document.getElementById('noiseImgStatus').style.display = 'none';
        draw();
    }

    document.getElementById('btnLoadFonts').addEventListener('click', async () => {
        if(!('queryLocalFonts' in window)) { alert('需使用 Chrome/Edge'); return; }
        try {
            const fonts = await window.queryLocalFonts();
            const families = [...new Set(fonts.map(f => f.family))].sort();
            const sel = document.getElementById('fontSelect');
            sel.innerHTML = '<option value="">-- 系统字体 --</option>';
            families.forEach(f => sel.appendChild(new Option(f, f)));
        } catch(e) {}
    });

    document.getElementById('btnDownload').addEventListener('click', async () => {
        if ('showSaveFilePicker' in window) {
            try {
                const handle = await window.showSaveFilePicker({
                    suggestedName: `kf2_gen_${Date.now()}.png`,
                    types: [{ description: 'PNG', accept: {'image/png': ['.png']} }],
                });
                const writable = await handle.createWritable();
                const blob = await new Promise(resolve => canvas.toBlob(resolve));
                await writable.write(blob);
                await writable.close();
                return;
            } catch (err) { return; }
        }
        const a = document.createElement('a');
        a.download = `kf2_gen_${Date.now()}.png`;
        a.href = canvas.toDataURL('image/png');
        a.click();
    });

    draw();
});