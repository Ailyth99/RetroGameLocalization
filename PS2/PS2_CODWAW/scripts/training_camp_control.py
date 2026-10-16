"""Persistent PCSX2 MCP control for the training-camp audio investigation."""
from pathlib import Path
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SOUND/research/training_camp_20261004"
DATA = ROOT / "TEMP/runtime/large_font_pcsx2/PCSX2"
CONFIG = DATA / "inis/PCSX2.ini"
sys.path.insert(0, str(ROOT / "TEMP/runtime/vendor"))
from pcsx2_mcp import server

OUT.mkdir(parents=True, exist_ok=True)

def emit(value):
    line = json.dumps(value, ensure_ascii=False)
    with (OUT / "pcsx2_control.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                                 "event": value}, ensure_ascii=False) + "\n")
    print(line, flush=True)

try:
    server.background_input.gamepad.ensure()
    launch = server.launch_pcsx2(
        exe_path=r"C:\GAME\pcsx2-v2.0.2-windows-x64-Qt\pcsx2-qt.exe",
        game_path=str(ROOT / "COD5_Menu_Options_ZH_20261004.iso"),
        extra_args=["-batch", "-fastboot", "-datapath", str(DATA.parent)],
    )
    emit(launch)
    if not launch.get("ok"):
        raise SystemExit(1)
    pid = launch["pid"]
    (OUT / "launch.json").write_text(json.dumps(launch, indent=2), encoding="utf-8")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            action = request["action"]
            if action == "exit":
                break
            if action == "capture":
                name = Path(request.get("name", "current.png")).name
                result = server.capture_pcsx2_window(str(OUT / name), pid=pid)
            elif action == "button":
                result = server.input_button_press(request["button"], request.get("ms", 200),
                                                   "xinput", pid, str(CONFIG))
            elif action == "analog":
                result = server.input_analog_send(x=request.get("x", 0), y=request.get("y", 0),
                                                  stick=request.get("stick", "left"), backend="xinput")
            elif action == "reset":
                result = server.input_reset(backend="xinput")
            elif action == "connect":
                result = server.connect(target=request.get("target", "ee"), auto_resume=True)
            elif action == "read":
                result = server.read_memory(request["address"], request["length"])
            elif action == "status":
                result = server.status()
            else:
                raise ValueError(action)
            emit({"request": request, "result": result})
        except Exception as error:
            emit({"error": str(error)})
finally:
    server.background_input.gamepad.close()
