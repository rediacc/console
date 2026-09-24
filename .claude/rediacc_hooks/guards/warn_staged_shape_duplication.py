"""warn_staged_shape_duplication: is this commit the Nth copy of a shape the tree already has?

WHY THIS EXISTS, and why it is a WARNING. `scripts/gates/check-shape-duplication.ts` answers the question in CI, which is the right place for a refusal and the wrong place to learn. The stop judge (`.claude/hooks/stop/wl_shapedup.py`) asks the judged half of the same question, which costs a model call and happens after the work is done. Between them sits the moment the answer is
cheapest to act on: the commit that introduces the third copy. The operator's ruling is a synchronous check of the STAGED files only, against a cached index of the whole tree, inside about 200 ms, failing OPEN and LOUD when the cache cannot be trusted.

ONE IMPLEMENTATION, TWO ENTRY POINTS. Hashing a staged file means running the gate's `normalise`, `stripNoise` and `windows` over its bytes, and `isSharedHelperCall` derives its name set from the whole corpus, so the normalisation cannot be ported by reading a regex. A Python reimplementation of those would be a second implementation of ONE decision, which is the class of defect
the gate itself exists to count. So the gate bundles itself into `.ci/cache/shape-index/probe.mjs` under `--emit-index`, and this guard spawns that bundle. Nothing is left to disagree except the cache contents, which `.ci/rediacc_ci/tests/test_shape_probe_agreement.py` pins against the gate's own answer.

IT NEVER DENIES. "Is this the Nth copy" is a judgement with an escape hatch (the seed's `accepted` block, with a BLOCKER reason), the probe has the known approximation gaps listed below, and the CI gate owns the refusal. A warning must be SEEN, so it is written to stderr and, as a `systemMessage` plus `additionalContext`, to stdout. Whether a PreToolUse exit-0 JSON body reaches the
operator is unverified here; the stderr copy is what makes the message unconditional.

TWIN = None, the same sentinel and for the same reason as `block_unproven_bulk_transform`: a fresh guard authored directly, with no bash original to port from and nothing to differential-test against. `test-warn_staged_shape_duplication.py` beside it stands in for that differential.

THE DECISION TABLE, in the order the branches are taken:

    not a `git commit` at command position     silent allow
    `-a` / `--all`                             notice, allow (see below)
    no corpus file in the commit               silent allow
    more than 12 corpus files                  notice, allow
    index missing, corrupt, wrong schema       LOUD "did not run", allow
    an input or the bundle has changed sha     LOUD "did not run", allow
    a corpus path added, removed or changed    LOUD "did not run", allow
    node missing, or the probe fails           LOUD "did not run", allow
    the 0.3s deadline passes                   LOUD "did not run", allow
    the probe reports shapes at N copies       LOUD finding, allow
    anything else raises                       LOUD "did not run", allow

THE INDEX IS READ BEFORE THE CORPUS FILTER, and that ordering is deliberate rather than careless: the list of corpus globs LIVES in the index, because a second copy of the gate's `FAMILIES` written here would drift the first time a family moved, which has already happened once to the Stop hook's own cache signature. The cost is that a commit of ordinary files on a tree with no
cache still says so once. That window is short -- `wl_shapedup.py` writes the index on its next stop, and since this guard landed it does so when the index is merely MISSING as well as when the corpus has changed.

`-a` TAKES THE WORKING TREE FOR EVERY MODIFIED TRACKED FILE, which is a set this guard would have to compute a second way, and the repository already refuses that form at `block-pathspecless-git-commit.sh` ("it stages every modified tracked file in a tree that holds other sessions' work"). A notice rather than silence, so a commit that skipped the check says so.

A PATHSPEC COMMIT IS NOT SKIPPED, AND THAT IS A DELIBERATE DEPARTURE from the plan this guard was built from (`agent/plans/PLAN-staged-duplication-probe.md`, "known gaps"). The plan skips it with a notice; that would make the guard inert on this repository, because `block-pathspecless-git-commit.sh` BLOCKS every commit that does not carry one, so `git commit -F <msg> -- <paths>` is
the only form a commit here ever takes. A check that cannot fire on any sanctioned command is the instrument-that-never-ran failure `docs/agent-reference/TRAPS.md` is about. What a pathspec commit captures is the WORKING TREE for those paths rather than the index, so that is what the probe is handed; the index form is still read from the index.

KNOWN GAPS, stated rather than discovered later. The helper set is the cached one, so a staged file that newly makes a module shared changes the answer only at CI. The seed is read at PROBE time, so editing it does not stale the cache. A `.gitattributes` filter that rewrites content on checkout would show up as corpus drift, loudly rather than silently.

STDOUT IS EXCLUSIVE, and today it is free: no other pre-bash guard writes to stdout, so the chain's concatenated stdout is this guard's JSON document or nothing at all. A second stdout speaker in this chain would make both unparseable, which is worth knowing before one is added.
"""

