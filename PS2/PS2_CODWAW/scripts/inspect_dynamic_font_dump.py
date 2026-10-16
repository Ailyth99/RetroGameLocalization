"""Read cache diagnostics from a user-exported 32 MiB EE RAM dump. Read only."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('magic version size calls hits loads evictions fences opens blocks read_bytes errors '
        'last_error last_key font_resets tree_failures max_request direct_misses '
        'io_timeouts finish_timeouts bytes_reserved resident_hits io_ticks fence_ticks '
        'decode_ticks write_ticks miss_batches max_batch_ticks last_batch_ticks batch_ticks').split()
ERRORS={3:'FONT count/dimensions mismatch',4:'texture object absent',5:'TIM2 format mismatch',
        6:'DMA system not ready',7:'command buffer missing',8:'GS FINISH timeout',9:'bank open failed',
        10:'bank read reached unexpected EOF',11:'bank read timeout',12:'bank/ELF identity mismatch',
        13:'glyph header out of read buffer',14:'invalid/truncated glyph block',15:'glyph bounds invalid'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('dump',type=Path)
    args=parser.parse_args();data=args.dump.read_bytes();assert len(data)==32*1024*1024
    state=json.loads((ROOT/'SOUND/research/dynamic_font_cache/installed_build.json').read_text(encoding='utf-8'))
    address=int(state['diagnostics_address'],16)
    words=struct.unpack_from('<32I',data,address)
    assert words[0]==0x4643485a and words[1] in (1,2) and words[2]==128,'Dump does not contain this dynamic-cache build'
    counters=dict(zip(FIELDS if words[1]==2 else FIELDS[:21],words))
    counters['last_error_description']=ERRORS.get(counters['last_error'],'none')
    result={'dump':str(args.dump),'sha256':hashlib.sha256(data).hexdigest(),
            'diagnostics_address':hex(address),'counters':counters,
            'note':'Counters identify cache activity/errors; zero errors does not prove a complete level passed'}
    if 'profile_diagnostics_address' in state:
        addr=int(state['profile_diagnostics_address'],16)
        values=struct.unpack_from('<8I',data,addr)
        assert values[:2]==(0x5052485a,1),'Dump does not contain the matching profile loader'
        result['profile_counters']=dict(zip(('magic','version','loads','errors','read_bytes','ticks','current_profile','last_error'),values))
        result['profile_diagnostics_address']=hex(addr)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
