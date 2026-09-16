"""Block running the CLI bundle directly via node.

THE ENTRY ARGUMENT IS THE TEST, not the presence of a path anywhere in the
line. The original pattern was `node .*(cli-bundle|packages/cli/)`, and `.*`
spans the whole command, so it refused three things it had no business
refusing:

  node packages/cli/bundle.mjs        <- this repo's OWN build entry, the
                                         `build:bundle` script and line 144
                                         of build-cli-executables.sh
  node scripts/x.mjs --outdir packages/cli/dist
                                      <- the path is an OUTPUT flag, not the
                                         program being run
  any command merely QUOTING one of those strings

The third is not hypothetical: while measuring this guard on 2026-08-27 it
blocked the measurement twice, because the probe's own command line contained
the fixture text. That is the mention-as-execution class, and this session hit
it nine times across these guards and the ones written to catch it.

So: match `node`, skip its flags, and require the FIRST non-flag argument --
the program -- to be the bundle. `bundle.mjs` is not `cli-bundle`, so the
build entry passes by construction rather than by an allowlist.

ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant
matching PROSE: `echo '<the banned command>'` was refused, and so was a
worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and
quoted spans while still extracting `sh -c` / `eval` payloads, so a command
hidden in a wrapper is scanned exactly as before -- this narrows what the
guard refuses, never what it catches.

PORT NOTE ON A LINE THAT DOES NOTHING. The bash computes `SCAN` and only THEN
writes `[ -z "$CMD" ] && exit 0`, so the empty-command test is dead weight:
`hook_scan_target ""` has already run, and its answer for the empty command
matches nothing anyway. The order is carried across rather than tidied, because
the differential compares behaviour and the tidy version would be a change made
for taste rather than from a finding.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-cli-bundle.sh"
ORDER = 8

# Re-inserting the `.*` between the program slot and the bundle name is exactly
# the original defect this guard's header is about: the path stops having to be
# the program and goes back to being any substring of the line, so
# `node scripts/x.mjs --outdir packages/cli/dist/out.js` is refused again.
DEFECT = (r"]*(cli-bundle[^", r"]*.*(cli-bundle[^")

NODE_BUNDLE = hookio.rx(
    r"(^|[;&|(]|[{S}])node[{S}]+(-[^{S};|&]+[{S}]+)*[^{S};|&]*(cli-bundle[^{S};|&]*\.[cm]?js|packages/cli/dist/[^{S};|&]*)"
)

MESSAGE = "❌ BLOCKED: Do not run the CLI bundle directly via node. Use ./rdc.sh instead."

EDGE_CASES = [
    ("the bundle as the program", "node packages/cli/dist/cli.js"),
    ("a cli-bundle file as the program", "node cli-bundle.cjs"),
    ("flags before the program are skipped", "node --enable-source-maps cli-bundle.cjs"),
    # The three shapes the 2026-08-27 narrowing exists for.
    ("this repo's OWN build entry", "node packages/cli/bundle.mjs"),
    (
        "the path is an OUTPUT flag, not the program",
        "node scripts/x.mjs --outdir packages/cli/dist/out.js",
    ),
    ("prose merely quoting the banned command", "echo 'node packages/cli/dist/cli.js'"),
    ("a wrapper payload is still scanned", "sh -c 'node packages/cli/dist/cli.js'"),
    ("node with an unrelated program", "node scripts/dev/x.mjs"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if cmd == "":
        return hookio.ALLOW

    if hookio.grep_q(NODE_BUNDLE, scan):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
