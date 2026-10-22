#!/usr/bin/env python3
"""Inspect the built shim and model its 16-byte data copy (not CPU emulation)."""

import argparse
import json
from pathlib import Path
import struct


def forward_copy_model(source, destination, length):
    memory = bytearray((n * 37 + n // 13) % 256 for n in range(1024))
    expected = bytes(memory[source:source + length])
    if source != destination:
        for offset in range(0, length, 16):
            memory[destination + offset:destination + offset + 16] = memory[source + offset:source + offset + 16]
    return bytes(memory[destination:destination + length]) == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    shim = (args.repo / 'BootShim/BootShim.bin').read_bytes()
    config = json.loads((args.repo / 'build_cfg/sm7325.json').read_text())['bootshim']
    base, size = struct.unpack_from('<QQ', shim, 8)
    # These are the currently audited LDP/STP/SUBS/B.NE/BR encodings. Fail if the
    # assembly changes instead of claiming that a stale model describes it.
    expected = {0x54: 0xA8C10C82, 0x58: 0xA8810CA2, 0x5C: 0xF10040C6,
                0x60: 0x54FFFFA1, 0x68: 0xD61F00A0}
    if any(struct.unpack_from('<I', shim, offset)[0] != word for offset, word in expected.items()):
        raise ValueError('BootShim instructions changed; copy model requires review')
    assert shim[56:60] == b'ARM\x64'
    assert (base, size) == (int(config['UEFI_BASE'], 0), int(config['UEFI_SIZE'], 0))
    assert size > 0 and size % 16 == 0
    instruction = struct.unpack_from('<I', shim)[0]
    assert instruction & 0x9F00001F == 0x10000001  # ADR x1, immediate
    immediate = ((instruction >> 5) & 0x7FFFF) * 4 + ((instruction >> 29) & 3)
    if immediate & (1 << 20):
        immediate -= 1 << 21
    assert immediate == len(shim), (immediate, len(shim))
    outcomes = {
        'disjoint_destination_above_source': forward_copy_model(128, 512, 256),
        'disjoint_destination_below_source': forward_copy_model(512, 128, 256),
        'already_in_place': forward_copy_model(128, 128, 256),
        'overlap_destination_above_source': forward_copy_model(128, 160, 256),
        'overlap_destination_below_source_data_only': forward_copy_model(160, 128, 256),
    }
    assert outcomes['disjoint_destination_above_source']
    assert outcomes['disjoint_destination_below_source']
    assert outcomes['already_in_place']
    assert not outcomes['overlap_destination_above_source']
    assert outcomes['overlap_destination_below_source_data_only']
    print(json.dumps({
        'validation_type': 'binary inspection and data-copy model; no CPU/cache/loader simulation',
        'shim_bytes': len(shim), 'payload_offset': immediate,
        'uefi_base': hex(base), 'uefi_size': size, 'uefi_end': hex(base + size),
        'copy_iterations': size // 16, 'model_data_matches': outcomes,
        'known_risks': [
            'Forward copy corrupts source when source < destination < source + size.',
            'The model excludes executing-shim overwrite, CPU state and cache coherency.',
            'Actual Samsung bootloader decompression source and entry state are unknown.',
        ],
    }, indent=2))


if __name__ == '__main__':
    main()
