#!/usr/bin/env python3
"""Port of `.ci/scripts/infra/ci-pull-images.sh`.

Authenticate to GHCR with a short-lived token, pull the two backend images the
CI job needs, then scrub the credentials back off the runner. The twin's header
calls itself a "self-contained replacement for elite/action/ci-pull-images.sh",
which is why it carries its own credential cleanup rather than leaning on an
action's post step.

NOT `docker-prepull.sh`, which pulls PUBLIC base images with no credentials and
retries each one three times. This one authenticates, pulls exactly two OUR-OWN
images, and never retries. The two scripts are neighbours in the same directory
and it is worth knowing which is which before reading either.

-----------------------------------------------------------------------------
THE GHCR-AUTH DUPLICATION IS REAL, AND IT IS DELIBERATELY NOT FACTORED HERE
-----------------------------------------------------------------------------
`.ci/scripts/infra/docker-pull-ghcr.sh` (ported beside this file as
`rediacc_ci.infra.docker_pull_ghcr`) runs the SAME three-line dance:

    echo "$TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin
    docker pull ... ; docker logout ghcr.io

`.ci/scripts/lib/common.sh` is 772 lines and has NO ghcr, docker or registry
helper at all (grepped 2026-09-13: zero hits for `ghcr` and for `docker login`).
So the two bash twins do not share a helper, and inventing one on the Python
side would give the port a structure its twin does not have, which is exactly
the shape that makes a differential stop being a comparison. The duplication is
NAMED here and left in place; a shared `core.ghcr` is a cutover decision, not a
porting one.

FOUR WAYS THE TWO SCRIPTS DISAGREE WHILE DOING "THE SAME THING", all preserved,
because each is a live behavioural difference and not a spelling one:

  1. `docker-pull-ghcr.sh` calls `require_cmd docker` first. THIS ONE DOES NOT,
     so a runner with no docker reaches `docker login` and dies with bash's own
     `command not found` at exit 127 instead of the library's one-line refusal.
  2. `docker-pull-ghcr.sh` runs under `set -euo pipefail`. This one runs under
     bare `set -e`: no `-u`, no `-o pipefail`.
  3. `docker-pull-ghcr.sh` takes `--token`/`--actor` flags. This one is
     environment-only.
  4. `docker-pull-ghcr.sh` logs out UNGUARDED (a failing logout kills it under
     `set -e`). This one logs out with `2>/dev/null || true`.

-----------------------------------------------------------------------------
HAZARD, REPORTED RATHER THAN REPAIRED: A FAILED PULL LEAVES THE CREDENTIALS ON
THE RUNNER
-----------------------------------------------------------------------------
The cleanup block is straight-line code AFTER the subshell, with no `trap`. The
subshell runs under `set -e`, so a failing `docker login` or a failing
`docker pull` takes the whole script down at that line, and every line below it
-- `docker logout`, the `jq del(.auths["ghcr.io"])` scrub, the "environment is
now safe for debug access" claim -- is never reached. The comment on line 45
says the subshell exists "to contain credential exposure"; a subshell contains a
VARIABLE, not a file, and `~/.docker/config.json` is written by `docker login`
in the real filesystem where it outlives the subshell.

So the failure mode is: pull fails, job continues into a debug/ssh step, and the
GHCR token is sitting in `~/.docker/config.json`. The fix is one `trap ... EXIT`
around the cleanup block. It is NOT applied here: this port's contract is
one-for-one equivalence with a twin that stays live and registered, and a port
that cleaned up where the twin does not would be a divergence in exactly the
direction a differential cannot bless. Pinned by
`test_a_failing_pull_skips_the_credential_cleanup_on_both_sides`.

TWO SMALLER WARTS, both preserved:

  * `unset GITHUB_TOKEN` / `unset DOCKER_REGISTRY_PASSWORD` (lines 78-79) are
    theatre. They run in the script's own process, three lines before it exits,
    and cannot touch the parent shell or a later workflow step. `os.environ.pop`
    here is the same no-op, kept so the two processes end with the same
    environment rather than for any effect it has.
  * `DOCKER_REGISTRY` is documented in the header as "Registry URL" but the
    SERVER image ignores it: line 54 hard-codes `ghcr.io/rediacc/server`, and
    only renet is pulled from `$DOCKER_REGISTRY`. The twin's own comment says
    why (the onprem build lives outside the elite namespace). So setting
    `DOCKER_REGISTRY=ghcr.io/example` moves one image and not the other. Pinned
    by `test_docker_registry_moves_renet_and_not_server`.

-----------------------------------------------------------------------------
WHAT IS EXECUTED RATHER THAN REIMPLEMENTED, AND WHY
-----------------------------------------------------------------------------
`jq` and `grep` are RUN, not replaced with `json`/`re`:

  * the `jq 'del(.auths["ghcr.io"])'` rewrite decides the BYTES of the user's
    `~/.docker/config.json`. `json.dumps` would reformat indentation and could
    reorder nothing but would still not be jq's output, so the file a human
    later reads would differ depending on which implementation ran.
  * the final `grep -E "(rediacc|REPOSITORY)"` decides the bytes on stdout.
    `grep -E` on this machine is ugrep 7.5.0, which has documented divergences
    from PCRE on alternated anchors (CLAUDE.md). This pattern has no anchor, so
    the two would agree today -- and running the real binary means they agree
    regardless of which grep the runner has, which is the property worth having.

`docker` itself always inherits both streams: the twin never captures it, so a
pull's progress and any error text land on the caller's terminal interleaved
with this script's own log lines, and a port that captured and replayed would
reorder them.

Exit: 0 on the full path; 1 on either missing environment variable; the
subshell's failing status (docker's) when login or a pull fails; 127 when there
is no `docker` at all.

K=5 LEDGER: `.ci/shadow/w7p6-ci-pull-images.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log

# `echo "===...==="`, 70 columns. Measured off the twin rather than eyeballed.
RULE = "=" * 70
BANNER = "  Pre-pulling Docker images with temporary authentication..."

# `${DOCKER_REGISTRY:-ghcr.io/rediacc}` and `${TAG:-latest}` (lines 40-43).
DEFAULT_REGISTRY = "ghcr.io/rediacc"
DEFAULT_TAG = "latest"

# Line 54, hard-coded and NOT `$DOCKER_REGISTRY`. See the wart above.
SERVER_REPO = "ghcr.io/rediacc/server"

# The registry `docker login` / `docker logout` name. A bare host, no path.
REGISTRY_HOST = "ghcr.io"

# `docker images --format "table ..."` then `grep -E`. Kept as two constants so the test can assert the argv rather than re-typing the format string.
#
# THE `\t` IS TWO CHARACTERS, NOT A TAB, and this is the one thing in this file a Python author gets wrong by reflex. bash does NOT interpret `\t` inside
# double quotes, so `--format "...{{.Tag}}\t{{.Size}}"` hands docker a literal
# BACKSLASH followed by `t`, and docker's own template engine is what turns it into a tab. A real tab here reaches docker as a tab, renders the same, and makes the argv differ -- which the differential caught on its first run (`test_the_happy_path_is_five_docker_calls_in_this_order`).
IMAGES_FORMAT = "table {{.Repository}}:{{.Tag}}\\t{{.Size}}"
IMAGES_GREP = "(rediacc|REPOSITORY)"

# `jq 'del(.auths["ghcr.io"])'`, verbatim.
JQ_DEL_GHCR = 'del(.auths["ghcr.io"])'

# S105 fires on the NAME, not the value: it sees `TOKEN` and calls the string a hardcoded password. It is the twin's error TEXT (line 30), which has to stay byte-identical, and there is nothing secret in it. Same suppression, same reason, as `release_key_canonical.py:149` and `test_build_canonicalise_gpg_key.py:49`.
MISSING_TOKEN = "GITHUB_TOKEN environment variable is required"  # noqa: S105
MISSING_ACTOR = "GITHUB_ACTOR environment variable is required"

# bash's own message when a pipeline's command does not resolve, and its status. The twin has no `require_cmd docker` (difference 1 above), so this is the shape a docker-less runner actually sees. The BYTES differ -- bash prefixes `<script>: line 49: ` -- and the differential asserts that difference by name rather than papering over it.
NO_DOCKER_STATUS = 127
NOT_FOUND_TAIL = "command not found"


def resolve_tags(env: dict[str, str]) -> tuple[str, str, str]:
    """Lines 40-43 -> (registry, renet_tag, web_tag).

    `${VAR:-default}` is the COLON form throughout, so a variable exported as
    the empty string falls back to the default rather than producing
    `ghcr.io/rediacc/renet:`. Exported so the differential can drive the
    defaulting ladder directly: `TAG` feeds BOTH image tags, and either can
    override it on its own.
    """
    registry = env.get("DOCKER_REGISTRY") or DEFAULT_REGISTRY
    tag = env.get("TAG") or DEFAULT_TAG
    return registry, (env.get("RENET_TAG") or tag), (env.get("WEB_TAG") or tag)


def _not_found(binary: str) -> int:
    """bash's `command not found`, as this port's nearest honest equivalent.

    A NAMED DIVERGENCE. bash prefixes its own `<script>: line <n>: `, which
    names a line number this file does not have, so the two sides cannot be
    byte-identical here. What IS identical is the exit status (127) and the fact
    that a missing tool is loud rather than a traceback.
    `test_a_missing_docker_is_127_on_both_sides_with_a_named_text_divergence`
    asserts both halves.
    """
    print("%s: %s" % (binary, NOT_FOUND_TAIL), file=sys.stderr, flush=True)
    return NO_DOCKER_STATUS


def _run(argv: list[str], stderr: object = None) -> int:
    """`subprocess.run` with both streams inherited unless stderr is redirected.

    STDOUT IS FLUSHED FIRST, EVERY TIME. The child writes straight to fd 1 while
    this process buffers, so an unflushed `print` would land AFTER the child's
    output in a redirected stdout even though it was issued before. bash has no
    such buffer, so skipping the flush is a reordering the twin cannot produce.
    """
    sys.stdout.flush()
    try:
        return subprocess.run(argv, check=False, stderr=stderr).returncode  # type: ignore[arg-type]
    except OSError:
        return _not_found(argv[0])


def docker_login(token: str, actor: str) -> int:
    """`echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin`.

    THE NEWLINE MATTERS. `echo` appends one, and `--password-stdin` reads the
    whole of stdin and strips a single trailing newline, so a token piped
    without it is the same token -- but a port that sent no newline would differ
    from the twin on any docker that ever stops stripping. The twin's bytes are
    reproduced: token plus `\\n`.
    """
    sys.stdout.flush()
    try:
        proc = subprocess.run(
            ["docker", "login", REGISTRY_HOST, "-u", actor, "--password-stdin"],
            input=(token + "\n").encode(),
            check=False,
        )
    except OSError:
        return _not_found("docker")
    return proc.returncode


def pull(image: str) -> int:
    """`docker pull --quiet "$image"`. Both streams inherited."""
    return _run(["docker", "pull", "--quiet", image])


def authenticate_and_pull(token: str, actor: str, registry: str, renet: str, web: str) -> int:
    """The subshell (lines 46-60). Returns the status the subshell would exit with.

    `set -e` IS INHERITED BY A SUBSHELL, which is why this returns on the first
    non-zero instead of pressing on: a failed login must not be followed by two
    pulls that would fail again with worse messages.
    """
    log.step("Authenticating with ghcr.io...")
    code = docker_login(token, actor)
    if code != 0:
        return code

    log.step("Pulling server:%s..." % web)
    code = pull("%s:%s" % (SERVER_REPO, web))
    if code != 0:
        return code

    log.step("Pulling renet:%s..." % renet)
    code = pull("%s/renet:%s" % (registry, renet))
    if code != 0:
        return code

    log.info("All images pulled successfully")
    return 0


def scrub_docker_config(home: str) -> None:
    """Lines 67-75: strip the `ghcr.io` entry out of `~/.docker/config.json`.

    THREE GUARDS, IN THE TWIN'S ORDER, and the third is the one that matters:
    the file must exist, `jq` must resolve, and the rewrite must SUCCEED before
    the temporary file replaces the original. `>"$cfg.tmp"` truncates the
    temporary first, so a jq that fails writes an empty file, and the `||`
    branch deletes it rather than moving an empty file over the user's config.

    `$HOME` UNSET IS NOT SPECIAL-CASED, because it is not special-cased in the
    twin either: `"$HOME/.docker/config.json"` becomes `/.docker/config.json`,
    which does not exist, and the block is skipped. `env.get("HOME", "")` lands
    on the same path.
    """
    cfg = pathlib.Path(home) / ".docker" / "config.json"
    if not cfg.is_file():
        return
    if shutil.which("jq") is None:
        return
    tmp = pathlib.Path(str(cfg) + ".tmp")
    try:
        with tmp.open("wb") as out, open(os.devnull, "wb") as null:
            code = subprocess.run(
                ["jq", JQ_DEL_GHCR, str(cfg)], stdout=out, stderr=null, check=False
            ).returncode
    except OSError:
        # `command -v jq` said yes and the exec still failed. Treat it as the failing-jq branch, which deletes the temporary and leaves the config untouched -- the direction that cannot corrupt the user's file.
        code = 1
    if code == 0:
        try:
            os.replace(tmp, cfg)
            return
        except OSError:
            pass
    # `|| rm -f "$cfg.tmp"`, and `-f` means a missing file is not an error.
    tmp.unlink(missing_ok=True)


def list_pulled_images() -> None:
    """`docker images --format ... | grep -E "(rediacc|REPOSITORY)" || true`.

    THE REAL `grep`, PIPED, not `re.search` over captured text. See the module
    docstring: this decides bytes on stdout, and running the same binary the
    twin runs removes the whole question of whose regex engine is in play.

    `|| true` swallows grep's exit 1 on no match, so this is the LAST command of
    the script and the script's exit status is 0 whatever docker said.
    """
    sys.stdout.flush()
    try:
        images = subprocess.Popen(
            ["docker", "images", "--format", IMAGES_FORMAT], stdout=subprocess.PIPE
        )
    except OSError:
        _not_found("docker")
        return
    try:
        matcher = subprocess.Popen(["grep", "-E", IMAGES_GREP], stdin=images.stdout)
    except OSError:
        _not_found("grep")
        if images.stdout is not None:
            images.stdout.close()
        images.wait()
        return
    # The parent must drop its own handle or grep never sees EOF.
    if images.stdout is not None:
        images.stdout.close()
    matcher.wait()
    images.wait()


def main(argv: list[str]) -> int:
    # THE TWIN IGNORES ITS ARGUMENTS ENTIRELY -- no parse_args, no positional handling -- so `argv` is accepted and unused rather than validated. A port that refused an unexpected argument would refuse invocations the twin accepts.
    del argv
    env = os.environ

    # STDOUT, not the logger: these are bare `echo`s in the twin (lines 23-26), so they land on the data stream and not on stderr. Reproduced exactly, including the leading blank line.
    print(flush=True)
    print(RULE, flush=True)
    print(BANNER, flush=True)
    print(RULE, flush=True)

    if not env.get("GITHUB_TOKEN"):
        log.error(MISSING_TOKEN)
        return 1
    if not env.get("GITHUB_ACTOR"):
        log.error(MISSING_ACTOR)
        return 1

    registry, renet_tag, web_tag = resolve_tags(dict(env))

    code = authenticate_and_pull(
        env["GITHUB_TOKEN"], env["GITHUB_ACTOR"], registry, renet_tag, web_tag
    )
    if code != 0:
        # `set -e` on the subshell. THE CLEANUP BELOW IS SKIPPED, and that is the hazard in the module docstring, not an omission in this port.
        return code

    print(flush=True)
    log.step("Removing Docker credentials...")
    with open(os.devnull, "wb") as null:
        # `2>/dev/null || true`: a logout that fails is not allowed to end the run, and its complaint is not shown.
        _run(["docker", "logout", REGISTRY_HOST], stderr=null)

    scrub_docker_config(env.get("HOME", ""))

    # `unset` on the way out. A no-op in both implementations; see the module
    # docstring. Kept so the two processes end in the same state.
    env.pop("GITHUB_TOKEN", None)
    env.pop("DOCKER_REGISTRY_PASSWORD", None)

    log.info("Credentials cleaned - environment is now safe for debug access")
    print(RULE, flush=True)
    print(flush=True)

    print("Pulled images:", flush=True)
    list_pulled_images()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
