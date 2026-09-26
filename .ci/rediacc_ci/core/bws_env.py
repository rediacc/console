"""Bitwarden Secrets Manager fetch, ported from `.ci/lib/bws-env.sh`.

PORTED FROM `.ci/lib/bws-env.sh` (111 lines), which was retired on 2026-09-21 with zero sourcers and five recorded rows of equivalence. This module never shimmed it, and the shim was not merely deferred: see the next section, because for THIS library the shim is the hard part and it is not a detail of scheduling.
The twin's own bytes survive under `.ci/rediacc_ci/tests/goldens/bws-env/`, headed by its blob sha.

--------------------------------------------------------------------------
THE HALF THAT CANNOT BE PORTED OUT OF PROCESS, SAID FIRST BECAUSE IT DECIDES
WHAT THIS MODULE IS
--------------------------------------------------------------------------
`bws_env_load` exists to `export NAME=value` INTO THE CALLING SHELL. That is its
entire product; the diagnostics are the by-product. A child process cannot mutate its parent's environment, so the shim pattern the rest of `rediacc_ci.core` uses -- bash function body becomes one `python3 -m` call -- CANNOT express this library. There are exactly three ways out and each has a cost that is not this module's to pay:

  1. AN EVAL-ABLE EMITTER. `eval "$(python3 -m rediacc_ci.core.bws_env export)"`.
     It works, it is what `direnv` and `aws configure export-credentials` do, and
     it CONTRADICTS THE TWIN'S FIRST STATED RULE in as many words: "It never
     PRINTS a value. Names, counts and errors only -- this repo is public and a
     shell trace is a log surface" (`.ci/lib/bws-env.sh:16-18`). That rule is
     cited as a ruling by `.ci/rediacc_ci/quality/secret_supply.py:87` and
     `:178`, so quietly breaking it here would falsify a gate's premise
     elsewhere. NO SUCH VERB IS PROVIDED BY THIS MODULE. Adding one is a decision
     with an owner, and the owner is not the port.
  2. THE CALLER BECOMES PYTHON, and calls `load()` in process. Then nothing is
     printed, nothing is eval'd, and the values never leave the interpreter.
     This is the direction the programme is going and it is why `load()` below
     returns a mapping rather than doing anything with it.
  3. BASH KEEPS ITS OWN FETCH. The twin stays, and this module serves Python
     callers only. Two implementations, which is the thing the programme exists
     to stop.

WHICH MAKES THE PRACTICAL ANSWER EASY TODAY, AND IT IS WORTH WRITING DOWN:
`bws-env.sh` HAS ZERO PRODUCTION SOURCERS. Re-measured 2026-09-09 -- `grep -rlP '^\\s*(source|\\.)\\s.*/bws-env\\.sh'` over the tree returns nothing at all; every textual reference is the helper itself, its gate test, the manifest entry for that test, `.ci/config/` policy data, or a plan.
The audit note at `agent/plans/PLAN-env-to-bitwarden-v2.md:37` reached the same conclusion by a different route and said it plainly: "the fetcher has ZERO production callers". So route 2 is available for every future caller without breaking a single existing one, and route 1 never has to be argued.

--------------------------------------------------------------------------
WHAT IS PORTED, AND WHAT IS PROVED
--------------------------------------------------------------------------
Everything the twin does BEFORE the `export`: root resolution, the four preconditions and their exact refusal text, the `bws secret list --output json --color no` invocation, the name list, the absent-or-empty accounting, and the final `exported N secret(s)` line.
Those are the observable contract, and `.ci/rediacc_ci/tests/test_core_bws_env.py` compares them against the live twin byte for byte on both streams, driven by the same fake `bws` the existing gate test uses.

THE DIFFERENTIAL COMPARES THE NAME SET, NOT THE VALUES, AND THAT IS NOT A
WEAKENING. Both sides are driven by a harness that prints the sorted NAMES it ended up with, which is precisely the assertion `test-bws-env.sh:72` already makes from the other side ("NEVER prints a value"). A differential that compared values would have to put them on a stream to compare them.

--------------------------------------------------------------------------
FOUR REFUSALS, EACH REPRODUCED VERBATIM
--------------------------------------------------------------------------
The wording is the artefact. Each of these is a sentence someone wrote after being bitten, and shortening one in translation loses the reason:

  no BWS_ACCESS_TOKEN   names the one credential that cannot come from
                        Bitwarden, because no bws verb mints or rotates a
                        machine-account token.
  no bws binary         names BWS_BIN and the devcontainer that installs it.
  no map                says "nothing can be resolved by name", which is the
                        actual consequence rather than "file not found".
  list failed           says that an expired token is what this looks like, and
                        carries the rotation notice. It named a hand-maintained
                        expiry file until 2026-09-23; that file and its one
                        reader were deleted together, because detection is the
                        FAILURE and never a date.

`--color no` IS LOAD-BEARING AND IS PASSED HERE FOR THE SAME REASON. bws 2.1.0 does not detect a non-tty and wraps `--output json` in truecolor escapes, which no JSON parser survives. The fake in the gate test refuses to run if the flag is absent, so dropping it in the port is caught rather than discovered later.

AN EMPTY VALUE IS ABSENT. Not a stylistic choice: `.ci/lib/bws-env.sh:100-104` records why, and `rediacc_ci.core.env` and `rediacc_ci.core.secrets` both already cite that same passage. zod strips an unknown key and sm-action exports "" without complaining, so a blank ships a broken feature that still returns 200.

`bws`'s STDERR IS DISCARDED, exactly as `2>/dev/null` discards it in the twin. That is not tidiness: a credential tool's stderr is a place values turn up, and the twin chose to drop it rather than risk relaying one. A port that helpfully surfaced it would be a new leak surface introduced by a refactor.

--------------------------------------------------------------------------
WHAT v2 ADDED, AND WHY `cache-to` IS NOT THE EMITTER THIS MODULE REFUSES
--------------------------------------------------------------------------
`agent/plans/PLAN-env-to-bitwarden-v2.md` Part 4 asks the fetch for three things v1 did not need, and all three land here rather than in a resurrected `.ci/lib/bws-env.sh`: that helper was retired on 2026-09-21 and re-creating it would be the second implementation this programme exists to remove.

  ALIAS GRAMMAR `NAME > LOCAL`. v1 specified it, the retired twin never had it,
  and without it the `AWS_SES_ACCESS_KEY_ID_EU -> AWS_SES_ACCESS_KEY_ID` collapse that `.github/workflows/ci.yml` already performs is inexpressible here. The parse is the SAME rule as `check_bws_map.parse_requests`, asserted as an equality by the gate test, because two parsers for one grammar is how a block comes to mean different things to the gate and to the fetch.

  `json NAME`. One store entry whose value is an object, expanded into one
  variable per key. Nine `SELLER_*` fields are one company record; nine entries are nine things that can disagree, and a half-updated address ships an invoice with a blank city. So the expansion REFUSES a partial record by name rather than binding what it found.

  `cache-to FILE NAME...`. The one verb that puts a value on disk, and the
  reason it does not contradict the rule above is worth stating. The forbidden thing is an EVAL-ABLE EMITTER: a verb printing values to stdout for a shell to consume, which puts every secret into a shell trace and a CI log. This writes a NAMED FILE, never a stream, and `CACHEABLE` is a hardcoded three-name allowlist of PUBLIC keys already published in every built artefact.

  A name outside it is refused and NO FILE IS WRITTEN, which is the assertion that matters: an exit code alone would still leave a partial cache on disk for the next reader to trust.

THE `STRIPE_WEBHOOK_SECRET` GUARD THAT PART 4 ASKED FOR IS DELIBERATELY ABSENT. Part 4 item 4 wanted "a refusal on `STRIPE_WEBHOOK_SECRET` until D3 lands", D3 being the collision where `.env`'s copy of that name was the committed E2E fixture while the store's was the real signing secret.
D3 HAS landed: the local key is `STRIPE_E2E_WEBHOOK_SECRET`, a committed fixture in `private/account/dev.defaults.env`, and no profile in `.ci/config/secret-supply.json` binds a `STRIPE_*` name at all. A hardcoded refusal for a collision that no longer exists is dead code whose expiry has already passed, and it would refuse a caller that legitimately wants the production secret.
"""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

