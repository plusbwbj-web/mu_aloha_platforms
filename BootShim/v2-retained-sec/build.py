"""Build isolated v2 variants with the existing Zig/Clang, retain ELF symbols."""
import argparse,json,struct,subprocess,hashlib
from pathlib import Path
def extract(elf):
    b=elf.read_bytes(); assert b[:5]==b'\x7fELF\x02'
    shoff=struct.unpack_from('<Q',b,40)[0]; sz,n,si=struct.unpack_from('<HHH',b,58)
    sh=[struct.unpack_from('<IIQQQQIIQQ',b,shoff+i*sz) for i in range(n)]
    names=b[sh[si][4]:sh[si][4]+sh[si][5]]
    cstr=lambda data,off:data[off:data.index(0,off)].decode()
    text=next(s for s in sh if cstr(names,s[0])=='.text'); binary=b[text[4]:text[4]+text[5]]
    symbols={}
    for s in sh:
        assert s[1] not in [4,9] or s[5]==0,'Unresolved relocations'
        if s[1]!=2:continue
        st=sh[s[6]];strings=b[st[4]:st[4]+st[5]]
        for pos in range(s[4],s[4]+s[5],s[9]):
            name,info,other,ndx,value,size=struct.unpack_from('<IBBHQQ',b,pos)
            if name and ndx:symbols[cstr(strings,name)]=value
    assert len(binary)==4096 and symbols['_payload']==4096
    assert struct.unpack_from('<QQQ',binary,8)==(0x80000,0x2be000,10)
    return binary,symbols
def main():
    p=argparse.ArgumentParser();p.add_argument('--zig',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);src=Path(__file__).parent
    cfg=json.loads((src/'layout-profile.json').read_text())
    assert int(cfg['UEFI_BASE'],0)==0x9fc43000 and int(cfg['UEFI_SIZE'],0)==0x2bd000
    rows={}
    for mode,value in [('guarded',0),('lab',1)]:
        elf=a.out/(mode+'.elf');cmd=[str(a.zig),'cc','-target','aarch64-freestanding-none','-nostdlib','-Wl,-T,'+str(src/'link.ld'),'-Wl,--build-id=none','-DLAB_MEMORY_CONTRACT='+str(value),str(src/'BootShim.S'),'-o',str(elf)]
        r=subprocess.run(cmd,capture_output=True,text=True);(a.out/(mode+'-build.log')).write_text(r.stdout+r.stderr);r.check_returncode()
        binary,symbols=extract(elf);(a.out/(mode+'.bin')).write_bytes(binary);(a.out/(mode+'-symbols.json')).write_text(json.dumps(symbols,indent=2))
        rows[mode]={'bytes':len(binary),'sha256':hashlib.sha256(binary).hexdigest(),'command':cmd,'assembly_sha256':hashlib.sha256((src/'BootShim.S').read_bytes()).hexdigest()}
    (a.out/'build.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
