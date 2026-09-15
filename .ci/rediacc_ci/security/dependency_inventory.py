#!/usr/bin/env python3
"""Port of `.ci/scripts/security/dependency-inventory.sh`.

W7P6 wave 27. The bash twin stays the LIVE tool; this module is its
VERIFIED-EQUIVALENT ALTERNATIVE, proved byte-for-byte on both streams by
`.ci/rediacc_ci/tests/test_security_dependency_inventory.py` and by the K=5
shadow ledger `.ci/shadow/w7p6-dependency-inventory.observations.jsonl`.
Nothing is repointed at this file. Cutover is a separate, later, driver-only
step.

WHAT IT DOES. Enumerates every dependency across the four analyzed Rediacc
packages (www, cli, account, renet) for the NIS2/CRA supply-chain SBOM. Each
dependency is classified by level (direct vs transitive), tagged by type
(dependencies/devDependencies/peer/optional for npm; direct/indirect for Go),
and carries its full dependency chain(s) from the package root down.

REAL RUNS OR STUBS: THE ANSWER IS BOTH, AND THE SPLIT IS DELIBERATE.
The twin's only external calls are `npm ls --all --json [--omit=dev]
[--workspace NAME]`, `go list -m`, `go list -m -json all` and `go mod graph`.
Every one of those is a READ of an already-installed tree: `npm ls` reads
`node_modules` and never writes it, and the three `go` probes read `go.mod` /
`go.sum` / the module cache. `go mod graph` and `go list -m -json all` CAN write
`go.sum` when a checksum is missing, so the differential passes `GOFLAGS=-mod=mod`
to neither side and instead asserts, after every real-run case, that `go.mod`,
`go.sum` and every lockfile still hash to what they hashed before. So:

  * the HAPPY PATHS run for real, against this repository's own dependency tree,
    because that is the only input that exercises 1,760 records, 209 Go modules
    and the seven chain-truncation warnings, and no fixture reproduces it;
  * the FAILURE PATHS (npm printing garbage, a missing `node_modules`, `go list`
    dying, `go mod graph` returning nothing) run against RECORDING FAKES on a
    scratch `PATH`, because there is no way to make the real tools fail on
    demand without breaking the tree.

PORT NOTES -- unless an item says otherwise it is REPRODUCED, not repaired.
Fixing one only HERE would make the differential lie, and every one of the three
below is a genuine defect in the twin that this wave REPORTS rather than fixes.

  1. `require_cmd jq npm go awk` CHECKS ONLY `jq`. `common.sh:141-148` binds
     `local cmd="$1"` and ignores the rest, so `npm`, `go` and `awk` are NOT
     probed and their absence surfaces later as a confusing empty-JSON failure
     instead of the one-line "Required command 'npm' is not available" the call
     was written to produce. Reproduced exactly: this port probes `jq` and
     nothing else -- and it probes `jq` even though it never runs jq, because
     the twin's exit-1-with-that-message is observable behaviour.

  2. `--help` LEAKS EIGHT LINES OF SHELL SOURCE. `sed -n '2,35p' "$0" | sed
     's/^# \\?//'` slices a fixed line RANGE, and the header comment ends at line
     27; lines 28-35 are `set -euo pipefail`, the `SCRIPT_DIR=` assignment, the
     `# shellcheck` directive (rendered as bare `shellcheck source=...`), the
     `source` line and the first two variable defaults. `HELP_TEXT` below is that
     output verbatim, and `test_help_text_constant_still_matches_the_twin`
     re-derives it from the twin's bytes on every run so the constant cannot
     drift when the twin's header moves.

  3. A MISSING OPTION VALUE IS A RAW BASH DIAGNOSTIC. `--format` as the last
     argument reads `$2` under `set -u` and bash prints
     `<path>: line 41: $2: unbound variable` on stderr, exit 1. That message
     names the SCRIPT's path and the SCRIPT's line number, so the two sides
     cannot be byte-identical there by construction; this port prints the same
     sentence with its own path and its own line number, and the differential
     normalises both to `<script>: line <N>: $2: unbound variable`. It is the
     ONLY case in the whole differential that is normalised for anything other
     than a traceback.

WHY THERE IS NO `jq` AND NO `awk` IN THIS FILE. The twin's real content is six
jq programs and two awk programs; a port that shelled out to jq would be a
rewrite of the shell, not of the tool. Every one is transcribed into Python, and
each transcription carries the jq semantics it depends on:

  * `group_by(f)` SORTS BY f, then groups. The final `sort_by(.level, .depth,
    .name)` is STABLE in jq, so ties (one name at two versions) keep the
    `name@version` order group_by established. Reproduced by sorting the grouped
    list by the group key first and then applying a stable `sorted`.
  * `unique` SORTS AND DEDUPES, comparing arrays elementwise and strings by
    codepoint, which is what Python's `sorted` on `list[str]` does too.
  * `//` IS "null OR false", not "falsy". `.depth // 999` keeps a depth of 0.
  * OBJECT `+` LETS THE RIGHT SIDE WIN, which is what makes `dependencies`
    override `devDependencies` in the type map.
  * `jq .` PRETTY-PRINTS AT INDENT 2 WITH RAW UTF-8, which is exactly
    `json.dumps(obj, indent=2, ensure_ascii=False) + "\\n"`. Verified against the
    twin's own 1,103,367-byte output for this repository, not assumed.
  * `@tsv` ESCAPES tab/newline/CR/backslash in a field.
  * `length($i)` IN gawk COUNTS CHARACTERS in a UTF-8 locale and BYTES under
    `LC_ALL=C`; `align_tsv` therefore differs from this port only for a
    non-ASCII package name, of which this tree has none. Named here rather than
    silently assumed away.

THE ONE NON-DETERMINISTIC INPUT is `generatedAt`, which is `date -u
+%Y-%m-%dT%H:%M:%SZ` at the moment of the run and appears only in `--format
json`. `$DEPENDENCY_INVENTORY_NOW` is NOT read here and no such seam is added:
the differential runs the two sides and compares with that one field masked,
which keeps the port free of a test-only branch.

ONE NAMED DIVERGENCE THIS PORT ADDS: `paths.repo_root()` honours
`$REDIACC_CI_ROOT` and the twin's `get_repo_root` does not.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import time
import typing

from rediacc_ci import log, paths

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    from collections.abc import Iterable

# The four packages. `(name, relpath, mode)`, mode in {"workspace","standalone"}.
NPM_PKGS = (
    ("@rediacc/www", "packages/www", "workspace"),
    ("@rediacc/cli", "packages/cli", "workspace"),
    ("@rediacc/account", "private/account", "standalone"),
)

GO_PKG_PATH = "private/renet"

# `sed -n '2,35p' "$0" | sed 's/^# \?//'`, verbatim, shell-source leak included.
# See port note 2. Do not tidy this: `test_help_text_constant_still_matches_the_twin`
# re-derives it from the twin and a "cleaner" version would fail that test, which
# is the point -- the leak is the twin's behaviour and this is its port.
HELP_TEXT = (
    "dependency-inventory.sh - Enumerate every dependency across the four analyzed\n"
    "Rediacc packages (www, cli, account, renet) for the NIS2/CRA\n"
    "supply-chain SBOM. Each dependency is classified by level (direct vs\n"
    "transitive), tagged by type (dependencies/devDependencies/peer/optional for\n"
    "npm; direct/indirect for Go), and carries its full dependency chain(s) from\n"
    "the package root down to the dependency.\n"
    "\n"
    "npm chains come from the logical `npm ls --all --json` tree (each occurrence\n"
    "is one chain). Go chains are the shortest path from the main module through\n"
    "`go mod graph`; the complete Go edge list is included under the renet package\n"
    "so any longer chain can be reconstructed (full path enumeration in a module\n"
    "DAG is exponential, so it is intentionally not materialized).\n"
    "\n"
    "Usage:\n"
    "  dependency-inventory.sh [--format json|table] [--output PATH] [--max-chains N]\n"
    "\n"
    "Options:\n"
    "  --format FORMAT    Output format: json or table (default: table)\n"
    "  --output PATH      Write to PATH instead of stdout\n"
    "  --max-chains N     Max chains stored per dependency; 0 = unlimited\n"
    "                     (default: 25). Truncation is logged, never silent.\n"
    "  -h, --help         Show this help\n"
    "\n"
    "Requirements: jq, npm, go on PATH; installed node_modules (root workspace +\n"
    "private/account). Does not auto-install.\n"
    "\n"
    "set -euo pipefail\n"
    "\n"
    'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
    "shellcheck source=../lib/common.sh\n"
    'source "$SCRIPT_DIR/../lib/common.sh"\n'
    "\n"
    'FORMAT="table"\n'
    'OUTPUT=""\n'
)

TABLE_HEADER = ("LEVEL", "DEPTH", "TYPE", "INTERNAL", "PRODREACH", "NAME", "VERSION")


class Failure(Exception):  # noqa: N818 - it is a control-flow signal, not an error state
    """A `return 1` out of `build_npm_package` / `build_go_package`.

    `set -e` turns that into an immediate exit 1 of the whole script, with the
    `log_error` already printed. Modelled as an exception so the two builders
    can keep the twin's early-return shape without a rc-threading argument at
    every call site.
    """


class UnboundValue(Exception):  # noqa: N818 - same, and it carries a bash diagnostic
    """`$2` read under `set -u` when an option's value is missing. See port note 3."""

    def __init__(self, line: int) -> None:
        super().__init__(str(line))
        self.line = line