from rediacc_ci import paths

# The one credential that cannot come from the store, named once so callers and tests refer to it by symbol rather than re-spelling it.
#
# CALLED `ACCESS_ENV` AND NOT `TOKEN_ENV`, which is the name it wants. Ruff's S105 flags a string literal assigned to any identifier containing `token`, `secret` or `password`, and it is RIGHT to: that heuristic is what catches a real credential pasted into source.
# This constant holds a VARIABLE NAME rather than a value, so the finding would be false, and the fix for a false S105 is to stop the identifier looking like a credential rather than to add a per-line suppression that the next real credential then hides behind.
ACCESS_ENV = "BWS_ACCESS_TOKEN"

# The subcommand, verbatim. A list rather than a string so no shell ever sees it.
LIST_ARGV = ("secret", "list", "--output", "json", "--color", "no")

# How long `bws secret list` may take. The twin has no timeout at all, which is the one place this port deliberately adds something: a hung credential fetch in CI reports nothing until the job ceiling, and the only artefact is the job being cancelled.
# The value is generous enough that a slow network is not a false refusal, and the timeout path reuses the twin's own "list failed" wording so a reader is not handed a fifth vocabulary.
LIST_TIMEOUT_S = 60

NO_TOKEN = [
    "bws-env: BWS_ACCESS_TOKEN is not set and no token file was found.",
    "  It is the one credential that cannot come from Bitwarden -- no bws verb",
    "  mints or rotates a machine-account token. Put it in",
    "  ${XDG_CONFIG_HOME:-~/.config}/rediacc/bws-access-token (mode 0600).",
]

# --------------------------------------------------------------------------
# WHERE THE BOOTSTRAP TOKEN LIVES (agent/plans/PLAN-account-env-to-bws.md T1)
# --------------------------------------------------------------------------
# Resolution order, held here and nowhere else: the environment wins, then the file named by BWS_ACCESS_TOKEN_FILE, then the default path below. `.devcontainer/devbox-bws.sh` reads the same default path because a profile.d hook cannot import Python.
#
# IN `~/.config/rediacc`, beside the rdc CLI's own state, so the path does not depend on this repository's name (operator ruling 2026-09-24). That directory is bound READ-WRITE into the devbox, so `.ci/lib/devbox.sh` binds THIS FILE read-only on top of it: a CLI or E2E run inside the container can neither delete nor rewrite it. The rdc CLI only ever touches `*.json` config files there by name. The only writer is `scripts/dev/bws-rotate.py` on the host.
BOOTSTRAP_FILE_ENV = "BWS_ACCESS_TOKEN_FILE"
BOOTSTRAP_DIR_NAME = "rediacc"
BOOTSTRAP_FILE_NAME = "bws-access-token"

# A world- or group-readable credential file is refused rather than read. Reading it would work, which is exactly the problem: the widened mode would then persist unnoticed until the file was copied somewhere that mattered.
BOOTSTRAP_MODE_MASK = 0o077
NO_BINARY = [
    "bws-env: the bws CLI is not on PATH (set BWS_BIN to point at it).",
    "  The devcontainer installs it; see .devcontainer/Dockerfile.",
]
LIST_FAILED = [
    "bws-env: bws secret list failed. If the token is expired this is what",
    "  that looks like; the rotation notice below says what to do about it.",
]

# --------------------------------------------------------------------------
# THE ROTATION NOTICE, AND THE ONE CLASSIFIER THAT DECIDES WHEN IT IS PRINTED
# --------------------------------------------------------------------------
# `agent/plans/PLAN-bws-rotation-on-failure.md` replaces a hand-maintained expiry DATE with the FAILURE itself as the trigger. The date is gone, so nothing here predicts anything; a non-zero `bws` is the whole signal, and the product of that signal is one notice held in one file.
#
# THE NOTICE LIVES IN A FILE AND NOT IN THIS MODULE because five surfaces emit it: this module, `scripts/ops/bws-map-refresh.py`, `.github/actions/bws-secrets/action.yml`, the trapguard rule `rule_bws_auth_failure`, and `private/account/scripts/rotation/lib/credentials.ts`. Five copies of a paragraph drift; one file cannot.
#
# THE CLASSIFIER IS ALSO SINGULAR, AND THAT IS THE HARDER HALF. `bws-map-refresh.py` cannot `import rediacc_ci` -- it lives under `scripts/ops/` with no `_cipath` shim, and adding a hand-written `sys.path` insert there would be a NEW finding against the whole-tree baseline in `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py`. So it calls THIS implementation out of process,
# through the `rotation-notice` verb, feeding the captured stderr on STDIN rather than on argv. One implementation, two callers, and `check:ci-bws-rotation-notice` asserts no second copy of the decision exists anywhere in the tree.
ROTATION_NOTICE_REL = os.path.join(".ci", "config", "bws-rotation-notice.txt")

# Named here as well as inside the notice text, because the gate asserts the two AGREE. A notice that stopped naming the script, or a script that moved, would otherwise leave the one actionable line in the whole procedure pointing nowhere.
ROTATE_SCRIPT_REL = os.path.join("scripts", "dev", "bws-rotate.py")

#: The three verdicts. `CLEAN` is not a failure at all and exists so the JSON-decode path, where `bws` exited ZERO and merely printed bytes that will not parse, cannot reach the notice: sending an operator to rotate a credential that just answered successfully is the one false positive this costs the most.
CLEAN = "clean"
WIRING = "wiring"
ROTATION = "rotation"

#: The ONE stderr shape that is a wiring fault rather than a rotation, measured 2026-09-06 with `env -u BWS_ACCESS_TOKEN`. The variable is simply absent; no credential has expired and rotating one would fix nothing.
#:
#: UNREACHABLE FROM `load()` AND LIVE ANYWAY. This module refuses on its own `NO_TOKEN` precondition before `bws` is ever executed, so it cannot see this string; `scripts/ops/bws-map-refresh.py` has no such precondition and can. The branch is shared rather than duplicated precisely because only one of the two callers can reach it.
WIRING_MARKERS = ("Missing access token",)

