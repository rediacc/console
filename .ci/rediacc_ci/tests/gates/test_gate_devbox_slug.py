"""Port of `.ci/scripts/test/gates/test-devbox-slug.sh`.

Controls for the devbox HOSTNAME: the branch-derived slug, its drift against a running container, and the route label that reports it.

WHY THIS EXISTS. The slug is not decoration. It is the Host header, it names the
traefik ROUTERS (`traefik.http.routers.${slug}-code`), and it is baked into the
container at `docker run` while the rest of the world recomputes it live. Every failure in this area presents as a CONFIDENT WRONG ANSWER rather than an error: a drifted hostname makes traefik answer 404 for an unmatched Host, and the pre-change catch-all printed that as "live (HTTP 404)" -- three live rows whose URLs all 404 in a browser. A detached HEAD under `rev-parse
--abbrev-ref` yields the literal string HEAD, which sanitises to the perfectly VALID hostname `head.localhost`, so every detached worktree on the machine converges on one name and one router. Neither is
visible to a smoke test; both are visible here.

HOW. Function bodies are LIFTED out of `.ci/lib/devbox.sh` so this cannot drift from the real code, and every control is built BY CONSTRUCTION -- a variant function written into a temp file and sourced -- never by substituting a live source line, which is the vacuity shape `check-control-vacuity.sh` exists to stop.

THE LIFT IS THE ONE THING THE PORT RESPELLS. The twin runs
`eval "$(sed -n '/^name() {/,/^}/p' "$LIB")"`, which pulls the body into the test's
OWN shell; a Python process has no shell to eval into, so this module extracts the
same line range with the same two anchors and hands it to a fresh `bash -c` per call. The extractor asserts what `sed` leaves implicit and the twin then re-checks with `declare -F`: a name that did not extract is a FAILURE here and never an empty string, because "the function is not defined" and "the function returned nothing" are the same observation once the body is missing, and
the twin's own comment says every assertion below would then be vacuous.

BLIND SPOTS, stated so a green here is not read as more than it is:
  1. It never starts a container, a proxy or traefik. That the LABELS this library
     writes produce the routers traefik actually builds is assumed, not proven; only
     the string that goes into them is checked.
  2. `feat/x` and `feat-x` still collapse to ONE hostname. That collision is asserted
     below as DELIBERATE, not fixed -- two branches whose names differ only by a
     separator share a URL, and only the collision refusal in `devbox_up` stands
     between that and two silently duplicated routers.
  3. It exercises the PURE functions. `devbox_up`'s rehost path and `devbox_status`'s
     probe loop are read by text-scan here, not executed.

NO `xdist_group`. Every case runs one short-lived `bash -c` with an env overlay and
writes only into its own `mktemp -d`; the library is only ever READ, and the one git
repository built here lives entirely inside that temp directory.
"""

import re
import subprocess

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-devbox-slug.sh"

LIB = paths.from_root(".ci", "lib", "devbox.sh")

# A legal DNS label: the rule the slug must satisfy for traefik to route it at all.
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# The branch/slug vocabulary section 4 refuses in an identity or port function.
BRANCH_RE = re.compile(r"devbox_branch|devbox_slug|slug|branch|symbolic-ref|abbrev-ref")
COMMENT = re.compile(r"^\s*#")

LONG = "feature/an-extremely-long-branch-name-that-nobody-would-ever-type-but-git-happily-accepts-x"

# (input, expected). A 90-char name is included because the truncation to 40 can land ON a dash, and a trailing dash is not a legal DNS label.
SLUG_ROWS = (
    ("feat/x", "feat-x"),
    ("feat//x", "feat-x"),
    ("Feature/ABC-123", "feature-abc-123"),
    ("--lead-and-trail--", "lead-and-trail"),
    ("0826-2", "0826-2"),
    ("feat/über", "feat-ber"),
    ("", ""),
    ("///", ""),
    (LONG, "feature-an-extremely-long-branch-name-th"),
)