import fnmatch
import hashlib
import json
import os
import shlex
import signal
import subprocess
import time

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_prose_style_commit as PSC

CHAIN = "pre-bash"
TWIN = None
# Re-keyed from 42 to 43 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.
ORDER = 42

# THE WHOLE BUDGET, measured from the moment the command matches. The plan's ceiling is a 200 ms increment on a chain whose baseline is about 129 ms; everything this guard does after the match -- two git calls, a 200 KB index, and the probe -- lives inside this.
DEADLINE_S = 0.3

# A commit with more corpus files than this is a wave rather than an increment, and hashing them all is exactly the cost the cached index exists to avoid. The number is the plan's; the notice is what keeps the skip visible.
STAGED_CAP = 12

CACHE_REL = ".ci/cache/shape-index"
SCHEMA = 1

# `-a` / `--all`: the index is not what gets committed, so the staged bytes are the wrong subject. The same pattern `warn_stale_index` uses, for the same reason.
WORKING_TREE_FORM = hookio.rx(r"git +commit[^|;&]*(-a[{S}]|--all\b)")

CANNOT = (
    "⚠️  SHAPE PROBE DID NOT RUN: %s\n"
    "   The duplication advisory is unavailable for this commit; the CI gate still\n"
    "   owns the refusal. Refresh the cache with:\n"
    "     npx tsx scripts/gates/check-shape-duplication.ts --emit-index"
)

NOTICE_ALL = (
    "⚠️  shape probe skipped: `git commit -a` takes the working tree for every "
    "modified tracked file, which is not the set this probe reads."
)

NOTICE_CAP = "⚠️  shape probe skipped: %d corpus file(s) in one commit is above the cap of %d."

HEADLINE = "⚠️  THE Nth COPY: %d shape(s) in this commit already exist elsewhere in the tree."


def _cache_dir(ev, root):
    return ev.env("SHAPE_PROBE_CACHE", "") or os.path.join(root, CACHE_REL)


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _pathspecs(cmd):
    """The paths after a `--`, which is the only pathspec spelling trusted here.

    A bare trailing path is left to the index arm on purpose: telling `git commit -m msg` from `git commit msg-file` needs git's own option table, and guessing wrong would hand the probe the bytes of a file the commit is not taking. `--` is what `block-pathspecless-git-commit.sh` demands anyway, so the sanctioned form is the one that resolves.
    """
    try:
        tokens = shlex.split(cmd, comments=False)
    except ValueError:
        return []
    if "--" not in tokens:
        return []
    return [t for t in tokens[tokens.index("--") + 1 :] if t and not t.startswith("-")]


def _changed(paths, cwd):
    """(paths, from_worktree). A pathspec commit captures the WORKING TREE for those paths; a plain one captures the index."""
    if paths:
        out = hookio.git_out(["diff", "--name-only", "HEAD", "--", *paths], cwd=cwd, want_rc=True)
        return ([] if out is None else [p for p in out.splitlines() if p.strip()]), True
    out = hookio.git_out(["diff", "--cached", "--name-only"], cwd=cwd, want_rc=True)
    return ([] if out is None else [p for p in out.splitlines() if p.strip()]), False


