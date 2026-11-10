import sys, pathlib, subprocess, collections
sys.path.insert(0, ".claude/hooks/stop")
import wl_review as R
rows=[]
for p in sorted(pathlib.Path("agent/reviews").glob("*/*.md")):
    rev,err=R.read_review(p)
    if err or rev.repo!="console" or not rev.findings: continue
    if subprocess.run(["git","cat-file","-e",rev.sha+"^{commit}"],capture_output=True).returncode: continue
    kinds=[f.resolution_kind() for f in rev.findings]
    if any(k in ("open","deferred","waived") for k in kinds) : continue
    if rev.truncated or rev.diff_bytes>40000: continue
    rows.append((rev.sha,p.parent.name,kinds,rev.diff_bytes))
print(len(rows))
c=collections.Counter()
for r in rows: c.update(r[2])
print(c)
import json
json.dump(rows,open("/tmp/b6_cands.json","w"))
