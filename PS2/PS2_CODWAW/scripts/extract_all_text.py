"""Export English HTXT/LTXT/DLLN/PTXT text, retaining existing translations."""
import hashlib
import json
import re

from game_text_resources import ROOT, OriginalResources, locate_text


def old_menu_translations():
    text = (ROOT / "TEXT/exports/Menu_Am/Menu_Am.txt").read_text(encoding="utf-8-sig")
    result = {}
    for match in re.finditer(r"^EN: (.*)\nCN: (.*)$", text, re.M):
        en, zh = [s.replace(r"\r", "\r").replace(r"\n", "\n").replace(r"\t", "\t")
                  for s in match.groups()]
        if zh:
            result[en] = zh
    return result


def main():
    output = ROOT / "TEXT/full_game"
    generated = ROOT / "TEMP/full_game"
    output.mkdir(parents=True, exist_ok=True)
    generated.mkdir(parents=True, exist_ok=True)
    previous = {}
    if (output / "catalog.json").exists():
        previous = {r["en"]: r for r in json.loads((output / "catalog.json").read_text(encoding="utf-8"))}
    inherited = old_menu_translations()
    files = ["Misc/Menu/Menu_Am.asr", "Text/american.asr", "Text/CSText/cs_am.asr"]
    files += sorted(p.relative_to(ROOT / "ISO_UNPACK").as_posix()
                    for p in (ROOT / "ISO_UNPACK/Envs/sp").glob("*")
                    if p.suffix.lower() in (".am", ".ps2"))
    unique, resources = {}, []
    with OriginalResources() as source:
        for path in files:
            data = source.read(path)
            records = locate_text(data)
            nonempty = [r for r in records if r["text"].strip()]
            resources.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(),
                              "size": len(data), "records": records})
            for record in nonempty:
                unique.setdefault(record["text"], []).append({"file": path, "key": record["key"],
                                                              "capacity": record["capacity"]})
            print(f"{path}: {len(nonempty)} nonempty text records")
    catalog = []
    for index, (en, references) in enumerate(unique.items()):
        prior = previous.get(en, {})
        zh = prior.get("zh") or inherited.get(en, "")
        catalog.append({"id": f"T{index:04d}", "en": en, "zh": zh,
                        "status": prior.get("status", "inherited" if zh else "pending"),
                        "references": references})
    (output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (generated / "resources.json").write_text(json.dumps(resources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (generated / "source_lines.jsonl").write_text("".join(
        json.dumps({"id": r["id"], "en": r["en"]}, ensure_ascii=False) + "\n" for r in catalog), encoding="utf-8")
    (generated / "pending.jsonl").write_text("".join(
        json.dumps({"id": r["id"], "en": r["en"]}, ensure_ascii=False) + "\n" for r in catalog if not r["zh"]), encoding="utf-8")
    print(f"{len(catalog)} unique texts; {sum(not r['zh'] for r in catalog)} need translation.")


if __name__ == "__main__":
    main()
