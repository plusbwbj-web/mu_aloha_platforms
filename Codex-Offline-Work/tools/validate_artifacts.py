#!/usr/bin/env python3
"""Validate this repository's SM-T733 v0 image against its build inputs.

This is an offline format/integrity check, never a device boot or signing check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def align(value, page):
    return (value + page - 1) // page * page


def validate(repo, image_path, fd_path):
    repo = Path(repo)
    cfg = json.loads((repo / 'build_cfg/sm7325.json').read_text())
    base = int(cfg['bootshim']['UEFI_BASE'], 16)
    size = int(cfg['bootshim']['UEFI_SIZE'], 16)
    image, fd = Path(image_path).read_bytes(), Path(fd_path).read_bytes()
    shim = (repo / 'BootShim/BootShim.bin').read_bytes()
    dtb = (repo / 'Platforms/KodiakPkg/Device/samsung-gts7fewifi/DeviceTreeBlob/Android/android-gts7fewifi.dtb').read_bytes()
    ramdisk = (repo / 'PythonLibs/emptyramdisk').read_bytes()
    require(len(fd) == size, 'FD length does not equal UEFI_SIZE')
    require(base % 16 == size % 16 == 0, 'BootShim copy needs 16-byte aligned base/size')
    require(len(shim) >= 64 and shim[56:60] == b'ARM\x64', 'BootShim ARM64 magic missing')
    require(struct.unpack_from('<QQ', shim, 8) == (base, size), 'BootShim target differs from configuration')
    require(len(image) >= 1632 and image[:8] == b'ANDROID!', 'Android boot magic/header missing')
    fields = struct.unpack_from('<10I', image, 8)
    ks, ka, rs, ra, ss, sa, tags, page, version, osvalue = fields
    require(version == 0, 'SM-T733 validator expects boot header v0')
    require(page == cfg['default_aboot_args']['pagesize'] == 4096, 'Unexpected page size')
    require(ks > 0 and ss == 0 and sa == 0, 'Unexpected kernel or second-stage sizes')
    require(ka == 0x8000 and tags == 0x100, 'mkbootimg default load addresses changed')
    require(image[48:64] == bytes(16), 'Unexpected board name')
    require(image[64:576].rstrip(b'\0') == b'' and image[608:1632].rstrip(b'\0') == b'', 'Unexpected cmdline')
    require(not any(image[1632:page]), 'Nonzero boot-header page padding')
    encoded_version, patch = osvalue >> 11, osvalue & 0x7ff
    os_version = f'{encoded_version >> 14}.{(encoded_version >> 7) & 127}.{encoded_version & 127}'
    os_patch = f'{2000 + (patch >> 4):04d}-{patch & 15:02d}'
    require(os_version == '11.0.0' and os_patch == '2023-04', 'Boot header OS metadata changed')
    roff = page + align(ks, page)
    soff = roff + align(rs, page)
    require(len(image) == soff, 'Image is truncated or has an unexpected trailer')
    kernel = image[page:page + ks]
    packed_ramdisk = image[roff:roff + rs]
    require(packed_ramdisk == ramdisk and ra == (0x1000000 if rs else 0), 'Ramdisk differs from configured empty ramdisk')
    require(not any(image[page+ks:roff]) and not any(image[roff+rs:soff]), 'Nonzero image padding')
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    payload = dec.decompress(kernel) + dec.flush()
    require(dec.eof, 'GZIP stream did not terminate')
    require(payload == shim + fd, 'Decompressed payload differs from BootShim + independent FD')
    require(dec.unused_data == dtb, 'Appended DTB differs from SM-T733 source')
    require(len(dtb) >= 40 and dtb[:4] == b'\xd0\x0d\xfe\xed', 'DTB magic missing')
    dtb_size = struct.unpack_from('>I', dtb, 4)[0]
    require(dtb_size == len(dtb), 'DTB totalsize differs from appended data length')
    sha1 = hashlib.sha1()
    for blob in (kernel, packed_ramdisk, b''):
        sha1.update(blob)
        sha1.update(struct.pack('<I', len(blob)))
    require(image[576:608] == sha1.digest() + bytes(12), 'Android v0 image ID mismatch')
    volumes = []
    cursor = 0
    while True:
        signature = fd.find(b'_FVH', cursor)
        if signature < 0:
            break
        cursor = signature + 4
        start = signature - 40
        if start < 0 or start + 56 > len(fd):
            continue
        length = struct.unpack_from('<Q', fd, start + 32)[0]
        header_len = struct.unpack_from('<H', fd, start + 48)[0]
        if header_len < 56 or header_len % 2 or start + length > len(fd) or header_len > length:
            continue
        if fd[start+54] != 0 or fd[start+55] != 2:
            continue
        header = fd[start:start + header_len]
        if sum(struct.unpack('<' + 'H'*(header_len//2), header)) & 0xffff:
            continue
        block_length, terminated = 0, False
        for pos in range(56, header_len-7, 8):
            count, block_size = struct.unpack_from('<II', header, pos)
            if count == block_size == 0:
                terminated = True
                break
            if count == 0 or block_size == 0:
                break
            block_length += count * block_size
        if not terminated or block_length != length:
            continue
        volumes.append({'offset': start, 'length': length, 'header_length': header_len, 'header_checksum': 'passed'})
    require(volumes, 'No bounded UEFI firmware volume with a valid header checksum found')
    return {
        'result': 'passed', 'scope': 'offline format and integrity only; no hardware boot or AVB approval',
        'device': 'SM-T733/samsung-gts7fewifi',
        'artifacts': {str(Path(image_path)): {'bytes': len(image), 'sha256': digest(image)},
                      str(Path(fd_path)): {'bytes': len(fd), 'sha256': digest(fd)}},
        'boot_header': {'version': version, 'page_size': page, 'kernel_size': ks, 'kernel_addr': hex(ka),
                        'kernel_offset': page, 'ramdisk_size': rs, 'ramdisk_addr': hex(ra), 'ramdisk_offset': roff,
                        'tags_addr': hex(tags), 'os_version': os_version, 'os_patch_level': os_patch, 'image_id': 'passed'},
        'bootshim': {'bytes': len(shim), 'sha256': digest(shim), 'copy_base': hex(base), 'copy_size': size,
                     'copy_end': hex(base+size), 'payload_equals_inputs': True},
        'gzip': {'crc_and_length': 'passed', 'uncompressed_bytes': len(payload), 'compressed_bytes': ks-len(dtb)},
        'dtb': {'bytes': len(dtb), 'sha256': digest(dtb), 'totalsize': dtb_size, 'matches_source': True},
        'firmware_volumes': volumes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--img', type=Path)
    parser.add_argument('--fd', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = validate(args.repo, args.img or args.repo/'Build/KodiakPkg/samsung-gts7fewifi.img',
                      args.fd or args.repo/'Build/KodiakPkg/RELEASE_CLANGPDB/FV/SM7325_EFI.fd')
    text = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
