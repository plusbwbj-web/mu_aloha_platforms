/** Compile-only HOLD ABI. Does not authorize use of the supplied physical RAM. */
#ifndef T733_IMAGE_ARENA_H_
#define T733_IMAGE_ARENA_H_
#include <Base.h>
#include <Library/PlatformMemoryMapLib.h>
#define T733_ARENA_MAGIC 0x31414E4552413754ULL
typedef struct { UINT64 Base; UINT64 Length; } T733_ARENA_RANGE;
typedef struct {
  UINT64 Magic;
  UINT64 Version;
  UINT64 Bytes;
  T733_ARENA_RANGE Image;
  T733_ARENA_RANGE Sec;
  T733_ARENA_RANGE Fd;
  T733_ARENA_RANGE Vectors;
  T733_ARENA_RANGE Stack;
  T733_ARENA_RANGE Tables;
  T733_ARENA_RANGE Heap;
  T733_ARENA_RANGE Dtb;
} T733_IMAGE_ARENA;
typedef struct {
  UINT64 HobBase;
  UINT64 HobEnd;
  UINT64 FreeBottom;
  UINT64 FreeTop;
} T733_ARENA_RESULT;
EFI_STATUS EFIAPI T733ArenaPrepare(CONST T733_IMAGE_ARENA *Arena, UINTN Bytes, T733_ARENA_RESULT *Result);
EFI_STATUS EFIAPI T733ArenaLookupByName(CHAR8 *Name, ARM_MEMORY_REGION_DESCRIPTOR_EX *Region);
EFI_STATUS EFIAPI T733ArenaLookupByAddress(UINT64 Address, ARM_MEMORY_REGION_DESCRIPTOR_EX *Region);
VOID EFIAPI T733ArenaReset(VOID);
#endif
