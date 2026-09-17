r"""check:ci-secret-supply -- where every declared-secret name's value actually
comes from, and the truncation spec for `private/account/.env`.

THE QUESTION NO GATE ASKED. `check:ci-env-manifest` classifies every environment
name by shard, and its `secret` shard means "supplied by the Bitwarden vault or
by a GitHub Actions secret". `check:ci-bws-map` asserts that every MAPPED secret
is requested by some workflow and every requested one is mapped. Between them
sits a set nobody looked at: the names the manifest DECLARES vault-supplied that
no vault holds. Measured 2026-09-09, the day this landed: 26 of 84. That is a RECEIPT with a
date on it, not an acceptance -- every number in the output is derived on the
run that prints it, so a reader watches them move instead of trusting this line.
Each one is a name whose supply is unstated, and "unstated" has covered four
genuinely different things here -- a token the runner mints per job, an SDK
spelling exported from a name the vault DOES hold, a value generated inside the
run that consumes it, and a real credential that lives only in one developer's
`private/account/.env`. The last kind is the one this box exists for.

THE TWO HALVES, AND WHY THEY ARE ONE GATE.

  RESIDUE (tracked, always runs).  `shards.secret \ map.secrets`, derived on
  every run from two tracked files, then matched against the `residue` object in
  `.ci/config/secret-supply.json` by SET EQUALITY IN BOTH DIRECTIONS. A name in
  the residue with no entry reds; an entry whose name is no longer in the residue
  reds. Those are the same two set differences the shrink-only baselines in this
  estate are built on, and stating both is what makes the file untrimmable: you
  cannot delete a line to buy a green, and you cannot bank a line for a violation
  that does not exist.

  DOTENV (destinations tracked, the file itself local).  One destination per name
  `private/account/.env` assigns. The terminal state is `BWS_ACCESS_TOKEN` plus
  `BWS_ACCESS_TOKEN_ROTATE` and nothing else, per `agent/PLAN-env-to-bitwarden.md`
  section (c). Every other name has somewhere else to come from, and the
  destination is a CHECKABLE CLAIM rather than a note.

THE HALVES CHECK EACH OTHER, WHICH IS WHY THEY SHARE A FILE AND A GATE:

  * `ci-shared` is false unless the vault map holds the name.
  * `dev-shared` and `admin-bootstrap` are false if it does -- a value seeded
    into `ci-shared` instead is a DEV credential in the PRODUCTION store, which
    is the exact confusion this box's plan line names ("Dev keys come from
    `dev-shared`, not from production"), so it reds rather than passing as done.
  * `dev.defaults.env` and `dev.local.env` are refused for any name the manifest
    classifies `secret`. That destination is a COMMITTED file; a credential
    routed there is one commit from being public.
  * `stays` is refused for anything but the one `bootstrap-irreducible` name.

So the dotenv table cannot be filled in with wishes, even though the file it
describes is invisible to CI.

WHAT IS RUNNABLE TODAY AND WHAT IS NOT, stated up front because the seeding is
blocked and a gate that pretends otherwise is worse than no gate. The `dev-shared`
project DOES NOT EXIST. Verified against the live vault on 2026-09-09: `bws`
2.1.0 has six verbs and no service-account verb, `bw` 2026.8.0 exposes only org
item moves, and the organization holds exactly ONE project, `ci-shared`, with all
58 secrets. Only the web vault can create a project, so the seeding is
`door:operator-only`.

THIS GATE DOES NOT WAIT FOR THAT. It is red-or-green today, on the tree as it is,
because what it checks is the AGREEMENT between the recorded state and the
derived state -- not the presence of the project. And it starts enforcing the
seeded state with no edit to itself: a seeded name lands in
`.ci/config/bws-secret-map.json` at the next refresh, leaves the derived residue,
and its entry reds as RESOLVED with instructions to drain it. The blocked names
are PRINTED BY NAME on every run, the way the landmark gate prints its two
exempt pages, so the debt cannot go quiet while it waits.

THE LOCAL ARM, AND THE HONEST STATEMENT OF ITS LIMIT. `private/account/.env` is
gitignored and `private/account` is a submodule the `quality-static` lane does
not even check out, so in CI this file cannot exist. Two rules follow, and both
are in the code rather than in this paragraph:

  * the VERDICT never comes from the local arm. Every clause above is tracked.
  * when the file is absent the run prints `LOCAL ARM SKIPPED` with the path and
    the reason. A skipped arm is never folded into the success line as if it had
    run, which is the whole of the "unknown is not fine" rule applied to an arm
    whose subject is legitimately absent half the time.

When the file IS present -- on a developer machine, which is where the truncation
actually happens -- the arm asserts set equality between the names it assigns and
the `dotenv.names` table. A name assigned locally with no destination reds; a
destination for a name the file no longer assigns reds as DRAINED. That second
direction is the one that keeps the truncation moving instead of accumulating a
table of names nobody has looked at since.

NAMES ONLY, NEVER VALUES, and it is enforced by shape rather than by care: the
only thing this module extracts from `.env` is the text to the LEFT of the first
`=`. `.ci/lib/bws-env.sh:16-18` states the same rule for the fetch helper and the
reason applies here with more force, because a gate's output is a log surface and
this repository is public. The one opaque identifier this file does carry is the
`ci-shared` project UUID, which `.ci/config/bws-secret-map.json` already holds in
the clear; it is pinned so that a map regenerated against a DIFFERENT project
reds instead of silently reshaping the residue.

ANTI-VACUITY, and none of it is `n > 0` on a number that is supposed to fall.

  * an empty `secret` shard, or an empty vault map, is a REFUSAL naming which
    one collapsed. Either alone makes the residue meaningless, and the
    subtraction would still produce a plausible-looking set.
  * an empty derived residue while the spec still claims entries is a REFUSAL,
    not a drain: that combination is the deriver having gone blind, and treating
    it as success would empty the file.
  * an empty residue with an empty spec is the (unreachable today, but legal)
    TERMINAL state and passes, printing zero. THE FLOOR IS NOT TYPED. A floor of
    "at least 26" is the finish-line trap: it goes red exactly when the migration
    it guards succeeds, and a clause that reds on success is a clause someone
    suppresses.
  * a `kind` used but not defined reds. A kind DEFINED but no longer used does
    NOT red, for the same reason: the last `dev-shared` entry leaving is what
    winning looks like. It is printed instead.

EVERY REASON IS LIVENESS-CHECKED, which is the `BLOCKER` convention applied to a
file that carries no suppressions. Each residue entry names an `evidence` path;
the gate requires that path to be TRACKED and to still mention the name. A
deleted file reds, and so does a file that stopped talking about the name -- the
reason has to keep being true, not merely have been true once. THE EVIDENCE IS A
PATH AND NEVER A LINE NUMBER, for the reason this repo's baselines are keyed on
text: a line number churns the moment a paragraph moves above it, and a citation
that churns gets "fixed" wholesale, which is how a stale claim gets re-blessed.

WHY `.ci/config/` AND NOT `.ci/policy/`, re-applying clause 1 of
`.ci/policy/README.md` section 1 rather than re-deriving it. A policy file is a
DECISION: a set of entries someone chose to EXEMPT, each carrying a BLOCKER
reason that stops a gate firing. This file exempts nothing. Nothing in it
suppresses a finding anywhere in the estate; deleting it makes this gate refuse,
not pass. Its residue half is DERIVED wholesale from two other tracked files and
then annotated, exactly as `language-policy-baseline.json` and
`tracked-credentials-baseline.json` are, and it sits beside them. There is also
the hard mechanical reason W8 P6 records: `.ci/policy/` is under four-way set
equality (`check:ci-policy-inventory`), so a file landing there without matching
edits to two `POLICY_FILES` tuples and the README reds on arrival.

WHAT THIS GATE DOES NOT CLAIM, so nobody reads more into a green than is there:

  * it does not talk to Bitwarden. Its view of the vault is
    `.ci/config/bws-secret-map.json`, which `check:ci-bws-map` keeps fresh and
    whose staleness that gate, not this one, enforces.
  * it does not know whether a value is correct, only where it is supposed to
    come from.
  * it cannot see `private/account/.env` in CI, and says so on every run.
  * a name absent from `env-manifest.json` altogether is outside the residue by
    construction. That is not a hole this gate can close: the manifest's corpus
    is tracked files only and by its own design an untracked `.env` is one
    machine's opinion. The count of local names the manifest cannot see is
    PRINTED by the local arm rather than asserted, so the blind spot has a number
    instead of a silence.

Exit 1 on any finding or refusal, 2 on a failed control.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant

SPEC_REL = ".ci/config/secret-supply.json"
MANIFEST_REL = ".ci/config/env-manifest.json"
MAP_REL = ".ci/config/bws-secret-map.json"
DOTENV_REL = "private/account/.env"

# The shard whose definition is "supplied by the vault or by a GitHub secret". NOT called SECRET_SHARD: ruff's S105 reads any constant whose NAME contains `secret` and whose value is a string literal as a hardcoded password, and the right answer to a false positive is a better name rather than a per-line suppression this repo's lint gate refuses anyway. Same reason the fixture
# names below say CRED and not SECRET.
STORE_SHARD = "secret"

# The names allowed to carry `bootstrap-irreducible`, and the only names the `stays` destination may take, come from the SPEC's `bootstrap_names` and not
# from a constant here. Two reasons, and the second is the one that matters.
#
# It is a RULING rather than a measurement -- `.ci/lib/bws-env.sh:44-48` records that no `bws` verb mints or rotates a machine-account token, so the credential that opens the store cannot live in the store -- and a ruling belongs beside the entries it governs, where a reader of the file can see it.
#
# AND A HARD-CODED NAME HERE WOULD BE THE FINISH-LINE TRAP. `must equal ["BWS_ACCESS_TOKEN"]` reds the day the residue half is fully drained and the entry is legitimately gone, which is the state this whole box is working towards. The clause below is a MEMBERSHIP test with no lower bound, so it is true in every state including the terminal one.
BOOTSTRAP_KIND = "bootstrap-irreducible"

# Destinations, and the tracked claim each one makes. `None` means the destination asserts nothing about vault membership.
#
# True -> the name MUST be in the vault map False -> the name must NOT be in the vault map
IN_VAULT = {
    "ci-shared": True,
    "dev-shared": False,
    "admin-bootstrap": False,
    "dev.defaults.env": False,
    "dev.local.env": False,
    "stays": False,
}

# Destinations that are a COMMITTED or on-disk plain file. A name the manifest calls `secret` may never be routed to one.
PLAINTEXT_DESTS = frozenset({"dev.defaults.env", "dev.local.env"})

# Destinations and kinds that are blocked on an operator action. Printed by name on every run, never folded into a count.
BLOCKED_DESTS = ("dev-shared", "admin-bootstrap")

# `NAME=`, optionally exported, optionally indented. THE ONLY THING TAKEN FROM
# THE FILE IS THE TEXT LEFT OF THE FIRST `=`. There is no capture group for the
# right-hand side, so no value can reach a variable, a message or a log by accident rather than by decision.
ASSIGN_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=", re.MULTILINE)


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


# --------------------------------------------------------------------------- pure helpers, exported so the controls can drive them without a filesystem ---------------------------------------------------------------------------


def dotenv_names(text: str) -> set[str]:
    """The names an env file ASSIGNS. Values are not captured, ever.

    A comment line is not an assignment: `# FOO=bar` has a `#` before the name
    and the anchored pattern rejects it, which matters because a commented-out
    credential is exactly what a half-finished truncation leaves behind and
    counting it would report the drain as incomplete forever.
    """
    return set(ASSIGN_RE.findall(text))


def derive_residue(shard: set[str], vault: set[str]) -> set[str]:
    """Names DECLARED vault-supplied that no vault holds. Pure set arithmetic."""
    return shard - vault


def tracked_files(root: pathlib.Path) -> set[str]:
    """Every tracked path, for the evidence liveness check.

    `git ls-files` and not a directory walk, for the reason `paths.py` answers
    from a tracked path set: an untracked file is one machine's opinion, and an
    evidence citation that resolves only on the author's laptop is not a
    citation.
    """
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RefusalError(
            "`git ls-files` failed in %s (rc=%d). Without the tracked set the evidence "
            "citations cannot be checked at all, and a green would mean nothing."
            % (root, out.returncode)
        )
    tracked = {p for p in out.stdout.split("\0") if p}
    if not tracked:
        raise RefusalError(
            "`git ls-files` returned nothing in %s. Zero tracked files is the instrument "
            "having lost the tree, not a tree with no files: every evidence citation "
            "would report as DEAD and the wall of findings would say nothing true." % root
        )
    return tracked


def evaluate_residue(spec, residue: set[str], vault: set[str]) -> list[str]:
    """Set equality with the derived residue, in both directions, plus the kinds.

    NEW is `residue \\ spec`: a name the manifest calls vault-supplied, that no
    vault holds, and that nothing here explains. It is ALSO what happens when
    someone deletes an entry, which is why deleting one cannot buy a green.

    RESOLVED is `spec \\ residue`: an entry whose name is no longer in the
    residue. That is the SUCCESS shape -- it is what a completed seeding looks
    like from here -- and it is also what a pre-banked entry looks like, so it
    reds either way and the message names both readings.
    """
    entries = spec["residue"]
    kinds = spec["kinds"]
    findings = []

    findings.extend(
        "UNSTATED %s -- %s classifies it `%s`, meaning the vault or a GitHub secret "
        "supplies it, and %s does not hold it. Say where the value really comes from by "
        "adding an entry with a kind and an evidence path. If you got here by DELETING "
        "that entry, put it back: trimming this file is not a way past the gate, and "
        "this finding is what proves it." % (name, MANIFEST_REL, STORE_SHARD, MAP_REL)
        for name in sorted(residue - set(entries))
    )
    findings.extend(
        "RESOLVED %s -- this file explains where the value comes from, and the name is "
        "no longer in the derived residue. Either it is now IN %s (the seeding landed: "
        "delete this entry, and drain its `dotenv` row too) or it left the `%s` shard of "
        "%s (reclassified: delete this entry). An entry for a name that is not in the "
        "residue is also what pre-banking looks like, which is the other thing refused "
        "here." % (name, MAP_REL, STORE_SHARD, MANIFEST_REL)
        for name in sorted(set(entries) - residue)
    )

    for name in sorted(entries):
        entry = entries[name]
        kind = entry.get("kind")
        if kind not in kinds:
            findings.append(
                "UNDEFINED KIND %s: `%s` is not one of the kinds this file defines (%s). "
                "A kind nobody defined is a classification nobody agreed to."
                % (name, kind, ", ".join(sorted(kinds)))
            )
        if not str(entry.get("why", "")).strip():
            findings.append(
                "NO REASON %s: every entry states why its supply is what it is. An "
                "unreasoned classification is the shape a suppression takes when nobody "
                "is looking." % name
            )
        alias = entry.get("alias_of")
        if kind == "sdk-alias":
            if not alias:
                findings.append(
                    "ALIAS OF NOTHING %s: kind `sdk-alias` means the value comes from "
                    "another name; say which with `alias_of`." % name
                )
            elif alias not in vault:
                findings.append(
                    "DANGLING ALIAS %s -> %s: the alias target is not in %s, so this "
                    "entry claims the value comes from somewhere that does not hold it."
                    % (name, alias, MAP_REL)
                )
        elif alias:
            findings.append(
                "STRAY alias_of ON %s: only an `sdk-alias` entry may name one, and this "
                "is `%s`." % (name, kind)
            )
        if kind == "dev-shared" and entry.get("door") != "operator-only":
            findings.append(
                "UNDOORED %s: kind `dev-shared` is blocked on a project only the web "
                'vault can create, so the entry must carry "door": "operator-only". '
                "A block with no door recorded is a block that gets forgotten." % name
            )

    allowed = set(spec.get("bootstrap_names") or ())
    findings.extend(
        "UNRULED BOOTSTRAP %s: kind `%s` says this credential cannot come from the "
        "store it unlocks, and the file's `bootstrap_names` ruling does not list it "
        "(%s). A second name quietly opting out of the migration is exactly what that "
        "kind would look like." % (name, BOOTSTRAP_KIND, ", ".join(sorted(allowed)) or "empty")
        for name in sorted(entries)
        if entries[name].get("kind") == BOOTSTRAP_KIND and name not in allowed
    )
    findings.extend(
        "BOOTSTRAP IN THE STORE %s: `bootstrap_names` says it cannot come from the "
        "store it unlocks, and %s holds it. Either the ruling is wrong or a credential "
        "was seeded into the project it is meant to open." % (name, MAP_REL)
        for name in sorted(allowed & vault)
    )
    return findings


def evaluate_evidence(spec, tracked: set[str], read_text) -> list[str]:
    """Liveness for every citation: the path is tracked, and still names the name.

    This is the `BLOCKER` convention's liveness half applied to a file that
    suppresses nothing. A reason that has stopped being true is worse than no
    reason, because it reads as having been checked.
    """
    findings = []
    for name in sorted(spec["residue"]):
        rel = spec["residue"][name].get("evidence")
        if not rel:
            findings.append(
                "NO EVIDENCE %s: every entry cites one tracked file that shows where the "
                "value comes from." % name
            )
            continue
        if rel not in tracked:
            findings.append(
                "DEAD EVIDENCE %s -> %s: that path is not tracked. The citation cannot "
                "be checked, so the reason cannot be trusted." % (name, rel)
            )
            continue
        if not re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name), read_text(rel)):
            findings.append(
                "STALE EVIDENCE %s -> %s: the file is there and no longer mentions the "
                "name. Re-read it and cite what is true now; do not just repoint it." % (name, rel)
            )
    return findings


def evaluate_dotenv(spec, vault: set[str], shard: set[str]) -> list[str]:
    """The destination table's TRACKED claims. Runs with or without the .env.

    Every clause here is a statement about `bws-secret-map.json` or about the
    env manifest, so the table is enforced in CI even though the file it
    describes cannot exist there.
    """
    names = spec["dotenv"]["names"]
    dests = spec["dotenv"]["destinations"]
    bootstrap = set(spec.get("bootstrap_names") or ())
    # NOTES ARE OPTIONAL AND SPARSE ON PURPOSE. 49 machine-written sentences about destinations would be filler, and filler is how a required field stops being
    # read; a note exists only where the destination is counter-intuitive. What is
    # NOT optional is that a note names a row that exists -- a note for a drained name is a reason still arguing about something that left.
    notes = spec["dotenv"].get("notes") or {}
    findings = []
    findings.extend(
        "DANGLING NOTE %s: `dotenv.notes` explains a name `dotenv.names` does not "
        "route. Delete the note with the row." % name
        for name in sorted(set(notes) - set(names))
    )
    for name in sorted(names):
        dest = names[name]
        if dest not in dests:
            findings.append(
                "UNDEFINED DESTINATION %s -> `%s`: not one of %s."
                % (name, dest, ", ".join(sorted(dests)))
            )
            continue
        want = IN_VAULT.get(dest)
        if want is True and name not in vault:
            findings.append(
                "FALSE DESTINATION %s -> ci-shared: %s does not hold that name, so the "
                "claim that the value is already in the vault is false. Seed it, or give "
                "it the destination it really has." % (name, MAP_REL)
            )
        if want is False and name in vault:
            findings.append(
                "FALSE DESTINATION %s -> %s: %s already holds that name. If the seeding "
                "landed, the destination is now `ci-shared` and this row must say so; if "
                "a DEV value was seeded into `ci-shared`, that is the production store "
                "and the value is in the wrong place." % (name, dest, MAP_REL)
            )
        if dest in PLAINTEXT_DESTS and name in shard:
            findings.append(
                "CREDENTIAL ROUTED TO A PLAIN FILE %s -> %s: %s classifies it `%s`. That "
                "destination is a file on disk, and for `dev.defaults.env` a COMMITTED "
                "one. Route it to a store." % (name, dest, MANIFEST_REL, STORE_SHARD)
            )
        if name in notes and not str(notes[name]).strip():
            findings.append(
                "EMPTY NOTE %s: a note that says nothing is worse than no note, because "
                "it reads as having been thought about." % name
            )
        if dest == "stays" and name not in bootstrap:
            findings.append(
                "OVERSTAY %s -> stays: the terminal state of %s is the `bootstrap_names` "
                "ruling and nothing else (%s). Every other name leaves."
                % (name, DOTENV_REL, ", ".join(sorted(bootstrap)) or "empty")
            )
    return findings


def evaluate_local(spec, assigned: set[str]) -> list[str]:
    """Set equality between the real `.env` and the destination table.

    Only reachable on a machine that HAS the file. The caller decides that; this
    stays pure so the controls can drive both directions without one.
    """
    names = set(spec["dotenv"]["names"])
    findings = []
    findings.extend(
        "UNROUTED %s -- %s assigns it and the truncation spec has no destination for it. "
        "Every name in that file needs somewhere else to come from, including a new one. "
        "Deleting a row is not a destination either: this is what that looks like."
        % (name, DOTENV_REL)
        for name in sorted(assigned - names)
    )
    findings.extend(
        "DRAINED %s -- the spec routes it and %s no longer assigns it. The move happened: "
        "delete the row. Edit the single line by hand rather than regenerating the table, "
        "so another writer's fresh rows are not absorbed with it." % (name, DOTENV_REL)
        for name in sorted(names - assigned)
    )
    return findings


# --------------------------------------------------------------------------- reading the tree ---------------------------------------------------------------------------


def _load(root: pathlib.Path, rel: str):
    path = root / rel
    if not path.is_file():
        raise RefusalError(
            "%s does not exist. This gate compares three tracked files against each "
            "other; with one missing there is nothing to compare, and its absence is "
            "otherwise the cheapest way to make every finding disappear at once." % rel
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError(
            "%s exists but cannot be read (%s). A corrupt input is not an empty one: "
            "every entry would report as a finding. Repair the JSON." % (rel, exc)
        ) from exc


def read_spec(root: pathlib.Path):
    """The spec, with its shape checked. A shape error is a refusal, not a finding."""
    spec = _load(root, SPEC_REL)
    for key, kind in (("kinds", dict), ("residue", dict), ("dotenv", dict)):
        if not isinstance(spec.get(key), kind):
            raise RefusalError("%s has no %s under %r" % (SPEC_REL, kind.__name__, key))
    for key in ("names", "destinations"):
        if not isinstance(spec["dotenv"].get(key), dict):
            raise RefusalError("%s: `dotenv` has no object under %r" % (SPEC_REL, key))
    for name, entry in spec["residue"].items():
        if not isinstance(entry, dict):
            raise RefusalError("%s: the entry for %r is not an object" % (SPEC_REL, name))
    names = spec.get("bootstrap_names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise RefusalError(
            "%s has no non-empty list of strings under `bootstrap_names`. That list IS "
            "the ruling about which credentials may stay in %s; with it absent, `stays` "
            "would mean whatever the reader wanted and nothing would be checked."
            % (SPEC_REL, DOTENV_REL)
        )
    return spec


def run(root=None):
    """(findings, stats) for the real tree. Refuses rather than guessing."""
    root = pathlib.Path(root or paths.repo_root())
    spec = read_spec(root)
    manifest = _load(root, MANIFEST_REL)
    vault_doc = _load(root, MAP_REL)

    shard = set(manifest.get("shards", {}).get(STORE_SHARD) or [])
    vault = set(vault_doc.get("secrets") or [])
    if not shard:
        raise RefusalError(
            "the `%s` shard of %s is empty. The residue is that shard MINUS the vault, "
            "so an empty shard yields an empty residue and a green that means nothing."
            % (STORE_SHARD, MANIFEST_REL)
        )
    if not vault:
        raise RefusalError(
            "%s lists no secrets. Subtracting an empty vault would report the whole "
            "`%s` shard as unstated, and a refresh that produced an empty map is a "
            "broken refresh, not an empty vault." % (MAP_REL, STORE_SHARD)
        )

    pinned = spec.get("ci_shared_project")
    if pinned and vault_doc.get("project") != pinned:
        raise RefusalError(
            "%s was generated against project %r and %s pins %r. The residue is derived "
            "by subtracting that map; a map for a DIFFERENT project reshapes it for a "
            "reason that has nothing to do with the tree. If a second project now exists, "
            "the map has to say which secret came from which before this gate can "
            "subtract it." % (MAP_REL, vault_doc.get("project"), SPEC_REL, pinned)
        )

    residue = derive_residue(shard, vault)
    if not residue and spec["residue"]:
        raise RefusalError(
            "ZERO residue derived from a %d-name `%s` shard and a %d-name vault map, "
            "while %s still explains %d name(s). Every entry would report as RESOLVED "
            "and the drain would empty the file. That is the deriver having gone blind, "
            "not the migration having finished."
            % (len(shard), STORE_SHARD, len(vault), SPEC_REL, len(spec["residue"]))
        )

    tracked = tracked_files(root)
    findings = evaluate_residue(spec, residue, vault)
    findings += evaluate_evidence(
        spec, tracked, lambda rel: (root / rel).read_text(encoding="utf-8", errors="replace")
    )
    findings += evaluate_dotenv(spec, vault, shard)

    stats = {
        "shard": len(shard),
        "vault": len(vault),
        "residue": len(residue),
        "kinds_used": len({e.get("kind") for e in spec["residue"].values()}),
        "kinds_defined": len(spec["kinds"]),
        "routed": len(spec["dotenv"]["names"]),
        "notes": len(spec["dotenv"].get("notes") or {}),
        "local": None,
        "local_invisible": None,
    }

    dotenv = root / DOTENV_REL
    if dotenv.is_file():
        assigned = dotenv_names(dotenv.read_text(encoding="utf-8", errors="replace"))
        findings += evaluate_local(spec, assigned)
        stats["local"] = len(assigned)
        # The manifest's corpus is tracked files only, so a name that lives ONLY in this untracked file is invisible to it. Counted, never asserted: the blind spot gets a number instead of a silence.
        every_shard = {n for names in manifest.get("shards", {}).values() for n in names}
        stats["local_invisible"] = len(assigned - every_shard)
    return findings, stats, spec


# --------------------------------------------------------------------------- output ---------------------------------------------------------------------------


def blocked_rows(spec) -> list[tuple[str, list[str]]]:
    """The operator-blocked names, by destination, for printing BY NAME."""
    names = spec["dotenv"]["names"]
    return [(dest, sorted(n for n, d in names.items() if d == dest)) for dest in BLOCKED_DESTS]


def report(spec, stats) -> None:
    """The shape, printed whether or not there were findings.

    "251 gates, 2 workflow scopes, 8 exempt" lets a reader notice when a number
    collapses; "OK" does not. The blocked names are printed IN FULL rather than
    counted, for the same reason the landmark gate prints its two exempt pages
    every run.
    """
    log.info(
        "  %d name(s) in the `%s` shard, %d in %s, so %d unstated; %d kind(s) used of "
        "%d defined; %d name(s) routed out of %s"
        % (
            stats["shard"],
            STORE_SHARD,
            stats["vault"],
            MAP_REL,
            stats["residue"],
            stats["kinds_used"],
            stats["kinds_defined"],
            stats["routed"],
            DOTENV_REL,
        )
    )
    log.info(
        "  %d destination(s) carry a note, because the destination is not what the name "
        "suggests" % stats["notes"]
    )
    # `warn`, not `info`. A green tick beside a list of blocked credentials reads as approval, and the whole reason these are printed in full rather than counted is so a reader keeps seeing them as debt.
    for dest, rows in blocked_rows(spec):
        if rows:
            log.warn(
                "  OPERATOR-BLOCKED, door:operator-only, %s does not exist: %d name(s) "
                "-> %s" % (dest, len(rows), ", ".join(rows))
            )
    if stats["local"] is None:
        log.warn(
            "  LOCAL ARM SKIPPED: %s is not on disk, so the set equality between that "
            "file and the destination table did NOT run. It is gitignored and its "
            "submodule is not checked out in the quality lane, so this is expected in "
            "CI. Every clause above is over tracked files and does not depend on it." % DOTENV_REL
        )
    else:
        log.info(
            "  LOCAL ARM RAN: %s assigns %d name(s), all routed; %d of them are in no "
            "shard of %s at all, because its corpus is tracked files only."
            % (DOTENV_REL, stats["local"], stats["local_invisible"], MANIFEST_REL)
        )


def main(argv=None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("secret supply", selftest)
    if rc:
        return rc
    try:
        findings, stats, spec = run()
    except RefusalError as exc:
        log.error("secret supply: %s" % exc)
        return 1
    report(spec, stats)
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s) against %s. Do not add one to the file to make it go away: "
            "both halves are set-equal with the tree, so a row that does not correspond "
            "to something real reds in the other direction." % (len(findings), SPEC_REL)
        )
        return 1
    log.success(
        "secret supply: %d unstated name(s) all classified and cited, and %d .env "
        "name(s) all routed, matching %s in both directions"
        % (stats["residue"], stats["routed"], SPEC_REL)
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------
#
# BOTH DIRECTIONS, ON BOTH HALVES. A gate with only positive controls will happily flag the whole tree, and a set-equal spec with only the "missing entry" direction can be trimmed to green. Every mutation below goes through `plant()`, which raises when a substitution would not have changed anything, so no control here can pass against unmutated input.

_MANIFEST = {
    "shards": {
        "secret": ["FIX_HELD", "FIX_UNSTATED", "FIX_ALIAS_SRC", "FIX_ROUTED_CRED"],
        "harness": ["FIX_PLAIN"],
    }
}
_MAP = {"project": "fixture-project", "secrets": {"FIX_HELD": {}, "FIX_ALIAS_SRC": {}}}
_SPEC = {
    "ci_shared_project": "fixture-project",
    "bootstrap_names": ["FIX_UNSTATED"],
    "kinds": {
        "bootstrap-irreducible": "the one that cannot come from the store it opens",
        "sdk-alias": "a second spelling of a held name",
        "dev-shared": "blocked on a project that does not exist",
        "unused-kind": "defined and used by nothing, which is legal and printed",
    },
    "residue": {
        "FIX_UNSTATED": {
            "kind": "bootstrap-irreducible",
            "evidence": "evidence.txt",
            "why": "the fixture's bootstrap credential",
        },
        "FIX_ALIAS": {
            "kind": "sdk-alias",
            "alias_of": "FIX_ALIAS_SRC",
            "evidence": "evidence.txt",
            "why": "the fixture's SDK spelling",
        },
        "FIX_ROUTED_CRED": {
            "kind": "dev-shared",
            "door": "operator-only",
            "evidence": "evidence.txt",
            "why": "the fixture's blocked dev credential",
        },
    },
    "dotenv": {
        "path": "private/account/.env",
        "destinations": {
            "stays": "stays",
            "ci-shared": "already in the vault",
            "dev-shared": "blocked",
            "dev.defaults.env": "a committed plain file",
        },
        "names": {
            "FIX_HELD": "ci-shared",
            "FIX_PLAIN": "dev.defaults.env",
            "FIX_ROUTED_CRED": "dev-shared",
        },
    },
}

# `FIX_ALIAS` is deliberately in the spec's residue and NOT in the shard, so the clean fixture would red as RESOLVED unless the shard carries it. It does not: that asymmetry IS the RESOLVED control below, and the clean fixture adds it.
_MANIFEST["shards"]["secret"].append("FIX_ALIAS")


def _fixture(tmp, spec=None, manifest=None, vault_map=None, dotenv=None):
    """A real git repository, because the evidence check reads `git ls-files`."""
    import copy  # noqa: PLC0415

    root = pathlib.Path(tmp)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    docs = {
        SPEC_REL: copy.deepcopy(spec if spec is not None else _SPEC),
        MANIFEST_REL: copy.deepcopy(manifest if manifest is not None else _MANIFEST),
        MAP_REL: copy.deepcopy(vault_map if vault_map is not None else _MAP),
    }
    for rel, obj in docs.items():
        (root / rel).write_text(json.dumps(obj, indent=2), encoding="utf-8")
    (root / "evidence.txt").write_text(
        "FIX_UNSTATED and FIX_ALIAS and FIX_ROUTED_CRED all appear here.\n",
        encoding="utf-8",
    )
    if dotenv is not None:
        (root / "private" / "account").mkdir(parents=True, exist_ok=True)
        (root / DOTENV_REL).write_text(dotenv, encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f", ".ci", "evidence.txt"]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    return root


def _refuses(root) -> bool:
    try:
        run(root)
    except RefusalError:
        return True
    return False


def _findings(root) -> list[str]:
    return run(root)[0]


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    import copy  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    check = Checker()

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        findings, stats, spec = run(root)
        check("CONTROL: a spec that matches its inputs is clean", findings == [])
        check(
            "CONTROL: and the scan is NOT trivially empty",
            (stats["shard"], stats["vault"], stats["residue"], stats["routed"]) == (5, 2, 3, 3),
        )
        check(
            "CONTROL: a kind DEFINED and used by nothing is legal, not a finding",
            stats["kinds_defined"] == 4 and stats["kinds_used"] == 3,
        )
        check(
            "CONTROL: with no .env on disk the local arm is SKIPPED, not passed",
            stats["local"] is None,
        )
        check(
            "CONTROL: the blocked names are available BY NAME, not as a count",
            dict(blocked_rows(spec))["dev-shared"] == ["FIX_ROUTED_CRED"],
        )

    # ---- THE ARM THAT USUALLY GOES MISSING, direction 1 -------------------- Deleting an entry whose violation is still present must RED. A file that can be trimmed to escape the gate is not a baseline.
    with tempfile.TemporaryDirectory() as tmp:
        trimmed = copy.deepcopy(_SPEC)
        del trimmed["residue"]["FIX_UNSTATED"]
        root = _fixture(tmp, spec=trimmed)
        findings = _findings(root)
        check(
            "TAMPER 1: DELETING a residue entry whose name is still unstated reds",
            any(f.startswith("UNSTATED FIX_UNSTATED") for f in findings),
        )
        check(
            "TAMPER 1: and the message says trimming is not a way past the gate",
            any("trimming this file is not a way past" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        emptied = copy.deepcopy(_SPEC)
        emptied["residue"] = {}
        root = _fixture(tmp, spec=emptied)
        findings = _findings(root)
        check(
            "TAMPER 1b: emptying the residue half reds once per name, it does not pass",
            len([f for f in findings if f.startswith("UNSTATED ")]) == 3,
        )

    with tempfile.TemporaryDirectory() as tmp:
        trimmed = copy.deepcopy(_SPEC)
        del trimmed["dotenv"]["names"]["FIX_HELD"]
        root = _fixture(tmp, spec=trimmed, dotenv="FIX_HELD=x\nFIX_PLAIN=y\nFIX_ROUTED_CRED=z\n")
        findings = _findings(root)
        check(
            "TAMPER 1c: DELETING a dotenv row whose name is still assigned reds",
            any(f.startswith("UNROUTED FIX_HELD") for f in findings),
        )

    # ---- THE ARM THAT USUALLY GOES MISSING, direction 2 -------------------- An entry added for a violation that does not exist must red too.
    with tempfile.TemporaryDirectory() as tmp:
        banked = copy.deepcopy(_SPEC)
        banked["residue"]["FIX_NEVER"] = {
            "kind": "dev-shared",
            "door": "operator-only",
            "evidence": "evidence.txt",
            "why": "banked for a name that is not in the residue",
        }
        root = _fixture(tmp, spec=banked)
        findings = _findings(root)
        check(
            "TAMPER 2: BANKING an entry for a name outside the residue reds as RESOLVED",
            any(f.startswith("RESOLVED FIX_NEVER") for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, dotenv="FIX_HELD=x\nFIX_PLAIN=y\n")
        findings = _findings(root)
        check(
            "TAMPER 2b: a dotenv row for a name the file no longer assigns reds as DRAINED",
            any(f.startswith("DRAINED FIX_ROUTED_CRED") for f in findings),
        )

    # ---- THE SEEDING ARM: it starts enforcing the moment the project exists -
    with tempfile.TemporaryDirectory() as tmp:
        seeded = copy.deepcopy(_MAP)
        seeded["secrets"]["FIX_ROUTED_CRED"] = {}
        root = _fixture(tmp, vault_map=seeded)
        findings = _findings(root)
        check(
            "SEEDED: a name that lands in the vault reds as RESOLVED with no gate edit",
            any(f.startswith("RESOLVED FIX_ROUTED_CRED") for f in findings),
        )
        check(
            "SEEDED: and its dotenv row reds too, so both halves have to be drained",
            any(f.startswith("FALSE DESTINATION FIX_ROUTED_CRED -> dev-shared") for f in findings),
        )

    # ---- destination claims are CHECKED, not believed ----------------------
    with tempfile.TemporaryDirectory() as tmp:
        lying = copy.deepcopy(_SPEC)
        lying["dotenv"]["names"]["FIX_PLAIN"] = "ci-shared"
        root = _fixture(tmp, spec=lying)
        check(
            "CONTROL: a `ci-shared` destination the vault does not hold reds",
            any(f.startswith("FALSE DESTINATION FIX_PLAIN -> ci-shared") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        leaky = copy.deepcopy(_SPEC)
        leaky["dotenv"]["names"]["FIX_ROUTED_CRED"] = "dev.defaults.env"
        root = _fixture(tmp, spec=leaky)
        check(
            "CONTROL: routing a `secret`-shard name to a COMMITTED plain file reds",
            any(
                f.startswith("CREDENTIAL ROUTED TO A PLAIN FILE FIX_ROUTED_CRED")
                for f in _findings(root)
            ),
        )

    with tempfile.TemporaryDirectory() as tmp:
        dangling = copy.deepcopy(_SPEC)
        dangling["dotenv"]["notes"] = {"FIX_GONE": "a note for a row that is not there"}
        root = _fixture(tmp, spec=dangling)
        check(
            "CONTROL: a note explaining a name nothing routes reds",
            any(f.startswith("DANGLING NOTE FIX_GONE") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        blank = copy.deepcopy(_SPEC)
        blank["dotenv"]["notes"] = {"FIX_HELD": "  "}
        root = _fixture(tmp, spec=blank)
        check(
            "CONTROL: an empty note reds rather than reading as considered",
            any(f.startswith("EMPTY NOTE FIX_HELD") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        noted = copy.deepcopy(_SPEC)
        noted["dotenv"]["notes"] = {"FIX_HELD": "a live note on a routed name"}
        root = _fixture(tmp, spec=noted)
        findings, stats, _ = run(root)
        check(
            "ANTI-SILENCER: a note on a routed name is legal and counted, not a finding",
            findings == [] and stats["notes"] == 1,
        )

    with tempfile.TemporaryDirectory() as tmp:
        overstay = copy.deepcopy(_SPEC)
        overstay["dotenv"]["names"]["FIX_HELD"] = "stays"
        root = _fixture(tmp, spec=overstay)
        check(
            "CONTROL: a second name claiming `stays` reds; the terminal state is one name",
            any(f.startswith("OVERSTAY FIX_HELD") for f in _findings(root)),
        )

    # ---- the reasons are LIVENESS-CHECKED ----------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        text = (root / "evidence.txt").read_text(encoding="utf-8")
        (root / "evidence.txt").write_text(plant(text, "FIX_ALIAS and ", ""), encoding="utf-8")
        check(
            "CONTROL: evidence that stopped mentioning the name reds as STALE",
            any(f.startswith("STALE EVIDENCE FIX_ALIAS ->") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        dangling = copy.deepcopy(_SPEC)
        dangling["residue"]["FIX_UNSTATED"]["evidence"] = "gone.txt"
        root = _fixture(tmp, spec=dangling)
        check(
            "CONTROL: evidence pointing at an untracked path reds as DEAD",
            any(f.startswith("DEAD EVIDENCE FIX_UNSTATED -> gone.txt") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        untracked = root / "untracked.txt"
        untracked.write_text("FIX_UNSTATED lives here\n", encoding="utf-8")
        spec_path = root / SPEC_REL
        spec_path.write_text(
            plant(
                spec_path.read_text(encoding="utf-8"),
                '"evidence": "evidence.txt"',
                '"evidence": "untracked.txt"',
                count=1,
            ),
            encoding="utf-8",
        )
        check(
            "ANTI-SILENCER: an UNTRACKED evidence file does not satisfy the citation",
            any(
                f.startswith("DEAD EVIDENCE FIX_UNSTATED -> untracked.txt") for f in _findings(root)
            ),
        )

    # ---- kind and shape refusals -------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        bad = copy.deepcopy(_SPEC)
        bad["residue"]["FIX_ALIAS"]["kind"] = "invented-kind"
        root = _fixture(tmp, spec=bad)
        findings = _findings(root)
        check(
            "CONTROL: a kind nobody defined reds",
            any(f.startswith("UNDEFINED KIND FIX_ALIAS") for f in findings),
        )
        check(
            "CONTROL: and the alias target check comes with it, not instead of it",
            any(f.startswith("STRAY alias_of ON FIX_ALIAS") for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        bad = copy.deepcopy(_SPEC)
        bad["residue"]["FIX_ALIAS"]["alias_of"] = "FIX_NOT_IN_VAULT"
        root = _fixture(tmp, spec=bad)
        check(
            "CONTROL: an alias pointing at a name no vault holds reds",
            any(
                f.startswith("DANGLING ALIAS FIX_ALIAS -> FIX_NOT_IN_VAULT")
                for f in _findings(root)
            ),
        )

    with tempfile.TemporaryDirectory() as tmp:
        bad = copy.deepcopy(_SPEC)
        del bad["residue"]["FIX_ROUTED_CRED"]["door"]
        root = _fixture(tmp, spec=bad)
        check(
            "CONTROL: a `dev-shared` entry with no door recorded reds",
            any(f.startswith("UNDOORED FIX_ROUTED_CRED") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        bad = copy.deepcopy(_SPEC)
        bad["residue"]["FIX_ALIAS"]["kind"] = BOOTSTRAP_KIND
        bad["residue"]["FIX_ALIAS"].pop("alias_of")
        root = _fixture(tmp, spec=bad)
        check(
            "CONTROL: a SECOND bootstrap-irreducible name, outside the ruling, reds",
            any(f.startswith("UNRULED BOOTSTRAP FIX_ALIAS") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        seeded = copy.deepcopy(_MAP)
        seeded["secrets"]["FIX_UNSTATED"] = {}
        root = _fixture(tmp, vault_map=seeded)
        check(
            "CONTROL: seeding the BOOTSTRAP credential into the store it opens reds",
            any(f.startswith("BOOTSTRAP IN THE STORE FIX_UNSTATED") for f in _findings(root)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / SPEC_REL).write_text(
            plant(
                (root / SPEC_REL).read_text(encoding="utf-8"),
                '"bootstrap_names": [\n    "FIX_UNSTATED"\n  ],',
                "",
            ),
            encoding="utf-8",
        )
        check(
            "REFUSAL: deleting the `bootstrap_names` ruling refuses, it does not widen "
            "`stays` to mean anything",
            _refuses(root),
        )

    with tempfile.TemporaryDirectory() as tmp:
        bad = copy.deepcopy(_SPEC)
        bad["residue"]["FIX_UNSTATED"]["why"] = "   "
        root = _fixture(tmp, spec=bad)
        check(
            "CONTROL: an entry with a blank reason reds",
            any(f.startswith("NO REASON FIX_UNSTATED") for f in _findings(root)),
        )

    # ---- anti-vacuity refusals ---------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        blind = copy.deepcopy(_MANIFEST)
        blind["shards"]["secret"] = []
        check(
            "REFUSAL: an empty `secret` shard is a refusal, not an empty residue",
            _refuses(_fixture(tmp, manifest=blind)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        blind = copy.deepcopy(_MAP)
        blind["secrets"] = {}
        check(
            "REFUSAL: an empty vault map is a refusal, not 5 unstated names",
            _refuses(_fixture(tmp, vault_map=blind)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        swallowed = copy.deepcopy(_MAP)
        swallowed["secrets"] = {n: {} for n in _MANIFEST["shards"]["secret"]}
        check(
            "REFUSAL: a residue that derives to ZERO while the spec claims entries "
            "is the deriver going blind, not the migration finishing",
            _refuses(_fixture(tmp, vault_map=swallowed)),
        )

    # THE TERMINAL STATE, BUILT HONESTLY. Everything seeded, the truncation done, and the bootstrap credential OUT of the secret shard rather than into the store it opens -- which is the only shape in which the residue can reach zero, and the reason the clause above is a membership test and not a floor.
    with tempfile.TemporaryDirectory() as tmp:
        terminal = copy.deepcopy(_SPEC)
        terminal["residue"] = {}
        terminal["dotenv"]["names"] = {}
        done = copy.deepcopy(_MANIFEST)
        done["shards"]["secret"] = ["FIX_HELD", "FIX_ALIAS_SRC"]
        swallowed = copy.deepcopy(_MAP)
        swallowed["secrets"] = {n: {} for n in done["shards"]["secret"]}
        root = _fixture(tmp, spec=terminal, manifest=done, vault_map=swallowed)
        findings, stats, _ = run(root)
        check(
            "ANTI-SILENCER: an EMPTY residue with an EMPTY spec is the legal terminal "
            "state and passes, so the floor cannot red on success",
            findings == [] and stats["residue"] == 0,
        )

    with tempfile.TemporaryDirectory() as tmp:
        moved = copy.deepcopy(_MAP)
        moved["project"] = "some-other-project"
        check(
            "REFUSAL: a map generated against a different project is a refusal",
            _refuses(_fixture(tmp, vault_map=moved)),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / SPEC_REL).unlink()
        check("REFUSAL: deleting the spec refuses, it does not pass", _refuses(root))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        shutil.rmtree(root / ".git")
        check(
            "REFUSAL: zero tracked files is the instrument losing the tree, not 3 dead citations",
            _refuses(root),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / SPEC_REL).write_text("{not json", encoding="utf-8")
        check("REFUSAL: a corrupt spec refuses, it is not read as empty", _refuses(root))

    # ---- the .env parser, both directions ----------------------------------
    check(
        "PARSER: an assignment is a name",
        dotenv_names("FOO=1\n  export BAR=2\n\tBAZ=3\n") == {"FOO", "BAR", "BAZ"},
    )
    check(
        "ANTI-SILENCER: a COMMENTED-OUT assignment is not a name, so a half-finished "
        "truncation is not reported as incomplete forever",
        dotenv_names("# FOO=1\n#export BAR=2\n") == set(),
    )
    check(
        "ANTI-SILENCER: prose mentioning a name is not an assignment",
        dotenv_names("the value of FOO is set elsewhere\n") == set(),
    )
    check(
        "ANTI-SILENCER: the parser captures NO value, by shape and not by care",
        ASSIGN_RE.groups == 1,
    )

    return not check.ok


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
