# FD SEC entry checkpoint — HOLD

This experimental branch deliberately stops normal PrePi at its first entry.
The only executed SEC code is a position independent PSCI reset checkpoint.
The local no-copy Image launcher jumps into the FD at its current loaded address,
not at its linked base. This is valid ONLY for the statically audited checkpoint
prefix; the rest of this FD is not relocatable and must never be reached.

No stack, vector fill, MMU setup, HOB, scheduler, DXE, UFS, or Windows executes.
This is not evidence of functioning UEFI services, only a possible FD/SEC entry
checkpoint. Hardware remains HOLD; there is no flash or device operation in CI.

Matrix variants are clean full builds. The 3-second source differs from the
committed 12-second file by a declared configure_delay.py edit. Each artifact
retains the actual edited source and SHA256, not merely a Git head claim.
Do not merge this entry override into normal firmware.