def _load_index(path):
    """(index, reason). The reason names the CAUSE, because a warning that says only that something is stale teaches a reader to ignore it."""
    if not os.path.exists(path):
        return None, "no cached index at %s (the Stop hook writes one on its next run)" % path
    try:
        with open(path, encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, "the cached index is unreadable: %s" % exc
    if not isinstance(index, dict):
        return None, "the cached index is not an object"
    if index.get("schema") != SCHEMA:
        return None, "the cached index is schema %r, not %d" % (index.get("schema"), SCHEMA)
    for key in ("near", "helpers", "corpus", "pathspecs", "inputs", "bundle_sha"):
        if key not in index:
            return None, "the cached index has no %r" % key
    return index, ""


def _algorithm_moved(index, root, probe):
    """The sha of the bundle and of every source it was built from.

    THE ONE FAILURE A STALENESS CHECK MUST NOT MISS. A change to `normalise` or to the window rule rewrites every hash in the tree, so an index built before it describes a corpus that no longer exists -- and every staged file would then look like new duplication. HEAD and mtimes are deliberately not keys: either would invalidate on an unrelated commit or on a checkout.
    """
    if not os.path.exists(probe):
        return "the probe bundle is missing from the cache"
    if _sha256(probe) != index["bundle_sha"]:
        return "the probe bundle does not match the index that was built with it"
    for rel, want in sorted(index["inputs"].items()):
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            return "%s is gone, and the index was built from it" % rel
        if _sha256(full) != want:
            return "%s has changed since the index was built, so every hash in it may have" % rel
    return ""


def _corpus_moved(index, cwd, committing):
    """A corpus path added, removed or changed relative to `git ls-files -s`, EXCLUDING the paths this commit is about.

    The blob sha per path, which is what git already has computed: content, not mtime. A tree whose corpus has moved is one where the cached neighbour counts are about files that are no longer there.

    THE EXCLUSION IS WHAT MAKES THE CHECK USABLE, and its absence made the guard report drift on precisely the commits it exists to advise. `git ls-files -s` reports the INDEX, so staging the very file being committed changes that listing -- every real commit would have looked like corpus drift, and the finding beyond it was unreachable. What has to be unchanged is the REST of the
    corpus, which is what the cached neighbour counts are about.
    """
    out = hookio.git_out(["ls-files", "-s", "--", *index["pathspecs"]], cwd=cwd, want_rc=True)
    if out is None:
        return "git could not list the corpus"
    live = {}
    for row in out.splitlines():
        if "\t" not in row:
            continue
        meta, path = row.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 2 and path not in committing:
            live[path] = parts[1]
    cached = {p: sha for p, sha in index["corpus"].items() if p not in committing}
    if live == cached:
        return ""
    added = sorted(set(live) - set(cached))
    gone = sorted(set(cached) - set(live))
    changed = sorted(p for p in set(live) & set(cached) if live[p] != cached[p])
    first = (added + gone + changed)[:1]
    return "the corpus has drifted from the index (%d added, %d removed, %d changed%s)" % (
        len(added),
        len(gone),
        len(changed),
        "; e.g. %s" % first[0] if first else "",
    )


def _read_batch(specs, cwd, budget):
    """`git cat-file --batch` over `:<path>` revisions, in ONE fork.

    A `git show :<path>` per file is a fork per file, and twelve of those is most of the budget. The batch protocol answers `<sha> <type> <size>\\n<content>\\n` per request and `<spec> missing` for anything it cannot resolve, so a path that is newly added, deleted or unreadable simply contributes nothing.
    """
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=("\n".join(specs) + "\n").encode("utf-8"),
        capture_output=True,
        check=False,
        cwd=cwd,
        timeout=budget,
    )
    out = proc.stdout
    pos = 0
    bodies = {}
    for spec in specs:
        end = out.find(b"\n", pos)
        if end < 0:
            break
        header = out[pos:end].decode("utf-8", "replace").split()
        pos = end + 1
        if len(header) != 3:
            continue
        size = int(header[2])
        bodies[spec] = out[pos : pos + size].decode("utf-8", "replace")
        pos += size + 1
    return bodies


def _contents(paths, cwd, from_worktree, budget):
    """The bytes the commit will capture, keyed by repo-relative path."""
    if from_worktree:
        out = {}
        for path in paths:
            try:
                with open(os.path.join(cwd, path), encoding="utf-8") as handle:
                    out[path] = handle.read()
            except OSError:
                continue
        return out
    staged = _read_batch([":%s" % p for p in paths], cwd, budget)
    return {spec[1:]: body for spec, body in staged.items()}


def _run_probe(root, probe, index_path, files, budget):
    """(findings, reason). The child is its own process group, so a timeout kills what it started."""
    request = json.dumps({"root": root, "index": index_path, "files": files})
    try:
        child = subprocess.Popen(
            ["node", probe, "--probe"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=root,
            start_new_session=True,
        )
    except OSError as exc:
        return None, "the probe could not be started (%s)" % exc
    try:
        out, err = child.communicate(request.encode("utf-8"), timeout=budget)
    except subprocess.TimeoutExpired:
        # THE GROUP, not the pid. The probe is node, node spawns nothing today, and a deadline that killed only the parent would leave whatever it spawned tomorrow running past the commit it was meant to advise.
        try:
            os.killpg(os.getpgid(child.pid), signal.SIGKILL)
        except OSError:
            child.kill()
        child.communicate()
        return None, "the probe did not answer within the %.1fs budget" % DEADLINE_S
    if child.returncode != 0:
        tail = (err or b"").decode("utf-8", "replace").strip()[-300:]
        return None, "the probe exited %d: %s" % (child.returncode, tail or "<no output>")
    try:
        answer = json.loads(out.decode("utf-8", "replace"))
    except ValueError as exc:
        return None, "the probe's answer was not JSON: %s" % exc
    if isinstance(answer, dict) and answer.get("error"):
        return None, "the probe refused: %s" % answer["error"]
    findings = answer.get("findings") if isinstance(answer, dict) else None
    if not isinstance(findings, list):
        return None, "the probe returned no findings list"
    return findings, ""


def _report(findings, advice):
    """The message, as one block of lines. Built once and written to BOTH channels, which is what keeps the two saying one thing."""
    lines = [HEADLINE % len(findings)]
    for finding in findings[:5]:
        lines.append(
            "      ~%s lines x %d copies:  %s"
            % (finding.get("span"), len(finding.get("files") or []), finding.get("shape"))
        )
        lines.extend("        %s" % loc for loc in (finding.get("files") or [])[:8])
    if len(findings) > 5:
        lines.append("      ... and %d more" % (len(findings) - 5))
    lines.append(advice)
    return "\n".join(lines)


def _speak(ev, text):
    """LOUD means both channels. stderr is what a hook is guaranteed to show; the stdout document is what carries the same words into the session's own context if the harness delivers it."""
    ev.warn(text)
    ev.say(
        json.dumps(
            {
                "systemMessage": text,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": text,
                },
            }
        )
    )


