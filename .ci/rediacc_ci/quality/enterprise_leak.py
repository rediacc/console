"""No Enterprise company name reaches a public surface of this repository.

    .ci/scripts/quality/check_enterprise_leak.py              controls, then the verdict
    .ci/scripts/quality/check_enterprise_leak.py --selftest   controls only

WHY IT EXISTS (agent/plans/PLAN-enterprise-isolation.md, N2). This repository is public, and so is every CI log it produces. A company's name lives in the per-region control database and in gitignored generated configs, never in a tracked file. Four ways it could still escape are checked here, and the two public reports that read live Cloudflare names mask them through `Masker` below.

THE FOUR CHECKS, each over TRACKED files only (`git ls-files`; submodules are their own repositories and are not listed):

  tracked-company-toml   A tracked `enterprise.<x>.toml` anywhere, except `enterprise.template.toml`. The generator writes `workers/{account,proxy}/enterprise.<company>.toml`, which the two `.gitignore` files keep out; a `git add -f` or a lost ignore line would publish the name in the file name itself.
  store-name             Every secret NAME the two public secret records declare (.ci/config/bws-secret-map.json, which the vault refresh writes from the SHARED project, and .ci/config/secret-supply.json) is either a shared UPPER_SNAKE name or it is refused. An opaque company store id (`c<hex>`) is refused too: company stores live in the separate enterprise project, and one showing up in the shared record means it was created in the wrong project. Anything else (lowercase, dashes, a company spelled out) is a non-opaque store name.
  product-host           Every `<label>.<product domain>` and `<label>-proxy.<product domain>` in a tracked text file names a label a company cannot take (`rediacc_ci.enterprise.names.reserved()`: region ids, well-known host labels, service words) or the fake `acme`. Any other label is a company host. Placeholders like `<company>` do not match the label grammar and pass.
  known-label            Local only. The labels of the generated tomls on disk (tracked or not), plus `ENTERPRISE_LEAK_LABELS` (comma separated), are searched for in the shapes a company name takes: `account-<c>`, `proxy-<c>`, `configs-<c>`, `backups-<c>`, `signer-<c>`, `control-<c>`, `<c>.<domain>`, `<c>-proxy.<domain>`, `enterprise.<c>.toml`, and, in the files that carry store names (the two secret records and .github/), the uppercase token `<C>` inside a NAME beside at least one `_` part. CI holds no generated toml, so there this check knows zero labels and says so; it is the half that catches a leak on the operator's machine before the commit leaves it.

WHAT IT DOES NOT CATCH, said plainly: an uppercase shared-shaped store name such as `GLOBEX_JWT` in the shared record when the label is not known locally (the store-name check only sees shape), and a company name written as a plain word in prose. A plain-word search would flag any company whose name is a dictionary word in every unrelated sentence, with no way out but a suppression, so the known-label search is contexted on purpose.

EXIT. 0 clean, 1 on any finding, 2 when the instrument is broken: git cannot list the tree, zero tracked files, a secret record is missing or unreadable, zero store names were read, or a control failed. A green prints its shape so a collapsed number is visible.

THE MASKER. `Masker.for_tree(root)` knows every public name: the labels above, every string in regions.json, every string in a tracked `workers/**/*.toml`, every well-known value, and `pr-<n>` previews. `mask(text)` replaces a company label in a product host or in a `<prefix>-<label>` resource name with `<company-N>`, one N per label within one run, so `account-globex` and `globex.<domain>/*` both read as company 1 without naming it. Ordinals and not hashes: an unkeyed hash of a short name is a dictionary lookup away from the name. Cloudflare ids (D1 uuids, Containers application ids) carry no name and pass unchanged. `Masker.identity()` masks nothing; the two reports offer it as `--unmasked` and refuse that under `GITHUB_ACTIONS`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rediacc_ci import paths, well_known
from rediacc_ci.controls import Checker, controls_first, fixture_git_env
from rediacc_ci.enterprise import names

if TYPE_CHECKING:
    from collections.abc import Mapping

GATE = "enterprise leak"
TEMPLATE_STEM = "template"
GENERATED_TOML = re.compile(r"(?:^|/)enterprise\.([^/]+)\.toml$")
GENERATED_GLOB = "workers/*/enterprise.*.toml"
# A company store id: `c` and at least eight hex digits, optionally followed by the secret it holds (`c1a2b3c4d5_ACCOUNT_JWT_SECRET`). The same `c<hex>` shape names.check refuses as a company name.
OPAQUE_STORE = re.compile(r"c[0-9a-f]{8,}(?:[_-][A-Za-z0-9_-]*)?")
SHARED_STORE = re.compile(r"[A-Z][A-Z0-9_]*")
# The fake company the plan and its tests may name (PLAN-enterprise-isolation.md: "`acme` is the fake example").
FAKE_LABELS = frozenset({"acme"})
# The resource families a company gets (Design, Shape and Signers): `account-<c>` (Worker and D1), `proxy-<c>`, `configs-<c>`, `backups-<c>`; `signer-` and `control-` are the regional families the same code names.
RESOURCE_PREFIXES = ("account", "proxy", "configs", "backups", "signer", "control")
SECRET_RECORDS = (".ci/config/bws-secret-map.json", ".ci/config/secret-supply.json")
LABELS_ENV = "ENTERPRISE_LEAK_LABELS"
PROXY_SUFFIX = names.PROXY_SUFFIX
MAX_SCAN_BYTES = 4 * 2**20
PR_PREVIEW = re.compile(r"pr-[0-9]+")
_LABEL = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class LeakSetupError(Exception):
    """The instrument cannot look (exit 2); the message names what is missing."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    what: str
    fix: str

    def render(self) -> str:
        return "%s:%d: [%s] %s. Fix: %s" % (self.path, self.line, self.rule, self.what, self.fix)


