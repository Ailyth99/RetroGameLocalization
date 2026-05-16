package main

import (
	"XBOX_ISO_TOOL/xiso"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	extract := flag.String("e", "", "Extract ISO to folder")
	repack := flag.String("r", "", "Repack folder to ISO")
	output := flag.String("o", "", "Output path")
	tbl := flag.String("tbl", "", "Export LBA table as CSV")
	injectPath := flag.String("inject", "", "Inject: internal path (e.g. \\DATA\\INDEX.BIN)")
	injectFile := flag.String("file", "", "Inject: local file to inject")
	isoPath := flag.String("iso", "", "Inject: target ISO path")
	renamePath := flag.String("rename", "", "Rename: internal path (e.g. CHARS\\FONT.BIN)")
	renameNew := flag.String("newname", "", "Rename: new filename")
	appendFile := flag.String("append", "", "Append: local file to append to ISO")
	appendDir := flag.String("dir", "", "Append: target directory in ISO (e.g. DATA)")
	appendName := flag.String("name", "", "Append: filename in ISO (default: same as local file)")
	getPath := flag.String("get", "", "Extract single file: internal path (e.g. DATA\\INDEX.BIN)")
	flag.Parse()

	// -tbl mode
	if *tbl != "" {
		csvOut := *output
		if csvOut == "" {
			base := filepath.Base(*tbl)
			csvOut = strings.TrimSuffix(base, filepath.Ext(base)) + ".csv"
		}
		doTbl(*tbl, csvOut)
		return
	}

	// -inject mode
	if *injectPath != "" {
		if *injectFile == "" || *isoPath == "" {
			fmt.Fprintln(os.Stderr, "Inject requires -file and -iso")
			os.Exit(1)
		}
		doInject(*isoPath, *injectPath, *injectFile)
		return
	}

	// -rename mode
	if *renamePath != "" {
		if *renameNew == "" || *isoPath == "" {
			fmt.Fprintln(os.Stderr, "Rename requires -newname and -iso")
			os.Exit(1)
		}
		doRename(*isoPath, *renamePath, *renameNew)
		return
	}

	// -append mode
	if *appendFile != "" {
		if *isoPath == "" {
			fmt.Fprintln(os.Stderr, "Append requires -iso")
			os.Exit(1)
		}
		dir := *appendDir
		if dir == "" {
			dir = "/"
		}
		doAppend(*isoPath, *appendFile, dir, *appendName)
		return
	}

	// -get mode
	if *getPath != "" {
		if *isoPath == "" {
			fmt.Fprintln(os.Stderr, "Get requires -iso")
			os.Exit(1)
		}
	 doGet(*isoPath, *getPath, *output)
		return
	}

	// -e mode
	if *extract != "" {
		doExtract(*extract, *output)
		return
	}

	// -r mode
	if *repack != "" {
		doRepack(*repack, *output)
		return
	}

	fmt.Println("XBOX ISO Tool - XDVDFS image utility - aikika")
	fmt.Println()
	fmt.Println("Commands:")
	fmt.Println()
	fmt.Println("  Extract ISO to folder:")
	fmt.Println("    XBOX_ISO_TOOL -e game.iso")
	fmt.Println("    XBOX_ISO_TOOL -e game.iso -o output_dir")
	fmt.Println()
	fmt.Println("  Repack folder to ISO:")
	fmt.Println("    XBOX_ISO_TOOL -r game_dir")
	fmt.Println("    XBOX_ISO_TOOL -r game_dir -o output.iso")
	fmt.Println()
	fmt.Println("  Export LBA table as CSV:")
	fmt.Println("    XBOX_ISO_TOOL -tbl game.iso")
	fmt.Println("    XBOX_ISO_TOOL -tbl game.iso -o table.csv")
	fmt.Println()
	fmt.Println("  Extract single file from ISO:")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -get DATA\\INDEX.BIN")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -get DATA\\INDEX.BIN -o output.bin")
	fmt.Println()
	fmt.Println("  Inject (replace) file in-place (new file <= original size):")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -inject \\DATA\\INDEX.BIN -file new_index.bin")
	fmt.Println()
	fmt.Println("  Rename file in ISO directory table:")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -rename \\DATA\\FONT.BIN -newname 000")
	fmt.Println()
	fmt.Println("  Append file to ISO (adds at end, creates directory entry):")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -append new_font.bin -dir DATA -name FONT.BIN")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -append new_font.bin -dir /           (root dir)")
	fmt.Println("    XBOX_ISO_TOOL -iso game.iso -append new_font.bin                   (root dir)")
	os.Exit(1)
}

func doExtract(isoPath, outPath string) {
	absISO, err := filepath.Abs(isoPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	if outPath == "" {
		base := filepath.Base(absISO)
		name := strings.TrimSuffix(base, filepath.Ext(base))
		outPath = filepath.Join(filepath.Dir(absISO), name)
	}
	f, err := os.Open(absISO)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()
	stat, _ := f.Stat()
	if err := xiso.Extract(f, stat.Size(), outPath); err != nil {
		fmt.Fprintf(os.Stderr, "Extract error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}

func doRepack(dirPath, outPath string) {
	absDir, err := filepath.Abs(dirPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	if outPath == "" {
		base := filepath.Base(absDir)
		outPath = filepath.Join(filepath.Dir(absDir), base+".iso")
	}
	absOut, _ := filepath.Abs(outPath)
	if absOut == absDir {
		fmt.Fprintf(os.Stderr, "Error: source and destination are the same\n")
		os.Exit(1)
	}
	if err := xiso.Repack(absDir, absOut); err != nil {
		fmt.Fprintf(os.Stderr, "Repack error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}

func doTbl(isoFile, csvOut string) {
	f, err := os.Open(isoFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()
	stat, _ := f.Stat()
	if err := xiso.ExportTable(f, stat.Size(), csvOut); err != nil {
		fmt.Fprintf(os.Stderr, "Export error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}

func doInject(isoFile, internalPath, localFile string) {
	if err := xiso.InjectFile(isoFile, internalPath, localFile); err != nil {
		fmt.Fprintf(os.Stderr, "Inject error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}

func doRename(isoFile, internalPath, newName string) {
	if err := xiso.RenameFile(isoFile, internalPath, newName); err != nil {
		fmt.Fprintf(os.Stderr, "Rename error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}

func doAppend(isoFile, localFile, dir, name string) {
	if name == "" {
		name = filepath.Base(localFile)
	}
	if err := xiso.AppendFile(isoFile, localFile, dir, name); err != nil {
		fmt.Fprintf(os.Stderr, "Append error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}

func doGet(isoFile, internalPath, outPath string) {
	f, err := os.Open(isoFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()

	stat, _ := f.Stat()

	if outPath == "" {
		outPath = filepath.Base(internalPath)
	}

	if err := xiso.GetFile(f, stat.Size(), internalPath, outPath); err != nil {
		fmt.Fprintf(os.Stderr, "Get error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Done.")
}
