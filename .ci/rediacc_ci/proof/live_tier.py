"""The live tier of agent/plans/PLAN-tested-on-bench.md Design items 1, 4 and 6: the check registry, the live row body on top of `receipt`'s envelope, the ledger read, the match and the judge `rediacc_ci.ops.live_proof verify` and `check:ci-plan-live-proof` share.

THE REGISTRY. `tiers.live.checks` in `.ci/config/proof-tiers.json` maps a check id to its `targets`, the `surfaces` it covers, how its deploy is identified (`deploy`) and a list of `steps`, each a FIXED argv. The only parameters are values the map itself names: `{origin}` (the value of the target's `origin_wk`, a key of `.ci/config/well-known.env`, never a literal URL) and `{config}` from `tiers.live.targets.<target>`, and `{machine}`, one alias of `tiers.live.targets.<target>.machines`, for a check marked `per_machine`. There are no free arguments: `parse_checks` refuses an unknown placeholder, a shell or a no-op as a step's program, and a surface no target of the check admits. `expand` is the only way to an argv, and `validate_row` re-expands a row's check and refuses any argv that differs, so a hand-edited command cannot pass.

THE ARGV IS JUDGED AT THE ROW'S OWN TREE. An argv is a function of three files: the map's `tiers.live` block, `.ci/config/well-known.env` (the `origin_wk` values) and `regions.json` (a regional bench). A later commit may legitimately move any of them (PLAN-multi-region-bench M1 moved WK_BENCH_ORIGIN to bench-eu), and a receipt is a fact about the run it recorded, so with a `root` `validate_row` reads those three files from the row's tree (`sources_at`; the head successor's tree when a rebase took the row's tree, as for the inputs digest), takes the check's steps, targets and machines from that registry (`check_at`) and expands against it. A row whose argv was not the registry's argv at its own tree is still refused, and a tree that lacks the registry, or holds one that does not parse, refuses the row naming the file. Everything else about the check (its id, surfaces, deploy kind, rc) is still judged against the registry of today. Without a `root` there is no tree to read, and the argv is judged against the checkout's registry.

DEPLOY KINDS. `bench-cache`: the version `rediacc_ci.ops.deploy_bench` recorded in `.ci/cache/live-deploys/bench-eu.json`, confirmed serving 100% through wrangler at check time (a uuid). `bench-proxy-cache`: the same for the bench proxy, the version `rediacc_ci.deploy.deploy_proxy --target bench` recorded in `.ci/cache/live-deploys/proxy-bench-eu.json` after its smoke passed, confirmed serving 100% on proxy-bench through wrangler (a uuid). `renet-hash`: the renet binary built from the head's renet pointer, confirmed byte for byte on each machine (`renet:<vcs.revision>@sha256:<64 hex>`). `tree`: a CLI run from the clean head tree itself (`cli:<head>`). `tooling`: the Enterprise tooling of the clean head tree drives bench itself (the enterprise proofs stop or cut a bench signer, then start it again through `deploy_signer`'s own deploy), so the run is its own deploy and its rc its confirmation (`tooling:<head>`). `unrecorded`: nothing records which head the deployed version was cut from, so no run of that check can confirm a deploy and none is VERIFIED.

THE ROW (schema 1). `receipt.envelope` with `tier` `live`, plus `id`, `at`, `by`, `plan`, `box`, `target`, `region`, `deploy` (`surface`, `worker`, `version_id`, `source`, `deployed_head`, `confirmed_live`), `check` (`id`, `args`, `argv` as one argv per step run, `rc`, `duration_s`, `log_sha256`, `tail`) and `ladder` (`vm`, the admitting VM run id, null only when `ladder_phases` is empty or when the row is WAIVED: `vm` null, `waived` the operator's `ASKED:<YYYY-MM-DDTHH:MM>Z` the recorder proved against the transcript, and `head_tree` the row's own tree, which `check:ci-plan-live-proof` reports as owed a VERIFIED `vm:check` until one covers that tree or a descendant). `id` is `receipt.row_id`. The full log stays in the gitignored `.ci/cache/live-proof/<id>.log`; `check.log_sha256` is its digest, and `validate_row` re-reads the log when it is present and refuses a mismatch (box V10).

JUDGE SURFACES. A row is judged by `receipt.identity_refusal` over its surfaces, plus `renet` for a `renet-hash` check: that deploy IS the renet binary, so its build and the renet checkout are judged even when the plan touched only the CLI. The same set decides the ladder (`ladder_phases`): a `renet-hash` check provisions that binary on a real machine, so its row needs the VM run that admitted the renet phase, and a null `ladder.vm` is refused even for a CLI-only plan; a `tree` check that provisions nothing keeps the phases of its own surfaces.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import re
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci import well_known as WK
from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Collection, Iterable

SCHEMA = 1
TIER = "live"
LEDGER = ("agent", "ledgers", "live-proof.jsonl")
LOG_DIR = (".ci", "cache", "live-proof")
TAIL_MAX = 20
TAIL_LINE_MAX = 300
# tail_of replaces every `local@host` token in the captured check tail (wrangler's deployment listing carries `author_email`).
# No TLD is required, so ci@localhost goes too; a package spec such as name@1.2.3 is redacted as well, which costs nothing in a tail. The host is dot-separated labels, so it never ends in a dot: a sentence-ending period after `ci@localhost.` stays in the tail (review 6a8bfccb.1).
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")
DEFAULT_TIMEOUT_S = 600
BENCH_CACHE = "bench-cache"
BENCH_PROXY_CACHE = "bench-proxy-cache"
RENET_HASH = "renet-hash"
TREE = "tree"
TOOLING = "tooling"
UNRECORDED = "unrecorded"
DEPLOY_KINDS = (BENCH_CACHE, BENCH_PROXY_CACHE, RENET_HASH, TREE, TOOLING, UNRECORDED)
EXPECT_RC = "rc"
EXPECT_STALE_BINARY_EMPTY = "stale-binary-empty"
EXPECT_RENET_HASH = "renet-hash"
EXPECTS = (EXPECT_RC, EXPECT_STALE_BINARY_EMPTY, EXPECT_RENET_HASH)
LIVE_KEYS = ("id", "at", "by", "plan", "box", "target", "region", "deploy", "check", "ladder")
REGIONS = ("eu", "us", "asia")
BENCH_TARGET = "bench"
BENCH_REGIONS_REL = "regions.json"
MACHINE = "machine"
# A shell or a no-op as a step's program is a free command or a check that cannot fail.
REFUSED_PROGRAMS = frozenset({"sh", "bash", "zsh", "dash", "env", "eval", "exec", "true", ":"})
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VERSION_RES = {
    BENCH_CACHE: _UUID_RE,
    BENCH_PROXY_CACHE: _UUID_RE,
    RENET_HASH: re.compile(r"^renet:[0-9a-f]{40}@sha256:[0-9a-f]{64}$"),
    TREE: re.compile(r"^cli:[0-9a-f]{40}([0-9a-f]{24})?$"),
    TOOLING: re.compile(r"^tooling:[0-9a-f]{40}([0-9a-f]{24})?$"),
}
DEPLOY_SURFACE = {
    BENCH_CACHE: "account",
    BENCH_PROXY_CACHE: "proxy",
    RENET_HASH: "renet",
    TREE: "cli",
    TOOLING: "enterprise",
    UNRECORDED: None,
}
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_TARGET_KEYS = ("origin", "config")
# The operator answer a waived ladder carries (`live_proof record --vm-waived`); the minute shape `release.local_gates.ASKED_RE` spells.
WAIVED_RE = re.compile(r"ASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z")
# A target's origin is stored as a well-known key (`origin_wk`), never as a literal URL, so check:ci-literal-sources keeps one definition of each origin in .ci/config/well-known.env.
_ORIGIN_WK = "origin_wk"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACCEPT = re.compile(r"^\s*(?:[-*]\s+)?Accept:\s*live-proof\s+(\S+)\s+(\S+)((?:\s+\S+)*)\s*$")
_BOX_LINE = re.compile(r"^\s*[-*]\s+\[[ xX?>]\]\s")
_HEADING = re.compile(r"^#{1,6}\s")


class RegistryError(ValueError):
    """`tiers.live.checks` cannot be read, or a request names something the registry does not."""


@dataclasses.dataclass(frozen=True)
class Step:
    id: str
    argv: tuple[str, ...]
    expect: str = EXPECT_RC
    timeout_s: int = DEFAULT_TIMEOUT_S


@dataclasses.dataclass(frozen=True)
class Check:
    id: str
    targets: tuple[str, ...]
    surfaces: frozenset[str]
    deploy: str
    steps: tuple[Step, ...]
    per_machine: bool = False
    rebuild: tuple[str, ...] = ()
    what: str = ""


@dataclasses.dataclass(frozen=True)
class Run:
    """One step to run: its registry step, the machine it runs for (None unless per machine) and its expanded argv."""

    step: Step
    machine: str | None
    argv: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Sources:
    """What an argv is expanded from: the map's `tiers.live` block, the well-known values its `origin_wk` keys name, and a reader of regions.json's text, called only for a regional bench. `where` names them in a finding."""

    live: dict[str, Any]
    well_known: dict[str, str]
    regions: Callable[[], str]
    where: str = "the checkout"


def _checkout_regions() -> str:
    try:
        return paths.from_root(BENCH_REGIONS_REL).read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(
            f"{BENCH_REGIONS_REL} is unreadable ({exc.__class__.__name__})"
        ) from exc


def checkout_sources() -> Sources:
    """The checkout's own sources: the loaded map, `rediacc_ci.well_known` and regions.json under the repo root."""
    return Sources(S.MAP.live, WK.VALUES, _checkout_regions)