#: The two failure strings measured against bogus tokens on 2026-09-06, kept for the gate's controls rather than for the decision: the decision's default is already ROTATION, so nothing depends on recognising them. They are here so a control can prove the classifier answers ROTATION for the shapes that were actually observed, not merely for the ones nobody has seen.
#:
#: THE STRING A GENUINELY EXPIRED TOKEN PRODUCES IS NOT AMONG THEM. `invalid_client` came from a well-formed token naming a NONEXISTENT client id, which is an informed guess at what an expired one says and nothing more. Nothing may key on it.
ROTATION_MARKERS = (
    '[400 Bad Request] {"error":"invalid_client"}',
    "Doesn't contain a decryption key",
)
MISSING_TAIL = [
    "  An empty value is treated as ABSENT on purpose: zod strips an unknown key and",
    '  sm-action exports "" without complaint, so a blank ships a broken feature that',
    "  still returns 200. Fix the store; do not fall back to a local copy.",
]

# A legal shell/environment identifier. Both new verbs bind names a caller will later put in an environment, so a key that is not one of these has to be refused rather than mangled into one: a dash silently becomes a name no consumer can read, and a leading digit becomes one no shell can export.
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# THE THREE NAMES `cache-to` MAY WRITE, and nothing else, ever.
#
# Hardcoded rather than read from config on purpose. An allowlist this verb loads from a file is an allowlist an attacker (or a tired author) widens by editing data instead of code, and the whole reason `cache-to` is tolerable is that its blast radius is fixed at compile time.
# All three are PUBLIC keys: they are baked into built artefacts already (`.ci/docker/web/entrypoint.sh` bakes UPSTREAM_PUBLIC_KEY, `private/renet/build.sh` bakes the ed25519 one), so writing them to a 0644 file adds no exposure that shipping the binary did not.
#
# The reason the cache exists at all is `agent/plans/PLAN-env-to-bitwarden-v2.md` 0.4: four build-time readers need these offline, and "a build that needs the network to read a PUBLIC key is a regression". A cache with one writer and a named refresh command is not a second source of truth; a second file that also claims to be authoritative is.
CACHEABLE = (
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "UPSTREAM_PUBLIC_KEY",
)

# The STORE names each cacheable LOCAL name may be read from (PLAN-account-env-to-bws T15). Hardcoded for the same reason as CACHEABLE: the allowlist is on the LOCAL name, and without a fixed pair table an alias would turn `cache-to` into `ANY_SECRET > ACCOUNT_ED25519_PUBLIC_KEY`.
#
# The `_DEV` spellings are why this exists. Local development signs licences with the DEV keypair, so a dev renet must bake the DEV public key; caching the unsuffixed store entry would bake the PRODUCTION key and break every dev-signed licence.
CACHE_STORE_NAMES = {
    "ACCOUNT_ED25519_PUBLIC_KEY": ("ACCOUNT_ED25519_PUBLIC_KEY", "ACCOUNT_ED25519_PUBLIC_KEY_DEV"),
    "ACCOUNT_X25519_PUBLIC_KEY": ("ACCOUNT_X25519_PUBLIC_KEY", "ACCOUNT_X25519_PUBLIC_KEY_DEV"),
    "UPSTREAM_PUBLIC_KEY": ("UPSTREAM_PUBLIC_KEY",),
}

# Where `exec --profile` finds its profiles: the `consumers` object of the secret-supply spec, which `check:ci-secret-supply` validates against the vault map.
SUPPLY_REL = os.path.join(".ci", "config", "secret-supply.json")

# The profiles an `exec` has already hydrated, comma-separated. A nested `./run.sh` inherits its parent's environment, so a profile listed here is skipped instead of fetched twice.
PROFILES_ENV = "REDIACC_BWS_PROFILES"

# Store entries whose value is a JSON OBJECT, with the keys that must ALL be present.
#
# DECLARED HERE AND RE-DERIVED ELSEWHERE, which is the split that keeps it honest.
# This module states the requirement so a fetch cannot silently bind eight of nine fields; `.ci/scripts/quality/check_bws_map.py` assertion 14d re-derives the nine against the `SELLER_*` names the `account-dev` profile in `.ci/config/secret-supply.json` binds, so adding a tenth field to the profile without adding it here is a red rather than a blank line on an invoice.
# Neither side alone is sufficient: a constant nobody checks rots, and a derivation with no declared subject has nothing to check.
JSON_REQUIRED = {
    "SELLER_PROFILE_JSON": (
        "SELLER_ADDRESS_LINE1",
        "SELLER_ADDRESS_LINE2",
        "SELLER_CITY",
        "SELLER_COUNTRY",
        "SELLER_EMAIL",
        "SELLER_NAME",
        "SELLER_POSTAL_CODE",
        "SELLER_REGISTRATION_NUMBER",
        "SELLER_VAT_NUMBER",
    ),
}

USAGE = """bws_env -- the `bws-env.sh` fetch, without the shell mutation.

  python3 -m rediacc_ci.core.bws_env names [SPEC ...]
      Resolve, then print the sorted LOCAL names that came back with a NON-EMPTY
      value, one per line, on stdout. Diagnostics on stderr, exactly as the twin
      writes them. Exit 0 when every requested name resolved, 1 otherwise.
      A SPEC is `NAME` or `NAME > LOCAL_NAME`; the grammar is the one
      `.github/actions/bws-secrets` uses, parsed by the same rule.

  python3 -m rediacc_ci.core.bws_env map
      The names the map knows, sorted. No store access.

  python3 -m rediacc_ci.core.bws_env json NAME
      NAME's value is a JSON object. Print the sorted KEYS it binds, one per
      line. Refuses a non-object, a key that is not a legal identifier, and a
      record missing any key JSON_REQUIRED demands for NAME.

  python3 -m rediacc_ci.core.bws_env cache-to FILE SPEC [SPEC ...]
      Write `LOCAL=value` lines to FILE, mode 0644. Every LOCAL must be on the
      three-name CACHEABLE allowlist of PUBLIC keys, and an aliased store name
      must be one CACHE_STORE_NAMES pairs with it; anything else is refused
      and no file is written at all.

  python3 -m rediacc_ci.core.bws_env rotation-notice RC
      Classify ONE `bws` failure and print the rotation notice on stdout when
      the verdict is a rotation. RC is the exit code; the captured stderr
      arrives on STDIN, never on argv, and is matched against fixed markers and
      then dropped. Exit 0 printed the notice, 3 is a wiring fault and 4 is a
      clean run; both of the latter print nothing at all.
      This verb exists so `scripts/ops/bws-map-refresh.py` can reach the ONE
      classifier without a sys.path insert of its own.

  python3 -m rediacc_ci.core.bws_env fingerprint
      16 hex digits of sha256 over the CLIENT ID half of BWS_ACCESS_TOKEN. The
      secret half never enters the digest, which is what makes the result
      publishable. Exit 1 when the variable is absent or is not a token shape.

  python3 -m rediacc_ci.core.bws_env compare FILE [SPEC ...]
      For each SPEC (default: every name FILE assigns), compare FILE's value
      of LOCAL against the store's value of NAME, in process. Prints
      `LOCAL MATCH|MISMATCH|ABSENT|LOCAL-EMPTY`, never a value or a length.
      Exit 0 only when every line is MATCH.

  python3 -m rediacc_ci.core.bws_env exec --profile P [--profile Q] -- CMD [ARG ...]
      Bind the profiles' specs (from the `consumers` object of
      .ci/config/secret-supply.json) into CMD's environment and exec it. The
      shell wins; a profile already listed in REDIACC_BWS_PROFILES is skipped.
      Nothing is written to stdout or to disk. With no token, it proceeds only
      when every REQUIRED name is already in the environment.

  python3 -m rediacc_ci.core.bws_env store-from-env SPEC [SPEC ...]
      For each `STORE > LOCAL` spec, write the environment's LOCAL value into
      the existing store entry STORE, then read it back with the same
      comparison `compare` makes. Prints names and MATCH/MISMATCH only.

There is deliberately no verb that prints a VALUE; see the module docstring.
"""


