#!/usr/bin/env bash
# Block agent-browser output that would land inside the repo working tree.
#
# WHY THIS EXISTS. Two different mechanisms have each put untracked files into this repo,
# and BOTH exit 0 and print a success line, so nothing catches them:
#
#   1. POSITIONAL FLAG-EATING. `screenshot [selector] [path]` has two positional slots.
#      `--full-page` is not a real flag (the real one is `--full`), so it is consumed as
#      [path]: the intended path silently becomes the SELECTOR, a file named `--full-page`
#      lands in $PWD, and the tool prints "Screenshot saved to --full-page".
#      Reproduced 2026-08-27.
#   2. AGENT_BROWSER_SCREENSHOT_DIR IS IGNORED. A bare filename resolves against the
#      working directory. `.claude/agents/browser-probe.md:119-123` records that this put
#      three untracked PNGs into a repo before anyone noticed, and states the rule this
#      hook enforces: "Pass an absolute path to every screenshot."
#
# The rule already existed in prose and had no enforcement surface. This is that surface.
#
# THE UNKNOWN-FLAG ALLOWLIST IS DELIBERATE AND MUST NOT BE WIDENED TO SILENCE A FIRE.
# An unrecognised `--flag` on an output subcommand is exactly the bug in case 1. When
# agent-browser gains a genuinely new flag, ADD IT HERE on purpose. Narrowing the match
# instead fails silently, which is the trade this repo has already ruled on.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[[ -z "$CMD" ]] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# Only the subcommands that write a file to disk.
echo "$SCAN" | grep -qE '\bagent-browser\b[^;|&]*\b(screenshot|pdf|download)\b' || exit 0

# Repo root from BASH_SOURCE, not CLAUDE_PROJECT_DIR, which is unreliable inside hooks.
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)

# EVERY agent-browser segment that actually writes a file, not just the first one.
# `head -1` was wrong twice over: in `agent-browser open URL && agent-browser screenshot
# /abs/x.png` it judged the `open` half, which has no path, and blocked a correct command;
# and with two output subcommands on one line it never looked at the second at all.
mapfile -t SEGMENTS < <(printf '%s' "$SCAN" | grep -oE '\bagent-browser\b[^;|&]*' |
    grep -E '\b(screenshot|pdf|download)\b')

fail() {
    cat >&2 <<EOF
❌ BLOCKED: agent-browser would write into the repo working tree.

  $1

  Write to an absolute path outside the repo, and put the path BEFORE any flags:
      agent-browser screenshot /tmp/shot.png --full

  Two things make this fail silently if you do not:
    - an unknown flag is eaten as the [path] positional (--full-page is not a flag; --full is)
    - AGENT_BROWSER_SCREENSHOT_DIR is ignored, so a bare filename lands in \$PWD

  Screenshots are disposable. Evidence that must survive belongs in the program
  checkpoints directory, not in /tmp and not in the repo.
EOF
    exit 2
}

for SEGMENT in "${SEGMENTS[@]}"; do
    # 1. An unrecognised long flag will be consumed as a positional.
    for tok in $SEGMENT; do
        case "$tok" in
            --full | --annotate | --json | --headed | --webgpu | --quiet) ;;
            --screenshot-dir | --screenshot-quality | --screenshot-format | --viewport | --executable-path | --cdp | --device | --provider | --timeout) ;;
            --screenshot-dir=* | --screenshot-quality=* | --screenshot-format=* | --viewport=* | --executable-path=* | --cdp=* | --device=* | --provider=* | --timeout=* | --hide-scrollbars=*) ;;
            --hide-scrollbars) ;;
            --*) fail "Unrecognised flag '$tok'. agent-browser will consume it as the output PATH." ;;
        esac
    done

    # 2. An absolute path under the repo root is an in-tree write.
    for tok in $SEGMENT; do
        case "$tok" in
            "$REPO_ROOT"/*) fail "'$tok' is inside the repo at $REPO_ROOT." ;;
        esac
    done

    # 3. No absolute path at all means the file resolves against $PWD.
    printf '%s\n' $SEGMENT | grep -qE '^/' ||
        fail "No absolute output path. A bare or relative filename resolves against \$PWD."
done

exit 0
