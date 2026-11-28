#!/usr/bin/env python3
r"""check:ci-removed-env-vars -- a removed environment variable stays removed, in code, config, docs and locales.

WHAT IT GUARDS. `.ci/config/removed-env-vars.json` lists environment variables removed with no deprecation window (CLAUDE.md rule 2, clean break). The first is the config-edit override PLAN-rmcp-config-edit-removal.md deletes (decision D17): an agent could rewrite the whole config, including the policy that limits it, through it. A name that survives in a doc page, a locale string or a comment is how the habit of setting it comes back, so a mention is held to the same rule as a reader.

THE CLAUSES.

  1. NO OCCURRENCE. No tracked file in console or an initialized submodule
     (`git ls-files --recurse-submodules`) contains a listed name, outside the
     `excluded` entries of the JSON and this gate's own three files. An entry is a
     path prefix, or an `fnmatch` pattern when it holds a `*` (the one announcing
     blog post exists once per locale directory). Each finding prints `path:line`
     and the name.
  2. EACH EXCLUSION IS RE-DERIVED. An excluded entry must still match a tracked
     path; an entry that matches nothing is a dead exemption and reds.
  3. ANTI-VACUITY. An empty `removed` list, or a scan that lists zero tracked
     files, is a REFUSAL: the instrument lost its input, not a clean tree.

A test that must name the variable spells it in pieces (`['REDIACC', 'ALLOW', ...].join('_')` in TypeScript, two concatenated literals in Python, where ruff's FLY002 refuses a constant join), which is the one way through clause 1 and keeps the literal out of the corpus.

`--selftest` builds throwaway git repositories and requires a planted occurrence to red, an occurrence under an excluded prefix and a split spelling to stay green, and a dead exclusion to red. `--root <dir>` scans another checkout (the selftest and the pytest use it).

Exit 0 clean, 1 on a finding or refusal, 2 on a failed control or bad arguments.

NOT WIRED YET, ON PURPOSE. The tree still names the config-edit override in the www pages and a few files outside this plan, so the gate is red today; a header here would register a red gate (gen:gates reads it). The wiring commit (PLAN-rmcp-docs.md DO2, the last commit of the removal's landing) adds the header below between its `----` markers, the package.json script `check:ci-removed-env-vars` and the regenerated manifest, lock and workflow step:

    step: Removed env vars stay removed
    lane: quality-static
    needs: submodules
    selftest: true
    why: a variable removed with no deprecation window must not survive in code, config,
         docs or locales, where it teaches users and agents to set it again.
"""

from __future__ import annotations

import fnmatch
import json
import pathlib
import subprocess
import sys
import tempfile

import _cipath
import _gate_args

CONFIG_REL = ".ci/config/removed-env-vars.json"
# This gate's own files must name what they forbid.
SELF = (
    CONFIG_REL,
    ".ci/scripts/quality/check_removed_env_vars.py",
    ".ci/rediacc_ci/tests/test_check_removed_env_vars.py",
)


def tracked_files(root: pathlib.Path) -> list[str]:
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--recurse-submodules"],
        capture_output=True,
        check=True,
    )
    return [p for p in done.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def load_config(root: pathlib.Path) -> tuple[list[str], dict[str, str]]:
    data = json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))
    names = [entry["name"] for entry in data.get("removed", [])]
    return names, dict(data.get("excluded", {}))


def excluded_by(rel: str, entry: str) -> bool:
    """True when `entry` (a path prefix, or an fnmatch pattern if it holds `*`) covers `rel`."""
    if "*" in entry:
        return fnmatch.fnmatchcase(rel, entry)
    return rel.startswith(entry)


def scan(
    root: pathlib.Path, files: list[str], names: list[str], excluded: dict[str, str]
) -> list[tuple[str, int, str]]:
    """Every (path, line, name) occurrence outside the exclusions."""
    needles = [(name, name.encode("utf-8")) for name in names]
    findings: list[tuple[str, int, str]] = []
    for rel in files:
        if rel in SELF or any(excluded_by(rel, entry) for entry in excluded):
            continue
        path = root / rel
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        for name, needle in needles:
            if needle not in data:
                continue
            for number, line in enumerate(data.splitlines(), start=1):
                if needle in line:
                    findings.append((rel, number, name))
    return findings


def dead_exclusions(files: list[str], excluded: dict[str, str]) -> list[str]:
    return [entry for entry in excluded if not any(excluded_by(f, entry) for f in files)]


