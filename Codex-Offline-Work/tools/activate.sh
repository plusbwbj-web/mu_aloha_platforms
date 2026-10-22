#!/bin/bash
# Source this file from Bash to activate the prepared cloud build environment.
_aloha_tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
_aloha_repo_root=$(cd -- "$_aloha_tools_dir/../.." && pwd)
if [ ! -f /workspace/.cloud-setup/toolchain-env.sh ] || [ ! -f "$_aloha_repo_root/.venv/bin/activate" ]; then
    printf '%s\n' 'Run Codex-Offline-Work/tools/setup-cloud.sh before activation.' >&2
    return 1 2>/dev/null || exit 1
fi
source /workspace/.cloud-setup/toolchain-env.sh
source "$_aloha_repo_root/.venv/bin/activate"
export PIP_CACHE_DIR=/workspace/.cloud-setup/cache/pip
mkdir -p "$PIP_CACHE_DIR"
unset _aloha_tools_dir _aloha_repo_root
