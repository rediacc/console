"""wl_renettests: the renet Go test map read from Python, and the Stop hook's "renet changed, untested" advisory (agent/plans/PLAN-renet-change-test-triggers.md, box M4).

ONE MAP, TWO READERS. `.ci/config/renet-test-map.json` maps renet path globs to the Go packages they reach; `scripts/gates/check-renet-test-map.ts` runs the selected `go test` and writes a receipt keyed on the renet tree it tested. This module is the Python reading of the same map and the same receipts, used here and by `block_renet_untested_push`. `.ci/rediacc_ci/tests/test_renet_test_map_parity.py` holds the two readers to the same answer on the real map, so a rule changed on one side alone goes red.

THE RULES, mirrored from the gate: a path belongs to its MOST SPECIFIC glob (`<dir>/**` or an exact path); a `whole` path (go.mod, go.sum) selects every package; a path under pkg/ or cmd/, or any `.go` file, that no glob claims selects every package (unknown is never "none"); a non-empty selection adds the `always` packages; anything else (docs, Python e2e) selects nothing. A path under a `retired` glob (a package deleted from renet) selects only the `always` set, and one under an `outside` glob (build-tagged e2e Go the gate cannot run) selects nothing. A CONSOLE path under a `console` glob (a file renet tests read from outside the module) selects the packages that row names, and not the `always` set. The map holds no areas: they live once in `.ci/config/proof-tiers.json`.

THE RECEIPT is `<dir>/<renet tree>.json` with `dir` = `$RENET_TEST_RECEIPT_DIR`, else `$XDG_CACHE_HOME/rediacc/renet-tests`, else `~/.cache/rediacc/renet-tests`. It covers a selection when its tree is the tree in question and it ran every selected package (`all` covers anything).

THE ADVISORY is report-only and never raises: its effort row decides the level, and "could not measure" is silence, never a refusal to stop.
"""

import contextlib
import json
import os
import pathlib
import subprocess
import tempfile
import uuid

MAP_REL = ".ci/config/renet-test-map.json"
RENET = "private/renet"
RECEIPT_SCHEMA = 1
GO_ROOTS = ("pkg", "cmd", "scripts")
COMMAND = "npm run check:ci-renet-test-map"
MAX_LISTED = 8


# --------------------------------------------------------------------------- the map


