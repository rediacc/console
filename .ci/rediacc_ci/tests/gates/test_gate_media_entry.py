"""Port of `.ci/scripts/test/gates/test-media-entry.sh`.

Tests for `.ci/media/media-entry.sh` -- the one entry point for the media pipeline.

THE ASSERTION THIS FILE EXISTS FOR IS THE DELEGATION. Before the cutover run.sh
carried its own copy of the media surface, and the twin compared the two dispatch
trees as SETS in both directions. That comparison is spent: phase 2 deleted
run.sh's arms, so one of the two sets is empty by construction and comparing them
would agree with itself forever. What replaces it is the thing the mirror was a
proxy for: a sandbox repo, a REAL `./run.sh` invocation, a marker planted inside
the module function's own body, once per routed verb.

Everything runs with docker, node, npm, nvcc, aws and ssh absent -- the chain needs
`uname` and `dirname` and nothing else.

WHERE THIS REIMPLEMENTS grep, sed, sort AND awk, AND WHY THE ANSWERS AGREE.

  `dispatched_media_functions` is
  `grep -oE '(provision_(start|stop|status)|www_tutorials_[a-z_]+|www_all)' | sort -u`.
  `-o` prints EVERY match on a line, not one per line, so the Python form is
  `re.findall` over the whole text rather than a per-line search; `sort -u` over a
  set of ASCII identifiers sharing an alphabet is `sorted(set(...))` under any
  collation that cannot reorder them. The twin compares the result to the EMPTY
  STRING, so the port compares to the empty LIST, which is the same claim without a
  join in the middle.

  `sed -n '/^main() {/,$p' run.sh` is "from the first line equal to `main() {`
  through end of file". Rendered here as an index lookup for that exact line plus a
  slice, which is the same range because the address is a whole-line anchor at both
  ends (`^main() {` and `$`) and `sed` prints inclusively from the first match.

  `fidelity_extract` is already ported in `media_verify.py`, awk and all, and its
  agreement with the awk original is argued there.

  `grep -oE 'source "\\$MEDIA_DIR/[a-z0-9-]+\\.sh"' | sed 's|.*/||; s|"$||'` becomes
  one regex with a capture group for the basename. The sed pair only strips what the
  group already excludes, so the capture is the same string with one fewer pass.

WHY THE ROUTE TABLE IS DRIVEN ROW BY ROW AND FLOORED AT 16. A table that lost rows
would still pass every row it kept, which is the composition failure a count of
green cases cannot see. The floor is the twin's, unchanged.

NO `xdist_group`. The sandbox repo is built under pytest's own `tmp_path` and every
write lands inside it; the only process-wide state touched is `os.environ["PATH"]`,
which `harness.fake_bin` restores in a `finally`. The one case that sources the REAL
`media-entry.sh` does so in a FRESH `bash -c` with every routed verb replaced by a
stub, so nothing it can reach runs in this process or in the checkout.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness, media_verify, media_verify_ext

BASH_TWIN = ".ci/scripts/test/gates/test-media-entry.sh"

ROOT = paths.repo_root()
ENTRY = ROOT / ".ci" / "media" / "media-entry.sh"

# The twin's grep -oE, verbatim.
DISPATCHED_RE = re.compile(r"provision_(?:start|stop|status)|www_tutorials_[a-z_]+|www_all")
SOURCED_RE = re.compile(r'source "\$MEDIA_DIR/([a-z0-9-]+\.sh)"')

TUTORIALS_USAGE = (
    "Usage: ./run.sh www tutorials [record|extract|scaffold-locales|generate|media|"
    "watch|video|validate|all]"
)

# script | argv | module | function | expected "$*"
ROUTES = (
    ("run.sh", "provision start --basic", "bridge.sh", "provision_start", "--basic"),
    ("run.sh", "provision stop", "bridge.sh", "provision_stop", ""),
    ("run.sh", "provision status", "bridge.sh", "provision_status", ""),
    (
        "run.sh",
        "www tutorials record --force installation",
        "tutorials.sh",
        "www_tutorials_record",
        "--force installation",
    ),
    ("run.sh", "www tutorials extract", "tutorials.sh", "www_tutorials_extract", ""),
    (
        "run.sh",
        "www tutorials scaffold-locales",
        "tutorials.sh",
        "www_tutorials_scaffold_locales",
        "",
    ),
    (
        "run.sh",
        "www tutorials generate --lang de",
        "tutorials.sh",
        "www_tutorials_generate",
        "--lang de",
    ),
    (
        "run.sh",
        "www tutorials video --jobs 2",
        "tutorials.sh",
        "www_tutorials_video",
        "--jobs 2",
    ),
    (
        "run.sh",
        "www tutorials media --langs en,de",
        "tutorials.sh",
        "www_tutorials_media",
        "--langs en,de",
    ),
    ("run.sh", "www tutorials watch --once", "tutorials.sh", "www_tutorials_watch", "--once"),
    ("run.sh", "www tutorials validate", "tutorials.sh", "www_tutorials_validate", ""),
    (
        "run.sh",
        "www tutorials all installation",
        "tutorials.sh",
        "www_tutorials_all",
        "installation",
    ),
    ("run.sh", "www all installation", "tutorials.sh", "www_all", "installation"),
    ("media.sh", "run video_pipeline", "teaser.sh", "growth_run", "video_pipeline"),
    (
        "media.sh",
        "teaser safe-os-testing ru",
        "teaser.sh",
        "growth_teaser",
        "safe-os-testing ru",
    ),
    ("media.sh", "luma /tmp/nothing.mp4", "teaser.sh", "growth_luma", "/tmp/nothing.mp4"),
)

# STUBS replaces every verb the tree routes to. Sourcing the entry point defines
# them from the real modules first; these override them, so what is under test is
# the routing and nothing it routes to ever runs.
STUBS = """
provision_start() { echo "provision_start: $*"; }
provision_stop() { echo "provision_stop"; }
provision_status() { echo "provision_status"; }
www_tutorials_record() { echo "record: $*"; }
www_tutorials_extract() { echo "extract"; }
www_tutorials_scaffold_locales() { echo "scaffold"; }
www_tutorials_generate() { echo "generate: $*"; }
www_tutorials_video() { echo "video: $*"; }
www_tutorials_media() { echo "media: $*"; }
www_tutorials_watch() { echo "watch: $*"; }
www_tutorials_validate() { echo "validate"; }
www_tutorials_all() { echo "all: $*"; }
www_all() { echo "www_all: $*"; }
growth_run() { echo "growth_run: $*"; }
growth_teaser() { echo "growth_teaser: $*"; }
growth_luma() { echo "growth_luma: $*"; }
"""


def dispatched_media_functions(text: str) -> list[str]:
    """`grep -oE ... | sort -u` over a DISPATCH REGION, never a whole file.

    Fed the dispatch region because run.sh both defines and calls these names, and
    a definition is not a route.
    """
    return sorted(set(DISPATCHED_RE.findall(text)))


def run_dispatch_region(source: str) -> str:
    """`sed -n '/^main() {/,$p'`: from the `main() {` line to end of file."""
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if line == "main() {":
            return "\n".join(lines[index:])
    return ""


def drive_entry(argv: str) -> harness.RunResult:
    """Source the REAL entry point, override every verb, then dispatch.

    No fixture root: the entry point resolves ROOT_DIR from its own location, which
    is the real repo, and every verb it would reach is replaced above. Nothing runs.
    """
    return harness.run(
        [
            media_verify._BASH,
            "-c",
            "source '%s'\n%s\nmedia_entry_main %s" % (ENTRY, STUBS, argv),
        ]
    )


def test_the_entry_point_and_its_modules_all_exist(gate):
    if not (ENTRY.is_file() and ENTRY.stat().st_mode & 0o111):
        gate.log_fail("media-entry.sh is not executable: %s" % ENTRY)
    sourced = SOURCED_RE.findall(ENTRY.read_text(encoding="utf-8"))
    for name in sourced:
        if not (ROOT / ".ci" / "media" / name).is_file():
            gate.log_fail("media-entry.sh sources a module that does not exist: %s" % name)
    # Anti-vacuity: an extraction that stopped matching would report every module
    # present.
    if len(sourced) < 7:
        gate.log_fail(
            "media-entry.sh sources only %d module(s); the extraction has collapsed or "
            "the split has" % len(sourced)
        )
    gate.log_pass(
        "media-entry.sh is executable and every one of its %d sourced modules exists" % len(sourced)
    )


def test_the_whole_media_surface_is_delegated_and_this_file_owns_it(gate):
    run_region = run_dispatch_region((ROOT / "run.sh").read_text(encoding="utf-8"))
    try:
        entry_region = media_verify.fidelity_extract(ENTRY, "media_entry_main")
    except media_verify.ExtractionError as error:
        gate.log_fail("media_entry_main() could not be extracted from %s: %s" % (ENTRY, error))
        raise
    entry_set = dispatched_media_functions(entry_region)

    # ANTI-VACUITY FIRST, because every claim below is about a SET BEING EMPTY and
    # an extraction that matched nothing satisfies all of them at once. Pin the floor
    # on the side that must be FULL before asserting anything about the side that
    # must be empty.
    if len(entry_set) < 10:
        gate.log_fail(
            "only %d media function(s) found in media_entry_main; the extraction is "
            "broken, so nothing below proves anything" % len(entry_set)
        )

    gate.assert_eq(
        dispatched_media_functions(run_region),
        [],
        "run.sh's dispatch tree still calls these media functions, which it no longer defines",
    )

    run_source = (ROOT / "run.sh").read_text(encoding="utf-8")
    for arm in ("provision", "www"):
        needle = '        %s) exec "$ROOT_DIR/.ci/media/media-entry.sh" "$@" ;;' % arm
        if needle not in run_source:
            gate.log_fail("run.sh's '%s' arm does not exec .ci/media/media-entry.sh" % arm)
    if 'exec "$ROOT/.ci/media/media-entry.sh" growth "$@"' not in (ROOT / "media.sh").read_text(
        encoding="utf-8"
    ):
        gate.log_fail("media.sh does not exec .ci/media/media-entry.sh's growth arm")

    modules = [p for p in sorted((ROOT / ".ci" / "media").glob("*.sh")) if p != ENTRY]
    for name in entry_set:
        if not any(media_verify.media_defines(owner, name) for owner in modules):
            gate.log_fail(
                "media_entry_main routes %s(), which no module in .ci/media defines" % name
            )
    gate.log_pass(
        "media_entry_main routes %d media functions, each owned by a module beside it; "
        "run.sh routes none and execs here for both provision and www, and so does "
        "media.sh" % len(entry_set)
    )


def test_the_delegation_assertion_can_fail(gate):
    # CONTROL, on both halves. Put a media call back into a COPY of run.sh's
    # dispatch tree and the "routes none" check must see it; take the exec out and
    # the arm check must.
    source = (ROOT / "run.sh").read_text(encoding="utf-8")
    lines = source.splitlines()
    anchor = '        www) exec "$ROOT_DIR/.ci/media/media-entry.sh" "$@" ;;'
    if lines.count(anchor) != 1:
        gate.log_fail(
            "run.sh's www arm is not the single line this control rewrites, so the "
            "control would pass for the wrong reason"
        )
    mutant = "\n".join(
        '        www) www_tutorials_extract "$@" ;;' if line == anchor else line for line in lines
    )
    gate.assert_eq(
        dispatched_media_functions(run_dispatch_region(mutant)),
        ["www_tutorials_extract"],
        "a media call put back into run.sh must show up in the routed set",
    )
    if anchor in mutant:
        gate.log_fail(
            "the mutant still execs media-entry.sh from its www arm, so this control tested nothing"
        )
    gate.log_pass(
        "the delegation assertion fires when a media call reappears in run.sh and when "
        "the exec is removed"
    )


def test_the_usage_line_lives_in_exactly_one_place(gate):
    # The guidance still names ./run.sh, because that is still how a person reaches
    # this surface. What changed is that there is now ONE copy of the string.
    if TUTORIALS_USAGE not in ENTRY.read_text(encoding="utf-8"):
        gate.log_fail("media-entry.sh no longer carries the tutorials usage line")
    media_verify_ext.assert_absent_from_origins(
        gate,
        re.escape(TUTORIALS_USAGE),
        ROOT,
        "an origin carries a second copy of the tutorials usage line, which will fork "
        "from the one that prints",
    )
    gate.log_pass(
        "the tutorials usage line still names ./run.sh, and exists only in media-entry.sh"
    )


def test_every_routed_verb_reaches_the_module_that_owns_it(gate, tmp_path):
    repo = media_verify_ext.media_chain_sandbox(tmp_path)
    driven = 0
    for script, argv, module, function, expected in ROUTES:
        try:
            media_verify_ext.probe(repo, module, function)
        except media_verify_ext.ChainError as error:
            gate.log_fail("could not plant a probe for %s() in %s: %s" % (function, module, error))
        with harness.fake_bin("+uname +dirname"):
            result = media_verify_ext.run(repo, script, *argv.split(" "))
        if result.rc != 0:
            gate.log_fail(
                "./%s %s failed in the sandbox: %s" % (script, argv, result.combined.strip())
            )
        gate.assert_eq(
            result.combined.strip(),
            "MEDIA_CHAIN_REACHED:%s:%s" % (function, expected),
            "./%s %s must arrive inside %s() with its arguments intact" % (script, argv, function),
        )
        driven += 1
    # FLOOR, because a table that lost rows would still pass every row it kept.
    if driven < 16:
        gate.log_fail(
            "only %d route(s) were driven; the table has lost rows and its green covers "
            "less than it claims" % driven
        )
    gate.log_pass(
        "all %d routed verbs cross run.sh's (or media.sh's) exec and arrive inside the "
        "module function that owns them" % driven
    )


def test_the_chain_probe_can_fail(gate, tmp_path):
    # CONTROL FOR THE SIXTEEN ROWS ABOVE. Plant the marker exactly as they do, then
    # take run.sh's exec out. If the marker still appeared, every green above would
    # be measuring something other than the delegation.
    repo = media_verify_ext.media_chain_sandbox(tmp_path)
    media_verify_ext.probe(repo, "tutorials.sh", "www_tutorials_extract")
    media_verify_ext.mutate(repo, "run.sh", r"^        www\) exec .*", "        www) exit 9 ;;")
    with harness.fake_bin("+uname +dirname"):
        result = media_verify_ext.run(repo, "run.sh", "www", "tutorials", "extract")
    gate.assert_exit_code(
        9, result.rc, "the mutated run.sh must reach its own replacement arm, not the module"
    )
    gate.assert_not_contains(
        result.combined,
        "MEDIA_CHAIN_REACHED",
        "with the exec gone, no marker may be reported",
    )
    gate.log_pass("the chain probe goes quiet the moment run.sh stops exec-ing media-entry.sh")


def test_the_tree_routes_and_refuses(gate):
    for argv, expected in (
        ("provision start --basic", "provision_start: --basic"),
        ("www tutorials record --force installation", "record: --force installation"),
        ("www tutorials extract", "extract"),
        ("www tutorials media --langs en,de", "media: --langs en,de"),
        ("www all installation", "www_all: installation"),
        ("growth teaser safe-os-testing ru", "growth_teaser: safe-os-testing ru"),
    ):
        result = drive_entry(argv)
        if result.rc != 0:
            gate.log_fail("%s failed: %s" % (argv, result.combined.strip()))
        gate.assert_eq(result.combined.strip(), expected, "%s forwards its arguments" % argv)

    unknown = drive_entry("nosuchsurface")
    gate.assert_exit_code(1, unknown.rc, "an unknown top-level verb must exit 1")
    gate.assert_contains(
        unknown.combined, "provision", "the usage names the surfaces it does route"
    )

    unknown = drive_entry("www tutorials nosuchverb")
    gate.assert_exit_code(1, unknown.rc, "an unknown tutorials verb must exit 1")
    gate.assert_contains(
        unknown.combined,
        "Unknown tutorials command: nosuchverb",
        "names the verb it refused",
    )

    unknown = drive_entry("growth nosuchverb")
    gate.assert_exit_code(1, unknown.rc, "an unknown growth verb must exit 1")
    gate.assert_contains(
        unknown.combined,
        "cwd = private/growth",
        "falls back to media.sh's own usage text",
    )
    gate.log_pass(
        "every verb reaches its own function with its arguments intact, and unknown "
        "verbs are refused"
    )