def sources_at(root: pathlib.Path, tree: str) -> Sources:
    """The sources as they stood in `tree` of the repository at `root`, read with `git show`. RegistryError naming the file when the map or the well-known registry is absent from that tree or does not parse; regions.json is read (and refused the same way) only when a regional bench asks for it."""
    git = S.make_git(root)
    where = f"tree {tree[:12]}"

    def show(rel: str) -> str:
        text = git(["show", f"{tree}:{rel}"])
        if text is None:
            raise RegistryError(f"{rel} is not in {where}, so the registry there cannot be read")
        return text

    map_text = show(S.MAP_REL)
    try:
        raw = json.loads(map_text)
    except ValueError as exc:
        raise RegistryError(f"{S.MAP_REL} in {where} is not JSON ({exc})") from exc
    tiers = raw.get("tiers") if isinstance(raw, dict) else None
    live = tiers.get("live") if isinstance(tiers, dict) else None
    if not isinstance(live, dict):
        raise RegistryError(f"{S.MAP_REL} in {where} has no tiers.live object")
    try:
        well_known = WK.parse(show(WK.REGISTRY_REL), f"{WK.REGISTRY_REL} in {where}")
    except WK.RegistryError as exc:
        raise RegistryError(str(exc)) from exc
    return Sources(live, well_known, lambda: show(BENCH_REGIONS_REL), where)


