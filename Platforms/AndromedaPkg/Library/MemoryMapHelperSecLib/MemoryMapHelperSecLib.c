/** @file

  Copyright (c) 2022-2024 DuoWoA authors

  SPDX-License-Identifier: MIT

**/
#include <Library/BaseLib.h>
#include <Library/T733SecIsolationPolicy.h>
#include <Library/T733ImageArena.h>
#include <Library/MemoryMapHelperLib.h>
#include <Library/PlatformMemoryMapLib.h>

#if T733_SEC_ISOLATION_HOLD
STATIC T733_ARENA_LOOKUP_NAME mArenaByName;
STATIC T733_ARENA_LOOKUP_ADDRESS mArenaByAddress;
VOID EFIAPI T733SetArenaLookupCallbacks(T733_ARENA_LOOKUP_NAME ByName, T733_ARENA_LOOKUP_ADDRESS ByAddress) {
  mArenaByName=ByName;
  mArenaByAddress=ByAddress;
}
#endif

EFI_STATUS EFIAPI LocateMemoryMapAreaByName(
    CHAR8 *MemoryMapAreaName, ARM_MEMORY_REGION_DESCRIPTOR_EX *MemoryDescriptor)
{
#if T733_SEC_ISOLATION_HOLD
  if (mArenaByName != NULL) return mArenaByName(MemoryMapAreaName, MemoryDescriptor);
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
  if (mArenaByAddress != NULL) return mArenaByAddress(MemoryMapAreaAddress, MemoryDescriptor);
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