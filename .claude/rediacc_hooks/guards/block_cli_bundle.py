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

THE PROGRAM IS THE WORD BASH HANDS THE INTERPRETER (#e13fb555). The pattern reads the line as typed, so `B=packages/cli/dist/cli-bundle.cjs; node $B config field set ...` ran on 2026-10-15: the program slot held `$B`. Every run shellscan walks now carries its expanded words (`_Run.xargv`), and each one whose program is node, deno, bun or tsx has that program read the way the interpreter reads it (`shellscan.program_parse`), from the expanded words, and joined onto the directory the run executes in.
So `node "$B"`, `node ${B}`, `export B=...; node $B`, `node -- $B`, `cd packages/cli && node dist/index.js`, a symlink that resolves into the bundle, and `bun`/`deno run`/`tsx` of the bundle are refused alongside the typed form. deno, bun and tsx run the same file around ./rdc.sh just as node does, which is what docs/design/09-implementation-phases.md means by blocking a direct cli-bundle invocation.
A word whose value the walk cannot know (`$UNSET`, `$(...)`) is left unjudged, as before, and `env B=... node $B` hands node nothing, because bash expands `$B` before env sets it. Only a command's program is read, never an operand or an echoed sentence, so the guard still refuses commands and not prose.
"""

import os
import re

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


# The programs that run a JavaScript file named on their command line. `program_parse` reads each with its own grammar (deno's subcommands, bun's `run`, tsx's own options).
RUNNERS = ("node", "nodejs", *shellscan.RUNTIMES)
# The bundle, judged on one path: a `cli-bundle*.js` file name, or anything under the CLI's build output.
BUNDLE_PATH = re.compile(r"cli-bundle[^/]*\.[cm]?js$|(^|/)packages/cli/dist/")


def _is_bundle(word, directory):
    """True when `word`, a program path as bash expanded it, names the bundle: as written, or joined onto `directory` (the run's absolute directory, None when unknown) and resolved on disk, so a relative path from inside the package and a symlink into it both count."""
    if not word or shellscan.unresolved(word) or "\0" in word:
        return False
    if BUNDLE_PATH.search(word):
        return True
    if not os.path.isabs(word) and directory is None:
        return False
    try:
        landed = os.path.realpath(word if os.path.isabs(word) else os.path.join(directory, word))
    except (OSError, ValueError):
        return False
    return BUNDLE_PATH.search(landed) is not None


# A word that is one variable and nothing else, quoted or not: `$N`, `${N}`, `"$B"`. shellscan expands a run's operands (`xargv`) but not its command name, and not the words fed to xargs, so those two are looked up here in the shell state the walk recorded for the run (`_Run.vars`).
SOLE_VARIABLE = re.compile(r'^"?\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"?$')


def _value(word, shell):
    """`word` with a sole variable replaced by the value the walk gave it, else `word` unchanged (an unknown variable stays the typed `$NAME`, which names no bundle)."""
    m = SOLE_VARIABLE.match(word)
    if m is None:
        return word
    got = shell.get(m.group(1) or m.group(2))
    return got[0] if got and isinstance(got[0], str) else word


def _programs(run):
    """`(runner base, its expanded argv)` for every runner this run starts: itself, and each command a launcher among `npx`/`npm exec`/`find -exec` starts, re-read from the launcher's EXPANDED words. shellscan walks a launched command from the words as typed (`_quote_argv(argv)`), so in `B=...; npx node $B` the launched node run reads the literal `$B`."""
    xargv = run.xargv if run.xargv is not None else run.argv
    base = _value(run.name, run.vars).rsplit("/", 1)[-1]
    if base in RUNNERS:
        yield base, xargv
    for how, words, _launch, _span in shellscan._launches(base, xargv):
        if how == "argv" and words and not shellscan.unresolved(words[0]):
            inner = words[0].rsplit("/", 1)[-1]
            if inner in RUNNERS:
                yield inner, words[1:]


def _fed(run, kind, value):
    """The program paths an xargs in front of `run` may hand it. With no program on the runner's own line (`kind` "stdin"), xargs appends what it reads, so every fed word is a candidate; a program holding a replace marker (`-I{}`) is each fed word in the marker's place. Over-read on purpose: the fed text is every word of the producer unless shellscan knows it exactly."""
    if "xargs" not in run.via or not run.feed:
        return []
    fed = [
        _value(w, run.vars)
        for w in (run.feed_words if run.feed_words is not None else run.feed.split())
    ]
    if kind == "stdin":
        return fed
    if kind != "file":
        return []
    markers = [m for m in shellscan.xargs_marker_candidates(run.xargs) if m in value]
    return [value.replace(m, w) for m in markers for w in fed]


def _runs_bundle(cmd, cwd, depth=0):
    """True when a command bash would run starts the bundle through node, deno, bun or tsx (#e13fb555)."""
    for run in shellscan.every_run(cmd):
        directory = shellscan._run_directory(run, cwd) if cwd else None
        for base, argv in _programs(run):
            kind, value = shellscan.program_parse(base, argv)
            candidates = ([value] if kind == "file" else []) + _fed(run, kind, value)
            if any(_is_bundle(c, directory) for c in candidates):
                return True
        # A double-quoted `-c` payload is expanded by the OUTER shell before the inner one parses it: `B=...; bash -c "node $B"` runs `node <bundle>`, while shellscan walks the payload as typed. The expanded payload is walked again, in the run's directory.
        xargv = run.xargv or []
        if depth < 4 and run.name.rsplit("/", 1)[-1] in shellscan.SHELL_NAMES and xargv != run.argv:
            how, payload = shellscan._shell_payload(xargv)
            if (
                how == "c"
                and payload
                and not shellscan.unresolved(payload)
                and _runs_bundle(payload, directory, depth + 1)
            ):
                return True
    return False


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if cmd == "":
        return hookio.ALLOW

    if hookio.grep_q(NODE_BUNDLE, scan) or _runs_bundle(cmd, ev.field("cwd") or ev.cwd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