def _argv(value: object, where: str) -> tuple[str, ...]:
    if not (isinstance(value, list) and value and all(isinstance(a, str) and a for a in value)):
        raise RegistryError(f"{where} is not a non-empty list of strings")
    if value[0] in REFUSED_PROGRAMS:
        raise RegistryError(f"{where} runs {value[0]!r}: a shell or a no-op is not a fixed check")
    return tuple(value)


def _placeholders(argv: Iterable[str]) -> set[str]:
    return {name for arg in argv for name in _PLACEHOLDER.findall(arg)}


def _parse_step(raw: object, where: str) -> Step:
    if not isinstance(raw, dict):
        raise RegistryError(f"{where} is not an object")
    sid = raw.get("id")
    if not (isinstance(sid, str) and sid):
        raise RegistryError(f"{where}.id is missing")
    expect = raw.get("expect", EXPECT_RC)
    if expect not in EXPECTS:
        raise RegistryError(f"{where}.expect {expect!r} is not one of {', '.join(EXPECTS)}")
    timeout = raw.get("timeout_s", DEFAULT_TIMEOUT_S)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise RegistryError(f"{where}.timeout_s is not a positive integer")
    return Step(sid, _argv(raw.get("argv"), f"{where}.argv"), expect, timeout)


def _check_params(check: Check, targets: dict[str, Any], where: str) -> None:
    allowed = set(_TARGET_KEYS) | ({MACHINE} if check.per_machine else set())
    used = set().union(*(_placeholders(s.argv) for s in check.steps), _placeholders(check.rebuild))
    unknown = sorted(used - allowed)
    if unknown:
        raise RegistryError(
            f"{where} names {unknown}: the only parameters are {sorted(allowed)}, values the map itself names"
        )
    for target in check.targets:
        entry = targets[target]
        missing = sorted(k for k in used & set(_TARGET_KEYS) if not isinstance(entry.get(k), str))
        if missing:
            raise RegistryError(f"{where} needs {missing} from tiers.live.targets.{target}")
        if check.per_machine and not _machines(entry):
            raise RegistryError(
                f"{where} runs per machine, and tiers.live.targets.{target} names no machines"
            )


def _machines(entry: dict[str, Any]) -> tuple[str, ...]:
    machines = entry.get("machines")
    if not isinstance(machines, list):
        return ()
    return tuple(m for m in machines if isinstance(m, str) and m)


@dataclasses.dataclass(frozen=True)
class _Expansion:
    """The half of a check that decides its argv."""

    targets: tuple[str, ...]
    steps: tuple[Step, ...]
    per_machine: bool
    rebuild: tuple[str, ...]


def _parse_expansion(where: str, raw: dict[str, Any], targets: dict[str, Any]) -> _Expansion:
    tlist = raw.get("targets")
    if not (isinstance(tlist, list) and tlist and all(t in targets for t in tlist)):
        raise RegistryError(f"{where}.targets is not a non-empty list of {sorted(targets)}")
    steps = raw.get("steps")
    if not (isinstance(steps, list) and steps):
        raise RegistryError(f"{where}.steps is empty")
    per_machine = raw.get("per_machine", False)
    if not isinstance(per_machine, bool):
        raise RegistryError(f"{where}.per_machine is not a boolean")
    return _Expansion(
        targets=tuple(tlist),
        steps=tuple(_parse_step(s, f"{where}.steps[{n}]") for n, s in enumerate(steps)),
        per_machine=per_machine,
        rebuild=_argv(raw["rebuild"], f"{where}.rebuild") if "rebuild" in raw else (),
    )


