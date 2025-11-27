// main.go
package main

import (
	"encoding/binary"
	"fmt"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		printUsage()
		return
	}

	cmd := os.Args[1]

	switch cmd {
	case "-e": // Convert: rh2 -> png (File or Folder)
		if len(os.Args) < 3 {
			fmt.Println("Error: Missing arguments.")
			printUsage()
			return
		}
		inputPath := os.Args[2]
		info, err := os.Stat(inputPath)
		if err != nil {
			fmt.Printf("Error: %v\n", err)
			return
		}
		if info.IsDir() {
			doBatchConvert(inputPath)
		} else {
			outFile := ""
			if len(os.Args) >= 4 { outFile = os.Args[3] } else {
				ext := filepath.Ext(inputPath)
				outFile = strings.TrimSuffix(inputPath, ext) + ".png"
			}
			doConvertToPng(inputPath, outFile)
		}

	case "-i": // Create: png + rh2_template -> new_rh2
		if len(os.Args) < 5 {
			fmt.Println("Error: Missing arguments.")
			printUsage()
			return
		}
		doInject(os.Args[2], os.Args[3], os.Args[4])

	case "-c": // Inject CVT
		if len(os.Args) < 4 {
			fmt.Println("Error: Missing arguments.")
			printUsage()
			return
		}
		outCvt := os.Args[3]
		if len(os.Args) >= 5 { outCvt = os.Args[4] }
		doCvtInject(os.Args[2], os.Args[3], outCvt)

	case "-x": // Extract CVT
		if len(os.Args) < 3 {
			fmt.Println("Error: Missing arguments.")
			printUsage()
			return
		}
		cvtPath := os.Args[2]
		outDir := "output"
		if len(os.Args) >= 4 { outDir = os.Args[3] } else {
			base := filepath.Base(cvtPath)
			outDir = strings.TrimSuffix(base, filepath.Ext(base)) + "_extracted"
		}
		doCvtExtract(cvtPath, outDir)

	default:
		printUsage()
	}
}

func printUsage() {
	exe := filepath.Base(os.Args[0])
	fmt.Println("RH2 Texture Tool - aikika ")
	fmt.Println("\nUsage:")
	fmt.Printf("  Convert RH2 to PNG:      %s -e <file.rh2> [out.png]\n", exe)
	fmt.Printf("  Batch RH2 to PNG:        %s -e <folder>\n", exe)
	fmt.Printf("  Convert PNG to RH2:      %s -i <src.png> <template.rh2> <out.rh2>\n", exe)
	fmt.Printf("  Inject PNG into CVT:     %s -c <src.png> <target.cvt> [out.cvt]\n", exe)
	fmt.Printf("  Extract RH2 from CVT:    %s -x <file.cvt> [out_folder]\n", exe)
}

// --- Handlers ---

func doBatchConvert(dirPath string) {
	fmt.Printf("Batch converting RH2 files in: %s\n", dirPath)
	files, err := os.ReadDir(dirPath)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	count := 0
	for _, file := range files {
		if file.IsDir() { continue }
		name := file.Name()
		if strings.HasSuffix(strings.ToLower(name), ".rh2") {
			fullPath := filepath.Join(dirPath, name)
			outName := strings.TrimSuffix(name, filepath.Ext(name)) + ".png"
			outPath := filepath.Join(dirPath, outName)
			fmt.Printf("  Converting %s -> %s ... ", name, outName)
			
			data, err := os.ReadFile(fullPath)
			if err != nil { fmt.Println("Read Error"); continue }
			img, err := RH2ToImage(data)
			if err != nil { fmt.Printf("Error: %v\n", err); continue }
			
			f, err := os.Create(outPath)
			if err != nil { fmt.Println("Write Error"); continue }
			png.Encode(f, img)
			f.Close()
			fmt.Println("OK")
			count++
		}
	}
	fmt.Printf("Done. Converted %d files.\n", count)
}

func doConvertToPng(rh2Path, pngPath string) {
	data, err := os.ReadFile(rh2Path)
	if err != nil { fmt.Printf("Error: %v\n", err); return }
	img, err := RH2ToImage(data)
	if err != nil { fmt.Printf("Error: %v\n", err); return }
	f, err := os.Create(pngPath)
	if err != nil { fmt.Printf("Error: %v\n", err); return }
	defer f.Close()
	png.Encode(f, img)
	fmt.Println("Saved:", pngPath)
}

func doInject(pngPath, tmplPath, outPath string) {
	f, err := os.Open(pngPath)
	if err != nil { fmt.Printf("Error: %v\n", err); return }
	defer f.Close()
	img, _, err := image.Decode(f)
	if err != nil { fmt.Printf("Error: %v\n", err); return }

	tmpl, err := os.ReadFile(tmplPath)
	if err != nil { fmt.Printf("Error: %v\n", err); return }

	newData, err := InjectPNGToRH2(img, tmpl)
	if err != nil { fmt.Printf("Error: %v\n", err); return }

	if err := os.WriteFile(outPath, newData, 0644); err != nil {
		fmt.Printf("Error: %v\n", err); return
	}
	fmt.Println("Saved:", outPath)
}

