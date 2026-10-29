# SM-T733 SEC dependency isolation: COMPILE AUDIT ONLY

Base: 3d72ea79d5ce263548786acb41d7dd2c16aaa69f, branch-specific experiment.

Do not flash the artifacts. The existing non-returning 12-second SEC checkpoint
stays unchanged in BOTH profiles. New C code is not reached from this entry.
This is not a new timing experiment and does not test full UEFI on hardware.

The policy header defaults to 0, preserving the original behavior. The dedicated
workflow creates isolated control=0 and isolation=1 build jobs. At 1:

- PlatformPei retains our OWN ShLib config/serial bridge, but does not scan old
  XBL via InitProtocolFinder or publish retained Scheduler, InfoBlk, or fixed
  0x9D1C4000 FV-decompress pointer HOBs.
- PrePi does not start the old scheduler, regardless of configuration strings.
- Source-object symbol audit checks InitProtocolFinder and StartUpScheduler
  references are present in control objects and absent in isolation objects.

This does not establish that vendor drivers work without the omitted HOBs. The
exact payload has 67 modules with at least one matching GUID literal, including
39 Scheduler candidates; those are static candidates, not proven runtime calls.
ShLib itself is a new-UEFI structure, not intrinsically a retained SEC object.
Its callbacks still need correct memory maps, serial policy, and lifetime.

The fixed FD, vectors, stack, heap, DTB, cache, GIC, and driver-write issues remain
unreleased. No Image-relative complete PrePi relocation is implemented here.
The current Image-local MMU probe's success must not release these artifacts.

Only source, FD, map/object audit and build diagnostics may be uploaded as HOLD
artifacts. No BOOT TAR, automatic release, signing key, device I/O, or deployment.
The new branch must not be merged as a production change on this evidence.
