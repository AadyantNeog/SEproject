# Native approval

P2-03 implements the native-dialog adapter and internal, one-use grants. The
dialog displays the complete A2-06 preview. The server starts it as a child
process and exchanges one JSON request/response over that child's stdin/stdout;
the helper is not registered as an MCP tool. The response must echo a fresh,
unpredictable challenge and the exact account binding, proposal ID/version and
digest, and server-issued operation ID. The parent checks those values and the
decision timestamp. It also loads the latest account-bound proposal before
opening the dialog and after receiving an approval. A revision or state change
while the dialog is open requires a new preview and approval.

Grants are held in a lock-protected, process-local store. The service rechecks
the stored proposal at consumption and rejects grants for revisions or state
changes made after issuance. The grant store checks all authority fields and
time bounds while holding the lock, then marks the grant consumed. A second
approval for an operation invalidates its prior outstanding
grant. A process restart discards outstanding grants, requiring fresh human
approval. Grants expire at the earlier of proposal expiry and ten minutes from
the request. P2-04 must consume the grant as part of its atomic operation claim
before it constructs an `ApprovedWriteContext`; P2-03 does not perform writes.

Rejecting or closing the dialog, expiration, cancellation, an invalid or stale
response, and helper launch/protocol failure all fail closed. No tool argument
or runtime flag can create a grant. The local trust boundary does not protect
against a compromised OS or software that can directly manipulate the user's
desktop; live writes remain blocked until the selected-client proof demonstrates
that boundary.

## Verification status

Offline security tests use synthetic proposals and a fake approval adapter.
They exercise grant binding/single use, rejection and close, expiry, stale or
forged helper responses, helper launch failure, and the fixture stdio preview
path. The Windows Claude Code connection and visible native-helper launch are
tracked as pending in [native approval evidence](../evidence/native-approval/).
No live approval control was operated as part of this implementation.
