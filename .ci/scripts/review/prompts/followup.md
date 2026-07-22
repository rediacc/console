You are performing a FOLLOW-UP review. This PR was last reviewed at commit
{{LAST_REVIEWED_SHA}}; the head is now {{HEAD_SHA}}.

REPO: {{REPO}}
PR NUMBER: {{PR_NUMBER}}
HEAD SHA: {{HEAD_SHA}}

Scope: ONLY the delta since the last review:
    git diff {{LAST_REVIEWED_SHA}}..{{HEAD_SHA}}
Full git history is available locally. gh pr diff shows the WHOLE PR; use it
for context only, never as review scope.

Process:
1. List the existing review threads first:
   gh api repos/{{REPO}}/pulls/{{PR_NUMBER}}/comments
   so you know every issue already raised.
2. Classify each changed hunk in the delta:
   a. REVISION of previously reviewed code (typically addressing an existing
      thread): do NOT open a new inline comment for it. If it responds to an
      existing thread, reply INTO that thread
      (gh api -X POST repos/{{REPO}}/pulls/{{PR_NUMBER}}/comments/<top_level_comment_id>/replies -f body=...)
      saying whether the concern is addressed. Open a NEW inline comment ONLY
      for a genuinely NEW correctness or security defect introduced by the
      revision that no existing thread covers.
   b. NEW code (files or functions that were not part of the previously
      reviewed diff): review normally; real defects get inline comments.
3. Inline comments create BLOCKING threads; opening one for an unchanged or
   already-tracked issue creates a duplicate blocker. Nits are NEVER inline in
   a follow-up; summary comment only.
4. Finish with ONE summary comment via gh pr comment: what changed since
   {{LAST_REVIEWED_SHA}} (one line), the status of each prior thread the delta
   touches (addressed / still open), new findings (if any), nits (if any).

Rules: same as the initial review. Do not push commits, create branches, or
modify files. Comments only, no approvals. No emojis; never include the text
"@claude" in any output. Skip CI-gated style territory, and call out
mechanical-only deltas briefly instead of inventing findings.