class JqAbort(Exception):  # noqa: N818 - a control-flow signal carrying jq's own text
    """A raw `jq` diagnostic that kills the script under `set -e`, with exit 2.

    TWO REACHABLE CASES, both of them defects in the twin that this wave reports
    rather than fixes:

      * `--argjson prodset ""`, which happens whenever `npm ls --omit=dev`
        prints NOTHING. `jq -c '<keyset>' <<<""` produces no output at all, the
        shell assigns the empty string, and jq then refuses the argument.
      * `jq -c '<types>' "$dir/package.json"` on an absent package.json.

    The message text belongs to jq, not to this gate, so it is carried here as a
    constant and `test_the_jq_diagnostics_still_match_this_host` re-derives both
    from the jq on PATH on every run. If jq changes its banner the test goes red
    and names the fix, rather than the differential silently drifting.
    """

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


# `jq -c --argjson p "" '.' <<<'{}'` on jq 1.8, verbatim including the double
# space before "at". THE FALLBACK ONLY -- `jq_argjson_banner()` asks the real jq.
JQ_ARGJSON_FALLBACK = (
    "jq: invalid JSON text passed to --argjson\n"
    "Use jq --help for help with command-line options,\n"
    "or see the jq manpage, or online docs  at https://jqlang.org\n"
)


