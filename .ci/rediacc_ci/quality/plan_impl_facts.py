"""Immutable git facts for check:ci-plan-implementation, kept across runs (PLAN-two-track-merge-dev P1, design D2).

Only facts that cannot change for their key are stored:

  patch    {sha: patch-id}            a commit's diff never changes
  date_c   {sha40: committer date}    likewise its dates
  date_a   {sha40: author date}
  follow   {"rel@last-touch": [names]} `git log --follow` behind the last commit that touched rel

Reachability from HEAD or origin/main is NEVER stored: a rebase moves it, so it is asked fresh every run (the REBASE control). The file is keyed on a closure hash, the sha256 of the source of every module that computes these facts, so a change to any of them starts the cache empty (the STALE control). A missing, unreadable or foreign file is an empty cache, and the cache is never a verdict source: every answer it holds is one the per-call path would compute (the DIFFERENTIAL control).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable

CACHE_REL = ".ci/cache/plan-implementation/facts-v1.json"
SCHEMA = 1
KINDS = ("patch", "date_c", "date_a", "follow")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def closure_hash(files: Iterable[str | os.PathLike]) -> str:
    """sha256 over SCHEMA and the bytes of each file (sorted by path); a file that cannot be read, missing or not, hashes as the body `unreadable`."""
    h = hashlib.sha256(b"plan-impl-facts\0%d\0" % SCHEMA)
    for path in sorted(str(f) for f in files):
        try:
            body = pathlib.Path(path).read_bytes()
        except OSError:
            body = b"unreadable"  # a missing or unreadable source hashes as such, so the run starts cold rather than aborting (review fdd241b3.4)
        h.update(path.encode() + b"\0" + body + b"\0")
    return h.hexdigest()


class Facts:
    """One run's view of the cache: load once, answer and record, save once if anything new was learned."""

    def __init__(self, root, closure: str, path: str | None = None):
        self.root = root
        self.rel = path or CACHE_REL  # an absolute path replaces the root-relative default (pathlib join), which is how a test or `--no-fact-cache` redirects the file
        self.path = pathlib.Path(root) / self.rel
        self.closure = closure
        self.data: dict[str, dict] = {k: {} for k in KINDS}
        self.dirty = False
        self.hits = 0
        self.misses = 0
        self._run_memo: dict[tuple[str, str], str] = {}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if (
            not isinstance(doc, dict)
            or doc.get("closure") != closure
            or doc.get("schema") != SCHEMA
        ):
            return
        for kind in KINDS:
            got = doc.get(kind)
            if isinstance(got, dict):
                self.data[kind] = got

    def get(self, kind: str, key: str):
        got = self.data[kind].get(key)
        if got is None:
            self.misses += 1
        else:
            self.hits += 1
        return got

    def put(self, kind: str, key: str, value) -> None:
        if kind not in KINDS:
            raise KeyError(
                "plan_impl_facts stores only %s, never %r: reachability is asked fresh every run"
                % (", ".join(KINDS), kind)
            )
        if value in (None, "", []) or self.data[kind].get(key) == value:
            return
        self.data[kind][key] = value
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            target = pathlib.Path(self.root) / self.rel
            # tree-write: safe the fact cache lives under .ci/cache/plan-implementation (CACHE_REL, gitignored); an absolute path replaces it only in tests and for /dev/null under --no-fact-cache
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            # tree-write: safe the fact cache lives under .ci/cache/plan-implementation (CACHE_REL, gitignored); an absolute path replaces it only in tests and for /dev/null under --no-fact-cache
            tmp.write_text(
                json.dumps({"schema": SCHEMA, "closure": self.closure, **self.data}),
                encoding="utf-8",
            )
            # tree-write: safe the fact cache lives under .ci/cache/plan-implementation (CACHE_REL, gitignored); an absolute path replaces it only in tests and for /dev/null under --no-fact-cache
            tmp.replace(target)
            self.dirty = False
        except OSError:
            pass  # an unwritable cache only makes the next run cold

    def commit_date(self, kind: str, sha: str, compute: Callable[[str], str]) -> str:
        """A commit date (kind date_c or date_a); only a full sha is a stable key, anything else is asked fresh."""
        if not SHA40.match(sha or ""):
            # Not a stable key across runs (an abbreviation, a ref), but stable within one: memoized for this run only (review fdd241b3.3).
            memo_key = (kind, sha)
            if memo_key not in self._run_memo:
                self._run_memo[memo_key] = compute(sha)
            return self._run_memo[memo_key]
        got = self.get(kind, sha)
        if got is None:
            got = compute(sha)
            self.put(kind, sha, got)
        return got

    def follow(
        self, rel: str, last_touch: str, compute: Callable[[str], tuple[str, ...]]
    ) -> tuple[str, ...]:
        """`git log --follow` names of rel, keyed on the last commit that touched it; no last-touch sha (a path git does not know) is asked fresh."""
        if not SHA40.match(last_touch or ""):
            return compute(rel)
        key = "%s@%s" % (rel, last_touch)
        got = self.get("follow", key)
        if not (isinstance(got, list) and all(isinstance(n, str) for n in got)):
            got = None  # absent, or a damaged value (a string would read as one name per character, review fdd241b3.2): a miss
            got = list(compute(rel))
            self.data["follow"][key] = got
            self.dirty = True
        return tuple(got)

    def patch_ids(
        self,
        listing: list[str],
        batch: Callable[[], dict[str, str] | None],
        one: Callable[[str], str],
        batch_over: int = 64,
    ) -> dict[str, str]:
        """{sha: patch-id} for `listing`: cached ones from the cache, and the rest from one batched pass when many are missing, else one call each."""
        missing = [s for s in listing if self.get("patch", s) is None]
        if len(missing) > batch_over:
            by_sha = batch()
            if by_sha is not None:
                for sha, pid in by_sha.items():
                    self.put("patch", sha, pid)
        for sha in missing:
            if self.data["patch"].get(sha) is None:
                self.put("patch", sha, one(sha))
        return {s: self.data["patch"][s] for s in listing if self.data["patch"].get(s)}
