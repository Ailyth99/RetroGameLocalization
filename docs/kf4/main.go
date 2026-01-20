package main

import (
	"encoding/binary"
	"math"
	"syscall/js"
)

// ==========================================
// 核心数据 (Vanilla Values)
// ==========================================

var VanillaValues = map[int][]float32{
	0:   {12.0, 12.0, 8.0, 6.0, 6.0, 0.0},
	24:  {1.2, 0.8, 1.2, 1.2, 1.2, 0.0},
	48:  {1.2, 0.6, 1.2, 1.2, 1.2, 0.0},
	72:  {0.029089, 0.029089, 0.019393, 0.014544, 0.014544, 0.0},
	96:  {0.002909, 0.002909, 0.001939, 0.001454, 0.001454, 0.0},
	144: {0.026180, 0.026180, 0.026180, 0.013090, 0.026180, 0.0},
	168: {0.002618, 0.002618, 0.002618, 0.001309, 0.002618, 0.0},
	192: {0.002618, 0.002618, 0.002618, 0.001309, 0.002618, 0.0},
	216: {0.033743, 0.033743, 0.033743, 0.016872, 0.033743, 0.0},
	240: {6.666667, 6.666667, 0.333333, 0.333333, 0.030000, 0.0},
}

// 辅助函数
func intToString(n int) string {
	if n == 0 { return "0" }
	s := ""
	for n > 0 {
		digit := n % 10
		s = string(rune('0'+digit)) + s
		n /= 10
	}
	return s
}

// 分析物理参数块
func analyzeChunk(this js.Value, args []js.Value) interface{} {
	if len(args) < 1 { return nil }
	jsData := args[0]
	data := make([]byte, jsData.Get("length").Int())
	js.CopyBytesToGo(data, jsData)

	result := make(map[string]interface{})
	if len(data) < 300 { return map[string]interface{}{"error": "Data chunk too small"} }

	for offset, vanillaList := range VanillaValues {
		addr := offset
		bits := binary.LittleEndian.Uint32(data[addr : addr+4])
		currentVal := math.Float32frombits(bits)
		vanillaVal := vanillaList[0]
		var multiplier float32 = 1.0
		if vanillaVal != 0 { multiplier = currentVal / vanillaVal }
		result[intToString(offset)] = multiplier
	}
	return result
}

// 分析 FOV 字节
func analyzeFOV(this js.Value, args []js.Value) interface{} {
	if len(args) < 1 { return "unknown" }
	jsData := args[0]
	data := make([]byte, 2)
	js.CopyBytesToGo(data, jsData)
	
	// 修正：移除未使用的 hexVal 声明
	hexStr := ""
	if data[0] == 0x80 && data[1] == 0x3F { hexStr = "1.0" } else
	if data[0] == 0xA0 && data[1] == 0x3F { hexStr = "1.25" } else
	if data[0] == 0xC0 && data[1] == 0x3F { hexStr = "1.5" } else
	if data[0] == 0xE0 && data[1] == 0x3F { hexStr = "1.75" }
	
	if hexStr == "" { return "custom" }
	return hexStr
}

// 修改物理参数块
func patchChunk(this js.Value, args []js.Value) interface{} {
	if len(args) < 2 { return nil }
	jsInputData := args[0]
	data := make([]byte, jsInputData.Get("length").Int())
	js.CopyBytesToGo(data, jsInputData)
	jsConfig := args[1]

	for offset, vanillaList := range VanillaValues {
		offsetStr := intToString(offset)
		jsVal := jsConfig.Get(offsetStr)
		if jsVal.IsUndefined() || jsVal.IsNull() { continue }
		multiplier := float32(jsVal.Float())
		for i, vVal := range vanillaList {
			newVal := vVal * multiplier
			bits := math.Float32bits(newVal)
			writePos := offset + (i * 4)
			if writePos+4 <= len(data) {
				binary.LittleEndian.PutUint32(data[writePos:writePos+4], bits)
			}
		}
	}
	jsOutputArray := js.Global().Get("Uint8Array").New(len(data))
	js.CopyBytesToJS(jsOutputArray, data)
	return jsOutputArray
}

func main() {
	js.Global().Set("kf4_AnalyzeChunk", js.FuncOf(analyzeChunk))
	js.Global().Set("kf4_AnalyzeFOV", js.FuncOf(analyzeFOV))
	js.Global().Set("kf4_PatchChunk", js.FuncOf(patchChunk))
	select {}
}