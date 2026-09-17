"""GO_VERSION, NODE_VERSION and NODE_VERSION_MIN must agree across four files.

Ported from `.ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh`, which
is NOT deleted; see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS.
-----------------------------------------------------------------------------

Gate: GO_VERSION and NODE_VERSION in toolchain.env and the devcontainer Dockerfile's matching ARG lines must be identical.

WHY THIS EXISTS. check-toolchain-pins.sh's A1 (one definition per pin) deliberately EXEMPTS GO_VERSION and NODE_VERSION from its single-source check, because both also appear as bare majors in third-party action inputs and go.mod -- values this repo does not own and must not try to unify. That exemption is correct for THOSE call sites, but it has a side effect: it also removes ANY
check between the two files that ARE supposed to carry the identical value on purpose -- .devcontainer/toolchain.env (the pin) and .devcontainer/Dockerfile's
`ARG GO_VERSION=`/`ARG NODE_VERSION=` (consumed at image-build time). Nothing
currently asserts these two stay equal; a bump to one without the other would
build a devcontainer image running a DIFFERENT Go/Node than the pin file claims, silently.

WHAT THIS CHECKS. For GO_VERSION and NODE_VERSION: the value in
.devcontainer/toolchain.env must equal the value of the matching `ARG <KEY>=`
line in .devcontainer/Dockerfile. Nothing else -- this is a narrow, two-file, two-key check, not a reopening of the broader exemption.

AND ONE MORE PAIR, ADDED LATER: NODE_VERSION_MIN. The paragraph above says "narrow, two-file", so the third pair needs its own justification rather than quietly widening that sentence.

NODE_VERSION_MIN is the repo's Node FLOOR, and it has three copies by necessity, not by sloppiness: .devcontainer/toolchain.env (the pin every shell path sources) plus engines.node in package.json and in packages/cli/package.json. The manifests cannot read a shell variable and npm will not accept one, so the value must be WRITTEN in all three -- which makes it the one pin where
"single-sourced" is impossible and a comparison is the only remaining instrument.

It is the same failure this gate already exists for, one file further out, and it had already happened: .ci/config/constants.sh COMPOSED the floor as
"${NODE_VERSION}.0.0" -> 22.0.0, while both manifests said ">=22.13.0". Nothing
compared them, so for the whole life of that line ./run.sh setup accepted hosts that npm then rejected. Composing a value from another pin passes a
single-source scan and still drifts; only an equality check catches it.

CONTROL-FIRST. Builds fixtures by construction (a temp toolchain.env + temp Dockerfile with a deliberately mismatched value), never by substituting into real source, so rewording a real file cannot silently void the control.

THE MANIFESTS ARE READ AND NEVER WRITTEN. This gate reports the drift and names
the file to edit; it does not reach into package.json, because the two manifests
are owned by npm tooling that rewrites them wholesale and a gate that edits one is a gate that loses a race with `npm pkg set`.

EVERY, NOT "A". `check_engines_pair` compares the floor against EVERY manifest it is given, because the failure mode worth catching is one of the two moving alone: packages/cli/package.json ships to npm as its own artifact, so a floor that is right in the root and stale in the CLI is invisible in this repo and wrong for everyone who installs the published package.

THE ">=" IS ASSERTED, NOT PARSED. The manifests carry a RANGE and the pin
carries a bare version; ">=" is the whole of the translation. Accepting any
range that happens to admit the pin (">=22", "^22") would let the two numbers
differ while the check stayed green, which is the drift itself.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`engines_node` IS PARSED, NOT GREPPED, and the twin explains the asymmetry with `env_value`/`arg_value` at length: `"node"` is a legal key in more than one place in a manifest -- a `volta` block pins a node version, so does a `packageManager`-adjacent stanza, and `"@types/node"` is one character away from matching a careless pattern. A `grep | head -1` would answer with whichever
copy sits highest in the file and be right only by luck, and a WRONG answer here does not read as a broken gate: it reads as a real floor mismatch and sends someone to edit the wrong number.

The twin shells out to `node -e` for that parse, guarded by "node(1) is guaranteed here because this gate runs as an npm script. If it ever is not, this returns empty and the caller reports 'engines.node not found', which is a failure and not a silent skip". This port uses `json.loads`, which is the same parse without the subprocess, and it keeps the same swallow: a malformed
manifest yields "" and is reported as "not found" rather than crashing. Keeping the `node -e` call would have made the port depend on node being on PATH for a question Python answers natively, and the differential proves the two agree.

`env_value` IS `grep -E "^KEY=" | head -1 | cut -d= -f2-`. THREE properties that
a "sensible" rewrite loses, so each is reproduced explicitly: the match is
ANCHORED and takes no leading whitespace (an indented `  GO_VERSION=` is not a
definition); the FIRST match wins, not the last, which is the opposite of the
`.npmrc` gate's `tail -n1`; and `cut -f2-` keeps everything after the first `=`,
so a value containing an `=` survives whole.

`arg_value` IS `grep -oP "^ARG\\s+KEY=\\K.*" | head -1`. `\\K` drops everything
matched before it, so the result is the value alone. `[[:space:]]+` after ARG means one or more spaces or tabs, and the anchor means an indented ARG inside a multi-stage block is NOT read. Both are carried.

A `\\r` AT THE END OF A DOCKERFILE LINE would end up inside the value on both sides, since neither implementation strips one. Stated rather than fixed: a CRLF Dockerfile would make this gate report a mismatch between two values that look identical, which is confusing but is the twin's behaviour and is caught by the editorconfig gate anyway.

THE FINAL FAILURE BANNER STARTS WITH A LOWERCASE `x`, NOT `✗`. That is the
twin's text (`echo "${RED}x $fails toolchain-env/Dockerfile mismatch(es)${NC}"`),
so `scripts/lib/shadow-gate.ts` classifies it as chatter rather than as a finding, while every `fail()` line above it IS a finding. Carried unchanged: the difference is invisible to a human and load-bearing for the comparator, and "fixing" the glyph would change which lines the ledger compares.

STREAMS. `fail()` writes to stderr, `pass()` and the banners to stdout. Nothing here uses `rediacc_ci.log`, because the twin sources no logger and its lines carry no glyph but the one typed into them.
"""

