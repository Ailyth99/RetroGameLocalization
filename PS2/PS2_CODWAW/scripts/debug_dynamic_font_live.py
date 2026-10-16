"""Persistent PCSX2-MCP driver for the user-authorized dynamic-font investigation.

Only stop the emulator launched by this process. PINE is explicitly a fallback
for live RAM access, not a claim that GDB register/step support is available.
"""
import json
from pathlib import Path
import sys
import time
import socket
import ctypes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'TEMP/runtime/vendor'))
from pcsx2_mcp import server
from pcsx2_pine_read import PineReader
import psutil

DATA = ROOT / 'TEMP/runtime/large_font_pcsx2'
EVIDENCE = ROOT / 'SOUND/research/dynamic_font_cache/live_debug'
CONFIG = DATA / 'PCSX2/inis/PCSX2.ini'
EXE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('C:/GAME/pcsx2-v2.0.2-windows-x64-Qt/pcsx2-qt.exe')
PORTABLE = EXE.parent == ROOT / 'TEMP/runtime/pcsx2_debug_portable'
if PORTABLE:
    CONFIG = EXE.parent / 'inis/PCSX2.ini'
EVIDENCE.mkdir(parents=True, exist_ok=True)
pid = None

def emit(value):
    value = {'time': time.time(), **value}
    with (EVIDENCE / 'session.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False) + '\n')
    print(json.dumps(value, ensure_ascii=False), flush=True)

emit({'ready': True})
for line in sys.stdin:
    if not line.strip():
        continue
    request = json.loads(line)
    try:
        action = request['action']
        if action == 'launch':
            if pid is not None and psutil.pid_exists(pid):
                raise RuntimeError('This driver already has a running emulator')
            if not request.get('manual_input'):
                server.background_input.gamepad.ensure()
            flags = ['-batch', '-slowboot' if request.get('fullboot') else '-fastboot']
            flags += ['-portable'] if PORTABLE else ['-datapath', str(DATA)]
            if request.get('break_on_entry'):
                flags.append('-debugger')
            result = server.launch_pcsx2(str(EXE), str(ROOT / 'COD5_TEST.iso'), flags)
            if result.get('ok'):
                pid = result['pid']
        elif action == 'connect':
            result = server.connect(target='ee', host='127.0.0.1', port=10501, auto_resume=True)
        elif action == 'debug':
            with socket.create_connection(('127.0.0.1',21512),timeout=10) as connection:
                connection.sendall((json.dumps(request['command'])+'\n').encode())
                result = json.loads(connection.makefile('rb').readline())
        elif action == 'capture':
            name = request['name']
            assert Path(name).name == name and name.endswith('.png')
            result = server.capture_pcsx2_window(str(EVIDENCE / name), pid)
        elif action == 'button':
            result = server.input_button_press(request['button'], request.get('ms', 200), 'xinput', pid, str(CONFIG))
        elif action == 'analog':
            result = server.input_analog_send(request.get('x', 0), request.get('y', 0),
                                               request.get('stick', 'left'), 'xinput', pid, str(CONFIG))
        elif action == 'reset_input':
            result = server.input_reset('xinput', pid)
        elif action == 'show':
            # Explicit user handoff: bring only our owned render window onscreen.
            assert pid is not None and Path(psutil.Process(pid).exe()).resolve() == EXE.resolve()
            window = server.window_capture.find_window([pid])
            hwnd = int(window['hwnd'], 16)
            u = ctypes.WinDLL('user32')
            u.ShowWindow(ctypes.c_void_p(hwnd), 9)
            u.SetWindowPos(ctypes.c_void_p(hwnd), None, 80, 60, 960, 780, 0x0040)
            u.SetForegroundWindow(ctypes.c_void_p(hwnd))
            result = {'shown_owned_pid': pid, 'hwnd': window['hwnd']}
        elif action == 'read':
            p = PineReader()
            try:
                data = p.read(int(request['address'], 0), int(request['length'], 0))
            finally:
                p.close()
            result = {'backend': 'PINE', 'data': data.hex()}
        elif action == 'dump':
            name = request['name']
            assert Path(name).name == name and name.endswith('.bin')
            p = PineReader()
            try:
                data = p.read(0, 0x2000000)
            finally:
                p.close()
            (EVIDENCE / name).write_bytes(data)
            result = {'backend': 'PINE', 'bytes': len(data), 'path': str(EVIDENCE / name)}
        elif action == 'stop':
            proc = psutil.Process(pid)
            assert Path(proc.exe()).resolve() == EXE.resolve()
            proc.terminate()
            proc.wait(10)
            result = {'stopped_owned_pid': pid}
            pid = None
        elif action == 'exit':
            server.background_input.gamepad.close()
            break
        else:
            raise ValueError(action)
        emit({'request': request, 'pid': pid, 'result': result})
    except Exception as error:
        emit({'request': request, 'pid': pid, 'error': str(error)})
