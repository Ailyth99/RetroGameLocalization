"""Apply reviewed translation batches and credit-heading translations."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "TEXT/full_game"


def main():
    path = DIRECTORY / "catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in catalog}
    credits = json.loads((DIRECTORY / "credits_terms.json").read_text(encoding="utf-8"))
    credit_ids = set(range(310, 324)) | set(range(358, 430))
    for record in catalog:
        index, en = int(record["id"][1:]), record["en"]
        if not record["zh"] and len(en) == 1:
            record.update(zh=en, status="keyboard_character")
        elif not record["zh"] and 176 <= index <= 206:
            record.update(zh=en, status="credit_name")
        elif not record["zh"] and 209 <= index <= 225:
            record.update(zh=en[:-4] + "测试", status="translated")
        elif not record["zh"] and index in credit_ids and index != 313:
            lines = []
            for line in en.split("\n"):
                term = line.strip().rstrip(":")
                lines.append(credits[term] + ("：" if line.strip().endswith(":") else "")
                             if term in credits else line)
            zh = "\n".join(lines)
            record.update(zh=zh, status="credit_name" if zh == en else "translated")
    for batch in sorted((DIRECTORY / "batches").glob("*.json")):
        changes = json.loads(batch.read_text(encoding="utf-8"))
        for key, zh in changes.items():
            if key not in by_id or not zh:
                raise ValueError(f"Invalid translation in {batch}: {key}")
            by_id[key].update(zh=zh, status="translated")
    # Reuse exact text differing only in whitespace, preserving the target controls.
    normalize = lambda s: re.sub(r"\s+", " ", s).strip()
    known = {normalize(r["en"]): r["zh"] for r in catalog if r["zh"]}
    for record in catalog:
        if not record["zh"] and normalize(record["en"]) in known:
            record.update(zh=known[normalize(record["en"])], status="translated")
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending = [r for r in catalog if not r["zh"]]
    (ROOT / "TEMP/full_game/pending.jsonl").write_text("".join(
        json.dumps({"id": r["id"], "en": r["en"]}, ensure_ascii=False) + "\n" for r in pending), encoding="utf-8")
    print(f"{len(catalog) - len(pending)}/{len(catalog)} resolved; {len(pending)} pending")


if __name__ == "__main__":
    main()