import io
import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The four subjects, root-relative.
ENV_REL = ".devcontainer/toolchain.env"
DOCKERFILE_REL = ".devcontainer/Dockerfile"
ROOT_PKG_REL = "package.json"
CLI_PKG_REL = "packages/cli/package.json"

# The escapes. The twin computes them only when stdout is a tty and NO_COLOR is unset, so under a pipe they are empty strings on both sides.
_ANSI = {"RED": "\033[0;31m", "GREEN": "\033[0;32m", "NC": "\033[0m"}


def colours(stream=None, env=None) -> dict[str, str]:
    """`[ -t 1 ] && [ -z "${NO_COLOR:-}" ]`, as a mapping of the three names.

    STDOUT is the stream tested, not stderr, even though `fail()` writes to stderr. That is the twin's condition and it is reproduced rather than corrected: a run with stdout to a terminal and stderr to a file would put escapes in the file, which is a real (small) defect and not one a port may quietly change.
    """
    environ = os.environ if env is None else env
    target = sys.stdout if stream is None else stream
    if environ.get("NO_COLOR"):
        return {"RED": "", "GREEN": "", "NC": ""}
    try:
        tty = bool(target.isatty())
    except (AttributeError, ValueError):
        tty = False
    return dict(_ANSI) if tty else {"RED": "", "GREEN": "", "NC": ""}


def env_value(key: str, path: pathlib.Path) -> str:
    """`grep -E "^KEY=" file | head -1 | cut -d= -f2-`, or "" when absent.

    See the port notes for the three properties this spelling preserves. A file that cannot be read is "" too, matching the twin's `2>/dev/null`.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    prefix = key + "="
    for line in text.split("\n"):
        if line.startswith(prefix):
            # `cut -d= -f2-`: everything after the FIRST `=`.
            return line.split("=", 1)[1]
    return ""


# `^ARG[[:space:]]+KEY=\K.*` with the `\K` expressed as a capture group.
def arg_value(key: str, path: pathlib.Path) -> str:
    """The value of the first `ARG KEY=` line in a Dockerfile, or "".

    Anchored, so an indented ARG is not read; one-or-more spaces or tabs after
    `ARG`, matching `[[:space:]]+`; first match wins, matching `head -1`.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    pattern = re.compile(r"^ARG[ \t]+%s=(.*)$" % re.escape(key))
    for line in text.split("\n"):
        match = pattern.match(line)
        if match:
            return match.group(1)
    return ""