def _probe_commit(ev, deadline):
    cmd = ev.field("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not PSC.GIT_COMMIT.search(scan):
        return hookio.ALLOW
    if hookio.grep_q(WORKING_TREE_FORM, scan):
        ev.warn(NOTICE_ALL)
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR", "") or hookio.git_out(["rev-parse", "--show-toplevel"])

    # ANOTHER REPO'S STAGED FILES ARE NOT THIS GUARD'S BUSINESS, same class as block_unproven_bulk_transform's 2026-09-23 fix (see shellscan.target_root's own docstring): a `-C <other-repo>`/`cd <other-repo> &&` commit would otherwise be scanned against CONSOLE's own staged paths.
    if shellscan.target_root(scan, root) != "":
        return hookio.ALLOW

    cwd = ev.field("cwd") or root
    if not root:
        return hookio.ALLOW

    paths, from_worktree = _changed(_pathspecs(cmd), cwd)
    if not paths:
        return hookio.ALLOW

    cache = _cache_dir(ev, root)
    index_path = os.path.join(cache, "index.json")
    index, why = _load_index(index_path)
    if index is None:
        _speak(ev, CANNOT % why)
        return hookio.ALLOW

    # THE FILTER COMES FROM THE INDEX, never from a list retyped here. The corpus is `FAMILIES` in the gate, and a second copy of those globs in Python would drift the first time a family moved -- which has already happened once to the Stop hook's own signature.
    corpus = [p for p in paths if any(fnmatch.fnmatch(p, g) for g in index["pathspecs"])]
    if not corpus:
        return hookio.ALLOW
    if len(corpus) > STAGED_CAP:
        ev.warn(NOTICE_CAP % (len(corpus), STAGED_CAP))
        return hookio.ALLOW

    moved = _algorithm_moved(index, root, os.path.join(cache, "probe.mjs"))
    if moved:
        _speak(ev, CANNOT % moved)
        return hookio.ALLOW
    drift = _corpus_moved(index, cwd, set(paths))
    if drift:
        _speak(ev, CANNOT % drift)
        return hookio.ALLOW

    files = _contents(corpus, cwd, from_worktree, max(0.02, deadline - time.monotonic()))
    if not files:
        return hookio.ALLOW
    findings, why = _run_probe(
        root,
        os.path.join(cache, "probe.mjs"),
        index_path,
        files,
        max(0.02, deadline - time.monotonic()),
    )
    if findings is None:
        _speak(ev, CANNOT % why)
        return hookio.ALLOW
    if findings:
        _speak(ev, _report(findings, index.get("advice", "")))
    return hookio.ALLOW


def run(ev):
    """Never DENY, and never raise.

    THE WHOLE BODY IS WRAPPED, and the reason is that this guard reads a cache, forks git twice and spawns node: every one of those has a failure mode, and an advisory that turned one of them into a crash would be reported by the dispatcher as a crashed guard rather than as the thing that actually broke. The exception NAMES ITSELF in the message for the same reason the staleness
    reasons do.
    """
    deadline = time.monotonic() + DEADLINE_S
    try:
        return _probe_commit(ev, deadline)
    except Exception as exc:  # noqa: BLE001 -- an advisory may never fail a commit
        _speak(ev, CANNOT % ("the guard raised %s: %s" % (type(exc).__name__, exc)))
        return hookio.ALLOW


# The `-a` arm, which is the one branch that speaks on a tree with nothing staged. Planting it proves the differential can see this guard at all, exactly as the same substitution does for `warn_stale_index`.
DEFECT = ("if hookio.grep_q(WORKING_TREE_FORM, scan):", "if False:")

EDGE_CASES = [
    ("the plain commit", "git commit -m x"),
    ("the sanctioned pathspec form", "git commit -F /tmp/msg.txt -- scripts/gates/check-x.ts"),
    ("-a takes the working tree", "git commit -a -m x"),
    ("--all takes the working tree", "git commit --all -m x"),
    ("a commit after &&", "git add -A && git commit -m x"),
    ("quoted prose is not a command", "echo 'do not run git commit here'"),
    ("a different git verb", "git status"),
    ("a plain command is not a target", "ls -la"),
]
