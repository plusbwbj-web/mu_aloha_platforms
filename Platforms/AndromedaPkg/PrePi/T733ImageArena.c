/** HOLD: explicit Image ranges, partial HOB construction, no normal PrePi/DXE.
 * Caller supplies proven Image ownership, primary-core serialization, an EL1
 * stack/vectors and coherent relocated SEC before calling this alternate API.
 * This function neither establishes those conditions nor changes SP/VBAR/MMU.
 */
#include <PiPei.h>
#include <Library/T733SecIsolationPolicy.h>
#include <Library/T733ImageArena.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/HobLib.h>
#include <Library/PrePiHobListPointerLib.h>
#include <Library/PrePiLib.h>
#include <Library/MemoryAllocationLib.h>

#if T733_SEC_ISOLATION_HOLD
STATIC T733_IMAGE_ARENA mArena;
STATIC BOOLEAN mArenaActive;
STATIC EFI_HOB_HANDOFF_INFO_TABLE *mArenaHob;
STATIC BOOLEAN ValidRange(CONST T733_ARENA_RANGE *R) {
  return R->Base != 0 && R->Length != 0 && R->Base <= 0xFFFFFFFFULL &&
         R->Length <= 0x100000000ULL - R->Base;
}
STATIC BOOLEAN Contains(CONST T733_ARENA_RANGE *R, UINT64 Base, UINT64 Length) {
  return ValidRange(R) && Base >= R->Base && Base - R->Base <= R->Length &&
         Length <= R->Length - (Base - R->Base);
}
STATIC BOOLEAN Separate(CONST T733_ARENA_RANGE *A, CONST T733_ARENA_RANGE *B) {
  return A->Base + A->Length <= B->Base || B->Base + B->Length <= A->Base;
}
STATIC EFI_STATUS Validate(CONST T733_IMAGE_ARENA *A, T733_ARENA_RESULT *Result) {
  CONST T733_ARENA_RANGE *Ranges[6];
  UINTN I, J;
  Ranges[0]=&A->Sec; Ranges[1]=&A->Fd; Ranges[2]=&A->Vectors;
  Ranges[3]=&A->Stack; Ranges[4]=&A->Tables; Ranges[5]=&A->Heap;
  if (A->Magic != T733_ARENA_MAGIC || A->Version != 1 || A->Bytes != sizeof(*A) ||
      !ValidRange(&A->Image) || A->Image.Base < 0xA0000000ULL ||
      A->Image.Base + A->Image.Length > 0xB0000000ULL ||
      (A->Image.Base & 0xFFF) || (A->Image.Length & 0xFFF) ||
      !ValidRange(&A->Dtb) || A->Dtb.Length != 0x200000 || !Separate(&A->Image,&A->Dtb))
    return EFI_INVALID_PARAMETER;
  for (I=0; I<6; ++I) {
    if (!ValidRange(Ranges[I]) || (Ranges[I]->Base & 0xFFF) ||
        (Ranges[I]->Length & 0xFFF) ||
        !Contains(&A->Image,Ranges[I]->Base,Ranges[I]->Length)) return EFI_INVALID_PARAMETER;
    for (J=0; J<I; ++J) if (!Separate(Ranges[I],Ranges[J])) return EFI_INVALID_PARAMETER;
  }
  if (A->Vectors.Length < 0x1000 || A->Stack.Length < 0x4000 || A->Tables.Length < 0x5000 ||
      A->Heap.Length < 0x10000 ||
      !Contains(&A->Stack,(UINTN)A,sizeof(*A)) ||
      !Contains(&A->Stack,(UINTN)Result,sizeof(*Result)) ||
      Contains(&A->Heap,(UINTN)A,1) || Contains(&A->Heap,(UINTN)Result,1) ||
      ((UINTN)A < A->Heap.Base && (UINTN)A+sizeof(*A) > A->Heap.Base) ||
      ((UINTN)Result < A->Heap.Base && (UINTN)Result+sizeof(*Result) > A->Heap.Base) ||
      !Contains(&A->Sec,(UINTN)&mArena,sizeof(mArena)) ||
      !Contains(&A->Sec,(UINTN)&mArenaActive,sizeof(mArenaActive)) ||
      !Contains(&A->Sec,(UINTN)T733ArenaPrepare,4)) return EFI_INVALID_PARAMETER;
  if (!((UINTN)A+sizeof(*A)<=(UINTN)Result || (UINTN)Result+sizeof(*Result)<=(UINTN)A))
    return EFI_INVALID_PARAMETER;
  return EFI_SUCCESS;
}
STATIC EFI_STATUS Lookup(CHAR8 *Name, UINT64 Address, BOOLEAN ByAddress, ARM_MEMORY_REGION_DESCRIPTOR_EX *Region) {
  CONST CHAR8 *Names[6] = {"UEFI FD","CPU Vectors","UEFI Stack","MMU PageTables","DXE Heap","SEC Image"};
  CONST T733_ARENA_RANGE *Ranges[6];
  UINTN I;
  if (!mArenaActive) return EFI_NOT_READY;
  if (Region == NULL || (!ByAddress && Name == NULL)) return EFI_INVALID_PARAMETER;
  Ranges[0]=&mArena.Fd; Ranges[1]=&mArena.Vectors; Ranges[2]=&mArena.Stack;
  Ranges[3]=&mArena.Tables; Ranges[4]=&mArena.Heap; Ranges[5]=&mArena.Sec;
  for (I=0; I<6; ++I) {
    if ((ByAddress && Address==Ranges[I]->Base) || (!ByAddress && AsciiStriCmp(Name,Names[I])==0)) {
      ZeroMem(Region,sizeof(*Region));
      AsciiStrCpyS(Region->Name,sizeof(Region->Name),Names[I]);
      Region->Address=Ranges[I]->Base; Region->Length=Ranges[I]->Length;
      Region->HobOption=AddMem; Region->ResourceType=SYS_MEM;
      Region->ResourceAttribute=SYS_MEM_CAP; Region->MemoryType=BsData;
      Region->ArmAttributes=UNCACHED_UNBUFFERED;
      return EFI_SUCCESS;
    }
  }
  /* Active mode must never fall back to the static platform RAM map. */
  return EFI_NOT_FOUND;
}
#endif