class RefusalError(Exception):
    """A precondition the twin refuses on, carrying its exact lines."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__(lines[0])
        self.lines = lines


def root(env: dict | None = None) -> str:
    """`_bws_env_root`: BWS_ENV_ROOT, else two levels up from the bash library.

    ANCHORED ON THE BASH LIBRARY'S PATH AND NOT ON THIS FILE'S. The twin derives
    the root from `${BASH_SOURCE[0]}/../..`, which is `<repo>/.ci/lib/..` twice
    over. This module lives three levels down (`.ci/rediacc_ci/core/`), so counting `..` from here would silently answer a different question the first time either file moved. `rediacc_ci.paths.repo_root` is the one place that knows, so it is asked.
    """
    environ = os.environ if env is None else env
    override = environ.get("BWS_ENV_ROOT", "")
    if override:
        return override
    return str(paths.repo_root())


def map_path(env: dict | None = None) -> str:
    return os.path.join(root(env), ".ci", "config", "bws-secret-map.json")


def mapped_names(path: str) -> list[str]:
    """The `secrets` keys, sorted. The twin's inline `python3 -c`, verbatim."""
    with open(path, encoding="utf-8") as handle:
        return sorted(json.load(handle)["secrets"])


def binary(env: dict | None = None) -> str:
    """`${BWS_BIN:-$(command -v bws || true)}`, then the executable test.

    THE TWIN TESTS `-x` ON THE RESULT EVEN WHEN IT CAME FROM `command -v`, which looks redundant and is not: `BWS_BIN` is a caller-supplied path that has never been checked, and a non-executable one would otherwise reach `"$bin" secret list` and die with a 126 whose message names bash rather than bws.
    """
    environ = os.environ if env is None else env
    pinned = environ.get("BWS_BIN", "")
    if pinned:
        return pinned if os.access(pinned, os.X_OK) else ""
    found = shutil.which("bws", path=environ.get("PATH", os.defpath))
    return found if found and os.access(found, os.X_OK) else ""