def check(root: pathlib.Path) -> int:
    names, excluded = load_config(root)
    if not names:
        print(
            "✗ removed-env-vars: VACUOUS: %s lists no removed name; refusing an empty check"
            % CONFIG_REL
        )
        return 1
    files = tracked_files(root)
    if not files:
        print(
            "✗ removed-env-vars: VACUOUS: git ls-files listed zero tracked files under %s; refusing"
            % root
        )
        return 1
    rc = 0
    dead = dead_exclusions(files, excluded)
    for prefix in dead:
        print(
            "✗ excluded entry %r matches no tracked path: a dead exemption, delete it from %s"
            % (prefix, CONFIG_REL)
        )
        rc = 1
    findings = scan(root, files, names, excluded)
    for rel, number, name in findings:
        print("✗ %s:%d: names the removed variable %s" % (rel, number, name))
    if findings:
        touched = len({rel for rel, _, _ in findings})
        print(
            "✗ removed-env-vars: %d occurrence(s) in %d file(s). Delete each mention (the variable "
            "no longer exists); a test that must name it spells it in pieces. Reasons per name: %s"
            % (len(findings), touched, CONFIG_REL)
        )
        rc = 1
    if rc == 0:
        print(
            "✓ removed-env-vars: %d removed name(s) absent from %d tracked file(s); %d exclusion(s), "
            "each matching a tracked path" % (len(names), len(files), len(excluded))
        )
    return rc


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def make_repo(base: pathlib.Path, files: dict[str, str], excluded: dict[str, str]) -> pathlib.Path:
    """A throwaway git repository with `files` tracked and a config naming one removed variable."""
    name = "SELFTEST_REMOVED_VAR"
    config = {"removed": [{"name": name, "reason": "selftest"}], "excluded": excluded}
    base.mkdir(parents=True)
    _git(base, "init", "-q")
    for rel, text in {CONFIG_REL: json.dumps(config), **files}.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.replace("{VAR}", name), encoding="utf-8")
    _git(base, "add", "-A")
    return base


def selftest() -> int:
    cases = [
        ("a planted occurrence reds", {"docs/page.md": "set {VAR}=* first\n"}, {}, 1),
        ("a clean tree passes", {"docs/page.md": "nothing here\n"}, {}, 0),
        (
            "an occurrence under an excluded prefix passes",
            {"agent/ledgers/x.jsonl": "{VAR}\n", "docs/page.md": "clean\n"},
            {"agent/ledgers/": "record"},
            0,
        ),
        (
            "an occurrence matched by an excluded pattern passes",
            {"blog/de/post.md": "{VAR}\n", "blog/de/other.md": "clean\n"},
            {"blog/*/post.md": "announcement"},
            0,
        ),
        (
            "a pattern does not cover a sibling file",
            {"blog/de/post.md": "clean\n", "blog/de/other.md": "{VAR}\n"},
            {"blog/*/post.md": "announcement"},
            1,
        ),
        (
            "a split spelling passes",
            {"src/t.ts": "const V = ['SELFTEST', 'REMOVED', 'VAR'].join('_');\n"},
            {},
            0,
        ),
        (
            "a dead exclusion reds",
            {"docs/page.md": "clean\n"},
            {"agent/nothing-here/": "dead"},
            1,
        ),
    ]
    failures = 0
    with tempfile.TemporaryDirectory() as scratch:
        for index, (label, files, excluded, want) in enumerate(cases):
            repo = make_repo(pathlib.Path(scratch) / str(index), files, excluded)
            got = check(repo)
            ok = got == want
            failures += 0 if ok else 1
            print("  %s  %s (rc %d, want %d)" % ("PASS" if ok else "FAIL", label, got, want))
    print("%s removed-env-vars selftest: %d failure(s)" % ("✓" if failures == 0 else "✗", failures))
    return 0 if failures == 0 else 2


def main(parsed: _gate_args.Parsed) -> int:
    if "--selftest" in parsed.switches:
        return selftest()
    root = pathlib.Path(parsed.values.get("--root") or _cipath_root()).resolve()
    return check(root)


def _cipath_root() -> str:
    return str(pathlib.Path(__file__).resolve().parents[3])


if __name__ == "__main__":
    _parsed = _gate_args.parse(
        "check_removed_env_vars.py", sys.argv[1:], switches=("--selftest",), valued=("--root",)
    )
    raise SystemExit(main(_parsed))
