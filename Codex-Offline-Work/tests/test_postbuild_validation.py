"""Offline regressions for the real PostBuild packer; fixtures are not firmware."""

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'PythonLibs'))
from PostBuild import Bootimg


class PostBuildValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'Build' / 'KodiakPkg'
        self.bin_output = self.output / 'RELEASE_CLANGPDB'
        self.fd = self.bin_output / 'FV' / 'SM7325_EFI.fd'
        self.shim = self.root / 'BootShim' / 'BootShim.bin'
        self.device_dir = self.root / 'Platforms' / 'KodiakPkg' / 'Device' / 'samsung-gts7fewifi'
        self.dtb = self.device_dir / 'DeviceTreeBlob' / 'Android' / 'android-gts7fewifi.dtb'
        self.cfg_path = self.root / 'build_cfg' / 'sm7325.json'
        for path in (self.fd, self.shim, self.dtb, self.cfg_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg = {
            'bootshim': {'UEFI_BASE': '0x9FC41000', 'UEFI_SIZE': '0x40'},
            'default_aboot_args': {
                'header_version': 0, 'kernel_compressed': True,
                'emptyramdisk': False, 'pagesize': 4096, 'base': '0x0',
                'os_version': '11.0.0', 'os_patch_level': '2023-04-01',
            },
        }
        self.cfg_path.write_text(json.dumps(self.cfg))
        shim_data = bytearray(112)
        struct.pack_into('<QQ', shim_data, 8, 0x9FC41000, 0x40)
        shim_data[56:60] = b'ARM\x64'
        self.shim.write_bytes(shim_data)
        self.fd.write_bytes(bytes(range(64)))
        self.dtb.write_bytes(b'SYNTHETIC-DTB-TRAILER')

    def packer(self):
        return Bootimg(str(self.bin_output), str(self.output), str(self.root),
                       'samsung-gts7fewifi', 'gts7fewifi.dtb', 'KodiakPkg', 'Sm7325')

    def assert_rejected(self, message):
        payload = self.output / 'bootpayload.bin'
        payload.write_bytes(b'preserve-existing-payload')
        with self.assertRaisesRegex(ValueError, message):
            self.packer().makeAndroidImage()
        self.assertEqual(payload.read_bytes(), b'preserve-existing-payload')
        self.assertFalse((self.output / 'samsung-gts7fewifi.img').exists())

    def test_valid_small_payload_is_visible_to_mkbootimg(self):
        self.packer().makeAndroidImage()
        payload = (self.output / 'bootpayload.bin').read_bytes()
        image = (self.output / 'samsung-gts7fewifi.img').read_bytes()
        self.assertEqual(image[:8], b'ANDROID!')
        kernel_size = struct.unpack_from('<I', image, 8)[0]
        self.assertGreater(kernel_size, 0)
        self.assertEqual(kernel_size, len(payload))
        self.assertEqual(image[4096:4096 + kernel_size], payload)
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self.assertEqual(decoder.decompress(payload), self.shim.read_bytes() + self.fd.read_bytes())
        self.assertTrue(decoder.eof)
        self.assertEqual(decoder.unused_data, self.dtb.read_bytes())

    def test_valid_uncompressed_payload_preserves_bytes(self):
        self.cfg['default_aboot_args']['kernel_compressed'] = False
        self.cfg_path.write_text(json.dumps(self.cfg))
        self.packer().makeAndroidImage()
        self.assertEqual((self.output / 'bootpayload.bin').read_bytes(),
                         self.shim.read_bytes() + self.fd.read_bytes() + self.dtb.read_bytes())

    def test_rejects_truncated_shim_header(self):
        self.shim.write_bytes(self.shim.read_bytes()[:63])
        self.assert_rejected('ARM64 Image header')

    def test_rejects_invalid_shim_magic(self):
        data = bytearray(self.shim.read_bytes())
        data[56:60] = b'FAIL'
        self.shim.write_bytes(data)
        self.assert_rejected('ARM64 Image header')

    def test_rejects_stale_shim_destination(self):
        data = bytearray(self.shim.read_bytes())
        struct.pack_into('<Q', data, 8, 0xA7C41000)
        self.shim.write_bytes(data)
        self.assert_rejected('base/size does not match')

    def test_rejects_stale_shim_copy_size(self):
        data = bytearray(self.shim.read_bytes())
        struct.pack_into('<Q', data, 16, 0x50)
        self.shim.write_bytes(data)
        self.assert_rejected('base/size does not match')

    def test_rejects_truncated_fd(self):
        self.fd.write_bytes(self.fd.read_bytes()[:-1])
        self.assert_rejected('FD length')

    def test_rejects_oversized_fd(self):
        self.fd.write_bytes(self.fd.read_bytes() + b'!')
        self.assert_rejected('FD length')

    def test_rejects_zero_or_partial_copy_extent(self):
        for value in ('0x0', '0x41'):
            with self.subTest(size=value):
                self.cfg['bootshim']['UEFI_SIZE'] = value
                self.cfg_path.write_text(json.dumps(self.cfg))
                self.assert_rejected('positive multiple of 16')

    def test_rejects_unaligned_entry_or_wrapped_range(self):
        for value, message in (('0x9FC41001', 'aligned AArch64'),
                               ('0xFFFFFFFFFFFFFFF0', 'address space')):
            with self.subTest(base=value):
                self.cfg['bootshim']['UEFI_BASE'] = value
                self.cfg_path.write_text(json.dumps(self.cfg))
                self.assert_rejected(message)

    def test_bootpack_override_changes_android_metadata_only(self):
        (self.device_dir / 'bootpack.json').write_text(json.dumps({
            'bootshim': {'UEFI_BASE': '0x0', 'UEFI_SIZE': '0x0'},
            'default_aboot_args': {'base': '0x10000000'},
        }))
        self.packer().makeAndroidImage()
        image = (self.output / 'samsung-gts7fewifi.img').read_bytes()
        self.assertEqual(struct.unpack_from('<I', image, 12)[0], 0x10008000)


if __name__ == '__main__':
    unittest.main()