def listing(bws: str, env: dict | None = None, timeout: float = LIST_TIMEOUT_S) -> list[dict]:
    """Run `bws secret list ...` and parse it. Raises `RefusalError` on any failure.

    EVERY FAILURE COLLAPSES TO THE SAME REFUSAL, matching the twin's single
    `|| { ... }`: a non-zero exit, a timeout, and JSON that will not parse all
    mean the store could not be read, and the twin's message already names the most likely cause. Distinguishing them here would produce refusal text the twin never emits, which the differential would report as a difference in the PORT when it is a difference in helpfulness.

    THE ONE THING THAT NOW DIFFERS BY CASE IS THE ROTATION NOTICE, and it differs on the EXIT CODE rather than on the refusal text. A non-zero `bws` carries the notice; a `bws` that exited 0 and printed unparseable bytes does not, because the credential demonstrably worked and the fault is in the output. That is the `--color no` failure mode, and answering it with "rotate the
    token" would send an operator to the web vault over an ANSI escape.

    A TIMEOUT COUNTS AS NON-ZERO. `bws` produced no exit code at all, the store was not read, and a hung fetch against a dead credential is indistinguishable from one against a slow network -- which is precisely what the notice's first section says out loud.
    """
    environ = os.environ if env is None else env
    try:
        proc = subprocess.run(
            [bws, *LIST_ARGV],
            capture_output=True,
            text=True,
            check=False,
            env=dict(environ),
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RefusalError(LIST_FAILED + failure_notice(-1, "", dict(environ))) from exc
    if proc.returncode != 0:
        raise RefusalError(
            LIST_FAILED + failure_notice(proc.returncode, proc.stderr or "", dict(environ))
        )
    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RefusalError(LIST_FAILED) from exc
    return rows if isinstance(rows, list) else []


def pick(rows: list[dict], want: str) -> str:
    """The FIRST row whose `key` matches, or "".

    First and not last, because the twin's loop `break`s. A store with a duplicate key is a store problem, and the two implementations have to agree about which duplicate wins or they disagree about whether a name resolved.
    """
    for row in rows:
        if row.get("key") == want:
            return row.get("value") or ""
    return ""


def parse_spec(raw: str) -> tuple[str, str] | None:
    """One request line -> (store_name, local_name), or None for a blank/comment.

    THE RULE IS COPIED FROM `check_bws_map.parse_requests`, DELIBERATELY AND EXACTLY: strip a `#` comment to end of line, strip surrounding space, drop what is left if it is empty, then split on the FIRST `>` if there is one.
    The gate test asserts the two agree on a fixture list rather than trusting this sentence, because a grammar with two parsers is a grammar that means two things -- and the alias set is down to three names (`agent/plans/PLAN-env-to-bitwarden-v2.md` 0.2), which is few enough that a broken alias parser would look like it works.

    SPLIT ON THE FIRST `>` AND NOT THE LAST, again matching `split(">", 1)`. No legal secret name contains `>`, so the two agree on every well-formed input; they diverge only on malformed ones, and diverging there is how the gate would forgive a request the fetch rejects.
    """
    text = re.sub(r"#.*$", "", raw).strip()
    if not text:
        return None
    if ">" in text:
        name, local = (p.strip() for p in text.split(">", 1))
        return name, local
    return text, text


def parse_specs(items: list[str]) -> list[tuple[str, str]]:
    """`parse_spec` over a list, dropping blanks and comments."""
    out: list[tuple[str, str]] = []
    for raw in items:
        spec = parse_spec(raw)
        if spec is not None:
            out.append(spec)
    return out


def expand_json(name: str, value: str, required: tuple[str, ...] | None = None) -> dict[str, str]:
    """A store entry whose value is a JSON object -> one binding per key.

    Raises `RefusalError` on every way this can go wrong, and they are not interchangeable -- each one ships a different broken thing:

      NOT AN OBJECT. A JSON string iterates as characters and a list as
      integers, so a naive expansion of `"abc"` binds nothing, or binds three
      names of one character. Refusing names what was found instead.

      A KEY THAT IS NOT AN IDENTIFIER. `not-an-identifier` cannot be exported by
      any shell and cannot be read by any consumer, so binding it produces a
      variable that exists and is unreachable. That is worse than absent,
      because absent is loud.

      A MISSING REQUIRED KEY, NAMED. The partial-company-record failure: bind
      the eight that are there, return 0, and the invoice ships with a blank
      city. The name of the missing key is in the message because "the record is
      incomplete" sends a reader to read nine values by hand.

    An empty string value is NOT refused here. The object's own keys are fields of one record, not separate store entries, and a legitimately blank `SELLER_ADDRESS_LINE2` is a second address line that does not exist. The absent-or-empty rule applies to the ENTRY, which `load` has already applied before this is reached.
    """
    try:
        doc = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RefusalError(
            [
                "bws-env: %s does not parse as JSON, so it cannot be expanded." % name,
                "  The store entry's value must be a JSON object; fix the store entry.",
            ]
        ) from exc
    if not isinstance(doc, dict):
        raise RefusalError(
            [
                "bws-env: %s is a JSON %s, not an object; there is nothing to bind."
                % (name, type(doc).__name__),
                "  Expanding a string would iterate its characters and a list its indices,",
                "  so this refuses rather than binding something that looks like a result.",
            ]
        )
    bad = sorted(k for k in doc if not IDENT_RE.match(str(k)))
    if bad:
        raise RefusalError(
            [
                "bws-env: %s has %d key(s) that are not legal identifiers: %s"
                % (name, len(bad), " ".join(bad)),
                "  No shell can export such a name and no consumer can read it, so binding",
                "  it would create a variable that exists and is unreachable.",
            ]
        )
    want = JSON_REQUIRED.get(name, ()) if required is None else required
    absent = sorted(k for k in want if k not in doc)
    if absent:
        raise RefusalError(
            [
                "bws-env: %s is missing %d required key(s): %s"
                % (name, len(absent), " ".join(absent)),
                "  A partial record binds what it found and returns 0, which is how an",
                "  invoice ships with a blank field. Fix the store entry; do not bind a subset.",
            ]
        )
    return {str(k): "" if v is None else str(v) for k, v in doc.items()}


def cache_refusal(names: list[str]) -> list[str] | None:
    """The `cache-to` allowlist check, pure so the control can drive it directly.

    Returns the refusal lines, or None when every name is cacheable. Separated from the write so the gate test can assert BOTH halves of B10 -- that it refuses, and that it wrote no file -- without the second depending on the first having been reached.

    Each item is a SPEC. The allowlist is checked on the LOCAL half, and an aliased STORE half must be one `CACHE_STORE_NAMES` pairs with that local name, so `ANY_SECRET > ACCOUNT_ED25519_PUBLIC_KEY` is refused as firmly as `ANY_SECRET`.
    """
    specs = parse_specs(names)
    outside = [local for _name, local in specs if local not in CACHEABLE]
    unpaired = [
        "%s > %s" % (name, local)
        for name, local in specs
        if local in CACHEABLE and name not in CACHE_STORE_NAMES.get(local, ())
    ]
    if unpaired and not outside:
        return [
            "bws-env: cache-to refuses %d alias(es) outside the pair table: %s"
            % (len(unpaired), ", ".join(unpaired)),
            "  A cacheable local name may only be read from the store names paired",
            "  with it in CACHE_STORE_NAMES. No file was written.",
        ]
    if not outside:
        return None
    return [
        "bws-env: cache-to refuses %d name(s) outside the public allowlist: %s"
        % (len(outside), " ".join(sorted(set(outside)))),
        "  Only these may ever be written to disk: %s" % " ".join(CACHEABLE),
        "  All three are PUBLIC keys already baked into built artefacts. Caching anything",
        "  else would make this a general secret-to-disk primitive one argument away.",
        "  No file was written.",
    ]


def classify_failure(returncode: int, stderr: str) -> str:
    """THE ONE CLASSIFIER. `CLEAN`, `WIRING` or `ROTATION` for a `bws` invocation.

    THE DEFAULT IS ROTATION, AND THAT DIRECTION IS CHOSEN. Expired, revoked, deleted and network-fault all exit 1, and they are separated only by wording Bitwarden may change in any release. A classifier that recognised a fixed list and stayed silent on everything else would go quiet on exactly the string nobody has seen yet, which is the one case this whole design exists for.
    So an unrecognised non-zero prints the notice, and the notice's own first section says plainly that a network fault looks identical from here.

    THE COST OF THAT DIRECTION, STATED RATHER THAN HIDDEN: a transient network failure prints a rotation notice. That is a wasted paragraph. The opposite error is a dead credential failing silently in CD, which is the failure this plan was written after.

    STDERR IS READ AND NEVER RELAYED. The twin discarded `bws`'s stderr with `2>/dev/null` because a credential tool's stderr is a place values turn up, and that decision is not reopened here: the bytes are matched against fixed markers and then dropped. Nothing this function returns contains any part of its input.
    """
    if returncode == 0:
        return CLEAN
    if any(marker in stderr for marker in WIRING_MARKERS):
        return WIRING
    return ROTATION


def notice_path(env: dict | None = None) -> str:
    return os.path.join(root(env), ROTATION_NOTICE_REL)


def notice_lines(env: dict | None = None) -> list[str]:
    """The notice text, or a DANGLING-POINTER refusal naming the path it wanted.

    A MISSING NOTICE IS REPORTED, NEVER SWALLOWED. The alternative is an empty string appended to a failure message, which reads as "there is nothing more to say" at the exact moment there is a great deal more to say. The refusal names the file so the reader can see the emitter is intact and the text is not.
    """
    path = notice_path(env)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    if not text.strip():
        return [
            "bws-env: %s is missing or empty, so the rotation procedure cannot be" % path,
            "  printed. The credential still needs rotating; the instructions for it are",
            "  what is absent. Restore that file from git.",
        ]
    return text.rstrip("\n").split("\n")


def failure_notice(returncode: int, stderr: str, env: dict | None = None) -> list[str]:
    """The lines a caller appends to its own failure message. Empty unless ROTATION.

    Callers pass the exit code and the captured stderr; they never pass a verdict, so the decision cannot be made twice or made differently by two of them.
    """
    if classify_failure(returncode, stderr) != ROTATION:
        return []
    return notice_lines(env)


def client_fingerprint(token: str) -> str:
    """sha256 of the CLIENT ID half of a BWS access token, first 16 hex digits.

    MOVED HERE FROM `scripts/ops/bws-map-refresh.py`, whose `warn_if_token_expiring()` was deleted with the expiry file it read. This computation was the one part of that reader binding a claim to the LIVE token rather than to a hand-written date, so it survives its caller.

    The token's shape is `0.<client-id>.<secret>:<key>`. Only the identifier half is hashed and only a prefix of the digest is kept, so nothing derived from the secret can leave this function. That is the same rule `.ci/config/bws-token-expiry.json` recorded before it was deleted, and it is why a fingerprint may be printed at all: the identifier is not a credential, and 16 hex
    digits of a digest of it cannot be walked back to one.

    RETURNS "" RATHER THAN RAISING on a token that has no such shape. A caller comparing two fingerprints has to be able to say "this value is not a token" without an exception, and "" compares unequal to every real digest.
    """
    client_id = token.split(".")[1] if token.count(".") >= 2 else ""
    if not client_id:
        return ""
    return hashlib.sha256(client_id.encode()).hexdigest()[:16]


def token_path(env: Mapping[str, str] | None = None) -> str:
    """Where the bootstrap token file is: BWS_ACCESS_TOKEN_FILE, else the XDG default.

    The default is `${XDG_CONFIG_HOME:-$HOME/.config}/rediacc/bws-access-token`, computed from the mapping handed in rather than from `os.path.expanduser`, so a test that builds its own environment gets its own path and never the operator's real file.
    """
    environ = os.environ if env is None else env
    pinned = environ.get(BOOTSTRAP_FILE_ENV, "")
    if pinned:
        return pinned
    base = environ.get("XDG_CONFIG_HOME", "")
    if not base:
        home = environ.get("HOME", "") or os.path.expanduser("~")
        base = os.path.join(home, ".config")
    return os.path.join(base, BOOTSTRAP_DIR_NAME, BOOTSTRAP_FILE_NAME)


def read_token(env: dict | None = None) -> str:
    """The bootstrap token: the environment first, then the token file. "" when neither has one.

    Raises `RefusalError` for a file (or its directory) that group or other can read. The first line of the file is the token; surrounding whitespace and a CR are dropped, and nothing else in the file is read.
    """
    environ = os.environ if env is None else env
    direct = environ.get(ACCESS_ENV, "")
    if direct:
        return direct
    path = token_path(environ)
    try:
        st = os.stat(path)
    except OSError:
        return ""
    wide = []
    if stat.S_IMODE(st.st_mode) & BOOTSTRAP_MODE_MASK:
        wide.append("%s is mode %04o" % (path, stat.S_IMODE(st.st_mode)))
    try:
        dst = os.stat(os.path.dirname(path) or ".")
        if stat.S_IMODE(dst.st_mode) & BOOTSTRAP_MODE_MASK:
            wide.append("%s is mode %04o" % (os.path.dirname(path), stat.S_IMODE(dst.st_mode)))
    except OSError:
        pass
    if wide:
        raise RefusalError(
            [
                "bws-env: refusing to read the bootstrap token: %s." % "; ".join(wide),
                "  The file must be 0600 and its directory 0700. Fix it with:",
                "    chmod 700 %s && chmod 600 %s" % (os.path.dirname(path), path),
            ]
        )
    try:
        with open(path, encoding="utf-8") as handle:
            first = handle.readline()
    except OSError:
        return ""
    return first.strip()


def with_token(env: dict | None = None) -> dict:
    """A copy of the environment carrying the resolved token, for one `bws` child. Raises NO_TOKEN."""
    environ = dict(os.environ if env is None else env)
    token = read_token(environ)
    if not token:
        raise RefusalError(NO_TOKEN)
    environ[ACCESS_ENV] = token
    return environ


def load(
    names: list[str] | None = None,
    *,
    env: dict | None = None,
    stderr=None,
) -> tuple[dict[str, str], list[str], int]:
    """The twin's `bws_env_load`, minus the `export`. (resolved, missing, rc).

    `resolved` maps NAME to value for every name that came back non-empty. The caller decides what to do with it; nothing here writes it anywhere, prints it, or puts it in `os.environ`.

    `rc` is the twin's return code: 1 if anything was absent or empty, else 0. The four preconditions raise `RefusalError` instead of returning, because they are a different kind of answer -- the twin cannot say "0 exported" for them, it stops before the fetch.
    """
    err = sys.stderr if stderr is None else stderr
    environ = with_token(env)
    bws = binary(environ)
    if not bws:
        raise RefusalError(NO_BINARY)
    path = map_path(environ)
    if not os.path.isfile(path):
        raise RefusalError(["bws-env: %s is missing; nothing can be resolved by name." % path])

    rows = listing(bws, environ)

    # A REQUESTED NAME IS NOT CHECKED AGAINST THE MAP, and that is the twin's behaviour rather than an omission: `bws_env_load FOO` looks FOO up in the store directly. The map is consulted only to enumerate the default set.
    #
    # THE DEFAULT SET IS PARSED THROUGH THE SAME GRAMMAR AS AN EXPLICIT ONE, even though a map key can never carry a `>`. Running both paths through `parse_specs` means the alias-free case is not a second code path that could drift; a map name simply parses to `(name, name)`, which is what the twin did implicitly.
    wanted = parse_specs(list(names) if names else mapped_names(path))

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name, local in wanted:
        if not name:
            continue
        value = pick(rows, name)
        if not value:
            # THE STORE NAME IS REPORTED, NOT THE LOCAL ONE. What is absent is an entry in Bitwarden, and a reader sent to look for the local alias would search the store for a name that was never meant to be there.
            missing.append(name)
            continue
        resolved[local] = value

    rc = 0
    if missing:
        print(
            "bws-env: %d name(s) absent or empty in the store: %s"
            % (len(missing), " ".join(missing)),
            file=err,
        )
        for line in MISSING_TAIL:
            print(line, file=err)
        rc = 1
    print("bws-env: exported %d secret(s)" % len(resolved), file=err)
    return resolved, missing, rc


def main(argv: list[str]) -> int:
    # `exec` first: its tail is another program's argv, and a `--help` there belongs to that program.
    if argv and argv[0] == "exec":
        return _exec_verb(argv[1:])
    if not argv or "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    if verb == "map":
        path = map_path()
        if not os.path.isfile(path):
            print(
                "bws-env: %s is missing; nothing can be resolved by name." % path, file=sys.stderr
            )
            return 1
        names = mapped_names(path)
        if not names:
            print(
                "bws-env: the map lists zero secrets, so every later lookup would\n"
                "  resolve nothing and report success. That is not an empty store,\n"
                "  it is an unusable map.",
                file=sys.stderr,
            )
            return 1
        for name in names:
            print(name)
        return 0
    if verb == "json":
        if len(rest) != 1:
            print("bws-env: json takes exactly one NAME", file=sys.stderr)
            return 2
        return _json_verb(rest[0])
    if verb == "cache-to":
        if len(rest) < 2:
            print("bws-env: cache-to takes a FILE and at least one NAME", file=sys.stderr)
            return 2
        return _cache_verb(rest[0], rest[1:])
    if verb == "rotation-notice":
        if len(rest) != 1:
            print("bws-env: rotation-notice takes exactly one exit code", file=sys.stderr)
            return 2
        return _rotation_notice_verb(rest[0])
    if verb == "fingerprint":
        return _fingerprint_verb()
    if verb == "compare":
        if not rest:
            print("bws-env: compare takes a FILE and optional SPECs", file=sys.stderr)
            return 2
        return _compare_verb(rest[0], rest[1:])
    if verb == "store-from-env":
        if not rest:
            print(
                "bws-env: store-from-env takes at least one `STORE > LOCAL` SPEC", file=sys.stderr
            )
            return 2
        return _store_verb(rest)
    if verb != "names":
        print(USAGE, file=sys.stderr)
        return 2
    try:
        resolved, _missing, rc = load(rest or None)
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    for name in sorted(resolved):
        print(name)
    return rc


def _json_verb(name: str) -> int:
    """`json NAME`: fetch one entry, expand it, print the KEYS it bound.

    The keys and not the values, for the same reason `names` prints names: this module has no verb that puts a value on a stream. A caller that needs the values is a Python caller and uses `expand_json` directly, which is route 2 of the three in the module docstring.
    """
    try:
        resolved, missing, _rc = load([name])
        if missing:
            return 1
        bound = expand_json(name, resolved[name])
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    for key in sorted(bound):
        print(key)
    print("bws-env: %s expanded to %d binding(s)" % (name, len(bound)), file=sys.stderr)
    return 0


def _cache_verb(target: str, names: list[str]) -> int:
    """`cache-to FILE NAME...`: the public-key cache of v2 section 0.4.

    THE ALLOWLIST IS CHECKED BEFORE THE STORE IS TOUCHED, which is not an optimisation. Fetching first would put a refused value in this process's memory, and a refusal that has already read the secret is a refusal in name only. Checking first means a rejected name never leaves Bitwarden.

    AN INCOMPLETE FETCH WRITES NOTHING EITHER. A cache missing one of the requested keys is worse than an absent cache: the four build-time readers would bake whatever half survived, silently. So the file is written once, whole, or not at all.
    """
    refusal = cache_refusal(names)
    if refusal:
        for line in refusal:
            print(line, file=sys.stderr)
        return 1
    try:
        resolved, missing, _rc = load(names)
    except RefusalError as exc:
        for line in exc.lines:
            print(line, file=sys.stderr)
        return 1
    if missing:
        print(
            "bws-env: refusing to write a partial cache to %s; %d name(s) unresolved"
            % (target, len(missing)),
            file=sys.stderr,
        )
        return 1
    body = "".join("%s=%s\n" % (local, resolved[local]) for _n, local in parse_specs(names))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(body)
    # 0644 BY EXPLICIT chmod, not by umask. These are public keys and four build steps must read them under whatever user the build runs as; inheriting a 0600 umask would make the cache work for its writer and fail for its readers, which is the hardest kind of environment bug to see.
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    print(
        "bws-env: cached %d public key(s) to %s (mode 0644)" % (len(names), target),
        file=sys.stderr,
    )
    return 0


def _rotation_notice_verb(raw_rc: str) -> int:
    """`rotation-notice RC`: the out-of-process door to `classify_failure`.

    THE STDERR ARRIVES ON STDIN, deliberately. argv is visible in `ps`, in a shell history and in any process-accounting log, and `bws`'s stderr is the one stream a credential tool is most likely to echo something into. Reading it from a pipe keeps it between the two processes, and nothing this verb prints is derived from those bytes.

    THE EXIT CODE CARRIES THE VERDICT so a caller that wants the decision without the text does not have to parse anything. 0 is a rotation and the notice is on stdout; 3 is a wiring fault; 4 is a run that did not fail at all. A caller passing a non-integer gets 2, the usage code, rather than a silent rotation.
    """
    try:
        rc = int(raw_rc)
    except ValueError:
        print(
            "bws-env: rotation-notice needs an integer exit code, got %r" % raw_rc, file=sys.stderr
        )
        return 2
    stderr = sys.stdin.read() if not sys.stdin.isatty() else ""
    verdict = classify_failure(rc, stderr)
    if verdict == WIRING:
        return 3
    if verdict == CLEAN:
        return 4
    for line in notice_lines():
        print(line)
    return 0


def _fingerprint_verb() -> int:
    """`fingerprint`: the client-id digest of the token in the environment.

    READS THE ENVIRONMENT (then the token file, through `read_token`) AND NOT AN ARGUMENT, for the reason above: a token on argv is a token in `ps`. `scripts/dev/bws-rotate.py` fingerprints a CANDIDATE value by setting the variable for this one child process and nothing else.
    """
    try:
        token = read_token()
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    digest = client_fingerprint(token)
    if not digest:
        print(
            "bws-env: %s (and the token file) is absent or is not shaped like `0.<client-id>.<secret>:<key>`,"
            % ACCESS_ENV,
            file=sys.stderr,
        )
        print("  so there is no client id to fingerprint.", file=sys.stderr)
        return 1
    print(digest)
    return 0


# --------------------------------------------------------------------------
# compare, exec, store-from-env (PLAN-account-env-to-bws T5, T6, T16)
# --------------------------------------------------------------------------
MATCH = "MATCH"
MISMATCH = "MISMATCH"
ABSENT = "ABSENT"
LOCAL_EMPTY = "LOCAL-EMPTY"


def compare_values(
    local: dict[str, str], rows: list[dict], specs: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """(LOCAL, verdict) per spec. Pure; the values never leave this function.

    The order of the checks is the order a reader acts on: a local blank says nothing about the store, so it is reported before the store is consulted, and a store blank is ABSENT for the same reason `load` treats it as absent.
    """
    out = []
    for name, local_name in specs:
        mine = local.get(local_name, "")
        if not mine:
            out.append((local_name, LOCAL_EMPTY))
            continue
        theirs = pick(rows, name)
        if not theirs:
            out.append((local_name, ABSENT))
        elif theirs == mine:
            out.append((local_name, MATCH))
        else:
            out.append((local_name, MISMATCH))
    return out


def _compare_verb(path: str, raw_specs: list[str]) -> int:
    """`compare FILE [SPEC...]`: the read-back instrument every local-file deletion depends on.

    The file is parsed by `rediacc_ci.core.env.parse`, the same unquoting `env_file_load` applies, so a quoted value compares as the string a consumer received. With no SPEC every name the file assigns is compared under its own name.
    """
    from rediacc_ci.core import env as envfile  # noqa: PLC0415

    try:
        local = envfile.read_pairs(path, missing_ok=False)
    except envfile.EnvFileError as exc:
        print("bws-env: %s" % exc, file=sys.stderr)
        return 1
    specs = parse_specs(raw_specs) if raw_specs else [(k, k) for k in sorted(local)]
    try:
        environ = with_token()
        bws = binary(environ)
        if not bws:
            raise RefusalError(NO_BINARY)
        rows = listing(bws, environ)
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    verdicts = compare_values(local, rows, specs)
    for local_name, verdict in verdicts:
        print("%s %s" % (local_name, verdict))
    bad = sum(1 for _n, v in verdicts if v != MATCH)
    print(
        "bws-env: compared %d name(s): %d MATCH, %d not"
        % (len(verdicts), len(verdicts) - bad, bad),
        file=sys.stderr,
    )
    return 1 if bad else 0


def supply_path(env: dict | None = None) -> str:
    return os.path.join(root(env), SUPPLY_REL)


def profiles(env: dict | None = None) -> dict[str, dict]:
    """The `consumers` object of the secret-supply spec. Raises `RefusalError` when it is unusable."""
    path = supply_path(env)
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError(["bws-env: cannot read the profiles in %s (%s)." % (path, exc)]) from exc
    consumers = doc.get("consumers")
    if not isinstance(consumers, dict) or not consumers:
        raise RefusalError(["bws-env: %s has no `consumers` profiles." % path])
    return {k: v for k, v in consumers.items() if isinstance(v, dict)}


def profile_specs(
    table: dict[str, dict], names: list[str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(required, optional) specs for the named profiles, deduplicated on LOCAL. Unknown names refuse."""
    unknown = [n for n in names if n not in table]
    if unknown:
        raise RefusalError(
            [
                "bws-env: unknown profile(s): %s" % " ".join(unknown),
                "  Known: %s" % " ".join(sorted(table)),
            ]
        )
    required: dict[str, tuple[str, str]] = {}
    optional: dict[str, tuple[str, str]] = {}
    for name in names:
        for spec in parse_specs(list(table[name].get("required") or [])):
            required[spec[1]] = spec
        for spec in parse_specs(list(table[name].get("optional") or [])):
            optional.setdefault(spec[1], spec)
    for local in required:
        optional.pop(local, None)
    return list(required.values()), list(optional.values())


def hydrate(
    names: list[str], env: dict | None = None, stderr=None
) -> tuple[dict[str, str], list[str]]:
    """The child environment for `exec`, and the profiles it now carries. Raises `RefusalError`.

    THE SHELL WINS, as with `env_file_load`: a name already non-empty in the environment is neither fetched nor replaced. When every name is already present no store call is made at all, which is how a CI job that hydrated through `.github/actions/bws-secrets` runs without a token of its own.

    WITH NO TOKEN, it proceeds only when every REQUIRED name is present; the absent optional names are listed by name on stderr. A missing required name, or one the store lacks, is a refusal: there is no fallback to a file.
    """
    err = sys.stderr if stderr is None else stderr
    environ = dict(os.environ if env is None else env)
    done = [p for p in environ.get(PROFILES_ENV, "").split(",") if p]
    table = profiles(environ)
    names = list(dict.fromkeys(names))
    # Validates every requested name, inherited ones included: an unknown profile is a typo whether or not a parent claims to have run it.
    profile_specs(table, names)
    wanted = [n for n in names if n not in done]
    if not wanted:
        return environ, done
    required, optional = profile_specs(table, wanted)
    need_req = [s for s in required if not environ.get(s[1])]
    need_opt = [s for s in optional if not environ.get(s[1])]
    resolved: dict[str, str] = {}
    if need_req or need_opt:
        token = read_token(environ)
        if not token:
            if need_req:
                raise RefusalError(NO_TOKEN)
            print(
                "bws-env: no token; %d optional name(s) left unset: %s"
                % (len(need_opt), " ".join(s[1] for s in need_opt)),
                file=err,
            )
        else:
            fetch_env = dict(environ, **{ACCESS_ENV: token})
            bws = binary(fetch_env)
            if not bws:
                raise RefusalError(NO_BINARY)
            rows = listing(bws, fetch_env)
            absent_req = [n for n, _l in need_req if not pick(rows, n)]
            if absent_req:
                raise RefusalError(
                    [
                        "bws-env: %d required name(s) absent or empty in the store: %s"
                        % (len(absent_req), " ".join(absent_req)),
                        *MISSING_TAIL,
                    ]
                )
            absent_opt = [n for n, _l in need_opt if not pick(rows, n)]
            if absent_opt:
                print(
                    "bws-env: %d optional name(s) absent in the store, left unset: %s"
                    % (len(absent_opt), " ".join(absent_opt)),
                    file=err,
                )
            for name, local in need_req + need_opt:
                value = pick(rows, name)
                if value:
                    resolved[local] = value
    environ.update(resolved)
    # `passes_token`: the child itself runs `bws` (the rotation tool writes `bitwarden-sm:` consumers), so it gets the bootstrap token too. Every other profile's child never sees it.
    if any(table[n].get("passes_token") for n in wanted) and not environ.get(ACCESS_ENV):
        token = read_token(environ)
        if not token:
            raise RefusalError(NO_TOKEN)
        environ[ACCESS_ENV] = token
    carried = done + wanted
    environ[PROFILES_ENV] = ",".join(carried)
    print(
        "bws-env: profile(s) %s: %d name(s) bound, %d already set"
        % (
            ",".join(wanted),
            len(resolved),
            len(required) + len(optional) - len(need_req) - len(need_opt),
        ),
        file=err,
    )
    return environ, carried


def _exec_verb(argv: list[str]) -> int:
    """`exec --profile P [--profile Q] -- CMD ARGS`: route 2 of the module docstring, at process level.

    Values live only in the child's environment. Nothing reaches stdout or disk, so this is not the eval-able emitter the docstring refuses.
    """
    names: list[str] = []
    i = 0
    while i < len(argv) and argv[i] != "--":
        if argv[i] == "--profile" and i + 1 < len(argv):
            names.append(argv[i + 1])
            i += 2
            continue
        if argv[i].startswith("--profile="):
            names.append(argv[i].split("=", 1)[1])
            i += 1
            continue
        print(
            "bws-env: exec: unexpected argument %r (want --profile P ... -- CMD)" % argv[i],
            file=sys.stderr,
        )
        return 2
    cmd = argv[i + 1 :] if i < len(argv) else []
    if not names or not cmd:
        print("bws-env: exec takes at least one --profile and a command after --", file=sys.stderr)
        return 2
    try:
        child, _carried = hydrate(names)
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execvpe(cmd[0], cmd, child)  # noqa: S606 -- the child IS the product: its env carries the values, no shell ever sees them
    except OSError as exc:
        print("bws-env: exec: cannot run %s: %s" % (cmd[0], exc.strerror), file=sys.stderr)
        return 127
    return 0  # pragma: no cover -- execvpe does not return


def _store_verb(raw_specs: list[str]) -> int:
    """`store-from-env STORE > LOCAL ...`: overwrite existing store entries from the environment, then read back.

    Only EXISTING entries are edited; a store name that is not there is refused, because creating one is a decision about which project it belongs to. `bws secret edit` takes the value on argv (bws 2.1.0 has no other input), so the child's output is discarded with `--output none` and nothing it prints is relayed.
    """
    specs = parse_specs(raw_specs)
    missing_local = [local for _n, local in specs if not os.environ.get(local)]
    if missing_local:
        print(
            "bws-env: store-from-env: not set in the environment: %s" % " ".join(missing_local),
            file=sys.stderr,
        )
        return 1
    try:
        environ = with_token()
        bws = binary(environ)
        if not bws:
            raise RefusalError(NO_BINARY)
        rows = listing(bws, environ)
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    ids: dict[Any, Any] = {r.get("key"): r.get("id") for r in rows}
    absent = [n for n, _l in specs if not ids.get(n)]
    if absent:
        print(
            "bws-env: store-from-env: not in the store, refusing to create: %s" % " ".join(absent),
            file=sys.stderr,
        )
        return 1
    for name, local in specs:
        proc = subprocess.run(
            [
                bws,
                "secret",
                "edit",
                "--value",
                os.environ[local],
                "--output",
                "none",
                "--color",
                "no",
                ids[name],
            ],
            capture_output=True,
            text=True,
            check=False,
            env=environ,
            timeout=LIST_TIMEOUT_S,
        )
        if proc.returncode != 0:
            print(
                "bws-env: store-from-env: editing %s failed (rc=%d)" % (name, proc.returncode),
                file=sys.stderr,
            )
            return 1
    try:
        rows = listing(bws, environ)
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    verdicts = compare_values(dict(os.environ), rows, specs)
    for local, verdict in verdicts:
        print("%s %s" % (local, verdict))
    return 0 if all(v == MATCH for _l, v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