EFI_STATUS EFIAPI T733ArenaPrepare(CONST T733_IMAGE_ARENA *Arena, UINTN Bytes, T733_ARENA_RESULT *Result) {
#if T733_SEC_ISOLATION_HOLD
  EFI_STATUS Status;
  EFI_HOB_HANDOFF_INFO_TABLE *Hob;
  VOID *Previous;
  if (Arena==NULL || Result==NULL || Bytes!=sizeof(*Arena)) return EFI_INVALID_PARAMETER;
  if (mArenaActive) return EFI_ALREADY_STARTED;
  Status=Validate(Arena,Result); if (EFI_ERROR(Status)) return Status;
  CopyMem(&mArena,Arena,sizeof(mArena));
  Previous=PrePeiGetHobList();
  Hob=HobConstructor((VOID *)(UINTN)mArena.Heap.Base,(UINTN)mArena.Heap.Length,
                    (VOID *)(UINTN)mArena.Heap.Base,(VOID *)(UINTN)(mArena.Heap.Base+mArena.Heap.Length));
  PrePeiSetHobList(Hob);
  BuildFvHob(mArena.Fd.Base,mArena.Fd.Length);
  BuildStackHob(mArena.Stack.Base,mArena.Stack.Length);
  PrePeiSetHobList(Previous);
  Result->HobBase=(UINTN)Hob; Result->HobEnd=Hob->EfiEndOfHobList;
  Result->FreeBottom=Hob->EfiFreeMemoryBottom; Result->FreeTop=Hob->EfiFreeMemoryTop;
  mArenaHob=Hob;
  mArenaActive=TRUE;
  T733SetArenaLookupCallbacks(T733ArenaLookupByName,T733ArenaLookupByAddress);
  return EFI_SUCCESS;
#else
  (VOID)Arena; (VOID)Bytes; (VOID)Result;
  return EFI_UNSUPPORTED;
#endif
}
EFI_STATUS EFIAPI T733ArenaLookupByName(CHAR8 *Name, ARM_MEMORY_REGION_DESCRIPTOR_EX *Region) {
#if T733_SEC_ISOLATION_HOLD
  return Lookup(Name,0,FALSE,Region);
#else
  (VOID)Name; (VOID)Region; return EFI_NOT_READY;
#endif
}
EFI_STATUS EFIAPI T733ArenaLookupByAddress(UINT64 Address, ARM_MEMORY_REGION_DESCRIPTOR_EX *Region) {
#if T733_SEC_ISOLATION_HOLD
  return Lookup(NULL,Address,TRUE,Region);
#else
  (VOID)Address; (VOID)Region; return EFI_NOT_READY;
#endif
}
EFI_STATUS EFIAPI T733ArenaAllocatePages(UINTN Pages, UINT64 *Address) {
#if T733_SEC_ISOLATION_HOLD
  UINT64 Top, Bottom, Available;
  VOID *Previous, *Allocated;
  if (!mArenaActive) return EFI_NOT_READY;
  if (Address==NULL || !Contains(&mArena.Stack,(UINTN)Address,sizeof(*Address)) || Pages==0)
    return EFI_INVALID_PARAMETER;
  if (!Contains(&mArena.Heap,(UINTN)mArenaHob,sizeof(*mArenaHob)) ||
      mArenaHob->Header.HobType!=EFI_HOB_TYPE_HANDOFF ||
      mArenaHob->Header.HobLength!=sizeof(*mArenaHob)) return EFI_COMPROMISED_DATA;
  Top=mArenaHob->EfiFreeMemoryTop & ~0xFFFULL;
  Bottom=mArenaHob->EfiFreeMemoryBottom;
  if (Top > mArena.Heap.Base+mArena.Heap.Length || Bottom < mArena.Heap.Base ||
      Top < Bottom || sizeof(EFI_HOB_MEMORY_ALLOCATION)>Top-Bottom)
    return EFI_COMPROMISED_DATA;
  Available=Top-Bottom-sizeof(EFI_HOB_MEMORY_ALLOCATION);
  /* Divide before multiplication/subtraction in the underlying legacy allocator. */
  if (Pages > Available/0x1000) return EFI_OUT_OF_RESOURCES;
  Previous=PrePeiGetHobList();
  PrePeiSetHobList(mArenaHob);
  Allocated=AllocatePages(Pages);
  PrePeiSetHobList(Previous);
  if (Allocated==NULL) return EFI_OUT_OF_RESOURCES;
  if ((UINTN)Allocated != Top-(UINT64)Pages*0x1000 ||
      !Contains(&mArena.Heap,(UINTN)Allocated,(UINT64)Pages*0x1000))
    return EFI_COMPROMISED_DATA;
  *Address=(UINTN)Allocated;
  return EFI_SUCCESS;
#else
  (VOID)Pages; (VOID)Address; return EFI_UNSUPPORTED;
#endif
}
VOID EFIAPI T733ArenaReset(VOID) {
#if T733_SEC_ISOLATION_HOLD
  T733SetArenaLookupCallbacks(NULL,NULL);
  mArenaActive=FALSE;
  mArenaHob=NULL;
  ZeroMem(&mArena,sizeof(mArena));
#endif
}
