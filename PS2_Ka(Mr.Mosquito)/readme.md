Extract TIM2 images from BIN files used in the PS2 game "Ka" (also known as "Mr. Mosquito"), and supports re-importing modified TIM2 images back into the BIN file.

**Compile:**
```bash
go build ka_tim2_tool.go
```
**Usage:**

*   **Extract TIM2:** `ka_tim2_tool -e <input.bin>`
    *   This will extract TIM2  to a folder with the same name as the input BIN file.
    *   The folder will contain multiple TM2 format images and a JSON index file (`extract_info.json`).
*   **Import TIM2:** `ka_tim2_tool -i <input.tm2> -j <info.json> -b <target.bin>`
    *   This will import a modified `input.tm2`(use the same name with original one) file back into the `target.bin` file.
    *   `<info.json>` should be the JSON index file generated during the extraction process.
    *   `<target.bin>` is the original BIN file from which the TIM2 was extracted.

**Known Issues:**

*   **Extra data at the end:** For the last TIM2 image in the BIN file, the extraction process might include some extra data. This can be manually removed using a hex editor. 