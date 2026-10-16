"""Read-only Ghidra HTTP queries, with complete responses saved for research.

Examples: python -X utf8 scripts/ghidra_research.py d:0x0020fd60 x:0x00492fa0
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SOUND/research/subtitle_test_20261004"
ENDPOINTS = {"d": "decompile_function", "x": "get_xrefs_to",
             "callers": "get_function_callers", "asm": "disassemble_function",
             "read": "read_memory", "from": "get_xrefs_from"}

def query(spec):
    parts = spec.split(":")
    endpoint = ENDPOINTS[parts[0]]
    params = {"address": parts[1], "program": "slus_217.46"}
    if parts[0] == "read":
        params["length"] = int(parts[2], 0)
    with urlopen("http://127.0.0.1:8089/" + endpoint + "?" + urlencode(params), timeout=45) as response:
        result = response.read().decode("utf-8").replace("\r", "")
    return {"time": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint,
            "params": params, "result": result}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(query, sys.argv[1:]))
    with (OUT / "ghidra_reads.jsonl").open("a", encoding="utf-8") as log:
        for result in results:
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(result["endpoint"], result["params"])
            text = result["result"]
            if len(text) > 22000:
                print(text[:22000], "\n[Console output shortened; complete response saved in log]")
            else:
                print(text)
