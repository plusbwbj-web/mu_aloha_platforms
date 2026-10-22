#!/bin/bash
# Prepare the existing checkout; each cloud task is already isolated.
# Do not create a worktree or run build_setup.sh/timebuild.sh here: those scripts
# rewrite tracked version metadata. This script preserves source and lockfiles.
set -euo pipefail
aloha_tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
aloha_repo_root=$(cd -- "$aloha_tools_dir/../.." && pwd)
cd "$aloha_repo_root"
bash "$aloha_tools_dir/install-toolchain.sh"
source /workspace/.cloud-setup/toolchain-env.sh
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 or newer is required"'
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source "$aloha_tools_dir/activate.sh"
python -c 'import sys; assert sys.version_info >= (3, 12), "The existing .venv requires Python 3.12 or newer"'
python -m pip install --requirement pip-requirements.txt
python -m pip check
python - <<'PY'
from edk2toolext.bin.nuget import DownloadNuget
from pathlib import Path
import os

# The upstream downloader verifies its pinned NuGet.exe SHA-256 on every call.
print("Verified NuGet:", DownloadNuget())
local_tools = Path(".venv/local-tools")
local_tools.mkdir(exist_ok=True)
for name, scope, override in (
    ("nasm", "edk2-build", "nasm-1"),
    ("iasl", "cibuild", "iasl-ci-1"),
):
    target = Path("/workspace/.cloud-setup/toolchain/usr/bin") / name
    assert target.is_file() and os.access(target, os.X_OK), target
    link = local_tools / name
    if link.is_symlink():
        if link.resolve() != target.resolve():
            raise RuntimeError(f"Preserving unexpected local tool symlink: {link}")
    elif link.exists():
        raise RuntimeError(f"Preserving unexpected local tool file: {link}")
    else:
        link.symlink_to(target)
    # Only these two descriptors are managed; leave other local tools intact.
    descriptor = (
        '# Local host tools from signature-verified Debian packages.\n'
        '{\n'
        f'  "id": "codex-local-{name}",\n'
        f'  "scope": "{scope}",\n'
        f'  "override_id": "{override}",\n'
        '  "flags": [\n'
        '    "set_path"\n'
        '  ]\n'
        '}\n'
    )
    descriptor_file = local_tools / f"{name}_path_env.yaml"
    if descriptor_file.exists() and descriptor_file.read_text() != descriptor:
        raise RuntimeError(f"Preserving unexpected local descriptor: {descriptor_file}")
    descriptor_file.write_text(descriptor)
PY
aloha_nuget_path=$(python -c 'from edk2toolext.bin.nuget import DownloadNuget; print(DownloadNuget())')
mono "$aloha_nuget_path" help > /workspace/.cloud-setup/logs/nuget-help.log
stuart_setup -c Platforms/KodiakPkg/PlatformBuildNoSb.py -t RELEASE
stuart_update -c Platforms/KodiakPkg/PlatformBuildNoSb.py -t RELEASE
make -B -C BootShim -j4 UEFI_BASE=0x9FC41000 UEFI_SIZE=0x002BF000

# Exercise actual cross-compilation, PE/COFF linking and native build prerequisites.
aloha_smoke_dir=$(mktemp -d /workspace/.cloud-setup/compiler-smoke.XXXXXX)
trap 'rm -rf "$aloha_smoke_dir"' EXIT
cat > "$aloha_smoke_dir/arm.c" <<'C'
unsigned long add(unsigned long a, unsigned long b) { return a + b; }
C
aarch64-linux-gnu-gcc -ffreestanding -c "$aloha_smoke_dir/arm.c" -o "$aloha_smoke_dir/arm.o"
aarch64-linux-gnu-objdump -f "$aloha_smoke_dir/arm.o"
cat > "$aloha_smoke_dir/efi.c" <<'C'
unsigned long EfiMain(void *handle, void *system_table) { return 0; }
C
clang --target=aarch64-unknown-windows-msvc -ffreestanding -c "$aloha_smoke_dir/efi.c" -o "$aloha_smoke_dir/efi.obj"
lld-link /nologo /nodefaultlib /entry:EfiMain /subsystem:efi_application /machine:arm64 "/out:$aloha_smoke_dir/efi.efi" "$aloha_smoke_dir/efi.obj"
file "$aloha_smoke_dir/efi.efi"
cat > "$aloha_smoke_dir/uuid.c" <<'C'
#include <uuid/uuid.h>
int main(void) { uuid_t id; uuid_generate(id); return uuid_is_null(id); }
C
gcc "$aloha_smoke_dir/uuid.c" -o "$aloha_smoke_dir/uuid" -luuid
"$aloha_smoke_dir/uuid"
python - <<'PY'
from pathlib import Path
import json
import struct

cfg = json.loads(Path("build_cfg/sm7325.json").read_text())["bootshim"]
shim = Path("BootShim/BootShim.bin").read_bytes()
assert len(shim) == 112, len(shim)
assert shim[56:60] == b"ARM\x64", shim[56:60]
assert struct.unpack_from("<Q", shim, 8)[0] == int(cfg["UEFI_BASE"], 16)
assert struct.unpack_from("<Q", shim, 16)[0] == int(cfg["UEFI_SIZE"], 16)
assert Path("Platforms/KodiakPkg/Device/samsung-gts7fewifi/DeviceTreeBlob/Android/android-gts7fewifi.dtb").is_file()
print("PASS: Python dependencies, NuGet, Stuart setup/update, AArch64 GCC, ARM64 PE/COFF link, UUID and BootShim")
PY
