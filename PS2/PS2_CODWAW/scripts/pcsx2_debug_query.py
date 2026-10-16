"""Logged JSON/TCP queries to the explicitly launched PCSX2 DebugServer build."""
import json
from pathlib import Path
import socket
import time

OUT = Path(__file__).resolve().parents[1] / 'SOUND/research/dynamic_font_cache/live_debug'

def q(cmd, **params):
    request = {'cmd': cmd, 'cpu': 'ee', **params}
    with socket.create_connection(('127.0.0.1', 21512), timeout=15) as connection:
        connection.sendall((json.dumps(request)+'\n').encode())
        result = json.loads(connection.makefile('rb').readline())
    with (OUT/'debugserver.jsonl').open('a',encoding='utf-8') as log:
        log.write(json.dumps({'time':time.time(),'request':request,'result':result},ensure_ascii=False)+'\n')
    if not result.get('ok'):
        raise RuntimeError(result)
    return result

def regs():
    data = q('read_registers',category=0)['data']
    return {r['name']:r['value'] for category in data.values()
            if isinstance(category,dict) and 'regs' in category for r in category['regs']}
