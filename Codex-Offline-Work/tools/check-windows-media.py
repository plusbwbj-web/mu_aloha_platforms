#!/usr/bin/env python3
"""Read-only ARM64 media / driver-source inventory. Never services or writes an image."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pe_machine(path: Path) -> int:
    if not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    with path.open("rb") as stream:
        head = stream.read(64)
        if len(head) != 64 or head[:2] != b"MZ":
            raise ValueError(f"invalid DOS/PE header: {path}")
        offset = struct.unpack_from("<I", head, 60)[0]
        if offset < 64 or offset + 26 > path.stat().st_size:
            raise ValueError(f"PE header outside file: {path}")
        stream.seek(offset)
        coff = stream.read(26)
        if coff[:4] != b"PE\0\0":
            raise ValueError(f"invalid PE signature: {path}")
        return struct.unpack_from("<H", coff, 4)[0]


def efi_machine(path: Path) -> int:
    machine = pe_machine(path)
    with path.open("rb") as stream:
        stream.seek(60)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset + 20)
        optional_size = struct.unpack("<H", stream.read(2))[0]
        if optional_size < 70 or offset + 24 + optional_size > path.stat().st_size:
            raise ValueError("EFI optional PE header absent or outside file")
        stream.seek(offset + 24)
        optional = stream.read(70)
    if struct.unpack_from("<H", optional, 0)[0] != 0x20B or struct.unpack_from("<H", optional, 68)[0] != 10:
        raise ValueError("EFI boot loader must have PE32+ magic and EFI_APPLICATION subsystem")
    return machine


def wim_metadata(path: Path) -> dict:
    """Read bounded, uncompressed WIM XML; does not verify complete WIM resources."""
    if not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    with path.open("rb") as stream:
        head = stream.read(148)
        if len(head) < 148 or head[:8] != b"MSWIM\0\0\0":
            raise ValueError(f"invalid WIM header: {path}")
        header_size, version, flags = struct.unpack_from("<III", head, 8)
        if header_size < 148 or header_size > path.stat().st_size:
            raise ValueError(f"invalid WIM header size: {path}")
        encoded_size, offset, original_size = struct.unpack_from("<QQQ", head, 72)
        stored_size = encoded_size & ((1 << 56) - 1)
        resource_flags = encoded_size >> 56
        if resource_flags & 4:
            raise ValueError("compressed WIM XML requires trusted wimlib/DISM inspection")
        if not 0 < stored_size <= 32 * 1024 * 1024:
            raise ValueError("invalid or excessive WIM XML size")
        if original_size != stored_size or offset < header_size or offset + stored_size > path.stat().st_size:
            raise ValueError("WIM XML resource outside file or inconsistent size")
        stream.seek(offset)
        xml_bytes = stream.read(stored_size)
    tree = ET.fromstring(xml_bytes)
    images = []
    for image in tree.findall("IMAGE"):
        windows = image.find("WINDOWS")
        images.append({
            "index": image.get("INDEX"), "name": image.findtext("NAME"),
            "architecture": windows.findtext("ARCH") if windows is not None else None,
            "edition": windows.findtext("EDITIONID") if windows is not None else None,
            "build": windows.findtext("VERSION/BUILD") if windows is not None else None,
        })
    count = struct.unpack_from("<I", head, 44)[0]
    if len(images) != count or not images:
        raise ValueError("WIM image count / XML mismatch or no images")
    return {"header_version": hex(version), "flags": hex(flags), "images": images,
            "scope": "header/XML only; resource integrity and licensing not verified"}


def media_report(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("media root must be an extracted directory")
    candidates = {}
    for path in root.rglob("*"):
        if path.is_file():
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError(f"symlink escapes media root: {path}")
            name = str(path.relative_to(root)).replace("\\", "/").casefold()
            if name in candidates:
                raise ValueError(f"case-insensitive media path collision: {path}")
            candidates[name] = path
    boot = candidates.get("efi/boot/bootaa64.efi")
    if boot is None or efi_machine(boot) != 0xAA64:
        raise ValueError("ARM64 EFI/BOOT/BOOTAA64.EFI missing or has wrong PE architecture")
    files = {"boot": candidates.get("sources/boot.wim"),
             "install": candidates.get("sources/install.wim") or candidates.get("sources/install.esd")}
    result = {"root": str(root), "arm64_efi_sha256": sha256(boot), "images": {}}
    for name, path in files.items():
        if path is None:
            raise ValueError(f"{name} WIM/ESD missing; split SWM needs separate DISM/wimlib inspection")
        data = wim_metadata(path)
        if any(image["architecture"] != "12" for image in data["images"]):
            raise ValueError(f"{name} image has missing or non-ARM64 architecture metadata")
        result["images"][name] = data
    result["scope"] = "offline structural ARM64 checks; no installation, signature trust, or device compatibility claim"
    return result


def decode_inf(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16").lstrip("\ufeff")
    return raw.decode("utf-8-sig", errors="replace")


def inf_sections(raw: bytes) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    section = ""
    for raw_line in decode_inf(raw).splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and "]" in line:
            section = line[1:line.index("]")].casefold()
            sections.setdefault(section, [])
        elif section:
            sections[section].append(line)
    return sections


def assignments(lines: list[str]) -> dict[str, str]:
    return {key.strip().casefold(): value.split(";", 1)[0].strip().strip('"')
            for line in lines if "=" in line for key, value in [line.split("=", 1)]}


def driver_report(root: Path) -> dict:
    root = root.resolve(strict=True)
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    paths = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "--name-only", "HEAD"], text=True).splitlines()
    tree_paths = {path.casefold(): path for path in paths}
    if len(tree_paths) != len(paths):
        raise ValueError("case-insensitive source path collision")
    all_basenames = {Path(path).name.casefold() for path in paths}
    records = []
    for rel in paths:
        if not rel.casefold().endswith(".inf"):
            continue
        path = root / rel
        if not path.is_file():
            raise ValueError(f"INF not checked out: {rel}")
        sections = inf_sections(path.read_bytes())
        version = assignments(sections.get("version", []))
        strings = assignments(sections.get("strings", []))
        provider = version.get("provider", "")
        if provider.startswith("%") and provider.endswith("%"):
            provider = strings.get(provider[1:-1].casefold(), provider)
        catalogs = []
        for key, value in version.items():
            if not key.startswith("catalogfile"):
                continue
            cat_rel = str(Path(rel).parent / value).replace("\\", "/")
            canonical = tree_paths.get(cat_rel.casefold())
            cat = root / canonical if canonical else None
            catalogs.append({"directive": key, "declared_name": value,
                             "present_in_git_tree": canonical is not None,
                             "sha256": sha256(cat) if cat and cat.is_file() else None})
        payloads = []
        for section, lines in sections.items():
            if section.startswith("sourcedisksfiles"):
                payloads.extend(assignments(lines))
        model_ids = sorted(set(re.findall(r"(?:ACPI|USB|PCI|ROOT|SWC)\\[A-Za-z0-9_&.\\{}-]+",
                               "\n".join(line for lines in sections.values() for line in lines), flags=re.I)))
        arm64 = any("ntarm64" in section for section in sections)
        records.append({"path": rel, "sha256": sha256(path), "class": version.get("class"),
                        "driver_version": version.get("driverver"), "provider": provider,
                        "arm64_section_present": arm64, "catalogs": catalogs, "hardware_ids": model_ids,
                        "source_payload_basename_count": len(set(payloads)),
                        "source_payload_basenames_absent_from_git_tree": sorted({p for p in payloads if p not in all_basenames}),
                        "source_payload_check_scope": "basename inventory only; not full INF package or Windows staging validation"})
    sys_files = []
    for path in sorted((root / "Drivers").rglob("*.sys")) if (root / "Drivers").is_dir() else []:
        sys_files.append({"path": str(path.relative_to(root)), "pe_machine": hex(pe_machine(path)), "sha256": sha256(path)})
    return {"source_root": str(root), "commit": revision, "inf_count": len(records), "inf": records,
            "locally_inspected_sys": sys_files,
            "scope": "Git source/INF/CAT presence and hashes; Windows catalog trust, rank, full payload and device compatibility unverified"}


def source_hash_report(root: Path) -> dict:
    root = root.resolve(strict=True)
    git_root = Path(subprocess.check_output(["git", "-C", str(root), "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    if root != git_root:
        raise ValueError("source-hashes root must be the Git checkout root")
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-rz", "HEAD"])
    records = []
    for item in tree.split(b"\0"):
        if not item:
            continue
        metadata, path_bytes = item.split(b"\t", 1)
        mode, kind, expected = metadata.decode().split()
        rel = path_bytes.decode()
        path = root / rel
        if kind != "blob" or mode == "120000":
            raise ValueError(f"entry needs separate submodule/symlink review: {rel}")
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"not a regular in-checkout file: {rel}")
        size = path.stat().st_size
        content_hash = hashlib.sha256()
        object_hash = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                content_hash.update(block)
                object_hash.update(block)
        if object_hash.hexdigest() != expected:
            raise ValueError(f"working copy bytes differ from Git blob: {rel}")
        records.append({"path": rel, "bytes": size, "sha256": content_hash.hexdigest(), "git_blob": expected})
    return {"repository": root.name, "commit": revision, "file_count": len(records),
            "all_worktree_bytes_match_git_blobs": True, "files": records}


def self_test() -> dict:
    """Synthetic negative/positive parser cases, never represented as real-media validation."""
    checks = 0
    with tempfile.TemporaryDirectory(prefix="arm64-media-check-") as temporary:
        root = Path(temporary)
        pe = bytearray(160)
        pe[:2] = b"MZ"; struct.pack_into("<I", pe, 60, 64)
        pe[64:68] = b"PE\0\0"; struct.pack_into("<H", pe, 68, 0xAA64)
        struct.pack_into("<H", pe, 84, 72)
        struct.pack_into("<H", pe, 88, 0x20B)
        struct.pack_into("<H", pe, 156, 10)
        target = root / "arm64.efi"; target.write_bytes(pe)
        assert pe_machine(target) == 0xAA64; checks += 1
        struct.pack_into("<I", pe, 60, 10000); target.write_bytes(pe)
        try:
            pe_machine(target)
            raise AssertionError("out-of-file PE offset accepted")
        except ValueError:
            checks += 1
        xml = '<WIM><IMAGE INDEX="1"><NAME>Fixture</NAME><WINDOWS><ARCH>12</ARCH><VERSION><BUILD>22621</BUILD></VERSION></WINDOWS></IMAGE></WIM>'.encode("utf-16")
        header = bytearray(208); header[:8] = b"MSWIM\0\0\0"
        struct.pack_into("<I", header, 8, 208); struct.pack_into("<I", header, 44, 1)
        struct.pack_into("<QQQ", header, 72, len(xml), 208, len(xml))
        wim = root / "fixture.wim"; wim.write_bytes(header + xml)
        assert wim_metadata(wim)["images"][0]["architecture"] == "12"; checks += 1
        struct.pack_into("<Q", header, 80, 100000); wim.write_bytes(header + xml)
        try:
            wim_metadata(wim)
            raise AssertionError("out-of-file XML offset accepted")
        except ValueError:
            checks += 1
        data = '[Version]\r\nDriverVer=01/01/2025,1.0\r\n[Models.NTARM64]\r\n'.encode("utf-16")
        assert assignments(inf_sections(data)["version"])["driverver"] == "01/01/2025,1.0"; checks += 1
        # An entire synthetic media tree must reject an x64 EFI loader or WIM.
        efi_dir = root / "efi/boot"; efi_dir.mkdir(parents=True)
        source_dir = root / "sources"; source_dir.mkdir()
        struct.pack_into("<I", pe, 60, 64)
        loader = efi_dir / "bootaa64.efi"; loader.write_bytes(pe)
        struct.pack_into("<Q", header, 80, 208)
        for name in ("boot.wim", "install.wim"):
            (source_dir / name).write_bytes(header + xml)
        assert media_report(root)["images"]["install"]["images"][0]["architecture"] == "12"; checks += 1
        struct.pack_into("<H", pe, 68, 0x8664); loader.write_bytes(pe)
        try:
            media_report(root)
            raise AssertionError("x64 loader accepted as ARM64")
        except ValueError:
            checks += 1
        struct.pack_into("<H", pe, 68, 0xAA64); loader.write_bytes(pe)
        wrong_xml = xml.replace("12".encode("utf-16le"), "9".encode("utf-16le"))
        struct.pack_into("<QQQ", header, 72, len(wrong_xml), 208, len(wrong_xml))
        (source_dir / "install.wim").write_bytes(header + wrong_xml)
        try:
            media_report(root)
            raise AssertionError("x64 WIM accepted as ARM64")
        except ValueError:
            checks += 1
    return {"synthetic_parser_checks_passed": checks, "real_windows_media_tested": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    media = sub.add_parser("media", help="Inspect an extracted Windows ARM64 installation tree, read-only")
    media.add_argument("root", type=Path)
    drivers = sub.add_parser("drivers", help="Inventory checked-out INF/CAT files in a pinned driver Git checkout")
    drivers.add_argument("root", type=Path)
    hashes = sub.add_parser("source-hashes", help="Hash all tracked files and compare their raw bytes with Git blobs")
    hashes.add_argument("root", type=Path)
    sub.add_parser("self-test", help="Run bounded synthetic parser tests only")
    args = parser.parse_args()
    try:
        report = (media_report(args.root) if args.command == "media" else
                  driver_report(args.root) if args.command == "drivers" else
                  source_hash_report(args.root) if args.command == "source-hashes" else self_test())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ET.ParseError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error), "passed": False}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
