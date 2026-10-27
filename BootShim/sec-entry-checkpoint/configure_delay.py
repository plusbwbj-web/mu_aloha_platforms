from pathlib import Path
import argparse,json,hashlib
p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,choices=[3,12],required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[2];f=r/'Platforms/AndromedaPkg/PrePi/AArch64/ModuleEntryPoint.S';s=f.read_text();old='#define T733_SEC_CHECKPOINT_SECONDS 12';assert s.count(old)==1;s=s.replace(old,'#define T733_SEC_CHECKPOINT_SECONDS '+str(a.seconds));f.write_text(s)
print(json.dumps({'checkpoint_seconds':a.seconds,'entry_source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'scope':'checkpoint never returns to UEFI initialization; not a runtime UEFI boot'}))