def _parse_check(cid: str, raw: object, targets: dict[str, Any]) -> Check:
    where = f"tiers.live.checks.{cid}"
    if not isinstance(raw, dict):
        raise RegistryError(f"{where} is not an object")
    exp = _parse_expansion(where, raw, targets)
    tlist = list(exp.targets)
    names = raw.get("surfaces")
    if not (isinstance(names, list) and names and all(_known_surface(n) for n in names)):
        raise RegistryError(f"{where}.surfaces is not a non-empty list of known surfaces")
    for name in names:
        if not set(S.MAP.surfaces[name].live) & set(tlist):
            raise RegistryError(f"{where}: surface {name} admits none of the targets {tlist}")
    deploy = raw.get("deploy")
    if deploy not in DEPLOY_KINDS:
        raise RegistryError(f"{where}.deploy {deploy!r} is not one of {', '.join(DEPLOY_KINDS)}")
    check = Check(
        id=cid,
        targets=exp.targets,
        surfaces=frozenset(names),
        deploy=deploy,
        steps=exp.steps,
        per_machine=exp.per_machine,
        rebuild=exp.rebuild,
        what=str(raw.get("what") or ""),
    )
    expects = {s.expect for s in check.steps}
    if deploy == RENET_HASH and EXPECT_RENET_HASH not in expects:
        raise RegistryError(
            f"{where} identifies its deploy by the renet hash and has no renet-hash step"
        )
    if EXPECT_RENET_HASH in expects and deploy != RENET_HASH:
        raise RegistryError(f"{where} has a renet-hash step but deploy {deploy!r}")
    _check_params(check, targets, where)
    return check


def resolve_target(
    name: str, entry: dict[str, Any], well_known: dict[str, str] | None = None
) -> dict[str, Any]:
    """`entry` with its `origin_wk` resolved into `origin`, the value `{origin}` fills, through `well_known` (rediacc_ci.well_known's values unless given). RegistryError for a literal `origin` (the URL belongs in .ci/config/well-known.env) or a key the registry does not declare."""
    where = f"tiers.live.targets.{name}"
    if "origin" in entry:
        raise RegistryError(
            f"{where}.origin is a literal; store {_ORIGIN_WK!r}, a key of {WK.REGISTRY_REL}"
        )
    values = WK.VALUES if well_known is None else well_known
    out = {k: v for k, v in entry.items() if k != _ORIGIN_WK}
    if _ORIGIN_WK in entry:
        key = entry[_ORIGIN_WK]
        if not (isinstance(key, str) and key in values):
            raise RegistryError(f"{where}.{_ORIGIN_WK} {key!r} is not a key of {WK.REGISTRY_REL}")
        out["origin"] = values[key]
    return out


def _live_targets(live: dict[str, Any], well_known: dict[str, str] | None) -> dict[str, Any]:
    targets = live.get("targets")
    if not (
        isinstance(targets, dict) and targets and all(isinstance(v, dict) for v in targets.values())
    ):
        raise RegistryError("tiers.live.targets is empty")
    return {name: resolve_target(name, entry, well_known) for name, entry in targets.items()}


def parse_checks(live: object) -> dict[str, Check]:
    """The registry of `tiers.live` (the map's `live` block), or RegistryError naming the first defect. An empty registry is a defect: a blind registry is never a quiet one."""
    if not isinstance(live, dict):
        raise RegistryError("tiers.live is not an object")
    targets = _live_targets(live, None)
    raw = live.get("checks")
    if not (isinstance(raw, dict) and raw):
        raise RegistryError("tiers.live.checks is empty")
    return {cid: _parse_check(cid, entry, targets) for cid, entry in raw.items()}


def registry() -> dict[str, Check]:
    """The committed registry."""
    return parse_checks(S.MAP.live)


def check_at(check: Check, sources: Sources) -> Check:
    """`check` with the half that decides its argv (targets, steps, per machine, rebuild) as `sources` declare it, the rest kept. RegistryError when `sources` lack the check or declare it in a shape `parse_checks` refuses (a shell program, an unknown placeholder, a missing target parameter)."""
    where = f"tiers.live.checks.{check.id} in {sources.where}"
    try:
        targets = _live_targets(sources.live, sources.well_known)
    except RegistryError as exc:
        raise RegistryError(f"{exc} in {sources.where}") from exc
    checks = sources.live.get("checks")
    raw = checks.get(check.id) if isinstance(checks, dict) else None
    if not isinstance(raw, dict):
        raise RegistryError(f"check {check.id} is not in the registry in {sources.where}")
    exp = _parse_expansion(where, raw, targets)
    out = dataclasses.replace(
        check,
        targets=exp.targets,
        steps=exp.steps,
        per_machine=exp.per_machine,
        rebuild=exp.rebuild,
    )
    _check_params(out, targets, where)
    return out


def bench_object(region: str) -> dict[str, Any]:
    """The `bench` object of `region` in the checkout's regions.json, the one source of a regional bench's host, Worker names and rdc config. RegistryError when the file, the region or its bench object is missing."""
    return _bench_in(region, checkout_sources())


