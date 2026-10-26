/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * SM-T733 experimental shim. No stack, no firmware calls, no guessed scratch.
 * Memory ownership cannot be established from an Android memory snapshot.
 * Default build halts before any write; LAB_MEMORY_CONTRACT=1 is emulator-only.
 */
#ifndef LAB_MEMORY_CONTRACT
#define LAB_MEMORY_CONTRACT 0
#endif
#define FD_BASE 0x9fc43000
#define FD_BYTES 0x2bd000
#define SHIM_BYTES 4096
.section .text,"ax"
.global _start, _payload, _halt, _copy_forward, _copy_backward, _sync
_start:
    b _entry
    nop
    .quad 0x80000                  /* relative Linux Image offset, NOT FD_BASE */
    .quad SHIM_BYTES + FD_BYTES    /* full effective payload including shim */
    .quad 0xa                      /* LE, 4K, arbitrary 2M-aligned base */
    .quad 0, 0, 0
    .ascii "ARM\x64"
    .long 0
_entry:
    mov x16, #1                    /* unsupported exception level */
    mrs x9, CurrentEL
    cmp x9, #4
    b.eq 1f
    cmp x9, #8
    b.ne _halt
    mrs x10, sctlr_el2
    b 2f
1:  mrs x10, sctlr_el1
2:  mov x16, #2                    /* no virtual-address/cache-on contract */
    tst x10, #1
    b.ne _halt
    tst x10, #4
    b.ne _halt
    tst x10, #0x2000000            /* data accesses must be little endian */
    b.ne _halt
    msr daifset, #0xf
    adr x1, _start
    mov x16, #3                    /* arithmetic overflow */
    adds x2, x1, #SHIM_BYTES
    b.cs _halt
    ldr x3, _fd_size
    adds x4, x2, x3                /* exclusive source end */
    b.cs _halt
    ldr x5, _fd_base
    adds x6, x5, x3                /* exclusive destination end */
    b.cs _halt
    mov x16, #4                    /* incorrect fixed platform constants */
    mov x9, #0x3000
    movk x9, #0x9fc4, lsl #16
    cmp x5, x9
    b.ne _halt
    mov x9, #0xd000
    movk x9, #0x2b, lsl #16
    cmp x3, x9
    b.ne _halt
    mov x16, #5                    /* coarse address envelope, not ownership */
    mov x9, #0x80000000
    cmp x1, x9
    b.lo _halt
    mov x9, #0x300000000
    cmp x4, x9
    b.hi _halt
    tst x1, #15
    b.ne _halt
    mov x16, #6                    /* destination intersects executing shim */
    cmp x5, x2
    b.hs 3f
    cmp x1, x6
    b.lo _halt
3:  mov x16, #10                   /* reject before dereferencing unowned DTB */
    ldr x9, _lab_contract
    cmp x9, #1
    b.ne _halt
    mov x16, #7                    /* invalid DTB pointer/header/extent */
    tst x0, #7
    b.ne _halt
    mov x9, #0x80000000
    cmp x0, x9
    b.lo _halt
    adds x11, x0, #40
    b.cs _halt
    mov x9, #0x300000000
    cmp x11, x9
    b.hi _halt
    ldr w10, [x0]
    rev w10, w10
    mov w11, #0xfeed
    movk w11, #0xd00d, lsl #16
    cmp w10, w11
    b.ne _halt
    ldr w10, [x0, #4]
    rev w10, w10
    cmp x10, #40
    b.lo _halt
    mov x11, #0x200000
    cmp x10, x11
    b.hi _halt
    adds x11, x0, x10
    b.cs _halt
    cmp x11, x9
    b.hi _halt
    mov x16, #8                    /* destination would destroy live DTB */
    cmp x5, x11
    b.hs 4f
    cmp x0, x6
    b.lo _halt
4:  mov x16, #9                    /* DTB must not alias loaded Image */
    cmp x1, x11
    b.hs 5f
    cmp x0, x4
    b.lo _halt
5:  /* Lab ownership gate was checked before all DTB dereferences. */
    cmp x2, x5
    b.eq _sync
    mov x7, x2
    mov x8, x5
    mov x12, x3
    cmp x5, x2
    b.lo _copy_forward
    cmp x5, x4
    b.hs _copy_forward
    add x7, x7, x3
    add x8, x8, x3
_copy_backward:
    ldp x13, x14, [x7, #-16]!
    stp x13, x14, [x8, #-16]!
    subs x12, x12, #16
    b.ne _copy_backward
    b _sync
_copy_forward:
    ldp x13, x14, [x7], #16
    stp x13, x14, [x8], #16
    subs x12, x12, #16
    b.ne _copy_forward
_sync:
    /* C=0 is required; clean written lines then invalidate instructions.
     * Real hardware trap controls/coherency remain a separate proof obligation.
     */
    mrs x9, ctr_el0
    ubfx x10, x9, #16, #4
    mov x11, #4
    lsl x10, x11, x10
    sub x12, x10, #1
    bic x7, x5, x12
6:  dc cvau, x7
    add x7, x7, x10
    cmp x7, x6
    b.lo 6b
    dsb sy
    and x10, x9, #15
    lsl x10, x11, x10
    sub x12, x10, #1
    bic x7, x5, x12
7:  ic ivau, x7
    add x7, x7, x10
    cmp x7, x6
    b.lo 7b
    dsb sy
    isb
    mov x16, #0                    /* debugger-visible success before handoff */
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    br x5                          /* preserve caller DTB in x0 */
_halt:
    mov x17, #0x5632               /* x17='V2', x16=reason; no visible console */
8:  wfe
    b 8b
.balign 8
.global _fd_base, _fd_size, _lab_contract
_fd_base: .quad FD_BASE
_fd_size: .quad FD_BYTES
_lab_contract: .quad LAB_MEMORY_CONTRACT
.org SHIM_BYTES
_payload:
