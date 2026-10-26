"""Execute actual linked AArch64 instructions in Unicorn; never execute on device.
MRS inputs are injected: this does NOT model silicon caches or exception routing.
"""
import argparse,json,struct,hashlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_INSN,UC_HOOK_MEM_WRITE,UC_HOOK_MEM_READ
from unicorn.arm64_const import *
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
BASE=0x9fc43000;SIZE=0x2bd000;DTB=0x90000000
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--fd',type=Path,required=True);a=p.parse_args()
    lab=(a.out/'lab.bin').read_bytes();guard=(a.out/'guarded.bin').read_bytes();sy=json.loads((a.out/'lab-symbols.json').read_text());fd=a.fd.read_bytes();assert len(fd)==SIZE
    ins=list(Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(lab[64:sy['_fd_base']],64))
    cache={i.address:i.mnemonic+' '+i.op_str for i in ins if i.mnemonic in ['dc','ic','dsb','isb']}
    x1add=next(i.address for i in ins if i.mnemonic=='adds' and i.op_str.startswith('x2, x1,'))
    cases=[
      ('disjoint-low',0x81080000,0,{}),('disjoint-high',0xa1080000,0,{}),
      ('backward-overlap',BASE-0x2000,0,{}),('source-equals-target',BASE-4096,0,{}),
      ('forward-overlap-covers-shim',BASE+0x1000,6,{}),('target-covers-shim',BASE,6,{}),
      ('el2-disjoint',0x81080000,0,{'el':8}),('el0',0x81080000,1,{'el':0}),('el3',0x81080000,1,{'el':12}),
      ('mmu-on',0x81080000,2,{'sctlr':1}),('dcache-on',0x81080000,2,{'sctlr':4}),('big-endian',0x81080000,2,{'sctlr':0x2000000}),('icache-on',0x81080000,0,{'sctlr':4096}),
      ('source-outside-envelope',0x71080000,5,{}),('source-misaligned',0x81080004,5,{}),
      ('source-overflow',0x81080000,3,{'source_overflow':True}),('destination-overflow',0x81080000,3,{'dest':0xfffffffffffff000}),
      ('target-not-allowlisted',0x81080000,4,{'dest':BASE+16}),('wrong-size',0x81080000,4,{'size':SIZE-16}),
      ('dtb-bad-magic',0x81080000,7,{'bad_dtb':True}),('dtb-null',0x81080000,7,{'dtb':0}),
      ('dtb-misaligned',0x81080000,7,{'dtb':DTB+1}),('dtb-too-small',0x81080000,7,{'dtb_size':39}),('dtb-too-large',0x81080000,7,{'dtb_size':0x200001}),('dtb-destination-conflict',0x81080000,8,{'dtb':BASE+0x100}),
      ('dtb-source-conflict',0x81080000,9,{'dtb':0x81082000}),
      ('guarded-no-write',0x81080000,10,{'guarded':True}),('line128',0x81080000,0,{'ctr':(5<<16)|5}),
      ('guarded-unmapped-dtb',0x81080000,10,{'guarded':True,'dtb':0x92000000,'unmapped_dtb':True}),
      ('guarded-invalid-dtb',0x81080000,10,{'guarded':True,'bad_dtb':True}),
      ('guarded-null-dtb',0x81080000,10,{'guarded':True,'dtb':0}),
      ('guarded-dtb-in-stack',0x81080000,10,{'guarded':True,'dtb':0x9ff91000})]
    results=[]
    for name,entry,expected,opt in cases:
        code=bytearray(guard if opt.get('guarded') else lab)
        if 'dest'in opt:struct.pack_into('<Q',code,sy['_fd_base'],opt['dest'])
        if 'size'in opt:struct.pack_into('<Q',code,sy['_fd_size'],opt['size'])
        uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);mapped=set()
        def maprange(start,length):
            lo=start&~4095;hi=(start+length+4095)&~4095
            for page in range(lo,hi,4096):
                if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
        maprange(BASE-4096,SIZE+8192);maprange(entry,len(code)+len(fd));maprange(DTB,4096)
        uc.mem_write(entry,bytes(code)+fd);dt=opt.get('dtb',DTB)
        if dt>=0x80000000 and not opt.get('unmapped_dtb'):
            maprange(dt,4096);uc.mem_write(dt,struct.pack('>10I',0 if opt.get('bad_dtb') else 0xd00dfeed,opt.get('dtb_size',40),40,40,40,17,16,0,0,0))
        uc.reg_write(UC_ARM64_REG_X0,dt);uc.reg_write(UC_ARM64_REG_PSTATE,0x3c5)
        state={'stop':None,'writes':0,'cache':{},'order':[]}
        # Unicorn does not execute SCTLR_EL2 reads in this environment. Inject
        # all MRS at the instruction boundary consistently, including CurrentEL.
        # Remaining instructions execute normally; this is NOT an EL2 CPU test.
        mrs_ops={i.address:i.op_str for i in ins if i.mnemonic=='mrs'}
        def inject_mrs(u,address,size,data):
            reg,sys=mrs_ops[address-entry].split(', ')
            if sys.lower()=='currentel':value=opt.get('el',4)
            elif sys.lower() in ['sctlr_el1','sctlr_el2']:value=opt.get('sctlr',0)
            elif sys.lower()=='ctr_el0':value=opt.get('ctr',(4<<16)|4)
            else:raise AssertionError(sys)
            u.reg_write(globals()['UC_ARM64_REG_'+reg.upper()],value)
            u.reg_write(UC_ARM64_REG_PC,address+4)
        for off in mrs_ops:uc.hook_add(UC_HOOK_CODE,inject_mrs,None,entry+off,entry+off)
        def stop(u,address,size,data):state['stop']=u.reg_read(UC_ARM64_REG_X16);u.emu_stop()
        uc.hook_add(UC_HOOK_CODE,stop,None,entry+sy['_halt']+4,entry+sy['_halt']+4)
        # Stop only on the actual handoff BR, not at entry which may equal BASE.
        branch=next(i.address for i in ins if i.mnemonic=='br' and i.op_str=='x5')
        def handoff(u,address,size,data):
            assert u.reg_read(UC_ARM64_REG_X5)==BASE
            state['stop']=0;u.emu_stop()
        uc.hook_add(UC_HOOK_CODE,handoff,None,entry+branch,entry+branch)
        def write(u,access,address,size,value,data):
            assert BASE<=address and address+size<=BASE+SIZE,(name,hex(address));state['writes']+=size
        uc.hook_add(UC_HOOK_MEM_WRITE,write)
        def read(u,access,address,size,value,data):
            if opt.get('guarded'):
                assert not (dt<=address<dt+40),(name,'guarded DTB dereference',hex(address))
        uc.hook_add(UC_HOOK_MEM_READ,read)
        def trace(u,address,size,data):
            op=cache[address-entry];state['cache'][op]=state['cache'].get(op,0)+1
            typ=op.split()[0]
            if not state['order'] or state['order'][-1]!=typ:state['order'].append(typ)
        for off in cache:uc.hook_add(UC_HOOK_CODE,trace,None,entry+off,entry+off)
        if opt.get('source_overflow'):
            uc.hook_add(UC_HOOK_CODE,lambda u,*args:u.reg_write(UC_ARM64_REG_X1,0xfffffffffffff800),None,entry+x1add,entry+x1add)
        uc.emu_start(entry,0,count=3000000)
        assert state['stop']==expected,(name,state)
        if expected==0:
            assert bytes(uc.mem_read(BASE,SIZE))==fd,name
            assert uc.reg_read(UC_ARM64_REG_X0)==dt
            assert all(uc.reg_read(r)==0 for r in [UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3])
            assert state['order']==['dc','dsb','ic','dsb','isb'],state
            lines=SIZE//(128 if opt.get('ctr') else 64)
            assert state['cache']['dc cvau, x7']==lines and state['cache']['ic ivau, x7']==lines
        else:
            assert state['writes']==0 and not state['cache'],(name,state)
            assert uc.reg_read(UC_ARM64_REG_X17)==0x5632
        results.append({'case':name,'passed':True,**state});print(name,'PASS',flush=True)
    # Forward-overlap memmove unit: full entry correctly rejects such layouts
    # because an adjacent shim would be overwritten. Test its actual loop alone.
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(0x80000000,0x10000);u.mem_write(0x80000000,lab)
    payload=bytes(range(256))*4;u.mem_write(0x80005010,payload)
    for r,v in [(UC_ARM64_REG_X7,0x80005010),(UC_ARM64_REG_X8,0x80005000),(UC_ARM64_REG_X12,len(payload))]:u.reg_write(r,v)
    u.emu_start(0x80000000+sy['_copy_forward'],0x80000000+sy['_sync'],count=20000)
    assert bytes(u.mem_read(0x80005000,len(payload)))==payload
    results.append({'case':'forward-overlap-loop-unit','passed':True})
    (a.out/'instruction-tests.json').write_text(json.dumps({'input_kind':'SYNTHETIC_BYTES_NOT_UEFI','engine':'Unicorn 2.1.4','system_registers':'MRS injected; real cache coherence not modelled','lab_sha256':hashlib.sha256(lab).hexdigest(),'guarded_sha256':hashlib.sha256(guard).hexdigest(),'fd_sha256':hashlib.sha256(fd).hexdigest(),'cases':results},indent=2))
    print('PASS',len(results),'instruction tests')
if __name__=='__main__':main()
