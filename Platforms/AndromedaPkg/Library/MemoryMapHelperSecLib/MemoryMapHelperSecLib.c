/** @file

  Copyright (c) 2022-2024 DuoWoA authors

  SPDX-License-Identifier: MIT

**/
#include <Library/BaseLib.h>
#include <Library/T733SecIsolationPolicy.h>
#include <Library/T733ImageArena.h>
#include <Library/MemoryMapHelperLib.h>
#include <Library/PlatformMemoryMapLib.h>

EFI_STATUS EFIAPI LocateMemoryMapAreaByName(
    CHAR8 *MemoryMapAreaName, ARM_MEMORY_REGION_DESCRIPTOR_EX *MemoryDescriptor)
{
#if T733_SEC_ISOLATION_HOLD
  EFI_STATUS ArenaStatus = T733ArenaLookupByName(MemoryMapAreaName, MemoryDescriptor);
  if (ArenaStatus != EFI_NOT_READY) return ArenaStatus;
#endif
  PARM_MEMORY_REGION_DESCRIPTOR_EX MemoryDescriptorEx = GetPlatformMemoryMap();

  // Run through each memory descriptor
  while (MemoryDescriptorEx->Length != 0) {
    if (AsciiStriCmp(MemoryMapAreaName, MemoryDescriptorEx->Name) == 0) {
      *MemoryDescriptor = *MemoryDescriptorEx;
      return EFI_SUCCESS;
    }
    MemoryDescriptorEx++;
  }

  return EFI_NOT_FOUND;
}

EFI_STATUS EFIAPI LocateMemoryMapAreaByAddress(
    EFI_PHYSICAL_ADDRESS             MemoryMapAreaAddress,
    ARM_MEMORY_REGION_DESCRIPTOR_EX *MemoryDescriptor)
{
#if T733_SEC_ISOLATION_HOLD
  EFI_STATUS ArenaStatus = T733ArenaLookupByAddress(MemoryMapAreaAddress, MemoryDescriptor);
  if (ArenaStatus != EFI_NOT_READY) return ArenaStatus;
#endif
  PARM_MEMORY_REGION_DESCRIPTOR_EX MemoryDescriptorEx = GetPlatformMemoryMap();

  // Run through each memory descriptor
  while (MemoryDescriptorEx->Length != 0) {
    if (MemoryDescriptorEx->Address == MemoryMapAreaAddress) {
      *MemoryDescriptor = *MemoryDescriptorEx;
      return EFI_SUCCESS;
    }
    MemoryDescriptorEx++;
  }

  return EFI_NOT_FOUND;
}