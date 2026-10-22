#!/bin/env python3

# @file
# This script provideds android boot pack helper in PlatformBuild.py
#
# Copyright (c) DuoWoa Authors.
# SPDX-License-Identifier: BSD-2-Clause-Patent#
##

import logging
import gzip
import os
import json
import mkbootimg
import shlex
import struct


class Bootimg:
    # Configurations
    header_version: int = 0
    kernel_compressed: bool = False
    emptyramdisk: bool = False
    cmdline: str = ""
    pagesize: int = 4096
    base: int = 0
    os_version: str = "17.0.0"
    os_patch_level: str = "2026-06-18"
    second_offset: int = 0

    # Paths
    fd_path: str = ""           # UEFI FD path
    dtb_path: str = ""          # For passing abl dtbo overlay only
    bootshim_path: str = ""     # Copy fd to specific place in memory
    bootpayload_path: str = ""  # Fake kernel made from bootshim + uefi_fd
    device_name: str = ""

    def __init__(self, outputbin_dir,
                 output_dir, root_dir,
                 device_name, dtb_name, package_name, platform):

        # Parse configuration and fill attributes
        with open(os.path.join(root_dir, 'build_cfg', platform.lower()+'.json'), 'r') as cfg_file:
            cfg = json.load(cfg_file)
            self.parseConfiguration(cfg)
            self.uefi_base = int(cfg['bootshim']['UEFI_BASE'], 0)
            self.uefi_size = int(cfg['bootshim']['UEFI_SIZE'], 0)

        # Fill paths and other vars
        self.device_name = device_name
        self.bootpayload_path = os.path.join(output_dir, 'bootpayload.bin')
        self.output_path = os.path.join(output_dir, device_name + '.img')
        self.fd_path = os.path.join(
            outputbin_dir, 'FV', platform.upper()+'_EFI.fd')
        self.bootshim_path = os.path.join(root_dir, 'BootShim', 'BootShim.bin')
        self.dtb_path = os.path.join(root_dir, "Platforms", package_name, "Device",
                                     device_name, 'DeviceTreeBlob', 'Android', 'android-' + dtb_name)

        # Process android boot cfg override
        override_cfg_path = os.path.join(root_dir, "Platforms", package_name, "Device",
                                         device_name, "bootpack.json")
        try:
            with open(override_cfg_path, 'r') as override_cfg_file:
                override_cfg = json.load(override_cfg_file)
                # Parse again
                self.parseConfiguration(override_cfg)
        except FileNotFoundError:
            logging.info("ABoot pack paras override isn't appointed.")

    def parseConfiguration(self, cfg):
        cfg = cfg.get("default_aboot_args", {})
        self.header_version = cfg.get(
            "header_version", self.header_version)
        self.cmdline = cfg.get("cmdline", self.cmdline)
        self.kernel_compressed = cfg.get(
            "kernel_compressed", self.kernel_compressed)
        self.emptyramdisk = cfg.get("emptyramdisk", self.emptyramdisk)
        self.pagesize = cfg.get("pagesize", self.pagesize)
        self.os_version = cfg.get("os_version", self.os_version)
        self.os_patch_level = cfg.get(
            "os_patch_level", self.os_patch_level)
        self.base = int(cfg.get("base", hex(self.base)), 16)
        self.second_offset = int(
            cfg.get("second_offset", hex(self.second_offset)), 16)

        # basic sanity checks
        if self.header_version > 4 or self.header_version < 0:
            raise ValueError(
                "Invalid header version: {}".format(self.header_version))

    def generateMkbootimgParameters(self):
        args = [
            "--header_version", str(self.header_version),
            "--kernel", self.bootpayload_path,
            "-o", self.output_path,
            "--pagesize", str(self.pagesize),
            "--cmdline", self.cmdline,
            "--base", hex(self.base),
            "--os_version", self.os_version,
            "--os_patch_level", self.os_patch_level
        ]
        if self.emptyramdisk:
            args.extend(["--ramdisk", "./PythonLibs/emptyramdisk"])
        if self.second_offset != 0:
            args.extend(["--second_offset", hex(self.second_offset)])
        if self.header_version == 2:
            # Need to pack dtb in boot in header version 2.
            args.extend(["--dtb", self.dtb_path])
        return args

    def _validateBootPayload(self, bootshim_data, fd_data):
        # BootShim copies 16 bytes per iteration and jumps to UEFI_BASE. A
        # stale shim or mismatched FD must not become a candidate boot image.
        if self.uefi_base < 0 or self.uefi_base % 4:
            raise ValueError("UEFI_BASE must be an aligned AArch64 entry address")
        if self.uefi_size <= 0 or self.uefi_size % 16:
            raise ValueError("UEFI_SIZE must be a positive multiple of 16")
        if self.uefi_base + self.uefi_size > 1 << 64:
            raise ValueError("UEFI destination range exceeds the address space")
        if len(bootshim_data) < 64 or bootshim_data[56:60] != b'ARM\x64':
            raise ValueError("BootShim is missing its ARM64 Image header")
        shim_base, shim_size = struct.unpack_from('<QQ', bootshim_data, 8)
        if (shim_base, shim_size) != (self.uefi_base, self.uefi_size):
            raise ValueError("BootShim base/size does not match the target build configuration")
        if len(fd_data) != self.uefi_size:
            raise ValueError(
                f"UEFI FD length {len(fd_data)} does not match UEFI_SIZE {self.uefi_size}")

    def makeAndroidImage(self):
        '''
        Boot Payload:
            | BootShim.bin | SMXXXX_EFI.fd |
        '''
        logging.info("Generating bootpayload.bin")
        with open(self.bootshim_path, 'rb') as bootshim_file:
            bootshim_data = bootshim_file.read()
        with open(self.fd_path, 'rb') as fd_file:
            fd_data = fd_file.read()
        self._validateBootPayload(bootshim_data, fd_data)
        payload_data = bootshim_data + fd_data

        if self.kernel_compressed:
            logging.info("Compressing kernel...")
            payload_data = gzip.compress(payload_data, 9)

        # For v0/v1 the Android DTB follows the (possibly compressed) kernel.
        if self.header_version < 2:
            with open(self.dtb_path, 'rb') as dtb:
                logging.info("Writing DTB...")
                payload_data += dtb.read()

        with open(self.bootpayload_path, 'wb') as payload_file:
            payload_file.write(payload_data)

        # Close the writer before mkbootimg reopens the payload, including for
        # small payloads that have not filled Python's buffered writer.
        logging.info("Writing " + self.device_name + '.img')
        paras = self.generateMkbootimgParameters()
        logging.info(f"Packing boot with \"{shlex.join(paras)}\"")
        mkbootimg.main(paras)
