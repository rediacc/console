#!/usr/bin/env python3
"""No tracked source file may be invisible to the linter, and biome's allowlist must actually be in force.

WHY THIS EXISTS. Biome is the only linter. Its scope is biome.json's `files.includes` allowlist, and the lint commands in package.json choose how much of it they hand over. Four failures this gate keeps shut:

  1. SCOPE INVISIBILITY. A file the allowlist does not name is linted by nothing, and every gate stays green because a file outside scope cannot produce a finding. On 2026-08-06 that hid 93 files (the repo's own lint rules, the live CI scope engine, ten gate implementations).

  2. A SILENTLY DISCARDED ALLOWLIST. A single `//` comment anywhere in biome.json's `files` object makes biome throw away the entire `includes` list -- no parse error, no warning. Measured: `biome lint private/account/` goes from 631 files to 1428 and reports 3657 errors. The failure LOOKS like a lint explosion in unrelated code.

  3. A COMMAND THAT NARROWS THE CONFIG. `lint`, `fix:lint` and `check:lint` must reach the same files, and the same files the allowlist declares: a root deleted from one of them removes files from the linter's view and leaves every gate green. The roots are compared by BIOME'S OWN COUNT, not by reimplementing its glob semantics (the pattern check_format_scope.py uses for the formatter).

  4. A PROBE THAT CANNOT FAIL. "Everything is covered" is satisfied by an oracle that answers yes to everything, so the allowlist is probed in both directions first (an anchor that must be in, a canary that must be out).

THE ORACLE IS BIOME'S "Checked N files". Handed N candidate paths, biome reports N when it reaches all of them and fewer when its file selection drops some; the dropped ones are then named by bisection. A file excluded on purpose is listed in BIOME_EXEMPT with the reason it is not source.

WHAT IT DOES NOT DO. It does not judge whether a file's rules are the right rules -- only that biome sees it. check_lint_rule_liveness.py proves a rule can fire; the two are complements and neither subsumes the other.

---- gate ----
step: Every source file reaches a linter
needs: submodules
selftest: true
lane: quality-code
---- end gate ----
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

# Extensions a linter is expected to cover.
JS_EXT = (".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx")

# Paths biome legitimately does not lint, each with the reason it is exempt.
# An entry here is a claim that the file is not source, and it is reviewable.
BIOME_EXEMPT = {
    "packages/cli/templates/": "shipped template files, embedded into the CLI binary rather than executed here",
    "packages/www/public/": "static site assets, including large generated search-index bundles",
    "packages/json/": "data templates for the JSON package, not program source",
    "private/": "submodules and sibling repos with their own CI",
    ".ci/cache/": "generated CI state, rewritten by CI on every run",
}

# Suffix-matched exemptions, same contract: each is a claim that the file is not hand-written source.
BIOME_EXEMPT_SUFFIX = {
    ".d.ts": (
        "type declarations only -- no executable code for a rule to have an "
        "opinion about; tsc is the checker that matters for these"
    ),
    ".generated.ts": "emitted by a generator and rewritten on every run; the generator is the source",
    "/renet-contract/data/functions.schema.ts": "generated from the renet contract",
    "/renet-contract/data/vault.schema.ts": "generated from the renet contract",
}

# The npm scripts that carry biome's lint command. All of them must reach the
# FILES the config declares: a developer script narrower than CI gives a clean local run over a tree CI lints more of.
LINT_ROOT_SCRIPTS = ("check:lint", "fix:lint", "lint")

# A path that MUST be outside biome's includes. If biome starts processing it, the allowlist has been discarded -- which is exactly what a stray comment in the `files` object does, silently.
BIOME_CANARY = "packages/www/src/i18n/translations/.translation-hashes.json"
# A path that MUST be inside it, so "everything is out of scope" cannot pass.
BIOME_ANCHOR = "packages/cli/src/index.ts"

CHECKED = re.compile(r"Checked (\d+) files?")


class BiomeUnreadableError(Exception):
    """biome did not answer the question at all."""


def tracked(root, patterns):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return None
    return out.stdout.split()


def exempt(path):
    for suffix, why in BIOME_EXEMPT_SUFFIX.items():
        if path.endswith(suffix):
            return why
    return next((why for prefix, why in BIOME_EXEMPT.items() if path.startswith(prefix)), None)


def biome_count(root, args):
    """How many files `biome lint <args>` reports, from biome's own summary line.

    RAISES rather than guessing when biome did not run: a probe that cannot distinguish absence from a negative answer is not a probe. "No files were processed" is a real answer (zero).
    """
    try:
        out = subprocess.run(
            ["npx", "--no-install", "biome", "lint", "--max-diagnostics=0", *args],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=False,
        )
    except OSError as exc:
        raise BiomeUnreadableError("could not launch biome: %s" % exc) from exc
    blob = out.stdout + out.stderr
    found = CHECKED.search(blob)
    if found:
        return int(found.group(1))
    if "No files were processed" in blob:
        return 0
    raise BiomeUnreadableError(
        "biome produced neither 'Checked N files' nor 'No files were processed' for %d path(s)\n"
        "  exit=%s\n  output:\n%s" % (len(args), out.returncode, blob[:800] or "  (empty)")
    )


def unreached(root, paths):
    """The subset of `paths` biome's file selection drops, named by bisection.

    The common case is ONE biome run (the count equals the number of paths). Bisection runs only when something is dropped, to name it.
    """
    if not paths:
        return []
    if biome_count(root, paths) == len(paths):
        return []
    if len(paths) == 1:
        return list(paths)
    mid = len(paths) // 2
    return unreached(root, paths[:mid]) + unreached(root, paths[mid:])


def lint_roots(scripts, name):
    """The path arguments of every `biome lint` call in script `name`.

    Returns None when the script is missing or invokes no `biome lint` at all.
    """
    body = scripts.get(name)
    if body is None:
        return None
    found: list[str] = []
    calls = 0
    for segment in body.split("&&"):
        tokens = segment.split()
        for i in range(len(tokens) - 1):
            if tokens[i] == "biome" and tokens[i + 1] == "lint":
                calls += 1
                found.extend(t for t in tokens[i + 2 :] if not t.startswith("-"))
                break
    if calls == 0:
        return None
    return list(dict.fromkeys(found))


def narrowing(root, scripts):
    """Lines explaining which lint script reaches fewer files than the config declares, or []."""
    out = []
    try:
        full = biome_count(root, ["."])
    except BiomeUnreadableError as exc:
        return ["CANNOT PROBE BIOME: %s" % exc]
    for name in LINT_ROOT_SCRIPTS:
        roots = lint_roots(scripts, name)
        if roots is None:
            out.append(
                "package.json script %r does not invoke `biome lint` (renamed, removed, or\n"
                "  moved to another tool). Until it parses, nothing here can speak for its scope."
                % name
            )
            continue
        mine = full if roots in ([], ["."]) else biome_count(root, roots)
        if mine < full:
            out.append(
                "%s hands biome %s and reaches %d file(s), but biome.json's scope is %d.\n"
                "  %d tracked file(s) are linted by nothing through that command. Make it\n"
                "  `biome lint .` and let biome.json own the scope."
                % (name, " ".join(roots), mine, full, full - mine)
            )
    return out


def selftest(root):
    """Controls on the oracle itself. Returns the number of failures."""
    bad = 0

    def check(name, ok, detail=""):
        nonlocal bad
        print(
            "  %s  %s%s"
            % ("PASS" if ok else "FAIL", name, "\n        " + detail if (detail and not ok) else "")
        )
        if not ok:
            bad += 1

    anchor, canary = BIOME_ANCHOR, BIOME_CANARY
    check("the anchor is inside biome's allowlist", biome_count(root, [anchor]) == 1)
    check("the canary is outside biome's allowlist", biome_count(root, [canary]) == 0)
    # PLANT: one reachable path and one unreachable one must be told apart by the very function the verdict uses.
    check(
        "PLANT: an excluded path among reachable ones is named by unreached()",
        unreached(root, [anchor, canary]) == [canary],
        str(unreached(root, [anchor, canary])),
    )
    check("CONTROL: a reachable path alone is not reported", unreached(root, [anchor]) == [])
    scripts = {"lint": "biome lint packages/cli", "ok": "biome lint . --error-on-warnings"}
    check("a narrowed command parses to its roots", lint_roots(scripts, "lint") == ["packages/cli"])
    check("a whole-tree command parses to the root `.`", lint_roots(scripts, "ok") == ["."])
    check("a non-biome command parses to None", lint_roots({"lint": "eslint ."}, "lint") is None)
    return bad


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="run the oracle controls only")
    args = parser.parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[3]

    files = tracked(root, ["*" + e for e in JS_EXT])
    if files is None:
        print("VACUOUS INPUT: not a git work tree, so nothing can be enumerated", file=sys.stderr)
        return 1
    if len(files) < 200:
        print(
            "VACUOUS INPUT: only %d js/ts file(s) tracked, expected 200+. A coverage\n"
            "check over an empty set exits 0 and reads exactly like full coverage." % len(files),
            file=sys.stderr,
        )
        return 1

    # ---- CONTROLS: biome's allowlist must be demonstrably IN FORCE, in both directions.
    try:
        failures = selftest(root)
    except BiomeUnreadableError as exc:
        print(
            "CANNOT PROBE BIOME, so no verdict about its scope is possible:\n  %s\n"
            "  This is an ENVIRONMENT failure, not a config failure. Do not go\n"
            "  editing biome.json on the strength of it." % exc,
            file=sys.stderr,
        )
        return 1
    if failures:
        print(
            "CONTROL FAILED: %d probe(s) above. biome's file selection is not behaving as\n"
            "  biome.json declares (a `//` comment inside the `files` object discards the\n"
            "  whole `includes` list with no warning), so nothing below is meaningful." % failures,
            file=sys.stderr,
        )
        return 1
    if args.selftest:
        return 0

    try:
        scripts = json.loads((root / "package.json").read_text())["scripts"]
    except (OSError, ValueError, KeyError):
        print(
            "could not read package.json's scripts, so the lint commands cannot be\n"
            "  checked. This is an ENVIRONMENT failure, not a scope failure.",
            file=sys.stderr,
        )
        return 1

    problems = narrowing(root, scripts)
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1

    candidates = [f for f in files if not exempt(f)]
    try:
        dropped = unreached(root, candidates)
    except BiomeUnreadableError as exc:
        print("CANNOT PROBE BIOME: %s" % exc, file=sys.stderr)
        return 1
    if dropped:
        print(
            "%d tracked file(s) are linted by NOTHING -- biome.json's `files.includes` does\n"
            "  not reach them and they carry no documented exemption:" % len(dropped),
            file=sys.stderr,
        )
        for path in sorted(dropped)[:40]:
            print("    %s" % path, file=sys.stderr)
        if len(dropped) > 40:
            print("    ... and %d more" % (len(dropped) - 40), file=sys.stderr)
        print(
            "\n  Either add the root to `files.includes` in biome.json, or exempt the prefix\n"
            "  in BIOME_EXEMPT here WITH THE REASON it is not source.",
            file=sys.stderr,
        )
        return 1

    print(
        "%d tracked js/ts file(s) reach biome (%d exempt by documented reason); the %d lint "
        "command(s) reach the whole config scope and its allowlist is in force"
        % (len(candidates), len(files) - len(candidates), len(LINT_ROOT_SCRIPTS))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
