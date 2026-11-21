# Review 161baeee: fix(hooks): scope block_worktree_add to this repository and its submodules

Commit: 161baeee5bb044dc56db5247ebb04f3ab72feb6e
Repo: console
Branch: 1104-1
Parent: 1190e29e83319e561b725f2f179b073a8e066e0f
Patch-Id: f4816e0ae773a63fcd1982041942432d39f2c301
Reviewed-At: 2026-11-11T17:24:34Z
Model: claude-haiku-5-5
Cost: $0.0085 USD, 1 call(s), 54.2s
Diff: 19575 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Loosens a pre-bash guard so scratch-repo worktree adds are admitted; a hook fix, not a product feature.
Dropped: 0
Body-Sig: feea0ca495649e47

## Findings

### 161baeee.1 [medium] .claude/rediacc_hooks/guards/block_worktree_add.py:349
Anchor: in-diff
Claim: _foreign_adds admits a direct `git -C <scratch> worktree add <path>` whenever the repository the run acts on is not this checkout, but never reads the add <path> argument, so the new worktree can be created inside this checkout's tree (e.g. under .claude/worktrees or a submodule path), outside the lease rule the file's own docstring names as the only permitted tree.
Class: other
Resolution: fixed 388ab3634e677fba85b33fccbb5721de142a5287 | d778be9d 2026-11-12T08:55:22Z

### 161baeee.2 [low] .claude/rediacc_hooks/guards/block_worktree_add.py:327
Anchor: in-diff
Claim: The commit message and docstring promise refusal for any GIT_* repository variable in the command text or hook environment, but the check tests only the five hard-coded names in GIT_REPO_ENV / GIT_REPO_ENV_TEXT, so other GIT_* variables pass this gate.
Class: doc-contradicts-code
Resolution: not-a-bug | .claude/rediacc_hooks/guards/_repo_scope.py:20 git_run_scope_doubt refuses any GIT_ variable outside the identity and neutral lists; test-_repo_scope.py GIT_DIR rows pin it | d778be9d 2026-11-12T08:55:27Z
