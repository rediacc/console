# Review 71abb9dd: feat(account-web): Cmd+K command mode for rdc lines

Commit: 71abb9dd4ab847af1d6db89bda707d0ca2c9acb0
Repo: private/account
Branch: 1121-1
Parent: 517553478cbc6b16b1b860d6691b5ffba75dfe67
Patch-Id: 4ebfb5026ebe674fef0140ef4e42f86a9c1f9d18
Reviewed-At: 2026-11-24T21:38:04Z
Model: claude-haiku-5-5
Cost: $0.0073 USD, 1 call(s), 40.9s
Diff: 25177 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New Cmd+K command mode for rdc lines is a new user-facing capability.
Dropped: 0
Body-Sig: 5f8be20e6fa18587

## Findings

### 71abb9dd.1 [low] web/src/components/console/CommandPalette.tsx:391
Anchor: in-diff
Claim: pendingCaret is only cleared when inputRef.current is set, so if a suggestion is applied before any keydown on the input (inputRef still null), the stale caret target survives and is applied on a later render, moving the caret unexpectedly.
Class: other
Resolution: open

### 71abb9dd.2 [low] web/src/components/console/CommandPalette.tsx:217
Anchor: in-diff
Claim: The comment says a command-mode query starts with `rdc` and a space, but RDC_LINE `/^\s*rdc\s/` also accepts leading whitespace and a tab after `rdc`, so the documented rule and the code disagree.
Class: doc-contradicts-code
Resolution: open

### 71abb9dd.3 [low] web/src/components/console/CommandPalette.tsx:472
Anchor: in-diff
Claim: If navigator.clipboard is unavailable (non-secure context), the synchronous TypeError from calling writeText escapes after the palette has already closed, and no test covers the clipboard-failure branch of this copy path.
Class: missing-control-test
Resolution: open