def _bench_in(region: str, sources: Sources) -> dict[str, Any]:
    """`bench_object` over the regions.json `sources` read."""
    text = sources.regions()
    try:
        doc = json.loads(text)
        rows = doc["regions"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RegistryError(
            f"{BENCH_REGIONS_REL} is unreadable ({exc.__class__.__name__})"
        ) from exc
    for row in rows:
        if isinstance(row, dict) and row.get("id") == region:
            bench = row.get("bench")
            if not (
                isinstance(bench, dict)
                and all(isinstance(bench.get(k), str) for k in ("host", "config"))
            ):
                raise RegistryError(
                    f"{BENCH_REGIONS_REL} region {region!r} has no usable bench object"
                )
            return bench
    raise RegistryError(f"{BENCH_REGIONS_REL} has no region {region!r}")


def is_regional_bench(target: str, region: str | None) -> bool:
    """True for a bench run that names a region: that region's host and config come from regions.json. A bench run with no `--region` keeps the registry's own entry."""
    return target == BENCH_TARGET and region is not None


def target_entry(
    target: str, region: str | None = None, sources: Sources | None = None
) -> dict[str, Any]:
    """The target's registry entry, resolved from the checkout's sources or from `sources`. A bench run with a `region` takes that region's bench host as `origin` and its rdc config as `config` from regions.json; no region keeps the registry's own (`origin_wk`)."""
    src = sources or checkout_sources()
    targets = src.live.get("targets")
    entry = targets.get(target) if isinstance(targets, dict) else None
    if not isinstance(entry, dict):
        raise RegistryError(f"{target!r} is not a live target")
    out = resolve_target(target, entry, src.well_known)
    if is_regional_bench(target, region):
        bench = bench_object(str(region)) if sources is None else _bench_in(str(region), sources)
        out["origin"] = "https://" + bench["host"]
        out["config"] = bench["config"]
    return out


def machines_for(
    check: Check, target: str, machine: str | None, sources: Sources | None = None
) -> tuple[str | None, ...]:
    """The machine aliases a run covers: every alias of the target, or the one named. RegistryError for an alias outside the registry or a machine given to a check that does not run per machine."""
    if not check.per_machine:
        if machine is not None:
            raise RegistryError(
                f"check {check.id} does not run per machine; --machine is not a parameter of it"
            )
        return (None,)
    known = _machines(target_entry(target, sources=sources))
    if machine is None:
        return known
    if machine not in known:
        raise RegistryError(
            f"machine {machine!r} is not in tiers.live.targets.{target}.machines {list(known)}"
        )
    return (machine,)


def check_args(machine: str | None) -> list[str]:
    """The Accept-line arguments of a run: `machine=<alias>` when it is narrowed to one alias, else none."""
    return [f"{MACHINE}={machine}"] if machine else []


def machine_of_args(args: Collection[str]) -> str | None:
    """The inverse of `check_args`. RegistryError for any other argument: the registry takes no free ones."""
    machine = None
    for arg in args:
        key, sep, value = arg.partition("=")
        if key != MACHINE or not sep or not value or machine is not None:
            raise RegistryError(
                f"argument {arg!r} is not a registry parameter (only one machine=<alias>)"
            )
        machine = value
    return machine


def _fill(arg: str, values: dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], arg)


def _values(
    target: str, machine: str | None, region: str | None = None, sources: Sources | None = None
) -> dict[str, str]:
    entry = target_entry(target, region, sources)
    values = {k: entry[k] for k in _TARGET_KEYS if isinstance(entry.get(k), str)}
    if machine is not None:
        values[MACHINE] = machine
    return values


def expand(
    check: Check,
    target: str,
    machine: str | None = None,
    region: str | None = None,
    sources: Sources | None = None,
) -> list[Run]:
    """Every step to run for `check` on `target`, in order (per machine: every step for the first alias, then the next). `region` picks the bench (see `target_entry`). The target values come from the checkout's sources unless `sources` is given (`sources_at` reads a past tree's; pair it with `check_at` for that tree's steps). RegistryError for a target the check does not name, or a machine outside the registry."""
    if target not in check.targets:
        raise RegistryError(f"check {check.id} runs on {list(check.targets)}, not {target!r}")
    runs: list[Run] = []
    for alias in machines_for(check, target, machine, sources):
        values = _values(target, alias, region, sources)
        runs.extend(
            Run(step, alias, tuple(_fill(a, values) for a in step.argv)) for step in check.steps
        )
    return runs


def rebuild_argv(check: Check, target: str, region: str | None = None) -> tuple[str, ...]:
    values = _values(target, None, region)
    return tuple(_fill(a, values) for a in check.rebuild)


def _known_surface(name: object) -> bool:
    """Whether `name` is a surface of the map. A non-string (a nested list or object a hand-edited row may carry) is unhashable, so the bare membership test raised TypeError and aborted `verify` instead of reporting the row (review b8f513f4.1)."""
    return isinstance(name, str) and name in S.MAP.surfaces


def judge_surfaces(surfaces: Iterable[str], check: Check | None) -> frozenset[str]:
    """The surfaces `receipt.identity_refusal` judges a row by: its own, plus renet for a renet-hash deploy."""
    out = set(surfaces)
    if check is not None and check.deploy == RENET_HASH:
        out.add("renet")
    return frozenset(out)