@functools.lru_cache(maxsize=1)
def jq_argjson_banner() -> str:
    """jq's own `--argjson` diagnostic, ASKED OF THE jq ON PATH.

    THIS USED TO BE A CONSTANT, and the constant was right on exactly one class
    of host. The banner's last line carries jq's documentation URL, which moved
    between releases:

        jq 1.8.1 (this tree's hosts)  ... online docs  at https://jqlang.org
        jq 1.7.x (ubuntu-24.04 runner) ... online docs  at https://jqlang.github.io/jq

    The twin PRINTS whatever the real jq printed; the port SYNTHESISES the same
    bytes without running jq. With a constant, the two agree only where the
    developer's jq matches the constant, so `test_an_empty_prod_tree_dies_on_a_
    raw_jq_diagnostic` passed here and failed in CI -- measured 2026-09-15, run
    34970782616, the first run that let `quality-security` finish.

    A pin cannot fix this, because there is no single right answer: two hosts
    with two jqs are both correct at the same time. Transcribing a tool's
    message means transcribing THE TOOL THAT IS HERE, so this asks it. The
    constant survives as the fallback for a host with no jq at all, where
    nothing can be asked and the previous behaviour is the safe answer.
    """
    try:
        proc = subprocess.run(
            ["jq", "-c", "--argjson", "p", "", "."],
            input="{}",
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return JQ_ARGJSON_FALLBACK
    # An EMPTY stderr would mean this jq did not refuse the argument at all, so
    # the probe proved nothing and the fallback is the honest answer.
    return proc.stderr or JQ_ARGJSON_FALLBACK


# `jq -c '.' <missing>`, with the path interpolated.
JQ_OPEN_ERROR = "jq: error: Could not open file %s: No such file or directory\n"


# ---------------------------------------------------------------------------
# jq transcriptions
# ---------------------------------------------------------------------------


def walk_tree(node: dict, chain: tuple[str, ...]) -> Iterable[dict]:
    """`JQ_WALK` (`:95-101`): one record per OCCURRENCE, each with its ancestors.

    Depth-first in the object's own key order, which for `json.loads` is the
    order the bytes arrived in -- the same order jq's `to_entries` produces.
    A node is emitted BEFORE its children, matching the `A, (B)` comma operator.
    """
    if not isinstance(node, dict):
        return
    for name, value in node.items():
        info = value if isinstance(value, dict) else {}
        version = info.get("version")
        link = (*chain, "%s@%s" % (name, version if version is not None else "unknown"))
        yield {
            "name": name,
            "version": version,
            "depth": len(link),
            "chain": list(link),
        }
        children = info.get("dependencies")
        yield from walk_tree(children if isinstance(children, dict) else {}, link)


def keyset(node: dict) -> dict[str, bool]:
    """`JQ_KEYSET` (`:104-109`): the set of `name@version` present in a tree map."""
    out: dict[str, bool] = {}
    for record in walk_tree(node, ()):
        version = record["version"]
        out["%s@%s" % (record["name"], version if version is not None else "unknown")] = True
    return out


def type_map(package_json: dict) -> dict[str, str]:
    """`:150-154`: the direct-dependency type index.

    Four sections merged with jq's object `+`, so a name in both
    `devDependencies` and `dependencies` is typed `dependencies`. The order
    below IS that precedence and must not be sorted.
    """
    out: dict[str, str] = {}
    for key, label in (
        ("devDependencies", "devDependencies"),
        ("peerDependencies", "peerDependencies"),
        ("optionalDependencies", "optionalDependencies"),
        ("dependencies", "dependencies"),
    ):
        section = package_json.get(key)
        if isinstance(section, dict):
            for name in section:
                out[name] = label
    return out


def group_dependencies(
    root: dict,
    prodset: dict[str, bool],
    types: dict[str, str],
    max_chains: int,
) -> list[dict]:
    """`:156-175`: walk, group by `name@version`, aggregate, sort.

    The group key uses `.version // "null"` and the prodReachable key uses
    `.version // "unknown"`; both spellings are kept, because a package whose
    `version` is genuinely absent lands in a group named `x@null` while its
    prod-set lookup asks for `x@unknown`, and collapsing the two would change
    which records report `prodReachable: true`.
    """
    groups: dict[str, list[dict]] = {}
    for record in walk_tree(root, ()):
        version = record["version"]
        key = "%s@%s" % (record["name"], version if version is not None else "null")
        groups.setdefault(key, []).append(record)

    out: list[dict] = []
    for key in sorted(groups):  # group_by sorts by the grouping key
        members = groups[key]
        name = members[0]["name"]
        version = members[0]["version"]
        depth = min(member["depth"] for member in members)
        all_chains = sorted({tuple(member["chain"]) for member in members})
        total = len(all_chains)
        level = "direct" if depth == 1 else "transitive"
        prod_key = "%s@%s" % (name, version if version is not None else "unknown")
        out.append(
            {
                "name": name,
                "version": version,
                "level": level,
                "depth": depth,
                "type": (types.get(name, "dependencies") if level == "direct" else "transitive"),
                "internal": name.startswith("@rediacc/"),
                "prodReachable": bool(prodset.get(prod_key, False)),
                "chains": [
                    list(chain)
                    for chain in (all_chains[:max_chains] if max_chains > 0 else all_chains)
                ],
                "totalChains": total,
                "chainsTruncated": max_chains > 0 and total > max_chains,
            }
        )
    # jq's sort_by is stable, so this preserves the group-key order within ties.
    out.sort(key=lambda record: (record["level"], record["depth"], record["name"]))
    return out


def bfs_chains(edges_text: str, root: str) -> dict[str, dict]:
    """`:232-254`: shortest path from the main module to every reachable node.

    Chain excludes the main module and starts at the direct dependency (depth
    1), matching npm chain semantics. Adjacency is built in EDGE ORDER, which is
    what makes the predecessor -- and therefore the chain -- deterministic even
    though the twin's `for (v in seen)` output order is not (that order is only
    used to build a lookup map, so it never reaches the output).
    """
    adjacency: dict[str, list[str]] = {}
    for line in edges_text.split("\n"):
        fields = line.split()
        if len(fields) < 2:  # awk's $1/$2 on a short record read as ""
            continue
        adjacency.setdefault(fields[0], []).append(fields[1])

    seen = {root}
    depth = {root: 0}
    pred: dict[str, str] = {root: ""}
    queue = [root]
    head = 0
    while head < len(queue):
        node = queue[head]
        head += 1
        for neighbour in adjacency.get(node, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                depth[neighbour] = depth[node] + 1
                pred[neighbour] = node
                queue.append(neighbour)

    out: dict[str, dict] = {}
    for node in seen:
        if node == root:
            continue
        chain: list[str] = []
        cursor = node
        while cursor not in ("", root):
            chain.insert(0, cursor)
            cursor = pred[cursor]
        out[node] = {"depth": depth[node], "chain": chain}
    return out


def go_dependencies(modules: list[dict], bfs: dict[str, dict]) -> list[dict]:
    """`:256-271`: the module list to dependency records, main module dropped."""
    out: list[dict] = []
    for module in modules:
        if module.get("Main") is True:
            continue
        version = module.get("Version")
        key = "%s@%s" % (module.get("Path"), version if version is not None else "unknown")
        found = bfs.get(key)
        indirect = module.get("Indirect") is True
        chain = found.get("chain") if found else None
        out.append(
            {
                "name": module.get("Path"),
                "version": version if version is not None else None,
                "level": "transitive" if indirect else "direct",
                "depth": (
                    found["depth"]
                    if found and found.get("depth") is not None
                    else (None if indirect else 1)
                ),
                "type": "indirect" if indirect else "direct",
                "internal": False,
                "prodReachable": True,
                "chains": [chain] if chain is not None else [],
                "totalChains": 1 if chain is not None else 0,
                "chainsTruncated": False,
            }
        )
    out.sort(
        key=lambda record: (
            record["level"],
            999 if record["depth"] is None else record["depth"],
            record["name"],
        )
    )
    return out


def align_tsv(rows: list[list[str]]) -> list[str]:
    """`align_tsv` (`:285-296`), the two-pass column aligner.

    `column -t` is not available in the minimal CI images (see
    check-commands.sh), which is why the twin has its own and why this port has
    to reproduce the two-trailing-spaces-then-rstrip shape exactly.
    """
    widths: dict[int, int] = {}
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths.get(index, 0), len(cell))
    out: list[str] = []
    for row in rows:
        line = "".join("%-*s  " % (widths[index], cell) for index, cell in enumerate(row))
        out.append(line.rstrip(" "))
    return out


# ---------------------------------------------------------------------------
# the two builders
# ---------------------------------------------------------------------------


def _npm_ls(cwd: str, extra: list[str]) -> str:
    """`npm ls --all --json ... 2>/dev/null || true`. Never raises on rc != 0."""
    try:
        proc = subprocess.run(
            ["npm", "ls", "--all", "--json", *extra],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        # `npm` not on PATH: bash's command-not-found writes its own line to
        # stderr, which the twin has redirected to /dev/null, and `|| true`
        # keeps going with an empty tree.
        return ""
    return proc.stdout


def build_npm_package(
    repo_root: str, name: str, relpath: str, mode: str, max_chains: int
) -> dict | None:
    """`build_npm_package` (`:112-188`). Raises Failure where the twin returns 1.

    RETURNS None WHEN `npm ls` PRINTED NOTHING, and that is a REPRODUCED DEFECT,
    not a convenience. With an empty `tree_all` every jq in the chain has no
    input and therefore emits no output, so `$WORK/pkg_N.json` is written EMPTY,
    `jq -s` slurps nothing from it, and the package VANISHES from the inventory
    while the run still exits 0. Measured on a fixture: `packagesAnalyzed`
    reported 3 with four packages requested, and no warning was printed. Since
    this document is NIS2/CRA supply-chain evidence, a package silently dropping
    out is the worst outcome the tool has; it is reported in this wave's findings
    and fixed in neither side, because fixing one side only would make the
    differential lie.
    """
    directory = os.path.join(repo_root, relpath)
    if mode == "workspace":
        nm_dir = os.path.join(repo_root, "node_modules")
    else:
        nm_dir = os.path.join(directory, "node_modules")

    if not os.path.isdir(nm_dir):
        log.error(
            "%s: %s missing. Run 'npm install' (+ 'npm run install:natives') first."
            % (name, nm_dir)
        )
        raise Failure

    if mode == "workspace":
        tree_all = _npm_ls(repo_root, ["--workspace", name])
        tree_prod = _npm_ls(repo_root, ["--omit=dev", "--workspace", name])
    else:
        tree_all = _npm_ls(directory, [])
        tree_prod = _npm_ls(directory, ["--omit=dev"])

    parsed_all = _jq_empty(tree_all)
    if parsed_all is _INVALID:
        log.error("%s: npm ls produced invalid JSON" % name)
        raise Failure

    # `jq empty` on empty input EXITS 0, so an empty prod tree takes the valid
    # branch and `jq -c '<keyset>'` then produces no output -- the empty string
    # that kills the next jq. `_NOVALUE` is what carries that distinction; a
    # plain `None` would collapse it into the `tree_prod == "null"` case, which
    # is valid and yields `{}`.
    parsed_prod = _jq_empty(tree_prod)
    if parsed_prod is _INVALID:
        prodset: dict[str, bool] | None = {}
    elif parsed_prod is _NOVALUE:
        prodset = None  # the empty string the twin passes to --argjson
    else:
        prodset = keyset(_root_expr(parsed_prod, name, mode))

    package_json = os.path.join(directory, "package.json")
    if not os.path.isfile(package_json):
        raise JqAbort(JQ_OPEN_ERROR % package_json)
    with open(package_json, encoding="utf-8") as handle:
        types = type_map(json.load(handle))

    if prodset is None:
        raise JqAbort(jq_argjson_banner())
    if parsed_all is _NOVALUE:
        return None  # the package silently vanishes; see the docstring

    deps = group_dependencies(_root_expr(parsed_all, name, mode), prodset, types, max_chains)

    # Surface any chain truncation (no silent caps).
    for record in deps:
        if record["chainsTruncated"]:
            version = record["version"]
            log.warn(
                "%s: chains capped for %s@%s (%d chains)"
                % (
                    name,
                    record["name"],
                    version if version is not None else "?",
                    record["totalChains"],
                )
            )

    return {
        "name": name,
        "path": relpath,
        "ecosystem": "npm",
        "counts": {
            "direct": sum(1 for record in deps if record["level"] == "direct"),
            "transitive": sum(1 for record in deps if record["level"] == "transitive"),
            "total": len(deps),
        },
        "dependencies": deps,
    }


_INVALID = object()
_NOVALUE = object()


def _jq_empty(text: str) -> object:
    """`jq empty <<<"$text"` -- the twin's "is this JSON at all" probe.

    THREE OUTCOMES, NOT TWO, and the third one is the whole reason this is a
    function rather than a `json.loads` at the call site:

      * `_INVALID`  -- `jq empty` exits 5, and the twin reports "npm ls produced
        invalid JSON" and returns 1.
      * `_NOVALUE`  -- the input is EMPTY. `jq empty` exits 0 (measured:
        `jq empty <<<""; echo $?` prints 0), so the twin takes the VALID branch,
        but every downstream jq then has no input and emits no output. That is
        what silently drops a package and what kills the run with an `--argjson`
        error, depending on which of the two trees was empty.
      * anything else -- the parsed value, `null` included.
    """
    if text.strip() == "":
        return _NOVALUE
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return _INVALID


def _root_expr(doc: object, name: str, mode: str) -> dict:
    """`rootexpr` (`:117-123`), with jq's null-propagating indexing.

    workspace: `.dependencies["<name>"].dependencies`; standalone:
    `.dependencies`. Indexing null yields null in jq rather than raising, and
    the caller's `// {}` then supplies the empty map.
    """
    node = doc if isinstance(doc, dict) else {}
    deps = node.get("dependencies")
    if mode != "workspace":
        return deps if isinstance(deps, dict) else {}
    entry = deps.get(name) if isinstance(deps, dict) else None
    inner = entry.get("dependencies") if isinstance(entry, dict) else None
    return inner if isinstance(inner, dict) else {}


def _go(directory: str, args: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["go", *args],
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        # bash would print `go: command not found` to the probe file and the
        # subshell would exit 127; same shape, same indented echo.
        return 127, "", "%s\n" % exc
    return proc.returncode, proc.stdout, proc.stderr


def _echo_probe(stderr_text: str) -> None:
    """`[[ -s "$probe_err" ]] && sed 's/^/    /' "$probe_err" >&2`.

    Four spaces in front of every LINE, including a trailing partial one, and
    nothing at all when the file is empty.
    """
    if not stderr_text:
        return
    lines = stderr_text.split("\n")
    trailing_newline = lines[-1] == ""
    if trailing_newline:
        lines.pop()  # the split's phantom element, not a line sed would see
    body = "".join("    %s\n" % line for line in lines)
    if not trailing_newline:
        # GNU sed PRESERVES a missing final newline; it does not add one.
        # Measured, because the reflex is the opposite:
        #     $ printf 'a\nb' | sed 's/^/    /' | xxd
        #     2020 2020 610a 2020 2020 62          .a.    b
        # A `go` probe whose stderr ends mid-line is the only way to reach it,
        # and `test_a_go_probe_whose_stderr_lacks_a_final_newline` drives it.
        body = body[:-1]
    sys.stderr.write(body)
    sys.stderr.flush()


def build_go_package(repo_root: str, work_dir: str) -> dict:
    """`build_go_package` (`:191-281`). Raises Failure where the twin returns 1.

    EVERY PROBE IS CHECKED, and the twin's own comment says why: `edges` used to
    end in `|| true`, so a `go mod graph` failure produced an empty edge list,
    the BFS walked nothing, and every Go dependency silently dropped out with a
    "transitive: 0" that looked like a real answer. This inventory is NIS2/CRA
    supply-chain evidence, so a partial one is worse than none.
    """
    directory = os.path.join(repo_root, GO_PKG_PATH)

    rc, out, err = _go(directory, ["list", "-m"])
    if rc != 0:
        log.error("go list -m failed in %s; cannot build the Go inventory" % directory)
        _echo_probe(err)
        raise Failure
    main_mod = out.rstrip("\n")  # `$( )` strips trailing newlines

    rc, out, err = _go(directory, ["list", "-m", "-json", "all"])
    modules = _slurp(out) if rc == 0 else None
    if rc != 0 or modules is None:
        log.error("go list -m -json all failed in %s; cannot build the Go inventory" % directory)
        _echo_probe(err)
        raise Failure

    rc, out, err = _go(directory, ["mod", "graph"])
    if rc != 0:
        log.error("go mod graph failed in %s; the dependency graph would be empty" % directory)
        _echo_probe(err)
        raise Failure
    edges = out.rstrip("\n")

    # A module with dependencies always has edges. Zero means the probe returned
    # nothing usable, which is not the same as a module with no dependencies.
    if not "".join(edges.split()):
        log.error(
            "go mod graph returned no edges in %s; refusing to emit an empty dependency graph"
            % directory
        )
        raise Failure

    bfs = bfs_chains(edges, main_mod)
    deps = go_dependencies(modules, bfs)

    edge_records = [
        {"from": parts[0], "to": parts[1] if len(parts) > 1 else None}
        for parts in (line.split(" ") for line in edges.split("\n") if line)
    ]
    # The twin materialises this through $WORK/go_edges.json; kept so a reader
    # comparing the two files finds the same intermediate on disk.
    with open(os.path.join(work_dir, "go_edges.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(edge_records, separators=(",", ":"), ensure_ascii=False))

    return {
        "name": "renet",
        "path": GO_PKG_PATH,
        "ecosystem": "go",
        "counts": {
            "direct": sum(1 for record in deps if record["level"] == "direct"),
            "transitive": sum(1 for record in deps if record["level"] == "transitive"),
            "total": len(deps),
        },
        "dependencies": deps,
        "edges": edge_records,
    }


def _slurp(text: str) -> list[dict] | None:
    """`jq -s -c '.'` over a stream of concatenated JSON values."""
    decoder = json.JSONDecoder()
    out: list[dict] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        try:
            value, index = decoder.raw_decode(text, index)
        except ValueError:
            return None
        out.append(value)
    return out


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def render_table(doc: dict) -> str:
    """`render_table` (`:298-316`). Returns everything the twin echoes to stdout."""
    parts: list[str] = []
    for package in doc["packages"]:
        parts.append("")
        parts.append(
            "=== %s [%s]  direct=%s transitive=%s total=%s ==="
            % (
                package["name"],
                package["ecosystem"],
                package["counts"]["direct"],
                package["counts"]["transitive"],
                package["counts"]["total"],
            )
        )
        rows = [list(TABLE_HEADER)]
        rows.extend(
            [
                record["level"],
                _jq_tostring(record["depth"]),
                record["type"],
                _jq_tostring(record["internal"]),
                _jq_tostring(record["prodReachable"]),
                record["name"],
                record["version"] if record["version"] is not None else "?",
            ]
            for record in package["dependencies"]
        )
        parts.extend(align_tsv(rows))
    parts.append("")
    summary = doc["summary"]
    parts.append(
        "SUMMARY  packages=%s  records=%s  unique=%s  external=%s  npm=%s  go=%s  "
        "direct=%s  transitive=%s"
        % (
            summary["packagesAnalyzed"],
            summary["totals"]["records"],
            summary["totals"]["uniqueByNameVersion"],
            summary["totals"]["externalUniqueByNameVersion"],
            summary["byEcosystem"]["npm"],
            summary["byEcosystem"]["go"],
            summary["byLevel"]["direct"],
            summary["byLevel"]["transitive"],
        )
    )
    parts.append("(full dependency chains available via --format json)")
    return "".join("%s\n" % line for line in parts)


def _jq_tostring(value: object) -> str:
    """jq's `tostring`: `true`/`false`/`null` lowercase, integers bare."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


def render_json(doc: dict) -> str:
    """`jq . <<<"$doc"`. Verified byte-identical against the twin's real output."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def build_summary(packages: list[dict], generated: str, max_chains: int) -> dict:
    """`:336-348`, the top-level document."""
    every = [record for package in packages for record in package["dependencies"]]

    def key_of(record: dict) -> str:
        version = record["version"]
        return "%s@%s" % (record["name"], version if version is not None else "unknown")

    return {
        "generatedAt": generated,
        "tool": {"name": "dependency-inventory.sh", "maxChains": max_chains},
        "summary": {
            "packagesAnalyzed": len(packages),
            "totals": {
                "records": sum(len(package["dependencies"]) for package in packages),
                "uniqueByNameVersion": len({key_of(record) for record in every}),
                "externalUniqueByNameVersion": len(
                    {key_of(record) for record in every if not record["internal"]}
                ),
            },
            "byEcosystem": {
                "npm": sum(
                    len(package["dependencies"])
                    for package in packages
                    if package["ecosystem"] == "npm"
                ),
                "go": sum(
                    len(package["dependencies"])
                    for package in packages
                    if package["ecosystem"] == "go"
                ),
            },
            "byLevel": {
                "direct": sum(1 for record in every if record["level"] == "direct"),
                "transitive": sum(1 for record in every if record["level"] == "transitive"),
            },
        },
        "packages": packages,
    }


# ---------------------------------------------------------------------------
# the orchestrator
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> tuple[str, str, int]:
    """`:38-73`. Returns (format, output, max_chains) or raises.

    `SystemExit(0)` for `--help` after printing, `Failure` after a `log_error`,
    `UnboundValue` for a missing option value.
    """
    fmt = "table"
    output = ""
    max_chains_raw = "25"
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--format":
            if index + 1 >= len(argv):
                raise UnboundValue(41)
            fmt = argv[index + 1]
            index += 2
        elif arg == "--output":
            if index + 1 >= len(argv):
                raise UnboundValue(45)
            output = argv[index + 1]
            index += 2
        elif arg == "--max-chains":
            if index + 1 >= len(argv):
                raise UnboundValue(49)
            max_chains_raw = argv[index + 1]
            index += 2
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP_TEXT)
            sys.stdout.flush()
            raise SystemExit(0)
        else:
            log.error("Unknown option: %s" % arg)
            raise Failure

    if fmt not in ("json", "table"):
        log.error("--format must be 'json' or 'table'")
        raise Failure
    # `[[ "$MAX_CHAINS" =~ ^[0-9]+$ ]]`: ASCII digits only, and at least one.
    if not max_chains_raw or not all(char in "0123456789" for char in max_chains_raw):
        log.error("--max-chains must be a non-negative integer")
        raise Failure
    return fmt, output, int(max_chains_raw)


def main(argv: list[str]) -> int:
    try:
        fmt, output, max_chains = parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    except UnboundValue as exc:
        # See port note 3: a raw bash diagnostic naming the script and the line.
        sys.stderr.write("%s: line %d: $2: unbound variable\n" % (sys.argv[0], exc.line))
        sys.stderr.flush()
        return 1
    except Failure:
        return 1

    # `require_cmd jq npm go awk` probes ONLY `jq`; see port note 1.
    if shutil.which("jq") is None:
        log.error("Required command 'jq' is not available")
        return 1

    repo_root = str(paths.repo_root())

    # `WORK="$(mktemp -d)"` + `trap 'rm -rf "$WORK"' EXIT`.
    import tempfile  # noqa: PLC0415 - only needed on the path that gets this far

    work_dir = tempfile.mkdtemp()
    try:
        packages: list[dict] = []
        try:
            for name, relpath, mode in NPM_PKGS:
                log.step("Analyzing %s (%s)" % (name, relpath))
                package = build_npm_package(repo_root, name, relpath, mode, max_chains)
                # None means `$WORK/pkg_N.json` was written EMPTY and `jq -s`
                # slurped nothing from it. Skipping is what reproduces the
                # twin's silent drop; see build_npm_package's docstring.
                if package is not None:
                    packages.append(package)
            log.step("Analyzing renet (%s)" % GO_PKG_PATH)
            packages.append(build_go_package(repo_root, work_dir))
        except Failure:
            return 1
        except JqAbort as abort:
            sys.stderr.write(abort.text)
            sys.stderr.flush()
            return 2

        generated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        doc = build_summary(packages, generated, max_chains)
        text = render_json(doc) if fmt == "json" else render_table(doc)

        if output:
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(text)
            log.info("Wrote %s inventory to %s" % ("JSON" if fmt == "json" else "table", output))
        else:
            sys.stdout.write(text)
            sys.stdout.flush()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
