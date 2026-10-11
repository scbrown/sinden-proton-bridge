# Agent Instructions

Use GitHub issues for this repository's project work. Homelab crew work uses the
operator-configured aegis tracker; follow the crew's current instructions and
verify its route before reading or changing an item. Do not initialize a local
tracker in this checkout or treat the tracked `.beads` export as a live board.

The old Beads/Dolt integration and commit-message hook are retired. Historical
exports remain reference material. They do not authorize restoring the old
backend, hooks, credentials, or synchronization path.

Before making changes, use an owned worktree and preserve unrelated edits.
Fetch the remote and reconcile without forcing or discarding work. Run the
checks appropriate to the changed files. The legacy-hook workflow verifies that
commits no longer invoke the retired tracker, including an actual historical
hook as its positive control.

Use non-interactive SSH (`-o BatchMode=yes`) when automation must fail instead of
prompting. Check command failures explicitly; an empty result is not success.
Do not overwrite files or delete recovery material merely to avoid a prompt.

When finishing, commit and push authorized changes, verify the remote result,
and record any remaining work or blocker in the current issue tracker. Preserve
other contributors' branches, stashes, uncommitted files, and credentials.