def engines_node(path: pathlib.Path) -> str:
    """`(JSON.parse(...).engines || {}).node || ""`, PARSED, never grepped.

    Every failure -- unreadable, malformed, no engines block, a non-string value -- collapses to "", which the caller reports as "engines.node not found in <file>". That is a FAILURE and not a silent skip, and it is the same direction the missing-ARG case already fails in.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    engines = data.get("engines")
    if not isinstance(engines, dict):
        return ""
    node = engines.get("node")
    # `String(v)` in the twin's node snippet, so a numeric value becomes its text. `|| ""` first, so a false-y value is the empty string rather than the string "None" or "False".
    return "" if not node else str(node)


class Report:
    """The twin's `fails` counter with its two printers, as one object.

    An object rather than module state because `run_controls` and the real checks share the SAME counter in the twin -- a control failure makes the gate exit before it ever judges the tree -- and that coupling is easy to lose when the two halves are separate functions with separate globals.
    """

    def __init__(self, colour: dict[str, str] | None = None) -> None:
        self.colour = colours() if colour is None else colour
        self.fails = 0

    def fail(self, message: str) -> None:
        print("%s✗%s %s" % (self.colour["RED"], self.colour["NC"], message), file=sys.stderr)
        self.fails += 1

    def ok(self, message: str) -> None:
        print("%sok%s   %s" % (self.colour["GREEN"], self.colour["NC"], message))


def check_pair(
    report: Report, key: str, env_file: pathlib.Path, dockerfile: pathlib.Path, label: str
) -> None:
    """One pin against its Dockerfile ARG. Three failure shapes, then a pass."""
    value = env_value(key, env_file)
    arg = arg_value(key, dockerfile)
    if value == "":
        report.fail("%s: %s not found in %s" % (label, key, env_file))
        return
    if arg == "":
        report.fail("%s: ARG %s not found in %s" % (label, key, dockerfile))
        return
    if value != arg:
        report.fail(
            "%s: %s mismatch -- %s has '%s', %s ARG has '%s'"
            % (label, key, env_file, value, dockerfile, arg)
        )
        return
    report.ok("%s: %s='%s' matches in both files" % (label, key, value))


def check_engines_pair(
    report: Report, key: str, env_file: pathlib.Path, label: str, *manifests: pathlib.Path
) -> None:
    """The floor in the pins file against engines.node in EVERY manifest.

    A single `ok` line when all of them agree, naming the count, so a reader can see the number collapse if a manifest stops being passed in.
    """
    value = env_value(key, env_file)
    if value == "":
        report.fail("%s: %s not found in %s" % (label, key, env_file))
        return
    want = ">=%s" % value
    bad = False
    for manifest in manifests:
        got = engines_node(manifest)
        if got == "":
            report.fail("%s: engines.node not found in %s" % (label, manifest))
            bad = True
            continue
        if got != want:
            report.fail(
                "%s: %s floor mismatch -- %s has '%s' so engines.node must be '%s', "
                "but %s has '%s'" % (label, key, env_file, value, want, manifest, got)
            )
            bad = True
    if not bad:
        report.ok(
            "%s: %s='%s' matches engines.node '%s' in all %d manifest(s)"
            % (label, key, value, want, len(manifests))
        )


def run_controls(report: Report) -> None:
    """Every assertion, planted against a temp fixture, BEFORE the real tree.

    A control that does not fire fails this gate rather than letting it report a green it did not earn. The fixtures are written by construction, never by substituting into real source, so rewording a real file cannot silently void them.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        env_file = tmpdir / "toolchain.env"
        dockerfile = tmpdir / "Dockerfile"

        def probe(fn, *args) -> str:
            """Run one check into a private Report and return its combined text.

            The twin does this with `out="$(check_pair ... 2>&1)"`, a subshell
            whose `fails` increments are DISCARDED. A private Report is the same isolation without the subshell, and it is the reason the outer counter only moves when a control genuinely misbehaves.
            """
            inner = Report(colour={"RED": "", "GREEN": "", "NC": ""})
            out = io.StringIO()
            saved_out, saved_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = out
            try:
                fn(inner, *args)
            finally:
                sys.stdout, sys.stderr = saved_out, saved_err
            return out.getvalue()

        # CONTROL: a real mismatch is caught.
        env_file.write_text("GO_VERSION=1.26.6\n", encoding="utf-8")
        dockerfile.write_text("ARG GO_VERSION=1.26.5\n", encoding="utf-8")
        out = probe(check_pair, "GO_VERSION", env_file, dockerfile, "CONTROL")
        if "mismatch" in out:
            report.ok("control: a real GO_VERSION mismatch is detected")
        else:
            report.fail("control: a planted mismatch was NOT detected -- %s" % out)

        # CONTROL: matching values pass cleanly.
        env_file.write_text("GO_VERSION=1.26.6\n", encoding="utf-8")
        dockerfile.write_text("ARG GO_VERSION=1.26.6\n", encoding="utf-8")
        out = probe(check_pair, "GO_VERSION", env_file, dockerfile, "CONTROL")
        if "matches" in out:
            report.ok("control: matching values pass")
        else:
            report.fail("control: matching values were wrongly flagged -- %s" % out)

        # CONTROL: a missing ARG line is a failure, not a silent skip.
        env_file.write_text("GO_VERSION=1.26.6\n", encoding="utf-8")
        dockerfile.write_text("# no ARG line here\n", encoding="utf-8")
        out = probe(check_pair, "GO_VERSION", env_file, dockerfile, "CONTROL")
        if "not found" in out:
            report.ok("control: a missing ARG line is flagged, not silently skipped")
        else:
            report.fail("control: a missing ARG line was not flagged -- %s" % out)

        # --- NODE_VERSION_MIN controls --------------------------------------
        #
        # BY CONSTRUCTION, and note the fixture floor is 22.44.0 rather than the real one. That is not squeamishness: check-toolchain-pins.sh's A1 greps every .ci/**/*.sh for a literal copy of any value in toolchain.env, so writing the true floor into a fixture here would make THIS file report as a second definition of it. A control that breaks another gate gets deleted. The same
        # reasoning applies to this Python file, which that gate's corpus does not currently include but may.
        floor_env = tmpdir / "floor.env"
        floor_env.write_text("NODE_VERSION_MIN=22.44.0\n", encoding="utf-8")
        root_json = tmpdir / "root.json"
        cli_json = tmpdir / "cli.json"
        root_json.write_text('{"engines":{"node":">=22.44.0"}}\n', encoding="utf-8")
        cli_json.write_text('{"engines":{"node":">=22.44.0"}}\n', encoding="utf-8")

        out = probe(
            check_engines_pair, "NODE_VERSION_MIN", floor_env, "CONTROL", root_json, cli_json
        )
        if "matches" in out:
            report.ok("control: a floor matching both manifests passes")
        else:
            report.fail("control: agreeing manifests were wrongly flagged -- %s" % out)

        # CONTROL: the exact bug this pair was added for -- a floor of 22.0.0 in the manifests under a stricter pin. Both manifests are stale together,
        # which is what the composed "${NODE_VERSION}.0.0" line used to produce.
        root_old = tmpdir / "root-old.json"
        cli_old = tmpdir / "cli-old.json"
        root_old.write_text('{"engines":{"node":">=22.0.0"}}\n', encoding="utf-8")
        cli_old.write_text('{"engines":{"node":">=22.0.0"}}\n', encoding="utf-8")
        out = probe(check_engines_pair, "NODE_VERSION_MIN", floor_env, "CONTROL", root_old, cli_old)
        if "floor mismatch" in out:
            report.ok("control: manifests stuck at an older floor are detected")
        else:
            report.fail("control: a planted stale engines.node was NOT detected -- %s" % out)

        # CONTROL: ONLY packages/cli drifts. The root manifest is what a developer reads, so a check that stopped at the first match, or that only ever looked at the root, would call this tree clean while the PUBLISHED CLI advertised the wrong floor. The message must also name the file that is wrong.
        out = probe(
            check_engines_pair, "NODE_VERSION_MIN", floor_env, "CONTROL", root_json, cli_old
        )
        if "floor mismatch" in out and "cli-old.json" in out:
            report.ok("control: one manifest drifting alone is detected, and named")
        else:
            report.fail("control: a cli-only floor drift went undetected or unnamed -- %s" % out)

        # CONTROL: a `"node"` key OUTSIDE engines must not decide the verdict.
        # This is why engines_node parses instead of grepping; a first-match grep
        # would read the volta pin here and report a mismatch against a correct manifest.
        decoy = tmpdir / "decoy.json"
        decoy.write_text(
            '{"volta":{"node":"18.0.0"},"engines":{"node":">=22.44.0"}}\n', encoding="utf-8"
        )
        out = probe(check_engines_pair, "NODE_VERSION_MIN", floor_env, "CONTROL", decoy)
        if "matches" in out:
            report.ok("control: a node version outside engines is not mistaken for the floor")
        else:
            report.fail("control: a decoy node key outside engines changed the verdict -- %s" % out)

        # CONTROL: a manifest with no engines block is a failure, not a silent skip -- the same direction the missing-ARG case above fails in. Deleting engines.node is exactly how someone would "fix" a red floor check.
        bare = tmpdir / "bare.json"
        bare.write_text('{"name":"no-engines-here"}\n', encoding="utf-8")
        out = probe(check_engines_pair, "NODE_VERSION_MIN", floor_env, "CONTROL", bare)
        if "not found" in out:
            report.ok("control: a manifest with no engines.node is flagged, not skipped")
        else:
            report.fail("control: a missing engines.node was not flagged -- %s" % out)


