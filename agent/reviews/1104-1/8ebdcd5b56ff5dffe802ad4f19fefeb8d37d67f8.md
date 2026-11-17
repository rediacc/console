# Review 8ebdcd5b: fix(ci): fall back to certspotter when crt.sh cannot list the product certificates

Commit: 8ebdcd5b56ff5dffe802ad4f19fefeb8d37d67f8
Repo: console
Branch: 1104-1
Parent: 7d74db7631289941a9243343793b795d5cd1b5bc
Patch-Id: 47b019c38773d3a457e9ec90ae1d4687b30ead1d
Reviewed-At: 2026-11-17T12:21:17Z
Model: claude-haiku-5-5
Cost: $0.0053 USD, 1 call(s), 33.3s
Diff: 11448 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,ci why=Fixes enterprise proof routing lab so it can see certificates when crt.sh answers empty; CI tooling only, no product-facing API change.
Dropped: 0
Body-Sig: 844f7bb7672fb72c

## Findings

### 8ebdcd5b.1 [medium] .ci/rediacc_ci/enterprise/lab.py:1042
Anchor: in-diff
Claim: The _certspotter_names docstring says it returns every DNS name certspotter lists, but the loop stops silently after CERTSPOTTER_MAX_PAGES (5) pages even when the last page is still full, so names beyond 500 issuances are dropped without any LabError and an absent-from-logs claim can pass on an incomplete list.
Class: doc-contradicts-code
Resolution: open

### 8ebdcd5b.2 [low] .ci/rediacc_ci/tests/test_enterprise_lab.py:4710
Anchor: in-diff
Claim: test_cert_log_names_certspotter_follows_pages_by_last_id covers only the two-page happy path; no test exercises the page cap (a full page 5 that should not be trusted as complete) or a non-200/unreadable certspotter page after page 1 that discards names already found.
Class: missing-control-test
Resolution: open
