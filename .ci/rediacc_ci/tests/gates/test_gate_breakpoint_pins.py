"""Port of `.ci/scripts/test/gates/test-breakpoint-pins.sh`, retired in W7 P5.

Static analysis of breakpoint's third-party tool pins. Downloads NOTHING: a gate that hits the network to prove a checksum is a gate that goes red on somebody else's outage, and it would then get skipped.

WHAT WENT WRONG BEFORE, which is what each case below re-checks:

  `.ci/scripts/tunnel/start-cloudflare.sh` (deleted) curled
  `.../releases/latest/download/cloudflared-linux-amd64.deb` straight into
  `sudo dpkg -i`. Three separate problems in one line: `latest` means the artifact you
  reviewed is not the artifact you get, there was no checksum at all, and dpkg runs
  maintainer scripts as ROOT -- in a job that also held release secrets.

  `.github/actions/tmate/scripts/install-tmate.sh` (deleted) ran `apt-get install -y
  tmate` FIRST and only fell back to its pinned GitHub release if apt failed. On every
  Ubuntu runner apt succeeded, so the pinned path was dead code and the binary that
  actually ran was whatever the distro happened to ship. A pin bypassed on the common
  path is not a pin, and nothing failed to say so.

THE VERIFY-BEFORE-USE CASE IS THE LOAD-BEARING ONE. `sha256sum -c` after the chmod/extract it is supposed to guard proves nothing at all, and the two orderings look identical in review. Comparing LINE NUMBERS is a mechanical check that survives someone "simplifying" the installer later.

WHY THE DRIVER PORTED THIS AND NOT AN AGENT. `agent/8f55d4f0/W7P3-batch5-brief.md` records six `test-breakpoint-*.sh` subjects as unportable by any agent under the standard brief and NOT on merit, because plant-verifying one means temporarily writing under `.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching. The brief's two ways out are to hand one batch owner
that path explicitly or to exclude them in the derivation with the reason recorded, and it adds "Do not silently drop them a fourth time." This is the first option: `.ci/breakpoint` is the driver's path.

NO `xdist_group`. Every case only READS tracked files; nothing is written, no port is bound, no module global is mutated.
"""

import re

from rediacc_ci import paths

BP = paths.from_root(".ci", "breakpoint")
VERSIONS = BP / "versions.sh"
INSTALL_CF = BP / "scripts" / "install-cloudflared.sh"
INSTALL_TMATE = BP / "scripts" / "install-tmate.sh"

SHA_DECL = re.compile(r"^readonly (BREAKPOINT_[A-Z_]*_SHA256_[A-Z0-9]+)=(.*)$")
PIN_DECL = re.compile(r"^readonly BREAKPOINT_[A-Z_]*(?:VERSION|SHA256_[A-Z0-9]+)=")
BARE_PIN = re.compile(r"^BREAKPOINT_[A-Z_]*(?:VERSION|SHA256_[A-Z0-9]+)=")
SHA_NAME = re.compile(r"BREAKPOINT_[A-Z_]*_SHA256_[A-Z0-9]+")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
COMMENT = re.compile(r"^[ \t]*#")

# The word-boundary form is DELIBERATE: a naive `| sh` also matches `| sha256sum`.
PIPE_TO_INTERPRETER = re.compile(r"\|[ \t]*(?:bash|sh|sudo)(?:[ \t]|$)")
APT = re.compile(r"apt-get|apt install|apt-cache|add-apt-repository")
CHMOD_X = re.compile(r"^[ \t]*chmod \+x")
TAR = re.compile(r"(?:^|[^a-z])tar -")


