#!/bin/bash
# Rootless Debian 13 firmware toolchain installation. APT verifies signed indexes
# and package hashes; no system or repository files are modified.
set -euo pipefail
setup_root=/workspace/.cloud-setup
mkdir -p "$setup_root/apt/lists/partial" "$setup_root/apt/archives/partial" "$setup_root/toolchain" "$setup_root/logs" "$setup_root/apt/conf.d"
cat > "$setup_root/apt/sources.list" <<'SOURCES'
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie-updates main
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://security.debian.org/debian-security trixie-security main
SOURCES
cat > "$setup_root/apt/apt.conf" <<'APTCONF'
Dir::Etc::parts "/workspace/.cloud-setup/apt/conf.d";
Dir::Etc::main "/dev/null";
APTCONF
apt_opts=(-o "Dir::Etc::sourcelist=$setup_root/apt/sources.list" -o 'Dir::Etc::sourceparts=-' -o "Dir::State=$setup_root/apt" -o "Dir::State::lists=$setup_root/apt/lists" -o 'Dir::State::status=/var/lib/dpkg/status' -o "Dir::Cache=$setup_root/apt" -o "Dir::Cache::archives=$setup_root/apt/archives" -o 'APT::Get::List-Cleanup=0' -o 'Debug::NoLocking=1')
APT_CONFIG="$setup_root/apt/apt.conf" /usr/bin/apt-get "${apt_opts[@]}" update
APT_CONFIG="$setup_root/apt/apt.conf" /usr/bin/apt-get "${apt_opts[@]}" --download-only --no-install-recommends -y install clang-19 llvm-19 lld-19 binutils-aarch64-linux-gnu gcc-aarch64-linux-gnu acpica-tools nasm uuid-dev mono-runtime mono-devel
for pkg in "$setup_root"/apt/archives/*.deb; do
    dpkg-deb --extract "$pkg" "$setup_root/toolchain"
done
cat > "$setup_root/toolchain-env.sh" <<'ACTIVATE'
# Source this file in Bash before running the UEFI build tools.
export PATH=/workspace/.cloud-setup/toolchain/usr/lib/llvm-19/bin:/workspace/.cloud-setup/toolchain/usr/bin:$PATH
export LD_LIBRARY_PATH=/workspace/.cloud-setup/toolchain/usr/lib/x86_64-linux-gnu:/workspace/.cloud-setup/toolchain/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export CPATH=/workspace/.cloud-setup/toolchain/usr/include${CPATH:+:$CPATH}
export LIBRARY_PATH=/workspace/.cloud-setup/toolchain/usr/lib/x86_64-linux-gnu${LIBRARY_PATH:+:$LIBRARY_PATH}
export CLANG_BIN=/workspace/.cloud-setup/toolchain/usr/lib/llvm-19/bin/
export CLANGPDB_BIN=/workspace/.cloud-setup/toolchain/usr/lib/llvm-19/bin/
export CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-
export MONO_GAC_PREFIX=/workspace/.cloud-setup/toolchain/usr
export MONO_CFG_DIR=/workspace/.cloud-setup/toolchain/etc
export MONO_PATH=/workspace/.cloud-setup/toolchain/usr/lib/mono/4.5
export XDG_CONFIG_HOME=/workspace/.cloud-setup/config
export XDG_DATA_HOME=/workspace/.cloud-setup/data
export XDG_CACHE_HOME=/workspace/.cloud-setup/cache
ACTIVATE
source "$setup_root/toolchain-env.sh"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"
cat /etc/ssl/certs/ca-certificates.crt > "$setup_root/mono-ca-certificates.pem"
if [ -n "${SSL_CERT_FILE:-}" ] && [ "$SSL_CERT_FILE" != /etc/ssl/certs/ca-certificates.crt ]; then
    cat "$SSL_CERT_FILE" >> "$setup_root/mono-ca-certificates.pem"
fi
mono "$setup_root/toolchain/usr/lib/mono/4.5/cert-sync.exe" --user "$setup_root/mono-ca-certificates.pem" > "$setup_root/logs/mono-cert-sync.log" 2>&1
clang --version
lld-link --version
aarch64-linux-gnu-gcc --version
nasm -v
iasl -v
mono --version
