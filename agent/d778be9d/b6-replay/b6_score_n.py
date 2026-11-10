import json

import sys
rows = sum((json.load(open(p)) for p in sys.argv[1:]), [])
SLACK = 8


def match(n, o):
    return n["file"] == o["file"] and abs(n["line"] - o["line"]) <= SLACK


old_n = old_nab = old_fix = 0
new_n = new_nab = new_fix = new_unk = 0
fix_hit = 0
cost = 0.0
priors = 0
for r in rows:
    cost += (r["cost"] or {}).get("usd", 0)
    priors += bool(r["prior"])
    for o in r["old"]:
        old_n += 1
        old_nab += o["kind"] == "not-a-bug"
        if o["kind"] == "fixed":
            old_fix += 1
            fix_hit += any(match(n, o) for n in r["new"])
    for n in r["new"]:
        new_n += 1
        kinds = {o["kind"] for o in r["old"] if match(n, o)}
        if "fixed" in kinds:
            new_fix += 1
        elif kinds == {"not-a-bug"}:
            new_nab += 1
        else:
            new_unk += 1
print("commits", len(rows), "with prior line", priors, "cost $%.4f" % cost)
print("OLD findings", old_n, "not-a-bug", old_nab, "rate %.3f" % (old_nab / old_n), "fixed", old_fix)
print("NEW findings", new_n, "matched fixed", new_fix, "matched not-a-bug", new_nab, "unmatched", new_unk)
print("NEW not-a-bug rate, matched only: %.3f" % (new_nab / max(1, new_n - new_unk)))
print("NEW not-a-bug rate, unmatched counted as not refuted: %.3f" % (new_nab / max(1, new_n)))
print("fixed recall: %d/%d = %.3f" % (fix_hit, old_fix, fix_hit / old_fix))
print("failed calls:", [r["sha"][:8] for r in rows if r["why"]])
