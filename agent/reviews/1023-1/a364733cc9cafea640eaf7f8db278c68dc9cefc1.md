# Review a364733c: feat(deploy): durable deploy records in R2, and a www record

Commit: a364733cc9cafea640eaf7f8db278c68dc9cefc1
Repo: console
Branch: 1023-1
Parent: a0e9c10d16ac2d21a68fd29cd45d4ff83b8d858a
Patch-Id: ce3c4bd8660fc51f700739220c7e7b07432106c3
Reviewed-At: 2026-10-27T08:24:24Z
Model: claude-haiku-5-5
Cost: $0.0054 USD, 1 call(s), 28.2s
Diff: 25145 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature,ci why=Adds CI deploy-record tooling only (.ci/rediacc_ci); no product-facing behaviour change.
Dropped: 0
Body-Sig: f988bce378cc37b7

## Findings

### a364733c.1 [high] .ci/rediacc_ci/deploy/deploy_record.py:824
Anchor: in-diff
Claim: In cmd_after the record is written to --out (line 824) and printed and appended to $GITHUB_STEP_SUMMARY (lines 831-835) before the sink runs, so when refuse_secret_values blocks the sink (line 825-829) the record that carries a credential value is already on disk, in the job log, in the step summary and in the uploaded artifact.
Resolution: fixed 3629c1f3c3ba826ebfb41c70c7d8265ffe0d6d8a | d778be9d 2026-10-27T09:09:44Z

### a364733c.2 [medium] .ci/rediacc_ci/deploy/deploy_record.py:311
Anchor: in-diff
Claim: refuse_secret_values compares the raw secret value against the json.dumps output, so a secret containing a quote, backslash or control character or non-ASCII text is stored escaped in the body and the `value in body` test misses it, letting the credential be written to R2.
Resolution: fixed 3629c1f3c3ba826ebfb41c70c7d8265ffe0d6d8a | d778be9d 2026-10-27T09:09:44Z

### a364733c.3 [medium] .ci/rediacc_ci/deploy/deploy_record.py:324
Anchor: in-diff
Claim: write_record_once checks existence with get_object and only then calls put_object, so two concurrent runs for the same version, channel and target can both pass the probe and the second put overwrites the first, contrary to the documented write-once guarantee.
Resolution: fixed 3629c1f3c3ba826ebfb41c70c7d8265ffe0d6d8a | d778be9d 2026-10-27T09:09:44Z

### a364733c.4 [low] .ci/rediacc_ci/deploy/deploy_record.py:1
Anchor: outside-diff
Claim: record_www_deploy logs a failed post-deploy version lookup but still writes the record with version_after null and returns the deploy rc, so a successful deploy can ship a record with no after-version and no signal beyond a log line.
Resolution: fixed 3629c1f3c3ba826ebfb41c70c7d8265ffe0d6d8a | d778be9d 2026-10-27T09:09:45Z
