#!/usr/bin/env bash
# Route a gate at the devbox when the host cannot run it but the container can.
#
# WHY. Measured 2026-08-27, over several hours: `check:ci-python-lint` reported
# "ruff is not available and neither is uvx" and `check:ci-renet` reported
# `command not found`, and this session recorded BOTH as environmental gaps and
# moved on -- twice teaching a gate to say "cannot run here" and once nearly
# marking a third that way when the real cause was an empty node_modules.
#
# The devbox was running the entire time and carries ruff 0.16.1, the pinned
# shfmt 3.13.1, shellcheck and Go. Nothing was missing. The gates were being run
# in the wrong place, and every "environmental" verdict written on that basis
# was wrong.
#
# It cost more than tidiness. `check:ci-renet` inside the container does not
# fail to start -- it RUNS, and reports `govulncheck` exit 3 with six stdlib
# vulnerabilities. Attributed afterwards by running govulncheck in throwaway
# containers at three toolchains: those six belong to go1.26.4, the version this
# image happened to ship. go1.26.6 and go1.25.13 (which is what CI installs, via
# go-version-file on private/renet/go.mod) both report none of them. So the
# finding was about the IMAGE and not the shipped code, and CI was never red on
# it -- but it was invisible from the host either way, behind a message that
# read like a local inconvenience.
#
# WHAT THIS DOES NOT DO. It does not route every `npm run`. Most gates are node
# and TypeScript and run identically on the host, where they are faster and
# their output lands directly in the transcript. It fires only when the command
# names a gate whose toolchain THIS host lacks and the container has -- that is
# the whole condition, and it is checked against the host, not assumed.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# Already routed through the devbox, or driving the devbox itself: out of scope.
printf '%s' "$CMD" | grep -qE 'devbox|docker[[:space:]]+exec' && exit 0

# gate key -> the host binary it needs. Extend this table when a gate acquires
# a new toolchain dependency; the entry is what makes the refusal specific
# enough to act on, and a gate absent from it is never routed.
declare -A NEEDS=(
    ["check:ci-python-lint"]="ruff"
    ["check:ci-renet"]="go"
    ["check:ci-renet-tiers"]="go"
    # AN ENTRY BELONGS HERE ONLY IF THE GATE FAILS WITHOUT THE BINARY ON PATH.
    # Three of the original six did not, and each produced a confident, specific
    # refusal of a gate that works:
    #   check:ci-shell-lint    shellcheck.sh calls toolchain_acquire
    #   check:ci-shell-format  shfmt.sh      calls toolchain_acquire
    #   check:ci-actionlint    downloads a pinned, checksum-verified release
    # toolchain_acquire fetching the PIN is the entire point of that helper --
    # its own comment says a bare `command -v` accepts any version and "a stale
    # binary on a developer's PATH silently decided this gate's verdict".
    # Measured 2026-08-27 with neither tool on PATH: shfmt.sh acquired v3.13.1
    # and reported "Shell script formatting passed", exit 0.
    # Check for toolchain_acquire in the gate's script before adding an entry.
    # NO check:ci-actionlint ENTRY, DELIBERATELY. That gate provisions its own
    # tool: .ci/scripts/security/actionlint.sh uses actionlint from PATH if it is
    # there and otherwise downloads a pinned, checksum-verified release, refusing
    # any version with no recorded checksum. Verified 2026-08-27 with no
    # actionlint on this host: "actionlint clean across 29 workflow file(s)".
    # Listing it here sent a working gate into the fix-the-image branch, which is
    # confident and specific advice to do work that buys nothing. Only add a gate
    # here if it genuinely fails without the binary on PATH.
)

HIT=""
NEED=""
for key in "${!NEEDS[@]}"; do
    printf '%s' "$SCAN" | grep -qF "$key" || continue
    tool="${NEEDS[$key]}"
    # THE HOST IS ASKED, NOT ASSUMED. A developer who has installed ruff should
    # not be pushed into a container for it; the point is to stop a MISSING tool
    # being recorded as a property of the repo.
    # `command -v` resolves a name on PATH and says NOTHING about whether it can be
    # executed: on bash 5.3.9 it returns 0 for a mode-0600 file. A half-installed
    # ruff/go/shfmt would therefore read as "the host is fine" and this guard would
    # decline to route the gate, which is the exact outcome it exists to prevent wearing
    # the face of a guard that simply did not fire. `test -x` asks the real question.
    # Verified 2026-08-27: command -v rc=0 and test -x rc=1 on the same file.
    test -x "$(command -v "$tool" 2>/dev/null)" 2>/dev/null && continue
    HIT="$key"
    NEED="$tool"
    break
