#!/usr/bin/env python3
"""Compile and exercise the repository's actual RamPartitionDxe C with host stubs.

The stubs model UEFI service results, not physical RAM or live firmware behavior.
Run with Python 3 and a host C compiler; no device access is performed.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Platforms/AndromedaPkg/Driver/RamPartitionDxe/RamPartitionDxe.c'
PRELUDE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t UINT64, EFI_STATUS, EFI_PHYSICAL_ADDRESS;
typedef uint32_t UINT32;
typedef uint16_t UINT16;
typedef size_t UINTN;
typedef void VOID;
typedef void *EFI_HANDLE;
typedef void EFI_SYSTEM_TABLE;
typedef int EFI_MEMORY_TYPE, EFI_GCD_MEMORY_TYPE;
#define IN
#define OUT
#define STATIC static
#define EFIAPI
#define EFI_SUCCESS 0
#define EFI_NOT_FOUND 1
#define EFI_BUFFER_TOO_SMALL 2
#define EFI_OUT_OF_RESOURCES 3
#define EFI_PROTOCOL_ERROR 4
#define EFI_INVALID_PARAMETER 5
#define EFI_DEVICE_ERROR 6
#define EFI_ERROR(Status) ((Status) != EFI_SUCCESS)
#define MAX_UINT64 UINT64_MAX
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DEBUG(a) do {} while (0)
#define ASSERT(a) assert(a)
#define EfiReservedMemoryType 0
#define EfiConventionalMemory 1
#define EfiGcdMemoryTypeReserved 0
#define EfiGcdMemoryTypeSystemMemory 1
#define EFI_MEMORY_WB 8
#define FixedPcdGet64(a) 0x80000000ULL
#define MAX_ARM_MEMORY_REGION_DESCRIPTOR_COUNT 128
typedef struct { UINT64 Base, AvailableLength; } RamPartitionEntry;
typedef struct {
  const char *Name;
  UINT64 Address, Length;
  int HobOption, ResourceType, ResourceAttribute;
  EFI_MEMORY_TYPE MemoryType;
  UINT64 ArmAttributes;
} ARM_MEMORY_REGION_DESCRIPTOR_EX, *PARM_MEMORY_REGION_DESCRIPTOR_EX;
static ARM_MEMORY_REGION_DESCRIPTOR_EX gExtendedMemoryDescriptorEx[9];
static UINT32 gEfiRamPartitionProtocolGuid;
typedef struct _RamProtocol EFI_RAMPARTITION_PROTOCOL;
struct _RamProtocol {
  EFI_STATUS (*GetRamPartitions)(EFI_RAMPARTITION_PROTOCOL *, RamPartitionEntry *, UINT32 *);
};
static RamPartitionEntry input[16];
static UINT32 input_count;
static unsigned add_count, fail_add_at, free_count;
static int missing_protocol;
static UINT64 seen_base[32], seen_length[32];
static EFI_STATUS get_partitions(EFI_RAMPARTITION_PROTOCOL *self, RamPartitionEntry *out, UINT32 *count) {
  (void)self;
  if (!out) { *count = input_count; return EFI_BUFFER_TOO_SMALL; }
  assert(*count == input_count);
  memcpy(out, input, input_count * sizeof(*out));
  return EFI_SUCCESS;
}
static EFI_RAMPARTITION_PROTOCOL protocol = { get_partitions };
static EFI_STATUS locate(UINT32 *guid, VOID *registration, VOID **out) {
  (void)guid; (void)registration;
  *out = missing_protocol ? NULL : &protocol;
  return missing_protocol ? EFI_NOT_FOUND : EFI_SUCCESS;
}
static struct { EFI_STATUS (*LocateProtocol)(UINT32 *, VOID *, VOID **); } boot = { locate }, *gBS = &boot;
static EFI_STATUS add_space(EFI_GCD_MEMORY_TYPE type, UINT64 base, UINT64 length, UINT64 attributes) {
  (void)type; (void)attributes;
  assert(length > 0 && length <= 0x80000000ULL);
  assert(add_count < ARRAY_SIZE(seen_base));
  seen_base[add_count] = base; seen_length[add_count] = length;
  ++add_count;
  return add_count == fail_add_at ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}
static EFI_STATUS set_space(UINT64 base, UINT64 length, UINT64 attributes) {
  (void)base; (void)length; (void)attributes; return EFI_SUCCESS;
}
static struct {
  EFI_STATUS (*AddMemorySpace)(EFI_GCD_MEMORY_TYPE, UINT64, UINT64, UINT64);
  EFI_STATUS (*SetMemorySpaceAttributes)(UINT64, UINT64, UINT64);
} dxe = { add_space, set_space }, *gDS = &dxe;
static EFI_STATUS ArmSetMemoryAttributes(UINT64 base, UINT64 length, UINT64 attributes, UINT64 mask) {
  (void)base; (void)length; (void)attributes; (void)mask; return EFI_SUCCESS;
}
static VOID *AllocateZeroPool(UINTN size) { return calloc(1, size); }
static VOID FreePool(VOID *p) { assert(p); ++free_count; free(p); }
'''
TESTS = r'''
static void reset(void) {
  add_count = fail_add_at = free_count = input_count = missing_protocol = 0;
  memset(input, 0, sizeof(input));
  memset(gExtendedMemoryDescriptorEx, 0, sizeof(gExtendedMemoryDescriptorEx));
  gExtendedMemoryDescriptorEx[0].Address = 0xA0000000ULL;
  for (UINTN n=0; n<ARRAY_SIZE(gExtendedMemoryDescriptorEx); ++n)
    gExtendedMemoryDescriptorEx[n].MemoryType = EfiConventionalMemory;
}
static EFI_STATUS initialize(void) { return RamPartitionDxeInitialize(NULL, NULL); }
int main(void) {
  unsigned passed = 0;
  reset(); assert(SpiltAndAddRamPartitions(0x180000000ULL, 0, 0, 1) == EFI_INVALID_PARAMETER); assert(add_count == 0); ++passed;
  reset(); assert(SpiltAndAddRamPartitions(UINT64_MAX-1, 2, 0, 1) == EFI_INVALID_PARAMETER); assert(add_count == 0); ++passed;
  reset(); assert(SpiltAndAddRamPartitions(0x180000000ULL, 0x80000000ULL, 0, 1) == EFI_SUCCESS); assert(add_count == 1 && seen_length[0] == 0x80000000ULL); ++passed;
  reset(); assert(SpiltAndAddRamPartitions(0x180000000ULL, 0x100000000ULL, 0, 1) == EFI_SUCCESS); assert(add_count == 2 && seen_base[1] == 0x200000000ULL); ++passed;
  reset(); assert(SpiltAndAddRamPartitions(0x180000000ULL, 0x180001000ULL, 0, 1) == EFI_SUCCESS); assert(add_count == 4 && seen_length[3] == 0x1000); ++passed;
  reset(); fail_add_at=2; assert(SpiltAndAddRamPartitions(0x180000000ULL, 0x180000000ULL, 0, 1) == EFI_DEVICE_ERROR); assert(add_count == 3); ++passed;
  reset(); missing_protocol=1; assert(initialize() == EFI_NOT_FOUND); assert(add_count == 0 && free_count == 0); ++passed;
  reset(); input_count=1; input[0]=(RamPartitionEntry){0x180000000ULL,0x80000000ULL}; assert(initialize() == EFI_SUCCESS); assert(add_count == 1 && free_count == 1); ++passed;
  reset(); input_count=8; for (unsigned n=0;n<input_count;++n) input[n]=(RamPartitionEntry){0x200000000ULL+n*0x10000ULL,0x1000}; assert(initialize() == EFI_SUCCESS); assert(add_count == 8 && free_count == 1); ++passed;
  reset(); input_count=9; for (unsigned n=0;n<input_count;++n) input[n]=(RamPartitionEntry){0x200000000ULL+n*0x10000ULL,0x1000}; assert(initialize() == EFI_OUT_OF_RESOURCES); assert(add_count == 0 && free_count == 1); ++passed;
  reset(); input_count=1; input[0]=(RamPartitionEntry){0x80000000ULL,0x10000000ULL}; assert(initialize() == EFI_INVALID_PARAMETER); assert(add_count == 0 && free_count == 1); ++passed;
  reset(); input_count=1; input[0]=(RamPartitionEntry){UINT64_MAX-1,2}; assert(initialize() == EFI_INVALID_PARAMETER); assert(add_count == 0 && free_count == 1); ++passed;
  reset(); input_count=2; input[0]=(RamPartitionEntry){0x80000000ULL,0x100000000ULL}; input[1]=(RamPartitionEntry){0x180000000ULL,0x80000000ULL}; fail_add_at=1; assert(initialize() == EFI_DEVICE_ERROR); assert(add_count == 3 && seen_base[2] == 0x180000000ULL && free_count == 1); ++passed;
  reset(); input_count=8; for (unsigned n=0;n<input_count;++n) input[n]=(RamPartitionEntry){0x200000000ULL+n*0x10000ULL,0x1000}; fail_add_at=2; assert(initialize() == EFI_DEVICE_ERROR); assert(add_count == 8 && free_count == 1); ++passed;
  reset(); input_count=1; input[0]=(RamPartitionEntry){0x80000000ULL,0x180000000ULL}; fail_add_at=1; assert(initialize() == EFI_DEVICE_ERROR); assert(add_count == 3 && seen_base[0] == 0xA0000000ULL && seen_base[1] == 0x120000000ULL && seen_base[2] == 0x1A0000000ULL && free_count == 1); ++passed;
  printf("PASS: %u actual-C host cases (split boundaries, failures, protocol, overflow, capacity, cleanup)\n", passed);
  return 0;
}
'''

def main():
    # Keep function implementations exactly as in the working tree. Only their
    # platform headers are replaced by explicit host mocks above.
    source = '\n'.join(line for line in SOURCE.read_text().splitlines()
                       if not line.lstrip().startswith('#include'))
    with tempfile.TemporaryDirectory(prefix='ram-partition-test-') as tmp:
        c_path = Path(tmp) / 'test.c'
        executable = Path(tmp) / 'test'
        c_path.write_text(PRELUDE + source + TESTS)
        subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-O1', '-g',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                        '-Wall', '-Wextra', '-Wno-unused-parameter',
                        str(c_path), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)

if __name__ == '__main__':
    main()
