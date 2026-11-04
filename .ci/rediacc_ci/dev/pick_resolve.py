"""Continue a `git cherry-pick` in progress, merging the renet i18n hash table on the way.

    python3 .ci/rediacc_ci/dev/pick_resolve.py [--limit <n>]

Run it in the repository holding the pick (private/renet for renet commits) after the lead's own first `git cherry-pick -x ...` stopped on a conflict. It never starts a pick: with no `CHERRY_PICK_HEAD` it exits 2 and touches nothing.

WHY. Landing a lease's renet commits conflicted on `pkg/i18n/locales/hashes.json` every time, because each commit regenerates the same generated table and git sees two edits to neighbouring lines. A throwaway /tmp script settled it by hand each landing. This is that script, tracked: it merges the JSON three-way from the index stages (`:1:` base, `:2:` ours, `:3:` theirs) key by key, stages the result and runs `cherry-pick --continue`, and repeats while the sequencer stops again.

THE MERGE. A key one side changed and the other left stays changed. A key both sides changed to the same value is kept. A key both sides changed to different values is a real conflict, so the script stops and leaves the pick as it was, except `$meta.keyCount`, which the generator derives as the number of hashes and so is set from the merged table. Any other conflicted file, or a missing stage (an add/add or a delete), stops the run: only the hash table is merged here, and the rest is the lead's to read.

The output is `json.dumps(indent=2, ensure_ascii=False, sort_keys=True)` plus a newline, the form `scripts/gen/generate-translation-hashes.ts` writes.

Exit codes: 0 the pick sequence finished, 1 stopped on a conflict or a failed continue (the reason is printed), 2 no pick in progress.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

TABLE_SUFFIX = "pkg/i18n/locales/hashes.json"
MISSING = object()
DEFAULT_LIMIT = 50


class StopError(Exception):
    """The run cannot continue by itself; the message says why."""


def _git(*args, check=False):
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if check and done.returncode != 0:
        message = "git %s exited %d: %s" % (" ".join(args), done.returncode, done.stderr.strip())
        raise StopError(message)
    return done


def pick_in_progress():
    return _git("rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD").returncode == 0


def conflicted():
    return sorted(_git("diff", "--name-only", "--diff-filter=U", check=True).stdout.split())


def _short(value):
    text = "<absent>" if value is MISSING else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."


def merge3(base, ours, theirs, where=""):
    """Three-way merge of JSON values. Returns the merged value, or MISSING when the key is gone. Raises StopError on two different edits of one leaf."""
    if ours == theirs:
        return ours
    if base == ours:
        return theirs
    if base == theirs:
        return ours
    if all(isinstance(v, dict) for v in (base, ours, theirs)):
        merged = {}
        for key in sorted(set(base) | set(ours) | set(theirs)):
            value = merge3(
                base.get(key, MISSING),
                ours.get(key, MISSING),
                theirs.get(key, MISSING),
                "%s/%s" % (where, key),
            )
            if value is not MISSING:
                merged[key] = value
        return merged
    if where == "/$meta/keyCount":
        return ours
    message = "both sides changed %s differently: ours %s, theirs %s" % (
        where or "/",
        _short(ours),
        _short(theirs),
    )
    raise StopError(message)


def merge_table(base, ours, theirs):
    """`merge3` over whole files, with the derived key count set from the merged hashes."""
    for name, doc in (("base", base), ("ours", ours), ("theirs", theirs)):
        if not isinstance(doc, dict):
            message = "the %s stage is not a JSON object" % name
            raise StopError(message)
    merged = merge3(base, ours, theirs)
    meta, hashes = merged.get("$meta"), merged.get("hashes")
    if isinstance(meta, dict) and isinstance(hashes, dict) and "keyCount" in meta:
        meta["keyCount"] = len(hashes)
    return merged


def _stage(n, path):
    done = _git("show", ":%d:%s" % (n, path))
    if done.returncode != 0:
        message = (
            "%s has no stage %d in the index (add/add or delete), so it is not merged here"
            % (
                path,
                n,
            )
        )
        raise StopError(message)
    try:
        return json.loads(done.stdout)
    except ValueError as err:
        message = "stage %d of %s is not JSON: %s" % (n, path, err)
        raise StopError(message) from err


def resolve_table(path):
    merged = merge_table(_stage(1, path), _stage(2, path), _stage(3, path))
    top = pathlib.Path(_git("rev-parse", "--show-toplevel", check=True).stdout.strip())
    text = json.dumps(merged, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    (top / path).write_text(text, encoding="utf-8")
    _git("add", "--", str(top / path), check=True)


def step():
    """Resolve the hash table when it is the one conflict, then continue. Raises StopError on anything else."""
    unmerged = conflicted()
    if unmerged and not all(p.endswith(TABLE_SUFFIX) for p in unmerged):
        message = "other conflicts, not merged here: %s" % ", ".join(unmerged)
        raise StopError(message)
    for path in unmerged:
        resolve_table(path)
    done = _git("-c", "core.editor=true", "cherry-pick", "--continue")
    text = (done.stdout + done.stderr).strip()
    return done.returncode, text.splitlines()[0] if text else ""


def run(limit):
    if not pick_in_progress():
        sys.stderr.write(
            "pick_resolve: no cherry-pick in progress; start it with git cherry-pick first\n"
        )
        return 2
    for n in range(1, limit + 1):
        try:
            rc, first = step()
        except StopError as err:
            sys.stderr.write("pick_resolve: STOP %s\n" % err)
            return 1
        sys.stdout.write("pick_resolve: step %d: continue rc=%d %s\n" % (n, rc, first))
        if not pick_in_progress():
            sys.stdout.write("pick_resolve: done\n")
            return 0
        if rc != 0 and not conflicted():
            sys.stderr.write("pick_resolve: STOP the continue failed with no conflict to merge\n")
            return 1
    sys.stderr.write("pick_resolve: STOP still in progress after %d steps\n" % limit)
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="most picks to continue")
    return run(parser.parse_args().limit)


if __name__ == "__main__":
    sys.exit(main())