def ladder_phases(surfaces: Iterable[str], check: Check | None) -> frozenset[str]:
    """The VM phases whose run must admit a row's head before the live run: those of its judge surfaces, so a renet-hash deploy needs the renet phase even when the plan touched only the CLI."""
    return S.phases_for(judge_surfaces(surfaces, check))


def row_surfaces(touched: Iterable[str], check: Check, target: str) -> list[str]:
    """The surfaces a run proves: those the plan touched, the check covers, and `target` is admissible for."""
    return sorted(
        name for name in set(touched) & check.surfaces if target in S.MAP.surfaces[name].live
    )


# ----------------------------------------------------------------------------- plan and box


@dataclasses.dataclass(frozen=True)
class Accept:
    target: str
    check: str
    args: tuple[str, ...]


def accept_of(text: str, line: int) -> Accept | None:
    """The `Accept: live-proof <target> <check-id> [args]` sub-line of the box at 0-based `line` of a plan, or None. Sub-lines run to the next box, heading or unindented line; backticks are ignored."""
    lines = text.splitlines()
    for raw in lines[line + 1 :]:
        if _BOX_LINE.match(raw) or _HEADING.match(raw) or (raw and not raw[0].isspace()):
            break
        m = _ACCEPT.match(raw.replace("`", ""))
        if m:
            return Accept(m.group(1), m.group(2), tuple(m.group(3).split()))
    return None


# ----------------------------------------------------------------------------- the row


def tail_of(log: str) -> list[str]:
    """The last TAIL_MAX non-empty lines of an already scrubbed log, email addresses replaced by `<email>`, each clipped to TAIL_LINE_MAX characters."""
    lines = [ln.rstrip() for ln in log.splitlines() if ln.strip()]
    return [EMAIL_RE.sub("<email>", ln)[:TAIL_LINE_MAX] for ln in lines[-TAIL_MAX:]]


def secret_shapes(text: str) -> list[str]:
    """The secret shapes `text` carries, by the scanner every tracked worklist write passes (`wl_store.secret_shapes_in`). Names the shape, never the match."""
    store = importlib.import_module("wl_store")
    return list(store.secret_shapes_in(text))


def log_digest(log: str) -> str:
    return hashlib.sha256(log.encode("utf-8")).hexdigest()


def log_path(root: pathlib.Path, row_id: str) -> pathlib.Path:
    return root.joinpath(*LOG_DIR) / f"{row_id}.log"


def ledger_path(root: pathlib.Path) -> pathlib.Path:
    return root.joinpath(*LEDGER)


def build_row(ident: dict[str, Any], status: str, **body: Any) -> dict[str, Any]:
    """The live row: `ident` (from `receipt.identity`) with the envelope fields and the live body, and its `id`. A VERIFIED row is validated as an envelope (ValueError when it is not one); a refused run's row only names its log, so it is built as found."""
    if status == R.VERIFIED:
        row = R.envelope(TIER, SCHEMA, status, ident, **body)
    else:
        row = {**ident, **body, "tier": TIER, "schema": SCHEMA, "status": status}
    row.pop("id", None)
    row["id"] = R.row_id(row)
    return row


def _deploy_problems(row: dict[str, Any], check: Check | None) -> list[str]:
    deploy = row.get("deploy")
    if not isinstance(deploy, dict):
        return ["deploy is not an object"]
    out: list[str] = []
    version = deploy.get("version_id")
    if check is not None:
        rx = VERSION_RES.get(check.deploy)
        if rx is None:
            out.append(
                f"check {check.id} identifies no deploy ({check.deploy}), so no row of it is VERIFIED"
            )
        elif not (isinstance(version, str) and rx.match(version)):
            out.append(f"deploy.version_id {version!r} is malformed for a {check.deploy} deploy")
    if deploy.get("deployed_head") != row.get("head"):
        out.append("deploy.deployed_head is not the head")
    if deploy.get("confirmed_live") is not True:
        out.append("deploy.confirmed_live is not true")
    return out


def _check_problems(
    row: dict[str, Any], checks: dict[str, Check], at: Sources | RegistryError | None = None
) -> tuple[list[str], Check | None]:
    """The check body's problems, and the registry check it names. `at` is what the argv is judged against: the sources of the row's tree, the RegistryError reading them raised (a problem, never a skip), or None for the checkout's registry."""
    body = row.get("check")
    if not isinstance(body, dict):
        return ["check is not an object"], None
    out: list[str] = []
    check = checks.get(str(body.get("id")))
    if check is None:
        return [f"check {body.get('id')!r} is not in the registry"], None
    rc = body.get("rc")
    if rc != 0 or isinstance(rc, bool):
        out.append(f"check.rc is {rc!r}, not 0")
    if not (isinstance(body.get("log_sha256"), str) and _SHA256.match(body["log_sha256"])):
        out.append("check.log_sha256 is not a sha256 digest")
    tail = body.get("tail")
    if not (
        isinstance(tail, list) and len(tail) <= TAIL_MAX and all(isinstance(t, str) for t in tail)
    ):
        out.append(f"check.tail is not a list of at most {TAIL_MAX} strings")
    duration = body.get("duration_s")
    if not isinstance(duration, int | float) or isinstance(duration, bool) or duration < 0:
        out.append("check.duration_s is not a non-negative number")
    args = body.get("args")
    try:
        if not (isinstance(args, list) and all(isinstance(a, str) for a in args)):
            raise RegistryError("check.args is not a list of strings")
        if isinstance(at, RegistryError):
            raise RegistryError(f"check.argv cannot be judged: {at}")
        runs = expand(
            check if at is None else check_at(check, at),
            str(row.get("target")),
            machine_of_args(args),
            region=row.get("region"),
            sources=at,
        )
    except RegistryError as exc:
        out.append(str(exc))
    else:
        if body.get("argv") != [list(r.argv) for r in runs]:
            whose = "" if at is None else f" in {at.where}"
            out.append(
                f"check.argv is not the registry's argv for this check, target and arguments{whose}"
            )
    return out, check