@dataclass
class Shape:
    tracked: int = 0
    generated_tracked: int = 0
    store_names: int = 0
    hosts: int = 0
    host_files: int = 0
    labels: int = 0
    label_sources: str = ""

    def render(self) -> str:
        return (
            "%d tracked files, %d tracked company toml(s) (the template is allowed), "
            "%d store names in %d public records, %d product host(s) in %d file(s), "
            "%d company label(s) known locally%s"
            % (
                self.tracked,
                self.generated_tracked,
                self.store_names,
                len(SECRET_RECORDS),
                self.hosts,
                self.host_files,
                self.labels,
                " (%s)" % self.label_sources if self.label_sources else " (none generated here)",
            )
        )


def tracked_files(root: pathlib.Path, env: dict[str, str] | None = None) -> list[str]:
    """Every tracked path under root, repo-relative, from `git ls-files -z`; LeakSetupError when git cannot answer."""
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        raise LeakSetupError(
            "git cannot run (%s); install git, the gate lists the tree with it" % exc
        ) from None
    if done.returncode != 0:
        raise LeakSetupError(
            "git ls-files exited %d in %s: %s"
            % (done.returncode, root, done.stderr.decode("utf-8", "replace").strip())
        )
    return [p for p in done.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def _line_of(text: str, needle: str) -> int:
    at = text.find(needle)
    return 1 if at < 0 else text.count("\n", 0, at) + 1


def generated_toml_findings(files: list[str]) -> list[Finding]:
    """A finding per tracked `enterprise.<x>.toml` other than the template."""
    out = []
    for path in files:
        m = GENERATED_TOML.search(path)
        if m and m.group(1) != TEMPLATE_STEM:
            out.append(
                Finding(
                    path,
                    1,
                    "tracked-company-toml",
                    "a generated company config is tracked, and its file name is the company's name",
                    "`git rm --cached %s`; generated company configs stay untracked "
                    "(workers/account/.gitignore and workers/proxy/.gitignore ignore enterprise.*.toml)"
                    % path,
                )
            )
    return out


def _spec_name(spec: object) -> str | None:
    """The store NAME of a consumer spec, `NAME > LOCAL` or `NAME`."""
    if not isinstance(spec, str):
        return None
    return spec.split(">", 1)[0].strip() or None


def store_names(root: pathlib.Path) -> list[tuple[str, str]]:
    """(record, NAME) for every secret name the public secret records declare."""
    out: list[tuple[str, str]] = []
    for rel in SECRET_RECORDS:
        try:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LeakSetupError("%s cannot be read as JSON: %s" % (rel, exc)) from None
        if not isinstance(data, dict):
            raise LeakSetupError("%s is not a JSON object" % rel)
        found: list[str] = []
        if rel.endswith("bws-secret-map.json"):
            found.extend((data.get("secrets") or {}).keys())
        else:
            found.extend(n for n in data.get("bootstrap_names") or [] if isinstance(n, str))
            for name, row in (data.get("residue") or {}).items():
                found.append(name)
                if isinstance(row, dict) and isinstance(row.get("alias_of"), str):
                    found.append(row["alias_of"])
            for profile in (data.get("consumers") or {}).values():
                if isinstance(profile, dict):
                    for key in ("required", "optional"):
                        found.extend(
                            n for n in map(_spec_name, profile.get(key) or []) if n is not None
                        )
            dotenv = data.get("dotenv") or {}
            found.extend((dotenv.get("names") or {}).keys())
            for local, store in (dotenv.get("aliases") or {}).items():
                found.append(local)
                if isinstance(store, str):
                    found.append(_spec_name(store) or store)
        out.extend((rel, n) for n in found)
    return out


def store_findings(root: pathlib.Path, pairs: list[tuple[str, str]]) -> list[Finding]:
    """A finding per opaque company store in a shared record, and per name that is neither shared nor opaque."""
    texts: dict[str, str] = {}
    out = []
    seen: set[tuple[str, str]] = set()
    for rel, name in pairs:
        if (rel, name) in seen:
            continue
        seen.add((rel, name))
        if SHARED_STORE.fullmatch(name):
            continue
        text = texts.setdefault(rel, (root / rel).read_text(encoding="utf-8"))
        line = _line_of(text, '"%s' % name)
        if OPAQUE_STORE.fullmatch(name):
            out.append(
                Finding(
                    rel,
                    line,
                    "store-name",
                    "company store %r sits in the shared project's public record" % name,
                    "create company stores in the separate enterprise bws project, delete this one from "
                    "the shared project, and refresh the record (scripts/ops/bws-map-refresh.py)",
                )
            )
        else:
            out.append(
                Finding(
                    rel,
                    line,
                    "store-name",
                    "store name %r is neither a shared UPPER_SNAKE name nor an opaque c<hex> id"
                    % name,
                    "a company's secrets are stored under its opaque c<hex> id in the enterprise project; "
                    "rename the store so no company name reaches a public record",
                )
            )
    return out


def host_re(domain: str) -> re.Pattern[str]:
    """`<label>.<domain>` with the label directly under the domain; a dot before the label is allowed (`proxy.eu.<domain>` yields `eu`)."""
    return re.compile(
        r"(?<![A-Za-z0-9_-])([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.%s(?![A-Za-z0-9-])"
        % re.escape(domain)
    )


def label_is_public(label: str, public: frozenset[str]) -> bool:
    base = label.removesuffix(PROXY_SUFFIX)
    return label in public or base in public or base in FAKE_LABELS


def _read_text(root: pathlib.Path, rel: str) -> str | None:
    path = root / rel
    try:
        if not path.is_file() or path.stat().st_size > MAX_SCAN_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", "replace")


def host_findings(
    root: pathlib.Path, files: list[str], public: frozenset[str], domain: str, shape: Shape
) -> list[Finding]:
    """A finding per product host whose label a company could hold."""
    pattern = host_re(domain)
    out = []
    for rel in files:
        text = _read_text(root, rel)
        if text is None or domain not in text:
            continue
        hits = 0
        for m in pattern.finditer(text):
            hits += 1
            label = m.group(1)
            if label_is_public(label, public):
                continue
            out.append(
                Finding(
                    rel,
                    text.count("\n", 0, m.start()) + 1,
                    "product-host",
                    "%s names label %r, which is no region or service, so it reads as a company host"
                    % (m.group(0), label),
                    "write the fake `acme` or the placeholder `<company>` instead; when the label is a "
                    "service, reserve it in .ci/rediacc_ci/enterprise/names.py SERVICE_LABELS",
                )
            )
        if hits:
            shape.hosts += hits
            shape.host_files += 1
    return out


def known_labels(root: pathlib.Path, env: Mapping[str, str]) -> tuple[list[str], str]:
    """Company labels this machine knows: the generated tomls on disk plus ENTERPRISE_LEAK_LABELS."""
    labels: set[str] = set()
    on_disk = 0
    for path in sorted(root.glob(GENERATED_GLOB)):
        m = GENERATED_TOML.search(path.name)
        if m and m.group(1) != TEMPLATE_STEM and _LABEL.fullmatch(m.group(1)):
            labels.add(m.group(1))
            on_disk += 1
    from_env = 0
    for raw in (env.get(LABELS_ENV) or "").split(","):
        label = raw.strip().lower()
        if label and _LABEL.fullmatch(label) and label not in FAKE_LABELS:
            labels.add(label)
            from_env += 1
    labels -= FAKE_LABELS
    parts = []
    if on_disk:
        parts.append("%d generated toml(s)" % on_disk)
    if from_env:
        parts.append("%d from %s" % (from_env, LABELS_ENV))
    return sorted(labels), ", ".join(parts)


def label_patterns(label: str, domain: str) -> tuple[list[re.Pattern[str]], re.Pattern[str]]:
    """The shapes a company name takes, for one known label: (lowercase shapes searched everywhere, the uppercase NAME token searched only where store names live)."""
    lo = re.escape(label)
    up = re.escape(label.upper().replace("-", "_"))
    lower = [
        re.compile(
            r"(?<![A-Za-z0-9_])(?:%s)-%s(?![A-Za-z0-9])" % ("|".join(RESOURCE_PREFIXES), lo)
        ),
        re.compile(
            r"(?<![A-Za-z0-9_-])%s(?:%s)?\.%s(?![A-Za-z0-9-])"
            % (lo, PROXY_SUFFIX, re.escape(domain))
        ),
        re.compile(r"enterprise\.%s\.toml" % lo),
    ]
    # A NAME token, with at least one `_` part beside the label. Searched tree-wide it fired on every test constant spelling a dictionary word (a control labelled `planted` matched `PLANTED_VAR` in 30 unrelated lines), so it runs only over the files that carry store names.
    upper = re.compile(
        r"(?<![A-Za-z0-9])(?:(?:[A-Z0-9]+_)+%s(?:_[A-Z0-9]+)*|%s(?:_[A-Z0-9]+)+)(?![A-Za-z0-9])"
        % (up, up)
    )
    return lower, upper


def store_surface(rel: str) -> bool:
    """A file where store names are written: the two secret records and the workflows that request secrets by name."""
    return rel in SECRET_RECORDS or rel.startswith(".github/")


def label_findings(
    root: pathlib.Path, files: list[str], labels: list[str], domain: str
) -> list[Finding]:
    """A finding per tracked line that spells a locally known company label in a company shape."""
    if not labels:
        return []
    compiled = [(label, *label_patterns(label, domain)) for label in labels]
    out: list[Finding] = []
    for rel in files:
        text = _read_text(root, rel)
        if text is None:
            continue
        stores = store_surface(rel)
        for label, lower, upper in compiled:
            pats = [*lower, upper] if stores else lower
            if label not in text and not (stores and label.upper().replace("-", "_") in text):
                continue
            out.extend(
                Finding(
                    rel,
                    text.count("\n", 0, m.start()) + 1,
                    "known-label",
                    "%r spells a company this machine has generated configs for" % m.group(0),
                    "write the opaque c<hex> id, the fake `acme` or `<company>` instead; "
                    "a tracked file is published",
                )
                for pat in pats
                for m in pat.finditer(text)
            )
    return out


def scan(
    root: pathlib.Path,
    public: frozenset[str],
    env: Mapping[str, str],
    domain: str | None = None,
    git_env: dict[str, str] | None = None,
) -> tuple[list[Finding], Shape]:
    """Every finding and the scan's shape; LeakSetupError when the instrument cannot look."""
    domain = domain or well_known.PRODUCT_DOMAIN
    shape = Shape()
    files = tracked_files(root, git_env)
    shape.tracked = len(files)
    if not files:
        raise LeakSetupError(
            "git lists zero tracked files in %s; the gate is not seeing the tree" % root
        )
    findings = generated_toml_findings(files)
    shape.generated_tracked = len(findings)
    pairs = store_names(root)
    shape.store_names = len(pairs)
    if not pairs:
        raise LeakSetupError(
            "zero store names read from %s; the store check would vouch for nothing"
            % ", ".join(SECRET_RECORDS)
        )
    findings += store_findings(root, pairs)
    findings += host_findings(root, files, public, domain, shape)
    labels, sources = known_labels(root, env)
    shape.labels, shape.label_sources = len(labels), sources
    findings += label_findings(root, files, labels, domain)
    return findings, shape


# ---------------------------------------------------------------------------
# The masker the two public reports print through.
# ---------------------------------------------------------------------------


def _strings(node: object, into: set[str]) -> None:
    if isinstance(node, str):
        into.add(node)
    elif isinstance(node, dict):
        for value in node.values():
            _strings(value, into)
    elif isinstance(node, list):
        for value in node:
            _strings(value, into)


class Masker:
    """Replaces company labels in names and hosts with `<company-N>`; everything public passes unchanged."""

    def __init__(
        self,
        public_labels: frozenset[str],
        public_names: frozenset[str],
        domain: str,
        enabled: bool = True,
    ) -> None:
        self.public_labels = public_labels
        self.public_names = public_names
        self.domain = domain
        self.enabled = enabled
        self._tokens: dict[str, str] = {}
        self._host = host_re(domain)
        self._resource = re.compile(
            r"(?<![A-Za-z0-9_.-])(%s)-([a-z0-9]+(?:-[a-z0-9]+)*)(?![A-Za-z0-9_-])"
            % "|".join(RESOURCE_PREFIXES)
        )

    @classmethod
    def identity(cls) -> Masker:
        return cls(frozenset(), frozenset(), well_known.PRODUCT_DOMAIN, enabled=False)

    @classmethod
    def for_tree(cls, root: pathlib.Path | None = None) -> Masker:
        """The masker for this checkout: regions.json, tracked worker tomls and well-known are public."""
        root = root or paths.repo_root()
        public: set[str] = set()
        try:
            _strings(json.loads((root / "regions.json").read_text(encoding="utf-8")), public)
        except (OSError, ValueError) as exc:
            raise LeakSetupError("regions.json cannot be read: %s" % exc) from None
        for rel in tracked_files(root):
            if (
                rel.startswith("workers/")
                and rel.endswith(".toml")
                and not GENERATED_TOML.search(rel)
            ):
                try:
                    _strings(tomllib.loads((root / rel).read_text(encoding="utf-8")), public)
                except (OSError, tomllib.TOMLDecodeError):
                    # A name this file would have vouched for is masked instead: the safe direction.
                    continue
        public.update(v for v in well_known.VALUES.values())
        return cls(names.reserved() | FAKE_LABELS, frozenset(public), well_known.PRODUCT_DOMAIN)

    @property
    def masked(self) -> int:
        return len(self._tokens)

    def _token(self, label: str) -> str:
        return self._tokens.setdefault(label, "<company-%d>" % (len(self._tokens) + 1))

    def _rest_is_public(self, rest: str) -> bool:
        return rest in self.public_labels or all(t in self.public_labels for t in rest.split("-"))

    def mask(self, text: str) -> str:
        if not self.enabled or not text:
            return text

        def host(m: re.Match[str]) -> str:
            label = m.group(1)
            if label_is_public(label, self.public_labels):
                return m.group(0)
            proxy = label.endswith(PROXY_SUFFIX)
            base = label.removesuffix(PROXY_SUFFIX)
            return "%s%s.%s" % (self._token(base), PROXY_SUFFIX if proxy else "", self.domain)

        def resource(m: re.Match[str]) -> str:
            whole, prefix, rest = m.group(0), m.group(1), m.group(2)
            if (
                whole in self.public_names
                or PR_PREVIEW.fullmatch(whole)
                or self._rest_is_public(rest)
            ):
                return whole
            return "%s-%s" % (prefix, self._token(rest))

        return self._resource.sub(resource, self._host.sub(host, text))


def report_masker(argv: list[str], env: Mapping[str, str], prog: str) -> tuple[Masker | None, str]:
    """The masker a public report prints through, from its argv: (masker, "") or (None, refusal)."""
    if not argv:
        return Masker.for_tree(), ""
    if argv == ["--unmasked"]:
        if env.get("GITHUB_ACTIONS"):
            return None, (
                "%s: --unmasked is refused under GITHUB_ACTIONS; the run log is public and would name "
                "every company" % prog
            )
        return Masker.identity(), ""
    return None, "%s takes no arguments but --unmasked (local runs only)" % prog


# ---------------------------------------------------------------------------
# Controls and the verdict.
# ---------------------------------------------------------------------------


def _fixture(base: pathlib.Path, domain: str) -> dict[str, str]:
    """A tracked tree with one planted case per check and a quiet twin beside each."""
    env = fixture_git_env()
    files = {
        "workers/account/enterprise.template.toml": 'name = "account-__COMPANY__"\n',
        "workers/account/enterprise.globex.toml": 'name = "account-globex"\n',
        ".ci/config/bws-secret-map.json": json.dumps(
            {
                "secrets": {
                    "ACCOUNT_JWT_SECRET": {"id": "1"},
                    "c0123abcd4567_ACCOUNT_JWT_SECRET": {"id": "2"},
                    "globex-jwt": {"id": "3"},
                    "INITECH_JWT_SECRET": {"id": "4"},
                }
            }
        ),
        ".ci/config/secret-supply.json": json.dumps(
            {
                "bootstrap_names": ["BWS_ACCESS_TOKEN"],
                "residue": {"X_ALIAS": {"alias_of": "X_STORE"}},
                "consumers": {"p": {"required": ["AWS_KEY_EU > AWS_KEY"], "optional": []}},
            }
        ),
        "docs/hosts.md": "\n".join(
            [
                "eu.%s and proxy.us.%s are regions" % (domain, domain),
                "acme.%s and acme-proxy.%s are the fake" % (domain, domain),
                "<company>.%s is a placeholder" % domain,
                "globex.%s leaks" % domain,
                "initech-proxy.%s leaks" % domain,
            ]
        ),
        "docs/labels.md": "proxy-initech\nINITECH_DOC_CONSTANT\ninitechnology is a word\nINITECH heading\n",
    }
    for rel, body in files.items():
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(body)
    subprocess.run(["git", "init", "-q"], cwd=base, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=base, check=True, env=env)
    # Untracked, as the generator leaves it: the source of the known label.
    (base / "workers/proxy").mkdir(parents=True, exist_ok=True)
    (base / "workers/proxy/enterprise.initech.toml").write_text('name = "proxy-initech"\n')
    return env


def selftest() -> int:
    """1 when a control fails, 0 when every one held. Both directions per check."""
    check = Checker()
    domain = well_known.PRODUCT_DOMAIN
    public = names.reserved() | FAKE_LABELS
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        env = _fixture(base, domain)
        findings, shape = scan(base, public, {}, domain, env)
        by_rule: dict[str, list[Finding]] = {}
        for f in findings:
            by_rule.setdefault(f.rule, []).append(f)
        tomls = [f.path for f in by_rule.get("tracked-company-toml", [])]
        check(
            "a tracked enterprise.globex.toml fires",
            tomls == ["workers/account/enterprise.globex.toml"],
        )
        check("the template stays quiet", "workers/account/enterprise.template.toml" not in tomls)
        stores = " ".join(f.what for f in by_rule.get("store-name", []))
        check(
            "an opaque store in the shared record fires",
            "c0123abcd4567_ACCOUNT_JWT_SECRET" in stores,
        )
        check("a non-opaque store name fires", "globex-jwt" in stores)
        check(
            "shared names stay quiet",
            "'ACCOUNT_JWT_SECRET'" not in stores and "AWS_KEY_EU" not in stores,
        )
        check("exactly two store findings", len(by_rule.get("store-name", [])) == 2)
        hosts = " ".join(f.what for f in by_rule.get("product-host", []))
        check("a company host fires", "'globex'" in hosts)
        check("a company proxy host fires", "'initech-proxy'" in hosts)
        check(
            "regions, the fake and a placeholder stay quiet",
            len(by_rule.get("product-host", [])) == 2
            and "'eu'" not in hosts
            and "acme" not in hosts,
        )
        labels = [f.what for f in by_rule.get("known-label", [])]
        check("both generated tomls' labels are known", shape.labels == 2)
        check(
            "a resource name spelling a known label fires",
            any("proxy-initech" in w for w in labels),
        )
        check(
            "an uppercase NAME token spelling it fires",
            any("INITECH_JWT_SECRET" in w for w in labels),
        )
        check(
            "a longer word containing it stays quiet", not any("initechnology" in w for w in labels)
        )
        check("a bare uppercase word stays quiet", "'INITECH'" not in " ".join(labels))
        check(
            "a NAME token outside the store files stays quiet",
            "INITECH_DOC_CONSTANT" not in " ".join(labels),
        )
        check(
            "a known label fires in every company shape and nowhere else",
            sorted(w.split("'")[1] for w in labels)
            == sorted(
                [
                    "INITECH_JWT_SECRET",
                    "account-globex",
                    "globex.%s" % domain,
                    "initech-proxy.%s" % domain,
                    "proxy-initech",
                ]
            ),
        )
        check("the scan counted a non-trivial tree", shape.tracked == 6 and shape.store_names == 8)
        empty = pathlib.Path(tmp) / "empty"
        empty.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=empty, check=True, env=env)
        try:
            scan(empty, public, {}, domain, env)
            refused = False
        except LeakSetupError:
            refused = True
        check("zero tracked files is a refusal, not a pass", refused)

    m = Masker(public, frozenset({"account-db-eu"}), domain)
    check("a company Worker name is masked", m.mask("account-globex") == "account-<company-1>")
    check(
        "the same company's host takes the same token",
        m.mask("globex.%s/*" % domain) == "<company-1>.%s/*" % domain,
    )
    check(
        "a proxy host keeps its suffix",
        m.mask("globex-proxy.%s" % domain) == "<company-1>-proxy.%s" % domain,
    )
    check(
        "a second company takes the next token", m.mask("configs-initech") == "configs-<company-2>"
    )
    check(
        "region names, public names, previews and strays pass",
        [
            m.mask(s)
            for s in ("account-eu", "account-db-eu", "signer-bench-eu", "stray-worker", "pr-12")
        ]
        == ["account-eu", "account-db-eu", "signer-bench-eu", "stray-worker", "pr-12"],
    )
    check(
        "an embedded family word is not a resource",
        m.mask("rediacc-account-zz") == "rediacc-account-zz",
    )
    check("identity masks nothing", Masker.identity().mask("account-globex") == "account-globex")
    return 0 if check.ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return selftest()
    if argv:
        print("usage: check_enterprise_leak.py [--selftest]", file=sys.stderr)
        return 2
    refused = controls_first(GATE, selftest)
    if refused:
        return refused
    try:
        findings, shape = scan(paths.repo_root(), names.reserved() | FAKE_LABELS, dict(os.environ))
    except LeakSetupError as exc:
        print("%s: %s" % (GATE, exc), file=sys.stderr)
        return 2
    for f in findings:
        print(f.render(), file=sys.stderr)
    if findings:
        print(
            "%s: %d finding(s); %s. No company name may reach a tracked file or a public log."
            % (GATE, len(findings), shape.render()),
            file=sys.stderr,
        )
        return 1
    print("%s: clean; %s" % (GATE, shape.render()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
