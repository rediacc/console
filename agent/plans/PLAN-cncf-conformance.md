# PLAN: Certified Kubernetes conformance for the Rediacc-wrapped k3s -- a reproducible local run and captured artifacts (submission parked)

Status: proposed -- converted from console#606 (operator picked this item 2026-11-16); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: no-dep -- the run uses `rdc cluster create --provider kvm` as it is today; PLAN-kubelet-cgroup-rediacc-slice.md changes kubelet args, and a later change there re-runs C3 rather than blocking this plan
Priority: P3 -- an external mark with no product gap behind it; the run itself is the useful part, since a failing conformance test would be a real defect in the wrapping
Concurrency: parallel -- one new ops script, its test, one pins entry and a new docs/conformance tree; no file in another live plan's Owns
Owns: agent/plans/PLAN-cncf-conformance.md, .ci/rediacc_ci/ops/k8s_conformance.py, .ci/rediacc_ci/tests/test_ops_k8s_conformance.py, .ci/config/pins.json (one sonobuoy entry), docs/conformance/**
Source: https://github.com/rediacc/console/issues/606

## Ask

console#518 section 4 asked whether the Rediacc-wrapped k3s can carry the Certified Kubernetes mark; console#606 moved it to the operator-only list. The operator picked it on 2026-11-16. The plan runs the official conformance suite against a cluster built exactly the way customers build one (`rdc cluster create`), keeps the artifacts in the tree in the layout cncf/k8s-conformance wants, and leaves the parts only the operator can do (CNCF participation form, vendor identity, the pull request itself) as marked boxes.

## Context (checked 2026-11-16 against the tree and the CNCF repository)

1. renet embeds k3s `1.37.2+k3s1` (`private/renet/embed-assets.lock.json:140-171`, also asserted by `embed.AssetK3sVersion`, `:170`). The Kubernetes minor is therefore v1.37.
2. The wrapping differs from stock k3s in ways conformance can see: `--disable traefik --disable servicelb` always (`private/renet/pkg/kube/distro/k3s.go:148-151`), a kubelet root dir and optional cgroup root (`private/renet/pkg/kube/distro/distro.go:70-74`), the data dir inside the control datastore (`packages/cli/src/services/cluster/cluster-kube.ts:56-70`), and the API bound to the node's private NIC (`cluster-kube.ts:315-320`). Pod Security `restricted` is a label on repo namespaces only (`private/renet/pkg/reporuntime/kube_templates.go:46-47`), not a cluster-wide admission default, so conformance's own namespaces are unaffected. The NodePort and hostNetwork refusals live in renet's manifest linter (`private/renet/pkg/kube/manifest.go`) and apply to `rdc` applies, not to a client talking to the API directly.
3. cncf/k8s-conformance (`instructions.md`, read 2026-11-16): run `sonobuoy run --mode=certified-conformance` (required since v1.16), `sonobuoy retrieve`, and take `e2e.log` and `junit_01.xml` from `plugins/e2e/results/global/`. A submission is one squashed commit adding `vX.Y/<dir>/` with `README.md` (how to reproduce), `e2e.log`, `junit_01.xml` and `PRODUCT.yaml` (`vendor`, `name`, `version` = product version, `website_url`, `documentation_url`, `type` = distribution, `description`, `contact_email_address`; optional `repo_url`, `product_logo_url` as SVG, AI or EPS). The PR title is `Conformance results for vX.Y/<dir>`, one PR per Kubernetes version, and a bot checks title, folder and version. The vendor "must have a signed participation form on file with the CNCF". Hydrophone is also accepted.
4. The CNCF FAQ (`faq.md`, read 2026-11-16): the current release and the two before it are certifiable; a certification stays valid while a newer version is certified at least once a year; CNCF members pay nothing, a commercial non-member pays an annual fee equal to joining CNCF and the Linux Foundation; each product name needs its own participation form; the logo may not derive from the Kubernetes wheel. The FAQ says nothing on whether a product built on a certified distribution (k3s) needs its own certification; carrying the mark under the Rediacc name does.
5. The repository's newest version folders are v1.37, v1.36, v1.35 (read 2026-11-16), so v1.37 is certifiable now and stays so through v1.39's release.
6. Cluster verbs need `REDIACC_ALLOW_CLUSTER_OPS` in the launching shell (`packages/cli/src/utils/__tests__/cluster-env.test.ts`). `rdc cluster create --provider kvm` needs a dedicated `--net-name`/`--net-base` (`packages/cli/src/commands/cluster/declare.ts:63-91`), and `--control-ds-backend local` keeps a k8s-only cluster free of Ceph (`packages/cli/src/commands/cluster/index.ts:56-60`). Measured host memory 2026-11-16: 27 GiB available beside the shared ops fleet; VMs 11, 12 and 21-23 belong to other work.
7. Tool pins live in `.ci/config/pins.json` and move through `npm run pins -- bump`; the dependency freshness window is `.ci/config/release-age.json`.
8. Coverage search: no live or `_done/` plan covers conformance; `grep -ri 'sonobuoy\|hydrophone'` over `.ci`, `scripts`, `packages/*/src` and `private/renet` is empty.

## Design

**D1. One reproducible runner, not a hand session.** `.ci/rediacc_ci/ops/k8s_conformance.py` takes a cluster name, fetches its kubeconfig with `rdc cluster kubeconfig <cluster>`, checks that at least two nodes are Ready, runs the pinned sonobuoy in `certified-conformance` mode, polls `sonobuoy status --json` until done (bounded by `--timeout`, default 180 minutes), retrieves the tarball, copies `e2e.log` and `junit_01.xml` into `docs/conformance/v<minor>/rediacc/`, parses the junit for the pass, fail and skip counts, and runs `sonobuoy delete --wait`. Exit 0 only when failures are zero and the run reports completed. The Kubernetes minor comes from the API's `/version`, never typed.

**D2. Cluster shape: the customer path, small.** `cc-lab` on `renet15`/`192.168.115` (a net no other plan uses): one control VM, one k8s-server and two k8s-agents at `VM_RAM_WORKER=3072`, `--control-ds-backend local`, about 10 GiB. Two agents because several conformance tests schedule across nodes. No Ceph: conformance tests no storage class.

**D3. A failure is a defect, fixed before submission.** A failing conformance test points at the wrapping (Context 2) or the eBPF isolation. Each one becomes a worklist finding triaged through `worklist.py --triage`, and the run repeats after the fix. Skipping a test is not an option in certified mode.

**D4. Artifacts live in the tree.** `docs/conformance/v1.37/rediacc/` holds exactly the four files the CNCF PR needs, so the operator's PR is a copy. `README.md` gives the reproduction: `rdc cluster create` with D2's flags, then `sonobuoy run --mode=certified-conformance`. `PRODUCT.yaml` fields the session cannot know (vendor legal entity, contact address, logo) stay as a list in C6, filled only by the operator.

**D5. Re-certification follows the k3s pin.** A k3s minor bump in `embed-assets.lock.json` makes a new run due within a year (Context 4); this plan records the cadence in the README and adds no gate, because the run needs a VM lab CI does not have.

Out of scope: hosting a certified-conformance run in CI (no VM lab on runners; same constraint as console#521), and any trademark or logo design.

## Ruling

Operator ASKED:2026-11-16T08:59Z, after reviewing cost (non-member fee equal to CNCF plus Linux Foundation membership, about 7,000 USD a year at 1-10 employees) and the yearly re-certification: "Run conformance locally only". The participation form, vendor entity, `PRODUCT.yaml` contact fields and the cncf/k8s-conformance pull request are out of scope; the artifacts under `docs/conformance/` stay ready so a submission is a copy if that changes.

## Boxes

- [ ] C1 [writer] Pin sonobuoy in `.ci/config/pins.json` at the newest release that has cleared the `release-age.json` window and supports v1.37, recorded with its sha256 per platform. Accept: `npm run pins -- verify` rc 0.
- [ ] C2 [writer] `k8s_conformance.py` (D1) and `test_ops_k8s_conformance.py`: fake `rdc`, `kubectl` and `sonobuoy` on PATH; tests pin the argv sequence, the refusal on fewer than two Ready nodes, the timeout path, the junit parse (counts from a fixture `junit_01.xml`), exit non-zero on any failed test, and that `sonobuoy delete` runs on every exit path. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_k8s_conformance.py -q` rc 0.
- [ ] C3 [live] Build `cc-lab` (D2) from a shell with `REDIACC_ALLOW_CLUSTER_OPS=cc-lab`: `VM_RAM_WORKER=3072 rdc cluster create cc-lab --provider kvm --net-name renet15 --net-base 192.168.115 --pool s:k8s-server:1 --pool w:k8s-agent:2 --control-ds-backend local`, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.k8s_conformance cc-lab`. Accept: rc 0, zero failed tests in `docs/conformance/v1.37/rediacc/junit_01.xml`, and the pass, skip and duration figures recorded under this box. A failing test opens a finding (D3) and this box repeats after its fix.
- [ ] C4 [live] Tear down: `rdc cluster destroy cc-lab`. Accept: `virsh -c qemu:///system list --all` shows no `cc-lab` VM.
- [ ] C5 [writer] `docs/conformance/v1.37/rediacc/README.md` (D4 reproduction, the k3s version, the renet and rdc versions the run used, and the D5 cadence) and `PRODUCT.yaml` with every field the tree can supply (`name`, `version` from the release tag the run used, `website_url`, `documentation_url`, `type: distribution`, `description`, `repo_url`) and the operator fields left out. Accept: `python3 -c "import yaml,sys; d=yaml.safe_load(open('docs/conformance/v1.37/rediacc/PRODUCT.yaml')); sys.exit(0 if d['type']=='distribution' else 1)"` rc 0 and `npm run check:ci-prose-style` rc 0.

## Risks

- **The eBPF isolation and NodePort tests.** Conformance exercises NodePort Services and pod-to-pod traffic across nodes; the per-cluster /26 ACLs or the kubelet cgroup root may fail some of them. That is the point of the run (D3), and it can turn a P3 item into product fixes.
- **Image pulls.** Sonobuoy and the conformance image come from public registries; a lab without egress fails C3 at pull time. The runner names the image that failed to pull rather than timing out silently.
- **Version drift during review.** A k3s pin bump to v1.38 before the PR merges does not invalidate a v1.37 submission (Context 5); the next run targets the new minor.
- **Vendor identity.** Nothing here should guess the legal entity or a contact address; C6 is the only source of them.
