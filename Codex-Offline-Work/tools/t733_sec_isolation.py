"""Dedicated compile audit, not a firmware/device release tool."""
from pathlib import Path
import argparse,json,hashlib,struct
R=Path.cwd();p=argparse.ArgumentParser();p.add_argument('mode',choices=['configure','verify']);p.add_argument('--profile',choices=['control','isolation'],required=True);a=p.parse_args()
H=R/'Platforms/AndromedaPkg/Include/Library/T733SecIsolationPolicy.h'
entry=R/'Platforms/AndromedaPkg/PrePi/AArch64/ModuleEntryPoint.S'
sha=lambda b:hashlib.sha256(b).hexdigest()
if a.mode=='configure':
 s=H.read_text();assert s.count('#define T733_SEC_ISOLATION_HOLD 0')==1
 # Both builds keep the established non-returning SEC checkpoint.
 e=entry.read_text();assert '#define T733_SEC_CHECKPOINT_SECONDS 12' in e
 assert sha((e.rstrip()+'\n').encode())=='0ae14a28c23050b748eadbcc55a24c241b3400557a563aeac2c2c6126a6be809'
 assert 'b _T733SecCheckpointHalt' in e and 'unreachable' in e
 H.write_text(s.replace('#define T733_SEC_ISOLATION_HOLD 0','#define T733_SEC_ISOLATION_HOLD '+str(int(a.profile=='isolation'))))
 out={'profile':a.profile,'entry_sha256':sha(entry.read_bytes()),'HOLD':True,'firmware_runtime_or_flash_authorized':False}
 (R/'t733-sec-isolation-inputs.json').write_text(json.dumps(out,indent=2))
 print(json.dumps(out));raise SystemExit
def coff_symbols(path):
 b=path.read_bytes();assert len(b)>=20 and b[:2]==b'\x64\xaa',(str(path),'not ordinary AArch64 COFF object')
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
root=R/'Build/KodiakT733RetainedSec';rows=[]
for name,forbidden in [('PlatformPeiLib.obj','InitProtocolFinder'),('PrePi.obj','StartUpScheduler')]:
 paths=list(root.rglob(name));assert paths,('missing build object',name)
 for f in paths:
  symbols=coff_symbols(f);present=forbidden in symbols
  assert present==(a.profile=='control'),(str(f),forbidden,present,a.profile)
  rows.append({'file':str(f.relative_to(R)),'sha256':sha(f.read_bytes()),'symbol':forbidden,'present':present})
out={'status':'COMPILE_OBJECT_AUDIT_PASS','profile':a.profile,'objects':rows,
 'scope':'Two source objects only; not proof that every linked driver is independent of retained SEC.',
 'checkpoint_retained':True,'entry_sha256':sha(entry.read_bytes()),'HOLD':True,'no_BOOT_package':True,'no_device_operation':True}
(R/'t733-sec-isolation-objects.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
