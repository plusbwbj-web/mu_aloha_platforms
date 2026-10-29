/* HOLD-only source integration profile; does NOT make the FD bootable/safe.
 * Default preserves existing behavior. Only the dedicated workflow changes 0->1.
 * Do not remove the independent SEC entry checkpoint to test this profile.
 */
#ifndef T733_SEC_ISOLATION_POLICY_H
#define T733_SEC_ISOLATION_POLICY_H
#define T733_SEC_ISOLATION_HOLD 0
#endif
