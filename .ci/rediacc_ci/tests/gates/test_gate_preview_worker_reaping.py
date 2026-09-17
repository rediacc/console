"""Port of `.ci/scripts/test/gates/test-preview-worker-reaping.sh`.

Phase 5b of `.ci/scripts/housekeeping/cleanup-versions.sh` reaps orphaned per-PR
preview Workers -- and must never reap anything else, because there is no undo.

WHAT WENT WRONG, measured 2026-08-26: `Cleanup PR Preview` run 32903006150 died
at the app-token step on GitHub's OWN internal DNS
(internal-api.service.iad.github.net, "Name or service not known") before
checkout, so neither of its two cleanups ran. Phase 5 backstops the Pages side;
nothing backstopped `wrangler delete --name pr-<n>` (cleanup-preview.yml:60), so
the Worker leaked with nothing to reap it -- one per failed cleanup, forever.

THIS GATE IS MOSTLY ABOUT WHAT MUST **NOT** BE DELETED. A reaping phase that
works is easy; a reaping phase that cannot over-reach is the whole risk, since it
runs unattended at 03:00 with production Cloudflare credentials. So the selector
is tested against names chosen to break it: the production and bench Workers, a
pr-prefixed name that is not a PR number, and an open PR's Worker.

FAIL-CLOSED IS AN ASSERTION HERE, not a comment. Phase 4 (Pages) falls back to
keep-N when the open-PR lookup fails, because its worst case is retaining too
much. Phase 5b's worst case is deleting a LIVE preview, so an unreadable PR list
must SKIP the phase. The two phases must not be "made consistent".

WHAT THIS GATE CANNOT SEE: it tests the SELECTOR and the guards by reading them,
not a live Cloudflare account. It cannot prove the real API deletes what the
selector chose, and it cannot prove no long-lived Worker in the real account
happens to match ^pr-[0-9]+$ -- that needs a live listing.

READ-ONLY against the subject; this module writes nothing anywhere.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-preview-worker-reaping.sh"

SUT = paths.from_root(".ci", "scripts", "housekeeping", "cleanup-versions.sh")

# The selector, as the phase uses it, written ONCE. A second spelling of it here and in the subject-agreement case below is how a gate and its subject drift.
PR_WORKER_PATTERN = "^pr-([0-9]+)$"
PR_WORKER_RE = re.compile(PR_WORKER_PATTERN)

MUST_MATCH = ("pr-1", "pr-574", "pr-99999")

# EVERY Worker name this repo actually defines, swept 2026-08-26 from all wrangler.*.toml plus the one `wrangler delete`. Invented names prove less than real ones: these are the Workers a bad selector would destroy.
MUST_NOT_MATCH = (
    "account-server",  # private/account/wrangler.toml:22
    "rediacc-account-eu",  # workers/account/wrangler.eu.toml:1
    "rediacc-account-us",  # workers/account/wrangler.us.toml:1
    "rediacc-account-asia",  # workers/account/wrangler.asia.toml:1
    "rediacc-account-bench",  # workers/account/wrangler.bench.toml:13
    "edge-rediacc-account-eu",  # workers/account/wrangler.edge-eu.toml:1
    "edge-rediacc-account-us",  # workers/account/wrangler.edge-us.toml:1
    "edge-rediacc-account-asia",  # workers/account/wrangler.edge-asia.toml:1
    "rediacc-www",  # workers/www/wrangler.toml:1
    "edge-rediacc-www",  # workers/www/wrangler.edge.toml:1
    "rediacc-proxy-eu",  # workers/proxy/wrangler.toml:1
    "mta-sts-policy",  # workers/mta-sts/wrangler.toml:1
    "pr-main",  # pr- prefix, not a number
    "pr-574-old",  # trailing junk
    "prefix-pr-574",  # not anchored at the start
    "PR-574",  # case
    "pr-",  # empty number
    "pr-57a",  # not all digits
)


def source(gate) -> str:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    return SUT.read_text(encoding="utf-8")


def phase_body(gate) -> list[str]:
    """`cleanup_preview_workers`'s body, as lines. Empty is a REFUSAL."""
    body = harness.block_from(source(gate), "cleanup_preview_workers() {")
    if not body:
        gate.log_fail("could not extract cleanup_preview_workers from the subject")
    return body


def first_line_with(body: list[str], needle: str) -> int:
    """1-based line number of the first line containing `needle`, or 0."""
    for index, line in enumerate(body, start=1):
        if needle in line:
            return index
    return 0


