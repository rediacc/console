"""Port of `scripts/ops/linode-cluster-validation.sh` (248 lines): Linode cross-DC cluster validation for the Ceph+Kubernetes campaign.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.linode_cluster_validation [phase...] [--yes]

Validates the Linode VLAN cluster path against REAL Linode infrastructure and proves a clean provision -> teardown lifecycle with zero surviving billable resources. Nothing billable runs without `--yes`.

Phases (default `preflight plan`):
  preflight    inspect orphaned tofu state and query the live Linode API; exit 2 when live billable instances or volumes match a campaign prefix (never auto-destroys)
  plan         generate the cluster `main.tf.json` with the real CLI generator and run `terraform plan` (creates nothing)
  provision    [--yes] `rdc cluster create --declare-only` + `rdc cluster create`. BILLABLE
  verify       assert zero survivors in `tofu state list` and in the Linode API; exit 4 on any
  destroy      [--yes] `rdc cluster destroy --force`, verify, remove the workdir
  idempotency  [--yes] provision -> destroy -> verify

Config (environment): `CLUSTER_NAME` (default `lval`), `CLUSTER_POOLS` (default `k8s:k8s-server:2:g6-nanode-1`), `PROVIDER` (default `my-linode`), `NETWORK_CIDR` (default `10.0.0.0/24`). The Linode API token is the `apiToken` of the PROVIDER entry in `~/.config/rediacc/rediacc.json`. `rdc` is `./rdc.sh`.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_linode_cluster_validation.py` that fails on the bash behaviour).

  1. NOTHING IS INTERPOLATED INTO SOURCE CODE. `$CONFIG_JSON`, `$PROVIDER`, `$CLUSTER_NAME`, `$CLUSTER_POOLS`, `$NETWORK_CIDR` and the label prefix were spliced into `python3 -c "..."` and into a generated `.mts` file, so a provider name or pool spec containing a quote ran as code (and a `'` in any of them broke the script). The values reach the harness as JSON.
  2. THE LISTING IS NOT TRUNCATED. `GET /linode/instances` returns one page of at most 100 entries, so a zero-survivor verdict on a busy account read only the first page. Further pages are fetched when the response reports `pages > 1`; the first request is byte-identical to the bash.
  3. A FAILED LISTING IS A NAMED FAILURE. `curl -fsS` inside `$(...)` ended the script with curl's own status (22) and no sentence saying which scan failed, and for `verify` that is a zero-survivor check that never ran.
  4. `config cluster add` IS ALLOWED TO FAIL ONLY WHEN THE CLUSTER ALREADY EXISTS. `|| true` also swallowed a wrong provider name or a missing token, after which `cluster create` failed with a message about a cluster that was never defined. A non-zero `add` is tolerated when its output says the cluster exists, and fails the phase otherwise.
  5. `--help` PRINTS THIS MODULE'S USAGE, not `sed -n '2,40p'` of the script.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths

PHASES = ("preflight", "plan", "provision", "verify", "destroy", "idempotency")
API = "https://api.linode.com/v4"
CAMPAIGN_PREFIXES = ("rediacc", "linode", "lval")
HELP = __doc__ or ""


def log(message: str) -> None:
    print("\033[1;36m[linode-val]\033[0m %s" % message)


def warn(message: str) -> None:
    print("\033[1;33m[linode-val WARN]\033[0m %s" % message, file=sys.stderr)


def err(message: str) -> None:
    print("\033[1;31m[linode-val ERROR]\033[0m %s" % message, file=sys.stderr)


class PhaseError(Exception):
    """A phase failed with a specific exit status."""

    def __init__(self, status: int, message: str | None = None) -> None:
        super().__init__(message or "")
        self.status = status
        self.message = message


class Validation:
    def __init__(self, yes: bool) -> None:
        self.yes = yes
        self.cluster = os.environ.get("CLUSTER_NAME") or "lval"
        self.provider = os.environ.get("PROVIDER") or "my-linode"
        self.cidr = os.environ.get("NETWORK_CIDR") or "10.0.0.0/24"
        self.pools = os.environ.get("CLUSTER_POOLS") or "k8s:k8s-server:2:g6-nanode-1"
        self.root = paths.repo_root()
        self.rdc = str(self.root / "rdc.sh")
        home = pathlib.Path(os.environ.get("HOME") or str(pathlib.Path.home()))
        self.config_json = home / ".config" / "rediacc" / "rediacc.json"
        self.tofu_dir = home / ".config" / "rediacc" / "tofu" / "clusters" / self.cluster
        self.home = home
        self.token = ""

    # ------------------------------------------------------------------ Linode API

    def require_token(self) -> None:
        try:
            cfg = json.loads(self.config_json.read_text(encoding="utf-8"))
            token = cfg["resources"]["cloudProviders"][self.provider]["apiToken"]
        except (OSError, ValueError, KeyError, TypeError):
            token = ""
        if not token:
            raise PhaseError(
                1, "No apiToken for provider '%s' in %s" % (self.provider, self.config_json)
            )
        self.token = str(token)

    def _api_page(self, path: str) -> dict:
        proc = subprocess.run(
            ["curl", "-fsS", "-H", "Authorization: Bearer %s" % self.token, "%s%s" % (API, path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise PhaseError(
                1,
                "the Linode API listing %s failed (curl exit %d): %s"
                % (path, proc.returncode, proc.stderr.strip()[:200]),
            )
        try:
            body = json.loads(proc.stdout)
        except ValueError:
            raise PhaseError(1, "the Linode API listing %s did not return JSON" % path) from None
        if not isinstance(body, dict):
            raise PhaseError(1, "the Linode API listing %s returned a non-object body" % path)
        return body

    def api_list(self, path: str) -> list[dict]:
        items: list[dict] = []
        body = self._api_page(path)
        pages = body.get("pages", 1)
        items += [d for d in body.get("data", []) if isinstance(d, dict)]
        page = 2
        while isinstance(pages, int) and page <= pages:
            more = self._api_page("%s?page=%d" % (path, page))
            items += [d for d in more.get("data", []) if isinstance(d, dict)]
            page += 1
        return items

    def scan_live(self, prefix: str) -> tuple[int, int, int]:
        """Counts of instances, volumes and VLANs whose label starts with `prefix`; the matches are listed on stderr."""
        self.require_token()
        instances = [
            i
            for i in self.api_list("/linode/instances")
            if str(i.get("label", "")).startswith(prefix)
        ]
        for i in instances:
            print(
                "  INSTANCE",
                i["id"],
                i["label"],
                i["status"],
                i["region"],
                i["type"],
                file=sys.stderr,
            )
        volumes = [
            v for v in self.api_list("/volumes") if str(v.get("label", "")).startswith(prefix)
        ]
        for v in volumes:
            print("  VOLUME", v["id"], v["label"], v["status"], file=sys.stderr)
        vlans = [
            v
            for v in self.api_list("/networking/vlans")
            if str(v.get("label", "")).startswith(prefix)
        ]
        for v in vlans:
            print("  VLAN", v["label"], v["region"], v.get("linodes"), file=sys.stderr)
        return len(instances), len(volumes), len(vlans)

    # ------------------------------------------------------------------ phases

    def phase_preflight(self) -> None:
        log("Orphan preflight: inspecting tofu state + live Linode API")
        self.require_token()
        for d in (
            self.home / ".config/rediacc/tofu/linode-1",
            self.home / ".config/rediacc/tofu/linodeX",
            self.tofu_dir,
        ):
            state = d / "terraform.tfstate"
            if not state.is_file():
                continue
            log("tofu state in %s:" % d)
            for resource in json.loads(state.read_text(encoding="utf-8")).get("resources", []):
                for inst in resource.get("instances", []):
                    a = inst.get("attributes", {})
                    print(
                        "  ",
                        resource.get("type"),
                        a.get("label"),
                        "id",
                        a.get("id"),
                        a.get("status"),
                        a.get("region"),
                    )
        total = 0
        for prefix in (self.cluster, *CAMPAIGN_PREFIXES):
            instances, volumes, _ = self.scan_live(prefix)
            total += instances + volumes
        if total > 0:
            err(
                "LIVE billable resources exist on Linode (see stderr list above). Surface to operator; NOT auto-destroying."
            )
            raise PhaseError(2)
        log("Preflight CLEAN: no live billable instances/volumes matching campaign prefixes.")

    def phase_plan(self) -> None:
        log("Dry-run: generating tf.json via the real generator + terraform plan (free)")
        self.require_token()
        work = pathlib.Path(tempfile.mkdtemp())
        try:
            spec = {
                "root": str(self.root),
                "provider": self.provider,
                "cluster": self.cluster,
                "cidr": self.cidr,
                "pools": self.pools,
                "out": str(work / "main.tf.json"),
            }
            (work / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            harness = work / "gen.mts"
            harness.write_text(HARNESS, encoding="utf-8")
            self._run(
                ["npx", "tsx", str(harness), str(work / "spec.json")],
                cwd=self.root,
                what="tf.json generation",
            )
            self._run(
                ["terraform", "init", "-input=false"], cwd=work, what="terraform init", quiet=True
            )
            self._run(
                ["terraform", "plan", "-input=false", "-no-color"], cwd=work, what="terraform plan"
            )
            log("Plan complete (nothing created). Review the '+ N to add' summary above.")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _require_yes(self, phase: str) -> None:
        if not self.yes:
            raise PhaseError(3, "'%s' is BILLABLE and needs --yes. Refusing without it." % phase)

    def _run(self, argv: list[str], cwd=None, what: str = "", quiet: bool = False) -> int:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                check=False,
                stdout=subprocess.DEVNULL if quiet else None,
            )
        except FileNotFoundError:
            raise PhaseError(127, "%s: command not found" % argv[0]) from None
        if proc.returncode != 0:
            raise PhaseError(
                proc.returncode, "%s failed (exit %d)" % (what or argv[0], proc.returncode)
            )
        return proc.returncode

    def phase_provision(self) -> None:
        self._require_yes("provision")
        log(
            "Provisioning cluster '%s' (%s) on %s (BILLABLE)"
            % (self.cluster, self.pools, self.provider)
        )
        pool_args: list[str] = []
        for spec in self.pools.split(","):
            pool_args += ["--pool", spec]
        # The twin's declare step names a `config` subcommand the CLI no longer has, and `cluster create`/`cluster destroy` take the name positionally (check:cli-examples, 2026-10-01): its provision and destroy calls would all fail. Declare with `cluster create --declare-only` (an existing declaration is tolerated, as before), then provision with a bare `cluster create`.
        added = subprocess.run(
            [
                self.rdc,
                "cluster",
                "create",
                self.cluster,
                "--declare-only",
                "--provider",
                self.provider,
                "--network-cidr",
                self.cidr,
                "--network-primitive",
                "vlan",
                *pool_args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        sys.stdout.write(added.stdout)
        sys.stderr.write(added.stderr)
        if added.returncode != 0 and "exist" not in (added.stdout + added.stderr).lower():
            raise PhaseError(
                added.returncode,
                "rdc cluster create --declare-only failed (exit %d)" % added.returncode,
            )
        self._run([self.rdc, "cluster", "create", self.cluster], what="rdc cluster create")

    def phase_verify(self) -> None:
        log("Verifying ZERO survivors for cluster '%s'" % self.cluster)
        survivors = 0
        if (self.tofu_dir / "terraform.tfstate").is_file():
            listed = subprocess.run(
                ["terraform", "state", "list"],
                cwd=str(self.tofu_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            n = (
                len([ln for ln in listed.stdout.splitlines() if ln.strip()])
                if listed.returncode == 0
                else 0
            )
            if n:
                err("tofu state still lists %d resource(s) in %s" % (n, self.tofu_dir))
                survivors += n
        instances, volumes, vlans = self.scan_live(self.cluster)
        if instances or volumes or vlans:
            err(
                "Linode API survivors: instances=%d volumes=%d vlans=%d"
                % (instances, volumes, vlans)
            )
            survivors += instances + volumes + vlans
        if survivors:
            err("ZERO-SURVIVOR CHECK FAILED (%d survivor(s))." % survivors)
            raise PhaseError(4)
        log("ZERO survivors confirmed (tofu state empty AND Linode API clean).")

    def phase_destroy(self) -> None:
        self._require_yes("destroy")
        log("Destroying cluster '%s'" % self.cluster)
        rc = subprocess.run(
            [self.rdc, "cluster", "destroy", self.cluster, "--force"], check=False
        ).returncode
        if rc != 0:
            warn("destroy returned non-zero; verifying anyway")
        self.phase_verify()
        shutil.rmtree(self.tofu_dir, ignore_errors=True)
        log("Per-cluster tofu workdir removed: %s" % self.tofu_dir)

    def phase_idempotency(self) -> None:
        self._require_yes("idempotency")
        log("Idempotency loop: bare provision -> destroy -> verify")
        self.phase_provision()
        self.phase_destroy()
        log("Idempotency loop complete: clean create/destroy with zero orphans.")


HARNESS = """import { readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const spec = JSON.parse(readFileSync(process.argv[2], 'utf-8'));
const { resolveProviderMapping } = await import(join(spec.root, 'packages/cli/src/services/tofu/provider-resolver.ts'));
const { generateClusterTfJson } = await import(join(spec.root, 'packages/cli/src/services/tofu/cluster-tf-generator.ts'));
const cfg = JSON.parse(readFileSync(join(homedir(), '.config/rediacc/rediacc.json'), 'utf-8'));
const pc = cfg.resources.cloudProviders[spec.provider];
const pools = spec.pools.split(',').map((s) => {
  const [name, role, count, size] = s.split(':');
  return { name, role, count: Number(count), ...(size ? { size } : {}) };
});
const tf = generateClusterTfJson({
  clusterName: spec.cluster,
  mapping: resolveProviderMapping(pc),
  apiToken: pc.apiToken,
  sshPublicKey: readFileSync(join(homedir(), '.ssh/id_ed25519.pub'), 'utf-8').trim(),
  network: { primitive: 'vlan', cidr: spec.cidr, mtu: 1500 },
  pools,
});
writeFileSync(spec.out, JSON.stringify(tf, null, 2));
"""


def main(argv: list[str]) -> int:
    phases: list[str] = []
    yes = False
    for arg in argv:
        if arg == "--yes":
            yes = True
        elif arg in PHASES:
            phases.append(arg)
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP)
            return 0
        else:
            err("Unknown argument: %s" % arg)
            return 1
    if not phases:
        phases = ["preflight", "plan"]
    validation = Validation(yes)
    try:
        for phase in phases:
            getattr(validation, "phase_%s" % phase)()
    except PhaseError as exc:
        if exc.message:
            err(exc.message)
        return exc.status
    log("Done: %s" % " ".join(phases))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
