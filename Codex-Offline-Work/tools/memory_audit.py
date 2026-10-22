#!/usr/bin/env python3
"""Read-only SM-T733 DTB, static memory-map and ACPI structural audit.

This checks checked-in data. It cannot discover the device's live RAM map or
prove hardware compatibility. No third-party parser or device access required.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'Platforms/KodiakPkg/Device/samsung-gts7fewifi'

def parse_fdt(data):
    if len(data) < 40:
        raise ValueError('Truncated FDT header')
    h = struct.unpack_from('>10I', data)
    magic, total, off_struct, off_strings, off_reserve, version, last, cpu, size_strings, size_struct = h
    if magic != 0xd00dfeed or total > len(data) or version < 17:
        raise ValueError('Invalid FDT header/version/length')
    if off_struct + size_struct > total or off_strings + size_strings > total:
        raise ValueError('FDT blocks exceed total size')
    strings = data[off_strings:off_strings+size_strings]
    props, stack, nop_count = {}, [], 0
    pos, end = off_struct, off_struct + size_struct
    def cstring(blob, offset, limit):
        tail = blob.index(b'\0', offset, limit)
        return blob[offset:tail].decode('ascii'), tail+1
    while pos + 4 <= end:
        tag, = struct.unpack_from('>I', data, pos); pos += 4
        if tag == 1:
            name, pos = cstring(data, pos, end); pos = (pos+3) & ~3
            stack.append(name)
            props.setdefault('/'+'/'.join(stack[1:]), {})
        elif tag == 2:
            if not stack:
                raise ValueError('Unbalanced END_NODE')
            stack.pop()
        elif tag == 3:
            if pos+8 > end or not stack:
                raise ValueError('Invalid FDT property')
            length, nameoff = struct.unpack_from('>II', data, pos); pos += 8
            name, _ = cstring(strings, nameoff, len(strings))
            if pos+length > end:
                raise ValueError('Property exceeds structure')
            props['/'+'/'.join(stack[1:])][name] = data[pos:pos+length]
            pos = (pos+length+3) & ~3
        elif tag == 4:
            nop_count += 1
        elif tag == 9:
            if stack:
                raise ValueError('Unclosed FDT nodes')
            break
        else:
            raise ValueError(f'Unknown FDT tag {tag}')
    else:
        raise ValueError('Missing FDT_END')
    reserve = []
    pos = off_reserve
    while pos+16 <= total:
        address, size = struct.unpack_from('>QQ', data, pos); pos += 16
        if address == size == 0:
            break
        reserve.append((address, size))
    else:
        raise ValueError('Missing memory-reservation terminator')
    return props, reserve, {'total_size': total, 'version': version, 'nop_tags': nop_count}

def cells(value):
    if len(value) % 4:
        raise ValueError('Unaligned cell data')
    return struct.unpack('>'+str(len(value)//4)+'I', value)

def tuples(value, ac, sc):
    words = cells(value)
    if len(words) % (ac+sc):
        raise ValueError('reg property has incomplete tuple')
    def number(seq):
        out = 0
        for word in seq: out = (out << 32) | word
        return out
    return [(number(words[i:i+ac]), number(words[i+ac:i+ac+sc]))
            for i in range(0, len(words), ac+sc)]

def region(name, address, length, **extra):
    return {'name': name, 'base': address, 'length': length,
            'end_exclusive': address+length, **extra}

def overlaps(a, b):
    return (a['length'] > 0 and b['length'] > 0 and
            a['base'] < b['end_exclusive'] and b['base'] < a['end_exclusive'])

def audit_dtb(path, firmware):
    data = path.read_bytes()
    props, reserve, header = parse_fdt(data)
    root = props['/']
    ac = cells(root.get('#address-cells', b'\0\0\0\2'))[0]
    sc = cells(root.get('#size-cells', b'\0\0\0\1'))[0]
    memory, reserved, dynamic = [], [], []
    for name, p in props.items():
        if p.get('device_type', b'').rstrip(b'\0') == b'memory' and 'reg' in p:
            memory.extend(region(name, a, n) for a, n in tuples(p['reg'], ac, sc))
        if name.startswith('/reserved-memory/'):
            rp = props.get('/reserved-memory', {})
            rac = cells(rp.get('#address-cells', struct.pack('>I', ac)))[0]
            rsc = cells(rp.get('#size-cells', struct.pack('>I', sc)))[0]
            if 'reg' in p:
                reserved.extend(region(name, a, n) for a, n in tuples(p['reg'], rac, rsc))
            elif 'size' in p:
                dynamic.append({'name': name, 'size_cells': list(cells(p['size']))})
    reserved.extend(region('FDT memreserve', a, n) for a, n in reserve)
    return {'path': str(path.relative_to(ROOT)), 'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), **header,
            'model': root.get('model', b'').rstrip(b'\0').decode('ascii', 'replace'),
            'compatible': root.get('compatible', b'').rstrip(b'\0').decode('ascii', 'replace').split('\0'),
            'memory': memory, 'memory_bytes': sum(r['length'] for r in memory),
            'fixed_reserved': reserved, 'dynamic_reserved': dynamic,
            'firmware_fixed_reserved_overlaps': [r for r in reserved if overlaps(firmware, r)]}

def static_regions(serial_output):
    src = (TARGET/'Library/PlatformMemoryMapLib/PlatformMemoryMapLib.c').read_text()
    # Only this device's simple USE_MEMORY_FOR_SERIAL_OUTPUT conditional is
    # selected; C expressions are not evaluated or rewritten.
    active, selected = True, []
    for line in src.splitlines():
        if line.strip().startswith('#if USE_MEMORY_FOR_SERIAL_OUTPUT'):
            active = serial_output; continue
        if line.strip() == '#else': active = not active; continue
        if line.strip() == '#endif': active = True; continue
        if active: selected.append(line)
    pattern = r'\{\s*"([^"]+)"\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\}'
    out = [region(m[0], int(m[1], 16), int(m[2], 16), hob=m[3], resource=m[4], memory_type=m[6], attributes=m[7])
           for m in re.findall(pattern, '\n'.join(selected))]
    pairs = [{'a': a, 'b': b} for i, a in enumerate(out) for b in out[i+1:] if overlaps(a, b)]
    return {'serial_output': serial_output, 'regions': out, 'overlapping_pairs': pairs,
            'conventional_bytes': sum(r['length'] for r in out if r['memory_type'] == 'Conv' and r['resource'] == 'SYS_MEM')}

def audit_acpi(path):
    data = path.read_bytes()
    if len(data) < 8:
        raise ValueError('Truncated ACPI table')
    signature = data[:4].decode('ascii')
    length, = struct.unpack_from('<I', data, 4)
    result = {'path': str(path.relative_to(ROOT)), 'signature': signature,
              'file_size': len(data), 'declared_length': length,
              'length_matches': length == len(data),
              'sha256': hashlib.sha256(data).hexdigest()}
    if signature != 'FACS':
        if length < 36 or length > len(data):
            raise ValueError(f'Invalid ACPI length: {path}')
        result.update(checksum_ok=sum(data[:length]) % 256 == 0,
                      checksum_field=data[9],
                      oem_id=data[10:16].decode('ascii').strip(),
                      oem_table_id=data[16:24].decode('ascii').strip())
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    cfg = json.loads((ROOT/'build_cfg/sm7325.json').read_text())['bootshim']
    firmware = region('SM7325 UEFI FD', int(cfg['UEFI_BASE'], 16), int(cfg['UEFI_SIZE'], 16))
    dtb_paths = sorted((TARGET/'DeviceTreeBlob').glob('*/*.dtb'))
    empty_dtbs = [str(p.relative_to(ROOT)) for p in dtb_paths if p.stat().st_size == 0]
    dtbs = [audit_dtb(p, firmware) for p in dtb_paths if p.stat().st_size != 0]
    tables = [audit_acpi(TARGET/'ACPI/DSDT.aml')]
    include = ROOT/'Platforms/KodiakPkg/Include/ACPI.inc'
    for line in include.read_text().splitlines():
        if line.lstrip().startswith('#'): continue
        m = re.search(r'SECTION RAW = (SurfaceDuoACPI/[^\s]+)', line)
        if m: tables.append(audit_acpi(ROOT/'Platforms'/m.group(1)))
    result = {'scope': 'checked-in data only; no live RAM or hardware validation',
              'firmware_region': firmware, 'dtbs': dtbs,
              'empty_dtb_placeholders_unvalidated': empty_dtbs,
              'static_maps': [static_regions(False), static_regions(True)], 'acpi': tables}
    result['conventional_vs_android_fixed_reservation_overlaps_require_review'] = [
        {'uefi': r, 'android': reserved}
        for r in result['static_maps'][0]['regions']
        if r['memory_type'] == 'Conv' and r['resource'] == 'SYS_MEM'
        for reserved in dtbs[0]['fixed_reserved'] if overlaps(r, reserved)]
    # Vendor raw tables have zero placeholder checksums. AcpiTableDxe's
    # InstallAcpiTable passes Checksum=TRUE to AddTableToList, which computes
    # checksums on the installed copy. Preserve warnings; do not rewrite input.
    result['raw_acpi_checksum_warnings_require_runtime_recompute'] = [
        t['path'] for t in tables if t.get('checksum_ok') is False]
    text = json.dumps(result, indent=2, ensure_ascii=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else: print(text, end='')
    assert all(t['length_matches'] for t in tables), 'ACPI length failure'
    assert tables[0]['checksum_ok'], 'Device DSDT checksum failure'
    assert all(t.get('checksum_ok', True) or t['checksum_field'] == 0 for t in tables), 'Unexpected nonzero invalid ACPI checksum'
    assert all(not t['firmware_fixed_reserved_overlaps'] for t in dtbs), 'FD overlaps a fixed DTB reservation'
    assert all(t['memory'] for t in dtbs), 'DTB memory not found'

if __name__ == '__main__':
    main()