done
[ -z "$HIT" ] && exit 0

# The container must actually be able to help, or this is a wall rather than a
# route. If it is not running, or lacks the tool too, say so and let the command
# proceed -- the gate's own refusal is then the honest answer.
CID=$(docker ps --filter "label=com.rediacc.devbox.worktree" --format '{{.Names}}' 2>/dev/null | head -1)
if [ -z "$CID" ]; then
    cat >&2 <<'MSG'
NOTE: this gate needs a toolchain this host does not have. The devbox would have
it, but no devbox is running for this worktree.

There is ONE container per worktree, so a fresh branch or worktree has none yet
and `devbox up` alone will not conjure one:

    ./run.sh setup        # a worktree that has never been prepared: builds the
                          # image if needed, then creates this worktree's container
    ./run.sh devbox up    # the worktree is already prepared, container stopped

Then re-run the gate through it. Proceeding for now, so the gate's own refusal
is what you see rather than this note standing in for a verdict.
MSG
    exit 0
fi
if ! docker exec -u vscode "$CID" bash -lc "command -v $NEED" >/dev/null 2>&1; then
    cat >&2 <<MSG
NOTE: $HIT needs '$NEED'. Neither this host nor the devbox ($CID) has it, so the
gate genuinely cannot run anywhere right now -- that is a real finding about the
IMAGE, not about your change.

Fix the image rather than recording another "environmental" red:
  1. add '$NEED' to .devcontainer/Dockerfile with an explicit version, the way
     the other tools there are pinned (an unpinned tool that decides a CI
     verdict is a different verdict on every rebuild)
  2. REBUILD THE IMAGE, not just the container. "devbox remove" removes the
     CONTAINER; devbox_ensure_image then short-circuits on the image it
     already has (.ci/lib/devbox.sh:367), and if you delete the image it
     PULLS from the registry first -- so a local Dockerfile edit reaches the
     box by neither route. Measured 2026-08-27: GO_VERSION was bumped to
     1.26.6 and the container still reported go1.26.4. What actually works:
         docker build -t ghcr.io/rediacc/devcontainer:latest -f .devcontainer/Dockerfile .devcontainer
         ./run.sh devbox remove && ./run.sh devbox up
  3. re-run the gate and say in your summary that you changed the image

Proceeding, so the gate's own message is what you see.
MSG
    exit 0
fi

cat >&2 <<MSG
BLOCKED: $HIT needs '$NEED', which is missing on this host and PRESENT in the devbox.

Run it there instead:

  ./run.sh devbox exec -- npm run $HIT

WHY THIS IS REFUSED RATHER THAN WARNED. A gate that cannot run does not report a
verdict about your code, and this session recorded exactly that as an
"environmental gap" three times in one afternoon while the container sat running
with the right tool. Once it was worse than tidiness: check:ci-renet on the host
said 'command not found', and in the devbox it RUNS and reports six stdlib
vulnerabilities in the image's own go1.26.4. Not a defect in the shipped code --
CI installs a different toolchain and sees none of them -- but a real finding
about the image that the host could not see at all.

IF THE DEVBOX IS ALSO WRONG, FIX THE IMAGE -- that is in scope and is the point
of this guard. .devcontainer/Dockerfile is where the toolchain is declared, and
'$NEED' should be pinned there with an explicit version, because a tool that
decides a CI verdict must be the same one CI uses. Rebuild the IMAGE, not the
container: "devbox remove" leaves the image untouched and devbox_ensure_image
reuses or re-pulls it, so a Dockerfile edit reaches the box by neither route.
    docker build -t ghcr.io/rediacc/devcontainer:latest -f .devcontainer/Dockerfile .devcontainer
    ./run.sh devbox remove && ./run.sh devbox up
and say in your summary that you changed the image, since that is a change the
operator did not ask for.

If you genuinely mean to run it on the host and read its refusal, say so and use
the devbox form to get a real answer instead.
MSG
exit 2
