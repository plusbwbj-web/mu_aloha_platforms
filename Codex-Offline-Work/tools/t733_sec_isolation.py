"""HOLD compile audit. Supports actual CLANGPDB LLVM-LTO and ordinary COFF."""
from pathlib import Path
import argparse,json,hashlib,struct,subprocess,shutil,re
R=Path.cwd();p=argparse.ArgumentParser();p.add_argument('mode',choices=['configure','verify']);p.add_argument('--profile',choices=['control','isolation'],required=True)
p.add_argument('--zig-ir-reader',type=Path,help='Explicit local fallback when llvm-dis is unavailable; never executes firmware')
a=p.parse_args();H=R/'Platforms/AndromedaPkg/Include/Library/T733SecIsolationPolicy.h';entry=R/'Platforms/AndromedaPkg/PrePi/AArch64/ModuleEntryPoint.S'
sha=lambda b:hashlib.sha256(b).hexdigest()
SOURCES={'PlatformPeiLib.obj':'Silicon/QC/Sm7325/QcomPkg/PlatformPei/PlatformPeiLib.c','PrePi.obj':'Platforms/AndromedaPkg/PrePi/PrePi.c'}
ENTRY_SHA='0ae14a28c23050b748eadbcc55a24c241b3400557a563aeac2c2c6126a6be809'
if a.mode=='configure':
 s=H.read_text();assert s.count('#define T733_SEC_ISOLATION_HOLD 0')==1
 e=entry.read_text();assert sha((e.rstrip()+'\n').encode())==ENTRY_SHA
 assert '#define T733_SEC_CHECKPOINT_SECONDS 12' in e and 'b _T733SecCheckpointHalt' in e and 'unreachable' in e
 H.write_text(s.replace('#define T733_SEC_ISOLATION_HOLD 0','#define T733_SEC_ISOLATION_HOLD '+str(int(a.profile=='isolation'))))
 out={'profile':a.profile,'entry_sha256':sha(entry.read_bytes()),'normalized_entry_sha256':ENTRY_SHA,
  'source_sha256':{v:sha((R/v).read_bytes()) for v in SOURCES.values()},'policy_sha256':sha(H.read_bytes()),'HOLD':True,'firmware_runtime_or_flash_authorized':False}
 (R/'t733-sec-isolation-inputs.json').write_text(json.dumps(out,indent=2));print(json.dumps(out));raise SystemExit
def coff_symbols(b):
 assert len(b)>=20 and b[:2]==b'\x64\xaa','not ordinary AArch64 COFF'
 ptr,count=struct.unpack_from('<II',b,8);assert ptr+count*18+4<=len(b)
 strings=b[ptr+count*18:];ss=struct.unpack_from('<I',strings)[0];assert 4<=ss<=len(strings)
 result=[];i=0
 while i<count:
  q=ptr+i*18;name=b[q:q+8]
  if name[:4]==b'\0'*4:
   off=struct.unpack_from('<I',name,4)[0];assert 4<=off<ss;name=strings[off:strings.index(0,off)]
  else:name=name.rstrip(b'\0')
  result.append(name.decode(errors='replace'));i+=1+b[q+17]
 return result
def lto_ir(path):
 tool=shutil.which('llvm-dis') or shutil.which('llvm-dis-19')
 fixed=Path('/workspace/.cloud-setup/toolchain/usr/lib/llvm-19/bin/llvm-dis')
 if not tool and fixed.is_file():tool=str(fixed)
 out=path.with_suffix('.obj.ll')
 if tool:cmd=[tool,str(path),'-o',str(out)]
 elif a.zig_ir_reader:cmd=[str(a.zig_ir_reader),'clang','-cc1','-triple','aarch64-unknown-windows-msvc','-emit-llvm','-x','ir',str(path),'-o',str(out)]
 else:raise RuntimeError('LLVM bitcode detected but llvm-dis unavailable; audit must stop')
 q=subprocess.run(cmd,capture_output=True,text=True);assert q.returncode==0,q.stdout+q.stderr
 return out.read_text(),out
receipt=json.loads((R/'t733-sec-isolation-inputs.json').read_text());assert receipt['profile']==a.profile and receipt['normalized_entry_sha256']==ENTRY_SHA
assert sha(entry.read_bytes())==receipt['entry_sha256'] and sha(H.read_bytes())==receipt['policy_sha256']
root=R/'Build/KodiakT733RetainedSec';rows=[]
for name,forbidden in [('PlatformPeiLib.obj','InitProtocolFinder'),('PrePi.obj','StartUpScheduler')]:
 paths=list(root.rglob(name));assert paths,('missing build object',name)
 for f in paths:
  raw=f.read_bytes();src=R/SOURCES[name];assert sha(src.read_bytes())==receipt['source_sha256'][SOURCES[name]]
  row={'file':str(f.relative_to(R)),'sha256':sha(raw),'symbol':forbidden,'source_sha256':sha(src.read_bytes())}
  if raw[:4]==b'BC\xc0\xde':
   text,ir=lto_ir(f);calls=re.findall(r'\b(?:call|invoke)\b[^\n]*@'+forbidden+r'\(',text);present=bool(calls)
   md5=hashlib.md5(src.read_bytes()).hexdigest();base=Path(SOURCES[name]).name
   matches=[l for l in text.splitlines() if '!DIFile(' in l and 'filename:' in l and '/'+base+'"' in l]
   assert matches and all('checksumkind: CSK_MD5' in l and 'checksum: "'+md5+'"' in l for l in matches),'compiler source checksum mismatch'
   row.update(format='LLVM bitcode',method='Actual IR call/invoke instructions',call_count=len(calls),IR_sha256=sha(ir.read_bytes()),compiler_source_MD5_matches=True)
   if name=='PlatformPeiLib.obj':
    assert re.search(r'^@ShLib = .*global',text,re.M)
    assert re.search(r'\bcall\b[^\n]*@BuildGuidDataHob\([^\n]*@gEfiShLibHobGuid',text)
    for h in ['gEfiInfoBlkHobGuid','gEfiSchedIntfGuid','gFvDecompressHobGuid']:
     assert bool(re.search(r'\bcall\b[^\n]*@BuildGuidDataHob\([^\n]*@'+h+r'\b',text))==(a.profile=='control')
    row['own_ShLib_HOB_retained']=True
  elif raw[:2]==b'\x64\xaa':
   present=forbidden in coff_symbols(raw);row.update(format='AArch64 COFF',method='COFF symbol reference, not an IR call proof')
  else:raise RuntimeError('Unsupported object format: '+str(f))
  assert present==(a.profile=='control'),(str(f),forbidden,present,a.profile)
  row['present']=present;rows.append(row)
out={'status':'COMPILE_OBJECT_AUDIT_PASS','profile':a.profile,'objects':rows,
 'scope':'Two source objects only; not all drivers, linked FD ownership or runtime independence.',
 'checkpoint_retained':True,'entry_sha256':sha(entry.read_bytes()),'HOLD':True,'no_BOOT_package':True,'no_device_operation':True}
(R/'t733-sec-isolation-objects.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
