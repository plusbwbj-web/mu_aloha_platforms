#!/bin/bash
# Build and inspect only SM-T733; this script has no device-access operations.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo_root"
source /workspace/.cloud-setup/toolchain-env.sh
source .venv/bin/activate
variant=${1:-nosb}
case "$variant" in
  nosb) build_config=Platforms/KodiakPkg/PlatformBuildNoSb.py; suffix=NOSB ;;
  sb) build_config=Platforms/KodiakPkg/PlatformBuild.py; suffix=SB ;;
  *) echo 'Usage: bash Codex-Offline-Work/tools/build-sm-t733.sh [nosb|sb]' >&2; exit 2 ;;
esac
artifact_dir="$repo_root/Build/SM-T733-Codex/$variant"
mkdir -p "$artifact_dir"
read -r shim_base shim_size < <(python - <<'PY'
import json
c=json.load(open('build_cfg/sm7325.json'))
assert c['package']=='KodiakPkg' and c['platform']=='Sm7325'
print(c['bootshim']['UEFI_BASE'], c['bootshim']['UEFI_SIZE'])
PY
)
# The Makefile does not track changed -D values; force a fresh shim.
make -B -C BootShim -j4 "UEFI_BASE=$shim_base" "UEFI_SIZE=$shim_size"
printf 'Building SM-T733 %s; log: %s/build.log\n' "$suffix" "$artifact_dir"
if stuart_build -c "$build_config" TARGET=RELEASE TARGET_DEVICE=samsung-gts7fewifi MAX_CONCURRENT_THREAD_NUMBER=4 > "$artifact_dir/build.log" 2>&1; then
  tail -12 "$artifact_dir/build.log"
else
  result=$?
  tail -60 "$artifact_dir/build.log"
  exit "$result"
fi
cp Build/KodiakPkg/RELEASE_CLANGPDB/FV/SM7325_EFI.fd "$artifact_dir/SM7325_EFI_$suffix.fd"
cp Build/KodiakPkg/samsung-gts7fewifi.img "$artifact_dir/samsung-gts7fewifi_$suffix.img"
cp BootShim/BootShim.bin "$artifact_dir/BootShim.bin"
python Codex-Offline-Work/tools/validate_artifacts.py \
  --fd "$artifact_dir/SM7325_EFI_$suffix.fd" \
  --img "$artifact_dir/samsung-gts7fewifi_$suffix.img" \
  --output "Codex-Offline-Work/logs/$variant-artifacts.json"
git rev-parse HEAD > "$artifact_dir/source-head.txt"
git diff -- PythonLibs/PostBuild.py Platforms/AndromedaPkg/Driver/RamPartitionDxe/RamPartitionDxe.c > "$artifact_dir/source-changes.patch"
git submodule status --recursive > "$artifact_dir/submodules.txt"
sha256sum "$artifact_dir/SM7325_EFI_$suffix.fd" "$artifact_dir/samsung-gts7fewifi_$suffix.img" > "$artifact_dir/SHA256SUMS"
printf 'Offline format validation passed; artifacts: %s\n' "$artifact_dir"
