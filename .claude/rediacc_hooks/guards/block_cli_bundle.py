"""Block running the CLI bundle directly via node.

THE ENTRY ARGUMENT IS THE TEST, not the presence of a path anywhere in the line. The original pattern was `node .*(cli-bundle|packages/cli/)`, and `.*` spans the whole command, so it refused three things it had no business refusing:

  node packages/cli/bundle.mjs        <- this repo's OWN build entry, the
                                         `build:bundle` script and line 144
                                         of build-cli-executables.sh
  node scripts/x.mjs --outdir packages/cli/dist
                                      <- the path is an OUTPUT flag, not the
                                         program being run
  any command merely QUOTING one of those strings

The third is not hypothetical: while measuring this guard on 2026-08-27 it blocked the measurement twice, because the probe's own command line contained the fixture text. That is the mention-as-execution class, and this session hit it nine times across these guards and the ones written to catch it.

So: match `node`, skip its flags, and require the FIRST non-flag argument -- the program -- to be the bundle. `bundle.mjs` is not `cli-bundle`, so the build entry passes by construction rather than by an allowlist.

ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant matching PROSE: `echo '<the banned command>'` was refused, and so was a worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a command hidden in a wrapper is scanned exactly as before -- this narrows what the guard
refuses, never what it catches.

PORT NOTE ON A LINE THAT DOES NOTHING. The bash computes `SCAN` and only THEN writes `[ -z "$CMD" ] && exit 0`, so the empty-command test is dead weight: `hook_scan_target ""` has already run, and its answer for the empty command matches nothing anyway. The order is carried across rather than tidied, because the differential compares behaviour and the tidy version would be a change
made
for taste rather than from a finding.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 8

# Re-inserting the `.*` between the program slot and the bundle name is exactly the original defect this guard's header is about: the path stops having to be the program and goes back to being any substring of the line, so `node scripts/x.mjs --outdir packages/cli/dist/out.js` is refused again.
DEFECT = (r"]*(cli-bundle[^", r"]*.*(cli-bundle[^")

# COMMAND POSITION, NOT ANY WHITESPACE. The anchor used to be `(^|[;&|(]|[{S}])`, and the `[{S}]` arm admits `node` after any space, which is inside every sentence: `echo the docs say never to run node cli-bundle.js in this repo` was refused (found by check:ci-guard-mention-anchoring, 2026-10-09). Now `node` must open a command: the line start or a separator, then
# optional blanks, then an optional directory (`/usr/bin/node`). The prefixes the whitespace arm used to tolerate (`sudo`, `time`, `env`, `xargs`, an assignment, a leading redirect, `!`, `if ... then`) still reach it, because `scan_target` lifts every command bash runs onto a line of its own (`shellscan.lifted_commands`), and so do the launchers shellscan walks (`shellscan._launched`, #ec63ff8c):
# `npx node cli-bundle.js`, `npx -y node packages/cli/dist/cli.js` and `find . -exec node cli-bundle.js \;` each lift `node ...` onto its own line. The last two were allowed before. `npm exec`, `npm exe` and `npm x` are the same launcher, and npm's own option parse decides where the program starts, abbreviations included (`npx --logl silent node ...`, #31ed6c5f).
NODE_BUNDLE = hookio.rx(
    r"(^|[;&|(`{!])[{S}]*([^{S};|&()`]*/)?node[{S}]+(-[^{S};|&]+[{S}]+)*[^{S};|&]*(cli-bundle[^{S};|&]*\.[cm]?js|packages/cli/dist/[^{S};|&]*)"
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
    # Command position: the whitespace arm of the old anchor refused this sentence.
    (
        "a sentence naming the command is not running it",
        "echo the docs say never to run node cli-bundle.js in this repo",
    ),
    ("a prefix command still reaches it", "sudo node cli-bundle.js"),
    ("npx is a launcher shellscan walks", "npx node cli-bundle.js"),
    # Launchers walked by shellscan (#ec63ff8c): both were allowed before 2026-10-09.
    ("npx with its own flag before node", "npx -y node packages/cli/dist/cli.js"),
    ("find -exec running node", r"find packages -maxdepth 0 -exec node cli-bundle.js \;"),
    (
        "npx running another program over the bundle path",
        "npx -y prettier --check packages/cli/dist/cli.js",
    ),
    ("npx -c runs a shell string", "npx -c 'node cli-bundle.js'"),
    ("npx running tsx", "npx tsx scripts/gen/gen-docs.ts"),
    ("after && still reaches it", "cd x && node cli-bundle.js"),
    # npm's own parse finds the program (#31ed6c5f): abbreviated options, and `npm exec`/`exe`/`x` as launchers. Each refusal was allowed before.
    ("an abbreviated npx value option", "npx --logl silent node packages/cli/dist/cli.js"),
    ("npm exec launches node", "npm exec -- node packages/cli/dist/cli.js"),
    ("npm x launches node", "npm x node packages/cli/dist/cli.js"),
    (
        "an npm option before an abbreviated exec",
        "npm --logl silent exe -- node packages/cli/dist/cli.js",
    ),
    ("npm exec -c runs a shell string", "npm exec -c 'node packages/cli/dist/cli.js'"),
    (
        "npm exec running another program over the bundle path",
        "npm exec -- prettier --check packages/cli/dist/cli.js",
    ),
    ("npm run is not a launcher", "npm run build -- packages/cli/dist/cli.js"),
    ("npm x running tsx", "npm x tsx --version"),
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
