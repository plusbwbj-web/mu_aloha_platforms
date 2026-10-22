"""Exercise integrity failures using the repository's real mkbootimg packer.

Fixtures model the SM-T733 container and FV header, but contain no firmware and
are never usable on hardware. Mutations that target FV validation are repacked
so the image ID, GZIP CRC, and independent FD comparison remain valid.
"""

import gzip
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid
import zlib


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'artifact_validator', REPO / 'Codex-Offline-Work/tools/validate_artifacts.py')
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ArtifactValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = json.loads((REPO / 'build_cfg/sm7325.json').read_text())
        self.size = int(self.cfg['bootshim']['UEFI_SIZE'], 16)
        self.base = int(self.cfg['bootshim']['UEFI_BASE'], 16)
        self.fd = self.root / 'fixture.fd'
        self.image = self.root / 'fixture.img'
        self.shim = self.root / 'BootShim/BootShim.bin'
        self.dtb = self.root / ('Platforms/KodiakPkg/Device/samsung-gts7fewifi/'
                                'DeviceTreeBlob/Android/android-gts7fewifi.dtb')
        self.ramdisk = self.root / 'PythonLibs/emptyramdisk'
        cfg_path = self.root / 'build_cfg/sm7325.json'
        for path in (self.shim, self.dtb, self.ramdisk, cfg_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(self.cfg))
        shim = bytearray(112)
        struct.pack_into('<QQ', shim, 8, self.base, self.size)
        shim[56:60] = b'ARM\x64'
        self.shim.write_bytes(shim)
        # Valid minimal FDT: reservation terminator plus one empty root node.
        self.dtb.write_bytes(struct.pack('>10I', 0xd00dfeed, 72, 56, 72, 40,
                                         17, 16, 0, 0, 16)
                             + bytes(16) + struct.pack('>4I', 1, 0, 2, 9))
        self.ramdisk.write_bytes((REPO / 'PythonLibs/emptyramdisk').read_bytes())
        fd = bytearray(b'\xff' * self.size)
        fd[:72] = bytes(72)
        # This platform uses the FV ZeroVector slot for an ARM entry branch.
        fd[:4] = bytes.fromhex('9a220014')
        fd[16:32] = uuid.UUID('8c8ce578-8a3d-4f1c-9935-896185c32dd3').bytes_le
        struct.pack_into('<Q4sIHHHBB', fd, 32, self.size, b'_FVH',
                         0x0004feff, 72, 0, 0, 0, 2)
        struct.pack_into('<4I', fd, 56, self.size // 4096, 4096, 0, 0)
        self.rechecksum(fd)
        self.fd.write_bytes(fd)
        self.repack()

    @staticmethod
    def rechecksum(fd):
        header_length = struct.unpack_from('<H', fd, 48)[0]
        struct.pack_into('<H', fd, 50, 0)
        words = struct.unpack('<' + 'H' * (header_length // 2), fd[:header_length])
        struct.pack_into('<H', fd, 50, -sum(words) & 0xffff)

    def repack(self, kernel=None, appended_dtb=None):
        if kernel is None:
            compressed = gzip.compress(self.shim.read_bytes() + self.fd.read_bytes(),
                                       compresslevel=9, mtime=0)
            self.gzip_length = len(compressed)
            kernel = compressed + (self.dtb.read_bytes() if appended_dtb is None
                                   else appended_dtb)
        payload_path = self.root / 'kernel-payload.bin'
        payload_path.write_bytes(kernel)
        subprocess.run([
            sys.executable, str(REPO / 'PythonLibs/mkbootimg.py'),
            '--kernel', str(payload_path), '--ramdisk', str(self.ramdisk),
            '--output', str(self.image), '--pagesize', '4096',
            '--header_version', '0', '--base', '0x0', '--cmdline', '',
            '--os_version', '11.0.0', '--os_patch_level', '2023-04-01',
        ], check=True, capture_output=True)

    def validate(self):
        return VALIDATOR.validate(self.root, self.image, self.fd)

    def mutate_image(self, offset, value):
        data = bytearray(self.image.read_bytes())
        data[offset] ^= value
        self.image.write_bytes(data)

    def assert_rejected(self, message=None):
        if message:
            with self.assertRaisesRegex(ValueError, message):
                self.validate()
        else:
            with self.assertRaises((ValueError, zlib.error)):
                self.validate()

    def test_real_mkbootimg_v0_fixture_passes(self):
        report = self.validate()
        self.assertEqual(report['result'], 'passed')
        self.assertEqual(report['boot_header']['ramdisk_addr'], '0x1000000')
        self.assertEqual(report['bootshim']['copy_end'], '0x9ff00000')
        self.assertEqual(report['firmware_volumes'], [{
            'offset': 0, 'length': self.size, 'header_length': 72,
            'header_checksum': 'passed',
        }])

    def test_rejects_truncated_header(self):
        self.image.write_bytes(self.image.read_bytes()[:1000])
        self.assert_rejected('header missing')

    def test_rejects_truncated_image(self):
        self.image.write_bytes(self.image.read_bytes()[:-1])
        self.assert_rejected('truncated')

    def test_rejects_unexpected_trailer(self):
        self.image.write_bytes(self.image.read_bytes() + b'SEANDROIDENFORCE')
        self.assert_rejected('trailer')

    def test_rejects_bad_gzip_magic(self):
        self.mutate_image(4096, 1)
        self.assert_rejected()

    def test_rejects_bad_gzip_crc(self):
        self.mutate_image(4096 + self.gzip_length - 8, 1)
        self.assert_rejected()

    def test_rejects_unterminated_gzip_member(self):
        kernel = (self.root / 'kernel-payload.bin').read_bytes()
        self.repack(kernel=kernel[:10])
        self.assert_rejected('GZIP stream did not terminate')

    def test_rejects_stale_independent_fd(self):
        data = bytearray(self.fd.read_bytes())
        data[128] ^= 1
        self.fd.write_bytes(data)
        self.assert_rejected('independent FD')

    def test_rejects_wrong_fd_length(self):
        self.fd.write_bytes(self.fd.read_bytes()[:-16])
        self.assert_rejected('FD length')

    def test_rejects_wrong_appended_dtb(self):
        wrong_dtb = bytearray(self.dtb.read_bytes())
        wrong_dtb[-1] ^= 1
        self.repack(appended_dtb=wrong_dtb)
        self.assert_rejected('Appended DTB differs')

    def test_rejects_malformed_source_dtb_totalsize(self):
        data = bytearray(self.dtb.read_bytes())
        struct.pack_into('>I', data, 4, len(data) + 4)
        self.dtb.write_bytes(data)
        self.repack()
        self.assert_rejected('DTB totalsize')

    def test_rejects_wrong_android_image_id(self):
        self.mutate_image(576, 1)
        self.assert_rejected('image ID mismatch')

    def test_rejects_nonzero_image_id_tail(self):
        self.mutate_image(607, 1)
        self.assert_rejected('image ID mismatch')

    def test_rejects_unexpected_board(self):
        self.mutate_image(48, 1)
        self.assert_rejected('board')

    def test_rejects_nonzero_header_padding(self):
        self.mutate_image(1632, 1)
        self.assert_rejected('header.*padding')

    def test_rejects_nonzero_kernel_padding(self):
        kernel_size = struct.unpack_from('<I', self.image.read_bytes(), 8)[0]
        self.mutate_image(4096 + kernel_size, 1)
        self.assert_rejected('image padding')

    def test_rejects_changed_load_address(self):
        self.mutate_image(12, 1)
        self.assert_rejected('load addresses')

    def test_rejects_changed_os_metadata(self):
        self.mutate_image(44, 1)
        self.assert_rejected('OS metadata')

    def test_rejects_invalid_fv_checksum_after_repacking(self):
        data = bytearray(self.fd.read_bytes())
        data[50] ^= 1
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')

    def test_rejects_out_of_bounds_fv_after_repacking(self):
        data = bytearray(self.fd.read_bytes())
        struct.pack_into('<Q', data, 32, self.size + 4096)
        self.rechecksum(data)
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')

    def test_rejects_invalid_fv_revision_with_valid_checksum(self):
        data = bytearray(self.fd.read_bytes())
        data[55] = 1
        self.rechecksum(data)
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')

    def test_rejects_reserved_fv_byte_with_valid_checksum(self):
        data = bytearray(self.fd.read_bytes())
        data[54] = 1
        self.rechecksum(data)
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')

    def test_rejects_missing_blockmap_terminator(self):
        data = bytearray(self.fd.read_bytes())
        struct.pack_into('<II', data, 64, 0, 1)
        self.rechecksum(data)
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')

    def test_rejects_blockmap_that_does_not_cover_fv(self):
        data = bytearray(self.fd.read_bytes())
        struct.pack_into('<I', data, 56, self.size // 4096 - 1)
        self.rechecksum(data)
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')

    def test_rejects_checksum_correct_fv_header_without_blockmap(self):
        data = bytearray(self.fd.read_bytes())
        struct.pack_into('<H', data, 48, 56)
        self.rechecksum(data)
        self.fd.write_bytes(data)
        self.repack()
        self.assert_rejected('firmware volume')


if __name__ == '__main__':
    unittest.main()