def _surface_problems(row: dict[str, Any], check: Check | None) -> list[str]:
    names = row.get("surfaces")
    if not (isinstance(names, list) and names and all(_known_surface(n) for n in names)):
        return ["surfaces is not a non-empty list of known surfaces"]
    out: list[str] = []
    if check is not None:
        out.extend(
            f"check {check.id} does not cover surface {n}" for n in names if n not in check.surfaces
        )
    target = row.get("target")
    out.extend(
        f"surface {n} does not admit target {target!r}"
        for n in names
        if target not in S.MAP.surfaces[n].live
    )
    ladder = row.get("ladder")
    if not isinstance(ladder, dict) or "vm" not in ladder:
        out.append("ladder is not an object with vm")
    else:
        out.extend(_ladder_problems(row, ladder, bool(ladder_phases(names, check))))
    return out


def _ladder_problems(row: dict[str, Any], ladder: dict[str, Any], phased: bool) -> list[str]:
    """A phased row carries the admitting VM run id, or a waiver (`waived`, `head_tree`) and no run id; an unphased row carries no waiver."""
    vm_ok = isinstance(ladder["vm"], str) and bool(ladder["vm"])
    if "waived" not in ladder:
        if phased and not vm_ok:
            return ["a surface or deploy with a VM phase needs ladder.vm, the admitting VM run id"]
        return []
    out: list[str] = []
    if not phased:
        out.append("ladder.waived on a row with no VM phase to waive")
    if ladder["vm"] is not None:
        out.append("ladder carries both a VM run id and a waiver; a row is one or the other")
    waived = ladder.get("waived")
    if not (isinstance(waived, str) and WAIVED_RE.fullmatch(waived)):
        out.append(f"ladder.waived {waived!r} is not ASKED:<YYYY-MM-DDTHH:MM>Z")
    if ladder.get("head_tree") != row.get("tree"):
        out.append("ladder.head_tree is not the row's tree")
    return out


def _judged_tree(
    row: dict[str, Any],
    root: pathlib.Path,
    successor_of: Callable[[str], str | None] | None,
) -> tuple[str, str, list[str]]:
    """(head successor or "", the tree the row is judged at, problems): the row's own tree, or its head successor's tree when a rewrite took the row's tree too (see `_git_problems`). A head or tree that resolves to nothing is a problem, never a skip."""
    git = S.make_git(root)

    def present(sha: str) -> bool:
        return bool(sha) and git(["cat-file", "-e", sha]) is not None

    out: list[str] = []
    head, tree = str(row.get("head")), str(row.get("tree"))
    successor = ""
    if not present(head):
        mapped = successor_of(head) if successor_of is not None else None
        if mapped and mapped != head and present(mapped):
            successor = mapped
        else:
            out.append(f"head {head[:12]} does not resolve")
    judged_tree = tree
    if not present(tree):
        at = (git(["rev-parse", "--verify", "--quiet", f"{successor}^{{tree}}"]) or "").strip()
        if successor and at:
            judged_tree = at
        else:
            out.append(f"tree {tree[:12]} does not resolve")
    return successor, judged_tree, out


def _row_sources(
    row: dict[str, Any],
    root: pathlib.Path,
    successor_of: Callable[[str], str | None] | None,
) -> Sources | RegistryError:
    """The registry sources at the tree the row is judged at (`_judged_tree`), or the RegistryError naming why they cannot be read."""
    _successor, judged_tree, problems = _judged_tree(row, root, successor_of)
    if problems:
        return RegistryError("; ".join(problems))
    try:
        return sources_at(root, judged_tree)
    except RegistryError as exc:
        return exc