def main(argv: list[str] | None = None) -> int:
    """Run the controls, then the real tree. Exit 0 in sync, 1 otherwise."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    report = Report()

    print(
        "Toolchain env/Dockerfile sync (GO_VERSION, NODE_VERSION) + Node floor (NODE_VERSION_MIN)"
    )
    run_controls(report)
    if report.fails > 0:
        print(
            "%sx the rule itself is broken, so no verdict it produces means anything.%s"
            % (report.colour["RED"], report.colour["NC"]),
            file=sys.stderr,
        )
        return 1

    env_file = root / ENV_REL
    dockerfile = root / DOCKERFILE_REL
    for subject in (env_file, dockerfile):
        if not os.access(subject, os.R_OK) or not subject.is_file():
            report.fail("required subject missing: %s" % subject)
            return 1

    check_pair(report, "GO_VERSION", env_file, dockerfile, "devcontainer")
    check_pair(report, "NODE_VERSION", env_file, dockerfile, "devcontainer")

    root_pkg = root / ROOT_PKG_REL
    cli_pkg = root / CLI_PKG_REL
    for manifest in (root_pkg, cli_pkg):
        if not os.access(manifest, os.R_OK) or not manifest.is_file():
            report.fail("required subject missing: %s" % manifest)
            return 1
    check_engines_pair(report, "NODE_VERSION_MIN", env_file, "node floor", root_pkg, cli_pkg)

    if report.fails > 0:
        print(
            "%sx %d toolchain-env/Dockerfile mismatch(es)%s"
            % (report.colour["RED"], report.fails, report.colour["NC"]),
            file=sys.stderr,
        )
        print(
            "  A NODE_VERSION_MIN mismatch is fixed in whichever file is wrong, not by",
            file=sys.stderr,
        )
        print(
            "  loosening the pin: .devcontainer/toolchain.env holds the floor, and both",
            file=sys.stderr,
        )
        print(
            "  package.json and packages/cli/package.json must carry engines.node", file=sys.stderr
        )
        print("  '>=' + that value.", file=sys.stderr)
        return 1

    print(
        "%s✓ toolchain.env and Dockerfile agree on GO_VERSION and NODE_VERSION,%s"
        % (report.colour["GREEN"], report.colour["NC"])
    )
    print(
        "%s  and NODE_VERSION_MIN agrees with both engines.node floors%s"
        % (report.colour["GREEN"], report.colour["NC"])
    )
    return 0


def selftest() -> int:
    """Both directions on every extractor and on the whole gate.

    The twin's own controls run INLINE on every invocation and are preserved above. What they cannot reach is the extractors' edge cases and the missing-subject paths, which is what this adds.
    """
    ctl = Controls("toolchain-env-dockerfile-sync", floor=26, verbose=True)
    plain = {"RED": "", "GREEN": "", "NC": ""}

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        env_file = tmpdir / "toolchain.env"
        dockerfile = tmpdir / "Dockerfile"

        # -- env_value ------------------------------------------------------
        env_file.write_text("GO_VERSION=1.26.6\nNODE_VERSION=22\n", encoding="utf-8")
        ctl.check(
            "CONTROL: env_value reads a plain pin", env_value("GO_VERSION", env_file), "1.26.6"
        )
        ctl.check(
            "CONTROL: a second key is read independently", env_value("NODE_VERSION", env_file), "22"
        )
        ctl.check("MIRROR: an absent key is empty, not an error", env_value("NOPE", env_file), "")
        env_file.write_text("  GO_VERSION=1.0.0\n", encoding="utf-8")
        ctl.check(
            "MIRROR: an INDENTED assignment is not a definition (the grep is anchored)",
            env_value("GO_VERSION", env_file),
            "",
        )
        env_file.write_text("GO_VERSION=1.0.0\nGO_VERSION=2.0.0\n", encoding="utf-8")
        ctl.check(
            "CONTROL: the FIRST match wins, unlike the .npmrc gate's tail -n1",
            env_value("GO_VERSION", env_file),
            "1.0.0",
        )
        env_file.write_text("K=a=b\n", encoding="utf-8")
        ctl.check(
            "CONTROL: cut -f2- keeps a value containing an =", env_value("K", env_file), "a=b"
        )
        env_file.write_text("GO_VERSION_EXTRA=9\n", encoding="utf-8")
        ctl.check("MIRROR: a longer key is not this key", env_value("GO_VERSION", env_file), "")
        ctl.check(
            "VACUITY: an unreadable pins file is empty, and the caller calls that a failure",
            env_value("GO_VERSION", tmpdir / "gone.env"),
            "",
        )

        # -- arg_value ------------------------------------------------------
        dockerfile.write_text("FROM x\nARG GO_VERSION=1.26.6\n", encoding="utf-8")
        ctl.check(
            "CONTROL: arg_value reads an ARG line", arg_value("GO_VERSION", dockerfile), "1.26.6"
        )
        dockerfile.write_text("ARG\tGO_VERSION=1.26.6\n", encoding="utf-8")
        ctl.check(
            "CONTROL: [[:space:]]+ covers a tab as well as a space",
            arg_value("GO_VERSION", dockerfile),
            "1.26.6",
        )
        dockerfile.write_text("  ARG GO_VERSION=1.26.6\n", encoding="utf-8")
        ctl.check(
            "MIRROR: an indented ARG is not read (the grep is anchored)",
            arg_value("GO_VERSION", dockerfile),
            "",
        )
        dockerfile.write_text("# ARG GO_VERSION=9.9.9\n", encoding="utf-8")
        ctl.check("MIRROR: a commented ARG is not an ARG", arg_value("GO_VERSION", dockerfile), "")
        dockerfile.write_text("ARG GO_VERSION=1\nARG GO_VERSION=2\n", encoding="utf-8")
        ctl.check(
            "CONTROL: head -1 means the first ARG wins", arg_value("GO_VERSION", dockerfile), "1"
        )

        # -- engines_node ---------------------------------------------------
        manifest = tmpdir / "m.json"
        manifest.write_text('{"engines":{"node":">=22.44.0"}}', encoding="utf-8")
        ctl.check("CONTROL: engines.node is read", engines_node(manifest), ">=22.44.0")
        manifest.write_text(
            '{"volta":{"node":"18.0.0"},"engines":{"node":">=22.44.0"}}', encoding="utf-8"
        )
        ctl.check(
            "MIRROR: a volta node pin does not decide the answer",
            engines_node(manifest),
            ">=22.44.0",
        )
        manifest.write_text('{"devDependencies":{"@types/node":"^22"}}', encoding="utf-8")
        ctl.check("MIRROR: @types/node is not engines.node", engines_node(manifest), "")
        manifest.write_text('{"engines":{}}', encoding="utf-8")
        ctl.check("VACUITY: an empty engines block yields nothing", engines_node(manifest), "")
        manifest.write_text("{ not json", encoding="utf-8")
        ctl.check(
            "VACUITY: a malformed manifest yields nothing, and the caller fails on it",
            engines_node(manifest),
            "",
        )
        ctl.check(
            "VACUITY: an absent manifest yields nothing", engines_node(tmpdir / "gone.json"), ""
        )

        # -- check_pair and check_engines_pair, through a Report ------------
        env_file.write_text("GO_VERSION=1.26.6\n", encoding="utf-8")
        dockerfile.write_text("ARG GO_VERSION=1.26.6\n", encoding="utf-8")
        report = Report(colour=plain)
        check_pair(report, "GO_VERSION", env_file, dockerfile, "T")
        ctl.check("CONTROL: agreeing values do not increment the counter", report.fails, 0)
        dockerfile.write_text("ARG GO_VERSION=1.26.5\n", encoding="utf-8")
        check_pair(report, "GO_VERSION", env_file, dockerfile, "T")
        ctl.check("PLANT: a mismatch increments the counter", report.fails, 1)

        report = Report(colour=plain)
        floor_env = tmpdir / "floor.env"
        floor_env.write_text("NODE_VERSION_MIN=22.44.0\n", encoding="utf-8")
        good = tmpdir / "good.json"
        good.write_text('{"engines":{"node":">=22.44.0"}}', encoding="utf-8")
        loose = tmpdir / "loose.json"
        loose.write_text('{"engines":{"node":">=22"}}', encoding="utf-8")
        check_engines_pair(report, "NODE_VERSION_MIN", floor_env, "T", good, good)
        ctl.check("CONTROL: two agreeing manifests pass", report.fails, 0)
        check_engines_pair(report, "NODE_VERSION_MIN", floor_env, "T", good, loose)
        ctl.check("PLANT: a RANGE that merely admits the pin is still a mismatch", report.fails, 1)

        # -- the whole gate, over a fixture root ----------------------------
        def build(where: pathlib.Path, *, go_arg: str, floor: str, cli_floor: str) -> pathlib.Path:
            (where / ".devcontainer").mkdir(parents=True, exist_ok=True)
            (where / "packages" / "cli").mkdir(parents=True, exist_ok=True)
            (where / ".devcontainer" / "toolchain.env").write_text(
                "GO_VERSION=1.26.6\nNODE_VERSION=22\nNODE_VERSION_MIN=%s\n" % floor,
                encoding="utf-8",
            )
            (where / ".devcontainer" / "Dockerfile").write_text(
                "ARG GO_VERSION=%s\nARG NODE_VERSION=22\n" % go_arg, encoding="utf-8"
            )
            (where / "package.json").write_text(
                '{"engines":{"node":">=%s"}}' % floor, encoding="utf-8"
            )
            (where / "packages" / "cli" / "package.json").write_text(
                '{"engines":{"node":">=%s"}}' % cli_floor, encoding="utf-8"
            )
            return where

        def run(where: pathlib.Path) -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(where)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        with tempfile.TemporaryDirectory() as inner:
            here = build(pathlib.Path(inner), go_arg="1.26.6", floor="22.44.0", cli_floor="22.44.0")
            ctl.check("CONTROL: a fully agreeing tree passes", run(here), 0)
        with tempfile.TemporaryDirectory() as inner:
            here = build(pathlib.Path(inner), go_arg="1.26.5", floor="22.44.0", cli_floor="22.44.0")
            ctl.check("PLANT: a GO_VERSION drift reds the gate", run(here), 1)
        with tempfile.TemporaryDirectory() as inner:
            here = build(pathlib.Path(inner), go_arg="1.26.6", floor="22.44.0", cli_floor="22.0.0")
            ctl.check("PLANT: a CLI-only floor drift reds the gate", run(here), 1)
        with tempfile.TemporaryDirectory() as inner:
            here = pathlib.Path(inner)
            ctl.check(
                "VACUITY: a tree with no subjects at all is a FAILURE, never a pass",
                run(here),
                1,
            )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