def body_of(name: str) -> str:
    """`sed -n '/^<name>() {/,/^}/p'` over the library, as a string.

    The two anchors are the twin's exactly: an opening line that STARTS with
    `<name>() {` (devbox.sh writes a trailing comment after the brace on some of
    them, which is why this is a prefix test rather than an equality test), and the
    first `}` in COLUMN 0 after it.
    """
    lines = LIB.read_text(encoding="utf-8").splitlines()
    opening = "%s() {" % name
    for index, line in enumerate(lines):
        if line.startswith(opening):
            for end in range(index + 1, len(lines)):
                if lines[end] == "}":
                    return "\n".join(lines[index : end + 1])
            return ""
    return ""


def lift(gate, *names: str) -> str:
    """The bodies of `names`, concatenated, or a LOUD refusal.

    A name that did not extract is a FAILURE and never an empty prelude, because a prelude missing a definition turns every assertion downstream into "command not found" reported as somebody else's exit code. The twin makes the same refusal
    with `declare -F` and calls the alternative vacuous, which it is.
    """
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(LIB))
    parts = []
    for name in names:
        body = body_of(name)
        if not body:
            gate.log_fail(
                "LIFT FAILED: %s was not extracted from %s -- every assertion that used it "
                "would be vacuous" % (name, paths.relative_to_root(LIB))
            )
        parts.append(body)
    return "\n".join(parts)


def sh(gate, prelude: str, code: str, *, env: dict[str, str] | None = None) -> str:
    """Run `code` after `prelude` in a fresh bash; stdout, stripped of the trailing newline.

    stdout ALONE. Several of these functions log to stderr while returning their answer on stdout, and merging the two would let a log line become part of a hostname.
    """
    bash = harness.require_tool("bash", "install bash; the subject is a bash library")
    result = harness.run([bash, "-c", "%s\n%s" % (prelude, code)], env=env)
    if result.rc != 0:
        gate.log_fail(
            "the lifted probe exited %d rather than answering (stderr: %s)"
            % (result.rc, result.err.strip())
        )
    return result.out.rstrip("\n")