func doCvtExtract(cvtPath, outDir string) {
	data, err := os.ReadFile(cvtPath)
	if err != nil { fmt.Printf("Error: %v\n", err); return }
	if err := os.MkdirAll(outDir, 0755); err != nil { fmt.Printf("Error: %v\n", err); return }

	fmt.Printf("Scanning %s (Size: %d)...\n", filepath.Base(cvtPath), len(data))
	count := 0
	dataLen := int64(len(data))
	pos := int64(0)

	for pos < dataLen-4 {
		if pos%0x10 != 0 {
			pos = (pos/0x10 + 1) * 0x10
			continue
		}
		// Safety check for header read
		if pos+8 > dataLen { break }

		// Check RH2 signature (0x324852)
		if data[pos] == 'R' && data[pos+1] == 'H' && data[pos+2] == '2' && data[pos+3] == 0 {
			size1 := int64(binary.LittleEndian.Uint32(data[pos+8:]))
			
			// STRICT Bounds Check to prevent panic
			if pos+size1 > dataLen {
				fmt.Printf("  [Warning] Found header at 0x%X but size %d exceeds file end.\n", pos, size1)
				pos += 0x10
				continue
			}

			// Optional: Validate Size2 if possible
			valid := true
			if pos+44 <= dataLen {
				size2 := int64(binary.LittleEndian.Uint32(data[pos+40:]))
				if size1 != size2 && size2 != 0 {
					// Some files might vary, but usually match
					// valid = false
				}
			}

			if valid && size1 > 0x100 {
				filename := fmt.Sprintf("%s_%03d.rh2", strings.TrimSuffix(filepath.Base(cvtPath), filepath.Ext(cvtPath)), count)
				
				// Backward name search
				searchLimit := pos - 0x50
				if searchLimit < 0 { searchLimit = 0 }
				for i := pos - 4; i >= searchLimit; i-- {
					// Need at least 4 bytes for .rh2
					if i+4 <= pos && strings.EqualFold(string(data[i:i+4]), ".rh2") {
						start := i
						for start > searchLimit && data[start-1] != 0 {
							start--
						}
						extractedName := strings.Trim(string(data[start:i+4]), "\x00")
						if len(extractedName) > 4 {
							filename = extractedName
							break
						}
					}
				}

				outFile := filepath.Join(outDir, filename)
				// Safe slice
				err := os.WriteFile(outFile, data[pos:pos+size1], 0644)
				if err == nil {
					modeStr := "UNK"
					if pos+0x52 <= dataLen {
						m := binary.LittleEndian.Uint16(data[pos+0x50:])
						if m == 0x14 { modeStr = "4bpp" } else if m == 0x13 { modeStr = "8bpp" }
					}
					fmt.Printf("  [%03d] Extracted: %s (%s, %d bytes)\n", count, filename, modeStr, size1)
					count++
				}
			}
		}
		pos += 0x10
	}
	fmt.Printf("Done. Extracted %d files.\n", count)
}

func doCvtInject(pngPath, cvtPath, outCvtPath string) {
	fmt.Printf("Injecting %s into %s...\n", filepath.Base(pngPath), filepath.Base(cvtPath))
	cvtData, err := os.ReadFile(cvtPath)
	if err != nil { fmt.Printf("Error: %v\n", err); return }

	baseName := strings.TrimSuffix(filepath.Base(pngPath), filepath.Ext(pngPath))
	targetName := strings.ToLower(baseName + ".rh2")
	fmt.Println("Target Internal Name:", targetName)

	found := false
	dataLen := int64(len(cvtData))
	pos := int64(0)

	for pos < dataLen-4 {
		if pos%0x10 != 0 { pos = (pos/0x10 + 1) * 0x10; continue }
		if pos+8 > dataLen { break }

		if cvtData[pos] == 'R' && cvtData[pos+1] == 'H' && cvtData[pos+2] == '2' && cvtData[pos+3] == 0 {
			size := int64(binary.LittleEndian.Uint32(cvtData[pos+8:]))
			if pos+size > dataLen { pos += 0x10; continue }

			searchLimit := pos - 0x50
			if searchLimit < 0 { searchLimit = 0 }
			
			nameFound := ""
			// Backward Search for Name
			for i := pos - 4; i >= searchLimit; i-- {
				if i+4 <= pos && strings.EqualFold(string(cvtData[i:i+4]), ".rh2") {
					start := i
					for start > searchLimit && cvtData[start-1] != 0 {
						start--
					}
					nameFound = strings.Trim(string(cvtData[start:i+4]), "\x00")
					break
				}
			}

			if strings.EqualFold(nameFound, targetName) {
				fmt.Printf("Found %s at 0x%X (Size: %d)\n", nameFound, pos, size)
				
				tmplData := make([]byte, size)
				copy(tmplData, cvtData[pos:pos+size])
				
				f, err := os.Open(pngPath)
				if err != nil { fmt.Printf("Error PNG: %v\n", err); return }
				pngImg, _, err := image.Decode(f)
				f.Close()
				if err != nil { fmt.Printf("Error Decode: %v\n", err); return }
				
				newRH2, err := InjectPNGToRH2(pngImg, tmplData)
				if err != nil { fmt.Println("Error Inject:", err); return }
				
				if int64(len(newRH2)) != size {
					fmt.Printf("Error: Size mismatch (%d vs %d)\n", len(newRH2), size); return
				}
				
				copy(cvtData[pos:], newRH2)
				found = true
				break
			}
		}
		pos += 0x10
	}

	if !found {
		fmt.Println("Error: Target RH2 file not found in CVT.")
		return
	}
	if err := os.WriteFile(outCvtPath, cvtData, 0644); err != nil {
		fmt.Printf("Error Write: %v\n", err); return
	}
	fmt.Println("Success! Saved to", outCvtPath)
}