def _git_problems(
    row: dict[str, Any],
    root: pathlib.Path,
    successor_of: Callable[[str], str | None] | None = None,
) -> list[str]:
    """The row's `head` and `tree` resolve, and `inputs` is the digest of that tree for its surfaces.

    A REWRITTEN HEAD IS RE-RESOLVED, NEVER EXCUSED. A rebase or a message scrub replaces the commit a receipt recorded, and in CI's fresh clone the old sha does not exist. `successor_of` (`rediacc_ci.review.successor`, the map the investigation gate uses) names the patch-equal commit that replaced it. A head that resolves no successor is still refused. When the row's tree is gone with it, the inputs digest is recomputed at the SUCCESSOR's tree, so surface code that changed in the rewrite still fails the row.
    """
    successor, judged_tree, out = _judged_tree(row, root, successor_of)
    if out:
        return out
    tree = str(row.get("tree"))
    names = row.get("surfaces")
    known = isinstance(names, list) and names and all(_known_surface(n) for n in names)
    if known and S.inputs(root, judged_tree, names) != row.get("inputs"):
        whose = (
            "the row's tree" if judged_tree == tree else f"head successor {successor[:12]}'s tree"
        )
        out.append(f"inputs is not the digest of {whose} for its surfaces")
    return out


def validate_row(
    row: object,
    *,
    checks: dict[str, Check] | None = None,
    root: pathlib.Path | None = None,
    successor_of: Callable[[str], str | None] | None = None,
) -> list[str]:
    """Every reason `row` is not a valid VERIFIED live receipt, empty when it is one.

    Without `root` the judge is pure: the envelope, the live body, the id, the registry argv (against the checkout's registry), the deploy identity, the identity rules, the ladder and the secret scan. With `root` it judges the argv against the registry at the row's tree instead (`sources_at`, `check_at`; see the module docstring), and it also resolves `head` and `tree`, recomputes the inputs digest at the row's tree, and re-reads `.ci/cache/live-proof/<id>.log` when it is present, refusing a digest that differs from `check.log_sha256`. `successor_of` re-resolves a head a rebase rewrote (see `_git_problems`).
    """
    if not isinstance(row, dict):
        return ["the row is not an object"]
    checks = registry() if checks is None else checks
    out = list(R.envelope_errors(row))
    out.extend(f"missing field {k}" for k in LIVE_KEYS if k not in row)
    if row.get("tier") != TIER:
        out.append(f"tier is {row.get('tier')!r}, not {TIER!r}")
    if row.get("schema") != SCHEMA:
        out.append(f"schema {row.get('schema')!r} is not {SCHEMA}")
    if row.get("status") != R.VERIFIED:
        out.append(f"status is {row.get('status')!r}; the ledger holds VERIFIED rows only")
    if row.get("id") != R.row_id(row):
        out.append("id does not hash to the row")
    if row.get("region") is not None and row.get("region") not in REGIONS:
        out.append(f"region {row.get('region')!r} is not null or one of {', '.join(REGIONS)}")
    at = None if root is None else _row_sources(row, root, successor_of)
    problems, check = _check_problems(row, checks, at)
    out.extend(problems)
    out.extend(_deploy_problems(row, check))
    out.extend(_surface_problems(row, check))
    raw_names = row.get("surfaces")
    names: list[str] = raw_names if isinstance(raw_names, list) else []
    if all(_known_surface(n) for n in names):
        refused = R.identity_refusal(row, judge_surfaces(names, check))
        if refused is not None:
            out.append(f"{refused.code}: {refused.message}")
    shapes = secret_shapes(R.canonical(row))
    if shapes:
        out.append(f"the row carries a secret shape ({', '.join(shapes)})")
    if root is not None:
        out.extend(_git_problems(row, root, successor_of))
        out.extend(_log_problems(row, root))
    return out


def _log_problems(row: dict[str, Any], root: pathlib.Path) -> list[str]:
    path = log_path(root, str(row.get("id")))
    if not path.is_file():
        return []
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != (row.get("check") or {}).get("log_sha256"):
        return [f"the kept log {path.name} does not match check.log_sha256"]
    return []


# ----------------------------------------------------------------------------- the ledger


@dataclasses.dataclass(frozen=True)
class LedgerLine:
    lineno: int
    row: dict[str, Any] | None
    error: str = ""


def read_ledger(path: pathlib.Path) -> list[LedgerLine]:
    """Every non-blank line of the ledger, parsed. A line that is not a JSON object carries its error; an absent ledger is empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    out: list[LedgerLine] = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError as exc:
            out.append(LedgerLine(n, None, f"not JSON: {exc}"))
            continue
        if not isinstance(parsed, dict):
            out.append(LedgerLine(n, None, "not a JSON object"))
            continue
        out.append(LedgerLine(n, parsed))
    return out


def matches(row: dict[str, Any], plan: str, box: str, target: str, accept: Accept) -> bool:
    """True when `row` is the receipt of `plan`'s box `box` on `target`, by the box's Accept line (LP4): plan, box, target, VERIFIED, rc 0, a clean tree, and the Accept line's check id and arguments."""
    body = row.get("check") or {}
    return (
        row.get("plan") == plan
        and row.get("box") == box
        and row.get("target") == target == accept.target
        and row.get("status") == R.VERIFIED
        and row.get("dirty") is False
        and body.get("rc") == 0
        and body.get("id") == accept.check
        and list(body.get("args") or []) == list(accept.args)
    )
