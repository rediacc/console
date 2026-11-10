"""B6 replay: re-review historical commits with the NEW prompt, as of the time of the original review (the prior index excludes every record reviewed at or after it)."""
import json
import pathlib
import random
import sys

sys.path.insert(0, "/tmp/oldroot/.claude/hooks/stop")
import wl_review as R  # noqa: E402

root = pathlib.Path(".").resolve()
cfg = R.load_config(root)
cands = json.load(open("/tmp/b6_cands.json"))
random.Random(20261110).shuffle(cands)
both = [c for c in cands if "fixed" in c[2] and "not-a-bug" in c[2]][:10]
fx = [c for c in cands if set(c[2]) == {"fixed"}][:5]
nb = [c for c in cands if set(c[2]) == {"not-a-bug"}][:5]
picks = both + fx + nb
start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
stop = int(sys.argv[2]) if len(sys.argv) > 2 else len(picks)
out = []
for sha, branch, kinds, nbytes in picks[start:stop]:
    old, _ = R.read_review(R.review_path(root, branch, sha))

    def parse(text, at=old.reviewed_at):
        r = R.parse(text)
        if r.reviewed_at >= at:
            raise ValueError("later than the replayed review")
        return r

    paths, gl, subject, message, parent = R._commit_facts(root, sha)
    skips = R.skip_globs(root, cfg)
    diff_text, total, nfiles, cut = R.capped_diff(root, sha, int(cfg["diff_cap_bytes"]), skips)
    kept = R.stat_paths(paths, skips)
    rows = R.numstat_rows(root, sha)
    stat = R.render_stat(rows, kept) if rows is not None else "(unavailable)"
    prior = ""
    prompt = R.PROMPT % {
        "prior": prior + "\n\n" if prior else "",
        "message": message or "(empty)",
        "stat": stat or "(empty)",
        "truncated": ", ".join(cut) or "(none)",
        "diff": diff_text or "(empty)",
    }
    structured, why, cost = R.claude_reviewer(prompt, cfg, lambda *a: None)
    new = []
    if structured is not None:
        _v, fs, _l, dropped = R.validate(structured, paths, diff_text, sha)
        new = [
            {"file": f.file, "line": f.line, "sev": f.severity, "claim": f.claim}
            for f in fs
        ]
    out.append(
        {
            "sha": sha,
            "branch": branch,
            "prior": prior,
            "why": why,
            "cost": cost,
            "old": [
                {
                    "file": f.file,
                    "line": f.line,
                    "sev": f.severity,
                    "kind": f.resolution_kind(),
                    "claim": f.claim,
                }
                for f in old.findings
            ],
            "new": new,
        }
    )
    print(
        sha[:8],
        "prior_lines=%d" % (prior.count("\n") + 1 if prior else 0),
        "old=%d new=%d" % (len(old.findings), len(new)),
        cost,
        why,
        flush=True,
    )
    json.dump(out, open("/tmp/b6_oldctl_out_%d_%d_r3.json" % (start, stop), "w"), indent=1)
