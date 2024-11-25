document.addEventListener('DOMContentLoaded', () => {
    const selectFileBtn = document.getElementById('selectFile');
    const preview = document.getElementById('preview');

    function updateInfo(info) {
        document.getElementById('fileName').textContent = info.fileName;
        document.getElementById('imageType').textContent = info.imageType;
        document.getElementById('imageSize').textContent = `${info.width} * ${info.height}`;
        document.getElementById('palSize').textContent = `${info.palSize} colors`;
        document.getElementById('fileSize').textContent = `${(info.fileSize / 1024).toFixed(2)} KB`;
        preview.src = `data:image/png;base64,${info.base64}`;
    }

    selectFileBtn.addEventListener('click', async () => {
        const result = await window.electron.selectFile();
        try {
            const info = JSON.parse(result);
            if (info.error) {
                alert(info.error);
            } else {
                updateInfo(info);
            }
        } catch (error) {
            alert('Failed to process the file');
        }
    });
});
