"""`rediacc_ci.quality.commit_identity` against the jq and grep it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-commit-identity.observations.jsonl` drives the whole gate over five distinct trees: one unattributed commit, three from two addresses, an empty list, a list at the 250 page cap, and a null committer with a resolved author. (Those rows were recorded 2026-09-06, before the 250 cap was replaced by a
completeness check against the PR's own commit count; the row named for the cap
records what the pair did THEN, and is history rather than a live assertion.) What a ledger row cannot isolate is the four small readings the verdict rests on, and each of them is a place where jq and Python disagree if nobody looks:

  * `.author.login` on a NULL author is `null`, not an error. That null IS the
    finding, so a port that raised there would turn every offending PR into a
    crash and every crash into "the gate is flaky".
  * `grep -c .` counts LINES, which is only the commit count while gh emits one
    compact object per line. That coupling is what the completeness check reads.
  * `sort -u` on the offender list deduplicates; `sort -rn` on the tally is
    descending by count.
  * the address shape filter is the only thing between a 404 error BODY and two
    entries in a generated cache.

Each is run through the real jq, sort, uniq and grep and compared.
"""

import json
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import commit_identity as ci

TWIN = paths.from_root(".ci", "scripts", "quality", "check-commit-identity.sh")

BAD_JQ = (
    'select(.author == null or .committer == null) | "    \\(.sha[0:7])  \\(.name) <\\(.email)>"'
)
TALLY_JQ = "select(.author == null) | .email"


def _rows() -> str:
    """A payload with every shape the gate distinguishes, one object per line."""
    return "\n".join(
        json.dumps(row, separators=(",", ":"))
        for row in (
            {
                "sha": "a" * 40,
                "author": "mfbayraktar",
                "committer": "mfbayraktar",
                "email": "linked@example.invalid",
                "name": "M F B",
            },
            {
                "sha": "b" * 40,
                "author": None,
                "committer": "mfbayraktar",
                "email": "muhammed@rediacc.com",
                "name": "M F B",
            },
            {
                "sha": "c" * 40,
                "author": None,
                "committer": None,
                "email": "muhammed@rediacc.com",
                "name": "M F B",
            },
            {
                "sha": "d" * 40,
                "author": "mfbayraktar",
                "committer": None,
                "email": "linked@example.invalid",
                "name": "M F B",
            },
            {
                "sha": "e" * 40,
                "author": None,
                "committer": None,
                "email": "other@example.invalid",
                "name": "Someone",
            },
        )
    )


def _jq(program: str, payload: str, *extra: str) -> str:
    proc = subprocess.run(
        ["jq", "-r", program, *extra],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    return proc.stdout.decode("utf-8")


def test_a_null_author_is_null_in_jq_and_not_an_error() -> None:
    """The projection the twin runs must SURVIVE an unattributed commit.

    If `.author.login` raised, the twin would die on exactly the PRs it exists to judge, and the port must have the same tolerance rather than a wider one.
    """
    out = _jq(".author.login", '{"author":null}')
    assert out == "null\n"


def test_the_offender_list_matches_jq_and_sort_u() -> None:
    """`jq ... | sort -u`, run for real, against the port's set-and-sort."""
    payload = _rows()
    proc = subprocess.run(
        ["bash", "-c", 'jq -r "$1" | sort -u', "driver", BAD_JQ],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    want = [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]
    assert ci.unattributed(ci.parse_payload(payload)) == want
    assert len(want) == 4


def test_the_offender_list_deduplicates_like_sort_u() -> None:
    """Two identical commits collapse to one line, which is what `-u` buys."""
    one = json.dumps(
        {"sha": "b" * 40, "author": None, "committer": None, "email": "x@y.invalid", "name": "N"},
        separators=(",", ":"),
    )
    payload = one + "\n" + one
    proc = subprocess.run(
        ["bash", "-c", 'jq -r "$1" | sort -u', "driver", BAD_JQ],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    want = [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]
    assert ci.unattributed(ci.parse_payload(payload)) == want == ["    bbbbbbb  N <x@y.invalid>"]


def test_the_address_tally_matches_sort_uniq_c_sort_rn() -> None:
    """`jq ... | sort | uniq -c | sort -rn`, and it reads `.author` ONLY."""
    payload = _rows()
    proc = subprocess.run(
        ["bash", "-c", 'jq -r "$1" | sort | uniq -c | sort -rn', "driver", TALLY_JQ],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    want = [
        (int(line.split()[0]), line.split()[1])
        for line in proc.stdout.decode("utf-8").split("\n")
        if line.strip() != ""
    ]
    assert ci.email_tally(ci.parse_payload(payload)) == want
    # The null-committer commit has a resolved author, so its address is NOT in the tally even though the commit IS in the offender list above.
    assert all(email != "linked@example.invalid" for _n, email in want)


def test_count_lines_matches_grep_c_dot() -> None:
    """`grep -c .` counts non-empty lines, which is the completeness oracle."""
    for payload in (_rows(), "", "a\n\nb\n", "one"):
        proc = subprocess.run(
            ["bash", "-c", "grep -c . || true"],
            input=payload.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        want = int(proc.stdout.decode("utf-8").strip() or "0")
        assert ci.count_lines(payload) == want, repr(payload[:20])


def test_the_shape_filter_matches_the_twins_grep() -> None:
    """The address regex, run as the twin's `grep -E`, over the 404 body it once ate."""
    body = '{"message":"Not\nFound","documentation_url":"https://docs.github.com"}'
    for text in (body, "a@example.invalid\nb.c+d@sub.example.co", "mfbayraktar", "a@b.c"):
        proc = subprocess.run(
            [
                "bash",
                "-c",
                "grep -E '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$' || true",
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        want = [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]
        assert ci.valid_emails(text) == want, text[:30]


def test_the_endpoints_and_the_projection_still_match_the_twin() -> None:
    """The three strings that decide WHAT this gate reads, checked against the twin.

    Read from the twin's source rather than remembered, because a change to any of them silently re-scopes the gate. The compare endpoint is here by name:
    reverting it to `pulls/{n}/commits` would reintroduce the 250 cap that made
    this gate unable to report on a 254-commit PR, and that regression would otherwise be invisible to every other test in this file.
    """
    body = TWIN.read_text(encoding="utf-8")
    assert 'api "repos/${repo}/compare/${base}...${head}?per_page=100" --paginate' in body
    assert "pulls/${pr}/commits" not in body
    assert "{sha: .sha, author: .author.login, committer: .committer.login," in body
    assert ci.PROJECTION.startswith(".commits[] | {sha: .sha,")


def test_the_metadata_line_is_read_the_way_bash_reads_it() -> None:
    """`read -r base head total` against `parse_meta`, run through real bash.

    The interesting case is a FOURTH field: `read` hands the whole remainder to the last variable, so `1 2` is not the number 1. A port that split on whitespace and took `fields[2]` would accept it and judge a PR against the wrong total.
    """
    for line in ("b h 254", "b h many", "b h", "b h 1 2", "", "   "):
        proc = subprocess.run(
            [
                "bash",
                "-c",
                'read -r base head total <<<"$1"; printf "%s|%s|%s" "$base" "$head" "$total"',
                "driver",
                line,
            ],
            capture_output=True,
            check=True,
        )
        base, head, total = proc.stdout.decode("utf-8").split("|")
        bash_ok = base != "" and head != "" and total.isdigit()
        assert (ci.parse_meta(line) is not None) == bash_ok, line
        if bash_ok:
            assert ci.parse_meta(line) == (base, head, int(total))


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, with no token and no network."""
    assert ci.selftest() == 0
