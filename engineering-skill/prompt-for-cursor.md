Clone https://github.com/mattpocock/skills into a temp dir and read
from there (don't leave it in this workspace). Inspect the repo so
you understand each skill and its sibling files.
Install these as reusable on-demand prompts using whatever mechanism
THIS version of Cursor supports for custom slash-commands / rules —
pick the current best fit and tell me which you chose and how to
trigger each one. Port every engineering skill plus handoff. Cursor
won't auto-load sibling files, so INLINE each skill's referenced docs
into its body (grill-with-docs←CONTEXT/ADR formats,
tdd←tests/mocking/deep-modules/interface/refactoring,
improve-architecture←LANGUAGE, triage←AGENT-BRIEF/OUT-OF-SCOPE,
prototype←LOGIC/UI); rewrite cross-references to match.
Set up the per-repo config: local-markdown issue tracker
(PRDs/issues under .scratch/<feature>/, Status: line for triage),
default triage labels, single-context domain docs in docs/agents/,
plus CLAUDE.md, a near-empty CONTEXT.md, docs/adr/, and a README.
Print the final file tree, state which Cursor mechanism you used and
why, and confirm the temp clone was removed.

