### Build

**Windows (PowerShell/CMD):**
```bash
go build -o shana_font.exe shana_font.go
go build -o pr_tool.exe pr_tool.go
go build -o shana_tx_extract.exe shana_tx_extract.go swizzle.go utils.go
go build -o shana_tx_inject.exe shana_tx_inject.go swizzle.go utils.go
```
---

### 使用方法 / Usage

exe在bin目录里面

### 1. 字体工具 / Font Tool
```bash
# 导出 / Export
shana_font -e font.bin font.png

# 导入 / Import
shana_font -i font.png new_font.bin
```

### 2. （记忆卡文字图）PR工具 / PR Tool 
```bash
# 导出 / Export
pr_tool -e pr.bin

# 注入 / Inject
pr_tool -i pr.png -ref pr.bin
```

### 3. 纹理导出工具 / Texture Extract Tool
```bash
# 单文件 / Single file
shana_tx_extract -i texture.obj -o texture.png

# 批量处理 / Batch process
shana_tx_extract -i ./textures_folder
```

### 4. 纹理注入工具 / Texture Inject Tool
```bash
# 自动搜索最佳颜色数 / Auto search optimal colors
shana_tx_inject -i modified.png -ref original.obj -o new.obj

# 手动指定颜色数 / Manual color count
shana_tx_inject -i modified.png -ref original.obj -o new.obj -c 256
```

---



