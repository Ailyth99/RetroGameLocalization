"""Read-only EE RAM capture from a Windows PCSX2 process when GDB/PINE are off."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path

class MBI(c.Structure):
    _fields_=[('BaseAddress',c.c_void_p),('AllocationBase',c.c_void_p),
              ('AllocationProtect',w.DWORD),('PartitionId',w.WORD),
              ('RegionSize',c.c_size_t),('State',w.DWORD),
              ('Protect',w.DWORD),('Type',w.DWORD)]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('pid',type=int)
    ap.add_argument('output',type=Path); args=ap.parse_args()
    k=c.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.VirtualQueryEx.argtypes=[w.HANDLE,c.c_void_p,c.POINTER(MBI),c.c_size_t]
    k.VirtualQueryEx.restype=c.c_size_t
    k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
    k.ReadProcessMemory.restype=w.BOOL
    k.CloseHandle.argtypes=[w.HANDLE]
    handle=k.OpenProcess(0x410,False,args.pid)
    if not handle: raise c.WinError(c.get_last_error())
    def read(addr,size):
        buf=c.create_string_buffer(size); n=c.c_size_t()
        if not k.ReadProcessMemory(handle,addr,buf,size,c.byref(n)): return b''
        return buf.raw[:n.value]
    root=Path(__file__).resolve().parents[1]
    elf=(root/'ISO_UNPACK/slus_217.46').read_bytes()
    va=0x2320b8; signature=elf[va-0x100000+0x80:va-0x100000+0x80+64]
    try:
        regions=[]; pos=0
        while pos<0x7fffffffffff:
            mbi=MBI()
            if not k.VirtualQueryEx(handle,pos,c.byref(mbi),c.sizeof(mbi)):break
            base=mbi.BaseAddress or 0; size=mbi.RegionSize
            if mbi.State==0x1000 and not mbi.Protect&0x101 and size>=0x1000:
                regions.append((base,size))
            pos=base+size
        # Protection boundaries may split the EE mapping into small host regions.
        candidates=[]
        for base,size in regions:
            for addr in range(base,base+size,0x400000):
                block=read(addr,min(0x400000,base+size-addr))
                found=block.find(signature)
                if found>=0:
                    start=addr+found-va
                    if start<0:continue
                    candidates.append(start)
                    ram=read(start,0x2000000)
                    if len(ram)==0x2000000:
                        args.output.parent.mkdir(parents=True,exist_ok=True)
                        args.output.write_bytes(ram)
                        print(json.dumps({'pid':args.pid,'host_ee_base':hex(start),
                                          'bytes':len(ram),'output':str(args.output)}))
                        return
        raise RuntimeError(f'EE mapping not found; signature candidates={candidates}')
    finally:k.CloseHandle(handle)

if __name__=='__main__':main()