def lines_of(path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def code_of(path) -> str:
    """The file with WHOLE-LINE comments stripped.

    Every "what not to do" example in these installers lives in a comment, so a scan for banned constructs has to look at code only or it fails on its own documentation.
    """
    return "\n".join(line for line in lines_of(path) if not COMMENT.match(line))


def last_line_matching(path, pattern) -> int | None:
    """Line number (1-based) of the LAST match, or None.

    LAST, not first: `install-cloudflared.sh` verifies twice -- once to decide an existing binary is intact, once on the fresh download. Taking the first match would
    let someone add a decorative early check and move the real one after the chmod
    without this gate noticing.
    """
    found = None
    for number, line in enumerate(lines_of(path), start=1):
        if pattern.search(line):
            found = number
    return found


def first_line_matching(path, pattern) -> int | None:
    for number, line in enumerate(lines_of(path), start=1):
        if pattern.search(line):
            return number
    return None


def sha_declarations() -> list[tuple[str, str]]:
    out = []
    for line in lines_of(VERSIONS):
        m = SHA_DECL.match(line)
        if m:
            out.append((m.group(1), m.group(2).replace('"', "")))
    return out


def test_the_subjects_are_present(gate):
    """The twin refuses at source time if any of the three is missing. Kept as a case rather than an import-time check so an absent subject is a NAMED failure instead of a collection error nobody can read."""
    for path in (VERSIONS, INSTALL_CF, INSTALL_TMATE):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(path))
    gate.log_pass("all three subjects are present")


def test_every_sha_constant_is_a_real_sha256(gate):
    declarations = sha_declarations()
    for name, value in declarations:
        if not HEX64.match(value):
            gate.log_fail(
                "%s is not 64 lowercase hex chars: %r (%d chars)" % (name, value, len(value))
            )
    # A pinned artifact per (tool, arch): cloudflared x64/arm64 + tmate x64/arm64. Fewer means an arch is silently unpinned, and the installer for it would fail on an empty EXPECTED_SHA rather than on a mismatch.
    gate.assert_eq(len(declarations), 4, "expected one sha256 per (tool, arch) pair")
    gate.log_pass(
        "all %d BREAKPOINT_*_SHA256_* constants are 64 lowercase hex chars" % len(declarations)
    )


def test_every_sha_is_distinct(gate):
    """A copy-paste that gives two arches the same hash makes one of them permanently unverifiable -- it fails closed, but with a "CHECKSUM MISMATCH" that reads like a supply-chain attack."""
    values = [value for _, value in sha_declarations()]
    gate.assert_eq(len(set(values)), len(values), "every pinned artifact must have its own hash")
    gate.log_pass(
        "all %d pinned checksums are distinct (no copy-paste across arches)" % len(values)
    )


def test_constants_are_readonly(gate):
    """A pin a later `source` can quietly reassign is not a pin. `readonly` makes the reassignment an error instead of a shrug."""
    text = lines_of(VERSIONS)
    declared = sum(1 for line in text if PIN_DECL.match(line))
    if declared < 6:
        gate.log_fail("only %d pinned constants found; versions.sh looks wrong" % declared)
    bare = [line for line in text if BARE_PIN.match(line)]
    gate.assert_eq("\n".join(bare), "", "every version and sha constant must be declared readonly")
    gate.log_pass("all %d version/sha constants are readonly (none reassignable)" % declared)


def test_verify_before_use(gate):
    sha_check = re.compile(r"sha256sum -c")

    # cloudflared: the checksum must be verified BEFORE the file is made executable. Afterwards would mean an unverified binary is already runnable in the state dir.
    verify = last_line_matching(INSTALL_CF, sha_check)
    use = first_line_matching(INSTALL_CF, CHMOD_X)
    if verify is None:
        gate.log_fail("install-cloudflared.sh has NO sha256sum -c at all")
    if use is None:
        gate.log_fail("install-cloudflared.sh has no chmod +x to guard")
    if verify >= use:
        gate.log_fail(
            "install-cloudflared.sh verifies at line %d but chmods at line %d "
            "(verify must come FIRST)" % (verify, use)
        )
    gate.log_pass("install-cloudflared.sh verifies (L%d) before chmod +x (L%d)" % (verify, use))

    # tmate: before EXTRACT, which is the stronger requirement -- tar on an attacker-controlled archive is code execution's near neighbour, and it happens before any chmod would.
    verify = last_line_matching(INSTALL_TMATE, sha_check)
    use = first_line_matching(INSTALL_TMATE, TAR)
    if verify is None:
        gate.log_fail("install-tmate.sh has NO sha256sum -c at all")
    if use is None:
        gate.log_fail("install-tmate.sh has no tar extraction to guard")
    if verify >= use:
        gate.log_fail(
            "install-tmate.sh verifies at line %d but extracts at line %d "
            "(verify must come FIRST)" % (verify, use)
        )
    gate.log_pass("install-tmate.sh verifies (L%d) before tar extraction (L%d)" % (verify, use))