def load_map(root):
    """The parsed map, or None when it is missing or unreadable."""
    try:
        doc = json.loads((pathlib.Path(root) / MAP_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("entries"), list) else None


def glob_matches(glob, path):
    if glob.endswith("/**"):
        base = glob[:-3]
        return path == base or path.startswith(base + "/")
    return path == glob


def owner_of(test_map, path):
    """The entry claiming `path`: the longest matching glob, None when no glob matches."""
    best = None
    for entry in test_map["entries"]:
        if glob_matches(entry["glob"], path) and (
            best is None or len(entry["glob"]) > len(best["glob"])
        ):
            best = entry
    return best


def go_relevant(path):
    return path.endswith(".go") or any(path.startswith(r + "/") for r in GO_ROOTS)


def all_packages(test_map):
    return sorted({p for e in test_map["entries"] for p in e.get("packages", [])})


def required_for(test_map, changed, every=None, console_changed=()):
    """{"all", "packages", "all_why", "mapped"} for the changed renet paths and the changed console paths, the gate's `requiredFor`."""
    every = all_packages(test_map) if every is None else every
    picked = set()
    console_picked = set()
    all_why = []
    mapped = 0
    retired = False
    for path in console_changed:
        for row in test_map.get("console", []):
            if glob_matches(row["glob"], path):
                mapped += 1
                console_picked.update(row.get("packages", []))
    for path in changed:
        whole = next((w for w in test_map.get("whole", []) if glob_matches(w["glob"], path)), None)
        if whole is not None:
            all_why.append("%s (%s)" % (path, whole["why"]))
            mapped += 1
            continue
        entry = owner_of(test_map, path)
        if entry is not None:
            mapped += 1
            picked.update(entry.get("packages", []))
            picked.update(entry.get("dependents", []))
        elif any(glob_matches(r["glob"], path) for r in test_map.get("retired", [])):
            mapped += 1
            retired = True
        elif any(glob_matches(o["glob"], path) for o in test_map.get("outside", [])):
            mapped += 1
        elif go_relevant(path):
            all_why.append("%s (no glob in %s claims it)" % (path, MAP_REL))
    if all_why:
        return {"all": True, "packages": sorted(every), "all_why": all_why, "mapped": mapped}
    if picked or retired:
        picked.update(a["package"] for a in test_map.get("always", []))
    picked.update(console_picked)
    return {"all": False, "packages": sorted(picked), "all_why": [], "mapped": mapped}


# --------------------------------------------------------------------------- receipts


def receipt_dir(env=None):
    env = os.environ if env is None else env
    if env.get("RENET_TEST_RECEIPT_DIR"):
        return pathlib.Path(env["RENET_TEST_RECEIPT_DIR"])
    cache = env.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return pathlib.Path(cache) / "rediacc" / "renet-tests"


def read_receipt(tree, env=None):
    """The receipt for the renet tree `tree`, or None when there is none or it is not this schema."""
    if not tree:
        return None
    try:
        doc = json.loads((receipt_dir(env) / ("%s.json" % tree)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("schema") != RECEIPT_SCHEMA:
        return None
    return doc if doc.get("renetTree") == tree else None


def uncovered(receipt, required):
    """The selected packages `receipt` did not run; one "(every package ...)" line when an all-selection meets a partial receipt; None when there is no receipt at all."""
    if receipt is None:
        return None
    if receipt.get("all"):
        return []
    if required["all"]:
        return ["(every package: %s)" % "; ".join(required["all_why"][:3])]
    ran = set(receipt.get("packages") or [])
    return [p for p in required["packages"] if p not in ran]


# --------------------------------------------------------------------------- git


def _git(cwd, *argv, env=None):
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "-c", "core.quotePath=false", *argv],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def renet_base(root):
    """(renet commit the console merge-base with origin/main pins, None) or (None, why)."""
    merge_base = _git(root, "merge-base", "HEAD", "origin/main")
    if not merge_base:
        return None, "no merge-base of HEAD and origin/main"
    link = _git(root, "rev-parse", "%s:%s" % (merge_base, RENET))
    if not link:
        return None, "the origin/main merge-base pins no %s" % RENET
    return link, None


def changed_since(renet, base):
    """Renet paths differing between `base` and the working files (untracked included), or None when `base` is not in the checkout."""
    if _git(renet, "cat-file", "-e", "%s^{commit}" % base) is None:
        return None
    diff = _git(renet, "diff", "--name-only", base)
    extra = _git(renet, "ls-files", "--others", "--exclude-standard")
    if diff is None or extra is None:
        return None
    return sorted({p for p in (diff.split("\n") + extra.split("\n")) if p})


def console_changed_since(root):
    """Console paths differing between the merge-base with origin/main and the working files (untracked included); [] when git cannot say, since the renet side then selects every package anyway."""
    merge_base = _git(root, "merge-base", "HEAD", "origin/main")
    if not merge_base:
        return []
    diff = _git(root, "diff", "--name-only", merge_base)
    extra = _git(root, "ls-files", "--others", "--exclude-standard")
    if diff is None or extra is None:
        return []
    return sorted({p for p in (diff.split("\n") + extra.split("\n")) if p})


def changed_between(renet, old, new):
    """Renet paths changed from commit `old` to `new`, or None when either is not in the checkout."""
    for sha in (old, new):
        if _git(renet, "cat-file", "-e", "%s^{commit}" % sha) is None:
            return None
    diff = _git(renet, "diff", "--name-only", old, new)
    return None if diff is None else sorted(p for p in diff.split("\n") if p)


def working_tree(renet):
    """(tree of the working files, dirty): HEAD^{tree} when clean, else written through a throwaway index, as the gate does. (None, True) when git cannot say."""
    status = _git(renet, "status", "--porcelain", "--untracked-files=all")
    if status is None:
        return None, True
    if status == "":
        return _git(renet, "rev-parse", "HEAD^{tree}"), False
    index = os.path.join(tempfile.gettempdir(), "renet-test-index-%s" % uuid.uuid4().hex)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        if _git(renet, "read-tree", "HEAD", env=env) is None:
            return None, True
        if _git(renet, "add", "-A", env=env) is None:
            return None, True
        return _git(renet, "write-tree", env=env), True
    finally:
        with contextlib.suppress(OSError):
            os.unlink(index)


# --------------------------------------------------------------------------- the advisory


def pending(root, env=None):
    """(changed paths, required, tree, missing) when renet changed since origin/main and no receipt covers the working files, else None."""
    test_map = load_map(root)
    renet = pathlib.Path(root) / RENET
    if test_map is None or not (renet / "go.mod").is_file():
        return None
    base, _why = renet_base(root)
    changed = changed_since(renet, base) if base else None
    if changed is None:
        required = {
            "all": True,
            "packages": all_packages(test_map),
            "all_why": ["the renet base commit is unknown"],
            "mapped": 0,
        }
        changed = []
    else:
        required = required_for(test_map, changed, None, console_changed_since(root))
        if not required["packages"]:
            return None
    tree, _dirty = working_tree(renet)
    if not tree:
        return None
    missing = uncovered(read_receipt(tree, env), required)
    if missing == []:
        return None
    return changed, required, tree, missing


def advisory(root, env=None):
    """The advisory text, or None when renet is unchanged, untestable here, or already covered. Never raises: report-only, so a broken probe must never refuse a stop."""
    try:
        found = pending(root, env)
    except Exception:
        return None
    if found is None:
        return None
    changed, required, tree, missing = found
    if missing is None:
        detail = "no receipt for renet tree %s" % tree[:12]
    else:
        shown = ", ".join(missing[:MAX_LISTED])
        more = " (+%d more)" % (len(missing) - MAX_LISTED) if len(missing) > MAX_LISTED else ""
        detail = "the receipt for renet tree %s did not run %s%s" % (tree[:12], shown, more)
    scope = "every package" if required["all"] else "%d package(s)" % len(required["packages"])
    return (
        "RENET CHANGED, GO TESTS NOT RUN: %d renet path(s) changed since origin/main select %s, and %s.\n"
        "  Run `%s` (it runs exactly the mapped `go test` and writes the receipt the push guard reads)."
        " Report-only: nothing here blocks the stop; block_renet_untested_push refuses the push."
    ) % (len(changed), scope, detail, COMMAND)
