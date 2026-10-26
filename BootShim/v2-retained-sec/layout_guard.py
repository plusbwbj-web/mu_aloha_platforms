"""Reject static retained-SEC/FD conflicts. A pass never proves live RAM ownership."""
import argparse,struct,json
from pathlib import Path

def te_sections(te):
    if te[:4]!=b'VZ\x64\xaa':raise ValueError('expected AArch64 TE')
    ib=struct.unpack_from('<Q',te,16)[0];result=[]
    for i in range(te[4]):
        at=40+i*40;name=te[at:at+8].rstrip(b'\0').decode();size,va=struct.unpack_from('<II',te,at+8)
        result.append((name,ib+va,ib+va+size))
    return result

def audit_ranges(fd,sections,base,size):
    failures=[]
    if size<=0 or base<0 or base+size>1<<64:raise ValueError('invalid interval')
    end=base+size
    if len(fd)!=size:failures.append('FD_FILE_LENGTH_MISMATCH')
    if fd[40:44]!=b'_FVH':raise ValueError('expected FV at FD start')
    if struct.unpack_from('<Q',fd,32)[0]!=size:failures.append('FV_LENGTH_MISMATCH')
    # Audited outer FV/SEC/TE layout; locate and validate the TE in its first SEC file.
    hlen=struct.unpack_from('<H',fd,48)[0];ffs=(hlen+7)&~7;flen=int.from_bytes(fd[ffs+20:ffs+23],'little');pos=ffs+24;own_base=None
    while pos+4<=ffs+flen:
        n=int.from_bytes(fd[pos:pos+3],'little')
        if n<4 or pos+n>ffs+flen:raise ValueError('invalid section bounds')
        if fd[pos+3]==0x12:
            te=fd[pos+4:pos+n]
            if te[:4]!=b'VZ\x64\xaa':raise ValueError('invalid own TE')
            own_base=struct.unpack_from('<Q',te,16)[0];break
        pos=(pos+n+3)&~3
    if own_base is None:raise ValueError('SEC TE not found')
    if own_base!=base:failures.append('FD_LINKED_BASE_MISMATCH')
    if base<0x9fc00000 or end>0x9ff00000:failures.append('FD_EXCEEDS_STOCK_FD_DESCRIPTOR')
    overlaps=[]
    for name,start,limit in sections:
        lo=max(base,start);hi=min(end,limit)
        if lo<hi:overlaps.append({'section':name,'start':hex(lo),'end':hex(hi),'bytes':hi-lo})
    if overlaps:failures.append('RETAINED_STOCK_SEC_OVERLAP')
    return {'static_rejected':bool(failures),'failures':failures,'fd':[hex(base),hex(end)],'linked_base':hex(own_base),'retained_sec_overlaps':overlaps,'hardware_release':'HOLD: live ownership, entry state and diagnostics not certified by this checker'}

def audit(fd,stock_te,base,size):
    return audit_ranges(fd,te_sections(stock_te),base,size)

def main():
    p=argparse.ArgumentParser();p.add_argument('--fd',type=Path,required=True);p.add_argument('--stock-te',type=Path,required=True);p.add_argument('--base',type=lambda s:int(s,0),default=0x9fc41000);p.add_argument('--size',type=lambda s:int(s,0),default=0x2bf000);p.add_argument('--report',type=Path);a=p.parse_args()
    r=audit(a.fd.read_bytes(),a.stock_te.read_bytes(),a.base,a.size);s=json.dumps(r,indent=2)
    if a.report:a.report.write_text(s,encoding='utf-8')
    print(s);raise SystemExit(2 if r['static_rejected'] else 0)
if __name__=='__main__':main()