def test_no_pipe_to_interpreter_or_sudo(gate):
    for path in (INSTALL_CF, INSTALL_TMATE):
        name = path.name
        code = code_of(path)
        # `curl | bash` is the shape the deleted installer had in spirit: bytes go from the network into an interpreter with nothing in between where a checksum could be.
        hits = [line for line in code.splitlines() if PIPE_TO_INTERPRETER.search(line)]
        if hits:
            gate.log_fail("%s pipes into an interpreter or sudo: %s" % (name, "; ".join(hits)))
        # No sudo at all: the raw binary needs only chmod +x, and dropping sudo is what makes this work in a container and on a laptop.
        gate.assert_not_contains(code, "sudo ", "%s must not need sudo" % name)
        gate.assert_not_contains(
            code, "dpkg", "%s must not install a .deb (dpkg runs maintainer scripts as root)" % name
        )
    gate.log_pass("neither installer pipes to bash/sh/sudo, uses sudo, or touches dpkg")


def test_no_unpinned_download_urls(gate):
    """`latest` in any form defeats the checksum: the bytes hashed today are not the bytes fetched tomorrow."""
    for path in (INSTALL_CF, INSTALL_TMATE, VERSIONS):
        name = path.name
        code = code_of(path)
        gate.assert_not_contains(code, "@latest", "%s must not resolve @latest" % name)
        gate.assert_not_contains(
            code, "releases/latest/download", "%s must not use a releases/latest URL" % name
        )
        gate.assert_not_contains(code, "/latest/", "%s must not resolve any /latest/ path" % name)

    # CONTROL: the URLs that ARE there must interpolate the pinned version, or the assertions above are satisfied by a file with no download in it.
    gate.assert_contains(
        INSTALL_CF.read_text(encoding="utf-8"),
        "releases/download/${BREAKPOINT_CLOUDFLARED_VERSION}",
        "install-cloudflared.sh must download the PINNED version",
    )
    gate.assert_contains(
        INSTALL_TMATE.read_text(encoding="utf-8"),
        "releases/download/${VER}",
        "install-tmate.sh must download the PINNED version",
    )
    gate.log_pass("no @latest / releases-latest URLs; both installers fetch the pinned version")


def test_tmate_has_no_apt_fallback(gate):
    """THE regression this file exists for. An apt path here is not a harmless convenience: apt SUCCEEDS on every Ubuntu runner, so its mere presence makes the pinned, verified path dead code on the common path while the file still reads as if it pins something."""
    hits = [line for line in code_of(INSTALL_TMATE).splitlines() if APT.search(line)]
    gate.assert_eq(
        "\n".join(hits),
        "",
        "install-tmate.sh must have NO apt path (apt succeeds and makes the pin dead code)",
    )
    # Same for cloudflared, which had the equivalent problem via dpkg.
    hits = [line for line in code_of(INSTALL_CF).splitlines() if APT.search(line)]
    gate.assert_eq("\n".join(hits), "", "install-cloudflared.sh must have no apt path either")
    gate.log_pass("neither installer has an apt/dpkg fallback that would bypass the pin")


def test_every_pinned_sha_is_actually_consumed(gate):
    """A constant nothing reads is a pin that verifies nothing -- and it is the exact residue an "unpinning" edit leaves behind, because deleting the usage is easier than deleting the declaration."""
    installers = INSTALL_CF.read_text(encoding="utf-8") + INSTALL_TMATE.read_text(encoding="utf-8")
    for const in sorted(set(SHA_NAME.findall(VERSIONS.read_text(encoding="utf-8")))):
        if ("$" + const) not in installers:
            gate.log_fail(
                "%s is declared in versions.sh but never read by either installer" % const
            )
    gate.log_pass("every declared sha256 constant is actually read by an installer")