def test_the_hostname_rules_hold(gate):
    """One tally over all six sections, exactly as the flat twin runs them.

    KEPT AS ONE FUNCTION rather than split into six, because the twin is a FLAT script with no case set at all: `test_twin_parity.py` therefore compares against its runtime `PASS:` count, and the thing that must be preserved is the number and identity of the CONTROLS, not their arrangement into pytest functions. Splitting would also re-lift the library six times to say the same
    thing.
    """
    prelude = lift(
        gate, "devbox_slugify", "devbox_slug_drift", "devbox_route_label", "devbox_state_get"
    )

    # --------------------------------------------------------------------- 1. devbox_slugify -- the pure rule ---------------------------------------------------------------------
    gate.log_test("devbox_slugify: the branch-name-to-hostname rule")
    for value, want in SLUG_ROWS:
        got = sh(gate, prelude, "devbox_slugify %s" % shell_quote(value))
        if got == want:
            gate.ok("slugify: '%s' -> '%s'" % (value, got))
        else:
            gate.no("slugify: '%s' gave '%s', expected '%s'" % (value, got, want))
        if got and not HOSTNAME_RE.match(got):
            gate.no("slugify: '%s' is not a legal DNS label (from '%s')" % (got, value))
        if len(got) > 40:
            gate.no("slugify: '%s' produced %d chars; the cap is 40" % (value, len(got)))

    # CONTROL, by construction: the pre-change rule did not COLLAPSE runs of dashes. Write that rule as its own function and require the feat//x row to go RED.
    nocollapse = """devbox_slugify_planted() {
    local s
    s="$(LC_ALL=C printf '%s' "${1:-}" |
        LC_ALL=C tr '[:upper:]' '[:lower:]' |
        LC_ALL=C sed 's/[^a-z0-9-]/-/g; s/^-*//; s/-*$//')"
    LC_ALL=C printf '%s\\n' "${s:0:40}" | LC_ALL=C sed 's/^-*//; s/-*$//'
}"""
    planted = sh(gate, nocollapse, "devbox_slugify_planted 'feat//x'")
    if planted == "feat-x":
        gate.no(
            "CONTROL DID NOT FIRE: the un-collapsed rule also produced 'feat-x', so the "
            "collapse row proves nothing"
        )
    else:
        gate.ok(
            "CONTROL: without the collapse rule 'feat//x' gives '%s' -- the row would go red"
            % planted
        )

    # --------------------------------------------------------------------- 2. The deliberate collision --------------------------------------------------------------------- feat/x and feat-x are DIFFERENT branches that share ONE hostname. Assert the INPUTS differ first: if a refactor ever made them equal, comparing the outputs alone would pass while proving nothing.
    gate.log_test("devbox_slugify: the separator collision is deliberate, not accidental")
    a, b = "feat/x", "feat-x"
    slug_a = sh(gate, prelude, "devbox_slugify %s" % shell_quote(a))
    slug_b = sh(gate, prelude, "devbox_slugify %s" % shell_quote(b))
    if a == b:
        gate.no("the two collision inputs are identical; this assertion is vacuous")
    elif slug_a == slug_b:
        gate.ok(
            "collision: distinct branches '%s' and '%s' share hostname '%s' (known; devbox_up "
            "must refuse the duplicate)" % (a, b, slug_a)
        )
    else:
        gate.no(
            "collision: '%s' and '%s' no longer collide -- deliberate? then update this test "
            "and the refusal path in devbox_up" % (a, b)
        )

    # --------------------------------------------------------------------- 3. devbox_branch on a DETACHED HEAD --------------------------------------------------------------------- The whole point of symbolic-ref. Build a REAL repo, detach it, and require the slug to fall back to the worktree basename rather than to `head`.
    gate.log_test("devbox_branch: a detached HEAD yields no branch, so no shared 'head' hostname")
    git = harness.require_tool("git", "install git; the detached-HEAD case needs a real repo")
    with harness.temp_dir() as tmp:
        repo = tmp / "0826-2"
        repo.mkdir()
        for argv in (
            [git, "init", "-q", "-b", "main", "."],
            [
                git,
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "x",
            ],
        ):
            done = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True, check=False)
            if done.returncode != 0:
                gate.log_fail("could not build the fixture repository: %s" % done.stderr.strip())

        slug_prelude = "devbox_worktree() { printf '%%s\\n' '%s'; }\n%s" % (
            repo,
            lift(gate, "devbox_branch", "devbox_slug_basename", "devbox_slug", "devbox_slugify"),
        )
        # DEVBOX_SLUG is unset for these four: the escape hatch is asserted separately below, and leaving it set here would answer every one of them.
        clean = {"DEVBOX_SLUG": ""}

        branch = sh(gate, slug_prelude, "devbox_branch", env=clean)
        if branch == "main":
            gate.ok("branch: an attached HEAD reports 'main'")
        else:
            gate.no("branch: an attached HEAD reported '%s', expected 'main'" % branch)

        slug = sh(gate, slug_prelude, "devbox_slug", env=clean)
        if slug == "main":
            gate.ok("slug: on a branch, the hostname is the branch")
        else:
            gate.no("slug: on a branch, expected 'main', got '%s'" % slug)

        subprocess.run(
            [git, "-C", str(repo), "checkout", "-q", "--detach", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )

        branch = sh(gate, slug_prelude, "devbox_branch", env=clean)
        if branch == "":
            gate.ok("branch: a detached HEAD reports EMPTY, not the literal 'HEAD'")
        else:
            gate.no(
                "branch: a detached HEAD reported '%s' -- every detached worktree would share "
                "that hostname" % branch
            )

        slug = sh(gate, slug_prelude, "devbox_slug", env=clean)
        if slug == "0826-2":
            gate.ok(
                "slug: detached falls back to the worktree basename ('0826-2'), which is "
                "unique per checkout"
            )
        else:
            gate.no("slug: detached gave '%s', expected the basename '0826-2'" % slug)

        # CONTROL, by construction: the abbrev-ref form the rest of the repo uses.
        abbrev_prelude = (
            "devbox_worktree() { printf '%%s\\n' '%s'; }\n"
            "devbox_branch_planted() {\n"
            '    git -C "$(devbox_worktree)" rev-parse --abbrev-ref HEAD 2>/dev/null || true\n'
            "}\n%s" % (repo, lift(gate, "devbox_slugify"))
        )
        planted = sh(gate, abbrev_prelude, 'devbox_slugify "$(devbox_branch_planted)"', env=clean)
        if planted == "head":
            gate.ok(
                "CONTROL: --abbrev-ref on a detached HEAD gives the hostname 'head' -- the "
                "detached row would go red"
            )
        else:
            gate.no(
                "CONTROL DID NOT FIRE: --abbrev-ref gave '%s', so the detached assertion "
                "proves nothing" % planted
            )

        # The manual escape hatch still works, and is still sanitised.
        override = sh(gate, slug_prelude, "devbox_slug", env={"DEVBOX_SLUG": "My Box/2"})
        if override == "my-box-2":
            gate.ok(
                "slug: DEVBOX_SLUG overrides the branch and is sanitised ('My Box/2' -> 'my-box-2')"
            )
        else:
            gate.no("slug: DEVBOX_SLUG override gave '%s', expected 'my-box-2'" % override)

        # ----------------------------------------------------------------- 4. Identity and ports must NOT depend on the branch -----------------------------------------------------------------
        # A branch is renamed; a path is not. If either of these ever consults the
        # slug, a rename orphans the container or shuffles its port block.
        gate.log_test("identity and ports stay path-derived")
        for name in ("devbox_container_id", "devbox_base_port"):
            body = body_of(name)
            if not body:
                gate.no(
                    "%s: could not be located in %s -- this text-scan control is vacuous"
                    % (name, paths.relative_to_root(LIB))
                )
                continue
            code_lines = [ln for ln in body.splitlines() if not COMMENT.match(ln)]
            if any(BRANCH_RE.search(ln) for ln in code_lines):
                gate.no(
                    "%s: references the branch/slug; identity and ports must survive a rename"
                    % name
                )
            else:
                gate.ok(
                    "%s: no branch or slug reference (%d lines scanned)"
                    % (name, len(body.splitlines()) - 1)
                )

        # CONTROL, by construction: a body that DOES consult the slug must be caught.
        tainted = (
            "devbox_container_id_planted() {\n"
            "    local d\n"
            '    d="$(devbox_docker)"\n'
            '    $d ps -aq --filter "label=slug=$(devbox_slug)" | head -1\n'
            "}"
        )
        tainted_code = [ln for ln in tainted.splitlines() if not COMMENT.match(ln)]
        if any(BRANCH_RE.search(ln) for ln in tainted_code):
            gate.ok("CONTROL: a container lookup keyed on the slug is detected")
        else:
            gate.no("CONTROL DID NOT FIRE: a slug-keyed container lookup went undetected")

        # ----------------------------------------------------------------- 5. Drift: recorded vs baked vs wanted -----------------------------------------------------------------
        gate.log_test("devbox_slug_drift: a stale hostname is REPORTED, never printed as a URL")
        if sh(gate, prelude, "devbox_slug_drift alpha alpha alpha") == "":
            gate.ok("drift: three agreeing names report nothing")
        else:
            gate.no(
                "drift: agreeing names produced a report: %s"
                % sh(gate, prelude, "devbox_slug_drift alpha alpha alpha")
            )

        out = sh(gate, prelude, "devbox_slug_drift beta alpha alpha")
        if "container serves alpha" in out and "would use beta" in out:
            gate.ok('drift: a renamed branch is reported ("%s")' % out)
        else:
            gate.no('drift: a renamed branch produced "%s"' % out)

        # The recorded key comes from the state file through the REAL accessor, not a hand-rolled parser: this change added a key to a format that already had two readers, and a third would be the bug.
        state = tmp / ".devbox-state"
        state.write_text(
            "# Generated by ./run.sh setup - do not edit\n"
            "worktree=/home/x/console\n"
            "container=rediacc-devbox-7-console\n"
            "base_port=17000\n"
            "slug=stale-name\n",
            encoding="utf-8",
        )
        recorded = sh(gate, prelude, "devbox_state_get slug", env={"DEVBOX_STATE_FILE": str(state)})
        if recorded == "stale-name":
            gate.ok("state: devbox_state_get reads the new slug= key ('%s')" % recorded)
        else:
            gate.no("state: devbox_state_get slug gave '%s', expected 'stale-name'" % recorded)

        out = sh(gate, prelude, "devbox_slug_drift alpha alpha %s" % shell_quote(recorded))
        if "records stale-name" in out:
            gate.ok('drift: a state file disagreeing with the container is reported ("%s")' % out)
        else:
            gate.no('drift: a stale state file produced "%s"' % out)

        # CONTROL, by construction: a drift function that reports nothing.
        silent = "devbox_slug_drift_planted() { return 0; }"
        if sh(gate, silent, "devbox_slug_drift_planted beta alpha stale-name") == "":
            gate.ok(
                "CONTROL: a silent drift function reports nothing -- the two drift rows would "
                "go red"
            )
        else:
            gate.no("CONTROL DID NOT FIRE: the silent variant still produced output")

    # --------------------------------------------------------------------- 6. devbox_route_label: traefik's 404 is not "live" ---------------------------------------------------------------------
    gate.log_test("devbox_route_label: an unmatched Host must never be labelled live")
    label = sh(gate, prelude, "devbox_route_label 404 '' no")
    if "no such router" in label and "live" not in label:
        gate.ok('route: 404 with no router says "%s"' % label)
    else:
        gate.no(
            'route: 404 with no router said "%s" -- the browser would show a 404 for a '
            "'live' row" % label
        )

    label = sh(gate, prelude, "devbox_route_label 404 '' yes")
    if "live" in label:
        gate.ok(
            'route: 404 from a router that DOES exist is the backend\'s own not-found ("%s")'
            % label
        )
    else:
        gate.no('route: 404 behind a real router said "%s"' % label)

    label = sh(gate, prelude, "devbox_route_label 404 ''")
    if "live" not in label:
        gate.ok('route: 404 with no caller claim refuses to claim live ("%s")' % label)
    else:
        gate.no('route: an unqualified 404 claimed "%s"' % label)

    for code, hint, want in (
        ("000", "", "proxy unreachable"),
        ("502", "run account dev", "no backend"),
        ("200", "", "live"),
        ("301", "", "live"),
    ):
        label = sh(gate, prelude, "devbox_route_label %s %s" % (code, shell_quote(hint)))
        if want in label:
            gate.ok('route: HTTP %s -> "%s"' % (code, label))
        else:
            gate.no("route: HTTP %s said \"%s\", expected it to contain '%s'" % (code, label, want))

    # CONTROL, by construction: the pre-change catch-all.
    oldlabel = """devbox_route_label_planted() {
    local code="$1" hint="${2:-}"
    case "$code" in
        000) echo "proxy unreachable" ;;
        502) echo "no backend yet${hint:+ -- $hint}" ;;
        *) echo "live (HTTP $code)" ;;
    esac
}"""
    planted = sh(gate, oldlabel, "devbox_route_label_planted 404 '' no")
    if "live" in planted:
        gate.ok(
            'CONTROL: the old catch-all calls an unmatched Host "%s" -- the 404 row would go '
            "red" % planted
        )
    else:
        gate.no("CONTROL DID NOT FIRE: the old catch-all did not produce a 'live' 404")

    gate.tally_finish("devbox hostname")
    gate.log_pass("devbox hostname: %d control(s) passed" % gate.tally_count)
    gate.log_info(
        "Blind spots: no traefik and no container are started, so the LABELS are never proven "
        "to become routers; 'feat/x' and 'feat-x' still share one hostname by design; "
        "devbox_up's rehost path and devbox_status's probe loop are text-scanned here, not "
        "executed."
    )


def shell_quote(value: str) -> str:
    """A single-quoted bash word. The slug inputs contain slashes and a U+00FC."""
    return "'%s'" % value.replace("'", "'\\''")