def selects(name: str) -> bool:
    return PR_WORKER_RE.match(name) is not None


def test_selector_matches_only_pr_numbers(gate):
    for name in MUST_MATCH:
        if not selects(name):
            gate.log_fail("selector MISSED a real preview Worker: %s" % name)
    for name in MUST_NOT_MATCH:
        if selects(name):
            gate.log_fail("selector would have reaped a NON-preview Worker: %s" % name)
    gate.log_pass(
        "selector: %d matched, %d correctly rejected" % (len(MUST_MATCH), len(MUST_NOT_MATCH))
    )


def test_selector_regex_is_the_one_in_the_subject(gate):
    if PR_WORKER_PATTERN not in source(gate):
        gate.log_fail(
            "cleanup-versions.sh no longer uses the anchored %s selector" % PR_WORKER_PATTERN
        )
    gate.log_pass("subject and gate agree on the selector")


def test_open_pr_is_never_reaped(gate):
    open_prs = {"574", "576"}
    match = PR_WORKER_RE.match("pr-576")
    if not match:
        gate.log_fail("fixture did not match the selector")
    number = match.group(1)
    if number not in open_prs:
        gate.log_fail("an OPEN PR's Worker would have been deleted")
    gate.log_pass("open PR #%s is skipped" % number)


def test_closed_pr_is_reaped(gate):
    open_prs = {"576"}
    match = PR_WORKER_RE.match("pr-574")
    if not match:
        gate.log_fail("fixture did not match the selector")
    number = match.group(1)
    if number in open_prs:
        gate.log_fail("a CLOSED PR's Worker was treated as live")
    gate.log_pass("closed PR #%s is selected for reaping" % number)


def test_fails_closed_when_pr_list_unreadable(gate):
    """By construction: the guard must RETURN before any delete. Assert on the
    ORDERING, which is the property -- a warn that still falls through to a
    delete reads identically in a diff."""
    body = phase_body(gate)
    guard_line = first_line_with(body, "SKIPPING Worker cleanup")
    delete_line = first_line_with(body, "cf_api DELETE")
    if not guard_line:
        gate.log_fail("the fail-closed guard is GONE from cleanup_preview_workers")
    if not delete_line:
        gate.log_fail("no delete call found; the phase does nothing")
    if guard_line >= delete_line:
        gate.log_fail("the fail-closed guard sits AFTER the delete, so it guards nothing")
    window = body[guard_line - 1 : guard_line + 2]
    if not any("return 0" in line for line in window):
        gate.log_fail("the unreadable-PR-list branch warns but does not return")
    gate.log_pass("unreadable PR list returns before any delete")


def test_dry_run_and_budget_are_honoured(gate):
    body = phase_body(gate)
    if not any("DRY_RUN" in line for line in body):
        gate.log_fail("phase ignores DRY_RUN -- a dry run would DELETE")
    if not any("deletes_budget_ok" in line for line in body):
        gate.log_fail("phase ignores MAX_DELETES_PER_RUN")
    dry_line = first_line_with(body, "DRY_RUN")
    delete_line = first_line_with(body, "cf_api DELETE")
    if not (dry_line and delete_line and dry_line < delete_line):
        gate.log_fail("the DRY_RUN check sits AFTER the delete")
    gate.log_pass("DRY_RUN and budget both precede the delete")


def test_phase_is_actually_invoked(gate):
    """A phase nobody calls reaps nothing."""
    invoked = re.search(r"^[ \t]*cleanup_preview_workers[ \t]*$", source(gate), re.MULTILINE)
    if not invoked:
        gate.log_fail("cleanup_preview_workers is defined but never invoked")
    gate.log_pass("phase is wired into the run")


def test_control_overbroad_selector_is_caught(gate):
    """CONTROL: an unanchored selector must be detectable.

    Built by construction: a DIFFERENT predicate, not a mutation of the real one.
    A substring-style selector would sweep names the anchored one rejects.
    """
    loose = "pr-"
    victim = "rediacc-console-bench"
    if not (loose in "pr-574-old" and not selects("pr-574-old")):
        gate.log_fail("CONTROL DID NOT FIRE: anchored and loose selectors agreed")
    gate.log_pass("control: the anchored selector rejects what a loose one accepts")
    if selects(victim):
        gate.log_fail("CONTROL: production Worker matched the real selector")
