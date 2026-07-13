import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import type { ExecResult } from '../../src/utils/bridge/types';

// Suite 15 (`E2E K8s` job): a k8s repo end to end on the DATASTORE-CLUSTER model
// (redesign spec 06 §15). It promotes the wave3b deliverable-5 transcript
// (scratchpad/reports/p1-wave3b-vm.md) to a suite: a cluster-attached LOCAL
// datastore + a kube repo with a DECLARED VOLUME and a DECLARED SECRET, brought
// up through the runtime-generic `repository up` dispatch (kube arm:
// ApplyIsolation → ProvisionVolumes → InjectSecrets → Deploy).
//
// What it proves on the NEW model:
//   - anchor cluster: the control plane lives INSIDE a cluster-labeled control
//     datastore (`ds-control-<cluster>`); `kube install` on its mount is the
//     whole cluster (spec 02 §1 / 04 §1). Dedicated non-loopback node IP.
//   - kube repo up: repository_up on a repo folder inside a cluster-attached
//     data datastore materializes the isolation trio (PSA-restricted namespace +
//     default-deny NetworkPolicies + repo-namespace VAP), a no-provisioner
//     StorageClass, a bound local PV per declared volume, a Running pod, the
//     ROLE ConfigMap, and the wave3b per-namespace Opaque Secret transport.
//   - LOCAL-tier fork: a local datastore fork is REFUSED by design (gate C8);
//     repos inside a local datastore fork individually by REFLINK. So the fork
//     proof here is `repository fork` (CoW repo clone) + `repository up` on the
//     fork: instant, data diverges, parent untouched.
//
// RED-UNTIL-LIVE-RUN (spec 06 authoring bar): this file is authored to COMPILE
// (tsc) + keep the coverage gate green; its BODY is not executed by this wave
// (no live k3s-on-a-worker + RAM window). The live follow-up (P3 gate item 5)
// must exercise: node Ready on 10.150.x.1, the 9 up-verification checks, the F5
// default-SC hazard, and the reflink fork divergence — mirroring p1-wave3b-vm.md.
//
// Gated on K8S_MODE=1 + at least one worker VM.
const enabled = process.env.K8S_MODE === '1';
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && workers.length >= 1;

const K3S = '/usr/local/bin/rediacc-k3s';
const CLUSTER = 'prod';
// The anchor: a cluster-labeled control datastore whose mount holds the k3s
// data-dir (the control-plane image IS the cluster).
const CTRL_DS = `ds-control-${CLUSTER}`;
const CTRL_MOUNT = `/mnt/rediacc-ds/${CTRL_DS}`;
const CTRL_NET = '2816';
const KC = `${CTRL_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;
// The data datastore the kube repo lives on (cluster backref ⇒ KubeRuntime).
const DATA_DS = 'shopds';
const DATA_MOUNT = `/mnt/rediacc-ds/${DATA_DS}`;
const REPO = 'shop';
const REPO_NET = '2880';
const NS = REPO; // the repo's namespace mirrors its name
const SC = `rediacc-ds-${DATA_DS}`; // the repo's no-provisioner StorageClass
const APP_SECRET_VALUE = 's3cr3t-prod';
const FORK_REPO = `${REPO}-joseph`;
const FORK_NET = '2944';

// The kube repo's declared app: an annotated ClusterIP Service (routable), a PVC
// naming the repo's rediacc StorageClass (the F5 hazard guard — a PVC that omits
// it is silently adopted by stock k3s local-path), and a restricted-PSA-compliant
// Deployment that writes a marker into the local PV so fork divergence is
// observable. `scanDeclaredVolumes` reads the PVC to provision the LUKS volume.
const APP_MANIFEST = `apiVersion: v1
kind: Service
metadata:
  name: web
  annotations:
    rediacc.service_port: "80"
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 80
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ${SC}
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        runAsGroup: 65534
        fsGroup: 65534
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: busybox:1.36
          command: ["sh", "-c", "test -s /data/marker.txt || echo original-data > /data/marker.txt; exec tail -f /dev/null"]
          envFrom:
            - secretRef:
                name: rediacc-env
                optional: true
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: data
`;

// A minimal Rediaccfile: the kube repo runs its lifecycle through up()/health()
// exactly like a docker repo (the runtime-generic dispatch), and the manifests/
// deploy rides the Deploy phase.
const REDIACCFILE = `#!/usr/bin/env bash
up() { :; }
down() { :; }
health() { exit 0; }
`;

test.describe
  .serial('k8s repo end to end (datastore-cluster) @bridge @kube @k8s', () => {
    test.skip(!canRun, 'Requires K8S_MODE=1 and a worker VM');
    test.setTimeout(600_000);

    let w1: BridgeTestRunner;

    // --- kubectl-over-SSH helpers (no host kubectl; use the embedded k3s) ---
    const kubectl = async (args: string): Promise<ExecResult> =>
      w1.executeViaBridge(`sudo ${K3S} kubectl --kubeconfig ${KC} ${args}`);

    const writeFile = async (path: string, content: string): Promise<void> => {
      const b64 = Buffer.from(content).toString('base64');
      const res = await w1.executeViaBridge(
        `echo ${b64} | base64 -d | sudo tee ${path} >/dev/null`
      );
      expect(res.code, `write ${path}`).toBe(0);
    };

    const poll = async (
      fn: () => Promise<boolean>,
      timeoutMs = 120_000,
      stepMs = 5_000
    ): Promise<boolean> => {
      const attempts = Math.max(1, Math.ceil(timeoutMs / stepMs));
      for (let i = 0; i < attempts; i++) {
        if (await fn()) return true;
        await new Promise((res) => setTimeout(res, stepMs));
      }
      return fn();
    };

    const nodeReady = async (): Promise<boolean> => {
      const res = await kubectl('get nodes --no-headers');
      return res.code === 0 && /\sReady\s/.test(res.stdout);
    };

    const nodeName = async (): Promise<string> => {
      const res = await kubectl('get nodes -o jsonpath="{.items[0].metadata.name}"');
      return res.stdout.trim();
    };

    const podRunning = async (ns: string): Promise<boolean> => {
      const res = await kubectl(`-n ${ns} get pods -l app=web --no-headers`);
      return res.code === 0 && /\sRunning\s/.test(res.stdout);
    };

    const marker = async (ns: string): Promise<string> => {
      const res = await kubectl(`-n ${ns} exec deploy/web -- cat /data/marker.txt`);
      return res.stdout.trim();
    };

    // Bring the kube repo up carrying its declared secret. Secrets ride the SAME
    // CLI transport as the docker path: REDIACC_SECRET_<NAME> in the environment
    // → collectEnvSecrets → SecretSet.Env → InjectSecrets → per-namespace Opaque
    // Secret (wave3b). So the up call must carry the env var (bridge-once cannot).
    const repoUpWithSecret = async (name: string): Promise<ExecResult> =>
      w1.executeViaBridge(
        `sudo env REDIACC_SECRET_APP_SECRET=${APP_SECRET_VALUE} renet repository up ` +
          `--name ${name} --datastore ${DATA_MOUNT} --network-id ${REPO_NET}`
      );

    // A stopped k3s node leaves KERNEL mounts behind in TWO places: submounts UNDER
    // the datastore mount (kubelet pod volumes) and containerd overlays mounted at
    // /run/k3s/containerd/... whose lowerdir/upperdir point INTO the datastore (they
    // hold it busy from OUTSIDE its path). `kube uninstall` (cgroup-kill) unwinds
    // neither, so the datastore release is then CORRECTLY refused by the
    // no-lazy-success guard (spec 03 §2b, "target is busy"). The suite unwinds what
    // it created; the missing product porcelain is gate finding #20 (4 witnesses).
    //
    // Shell form: executeViaBridge relays through THREE shells and escapeForNestedSSH
    // does NOT escape `$`, so this stays variable-free (a `$(...)` would be expanded
    // on the LOCAL host). Excluding `^<root>/` from the outside-holder branch keeps a
    // SIBLING datastore (a prefix match) out of the list.
    const unwindSubmounts = async (runner: BridgeTestRunner, mount: string): Promise<void> => {
      const root = mount.replace(/\/[^/]+$/, '');
      const select =
        `{ cut -d" " -f2 /proc/mounts | grep "^${mount}/"; ` +
        `grep -F "${mount}" /proc/mounts | cut -d" " -f2 | grep -v "^${root}/"; } | sort -ru`;
      const res = await runner.executeViaBridge(
        `sudo bash -c 'for i in 1 2 3; do ${select} | xargs -r -n1 umount 2>/dev/null; ${select} | xargs -r -n1 umount -l 2>/dev/null; sleep 1; done; udevadm settle 2>/dev/null; ` +
          `sync; echo REMAINING_HOLDERS:; ${select}'; true`
      );
      process.stdout.write(
        `[suite15 unwind ${mount}] ${res.stdout.trim().replaceAll('\n', ' | ')}\n`
      );
    };

    // Every mountpoint the PRODUCT owns under the repo folder (the per-volume LUKS
    // mounts). `repository down` must leave none (CT-07 converge, no leak).
    const repoVolumeMounts = async (): Promise<string[]> => {
      const res = await w1.executeViaBridge(
        `grep -F "${DATA_MOUNT}/repos/" /proc/mounts | cut -d" " -f2 || true`
      );
      return res.stdout
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean);
    };

    // `renet kube install` auto-starts the node CSI units (rediacc-csi / -provisioner
    // / -snapshotter) as HOST daemons whose socket + state live INSIDE the datastore,
    // and NO verb ever stops them (`renet kube csi-node-down` exists with zero
    // callers) → every storage release hits EBUSY with no mount holder to find. Gate
    // finding #26. The suite stops what the product started.
    const csiNodeDown = async (runner: BridgeTestRunner): Promise<void> => {
      await runner.executeViaBridge('sudo renet kube csi-node-down 2>/dev/null; true');
    };

    const teardownAll = async (): Promise<void> => {
      await csiNodeDown(w1);
      // Repos down first (releases the LUKS volume mounts), then the fork, then
      // the cluster + datastores. Every step tolerates already-absent state.
      for (const [n, net] of [
        [FORK_REPO, FORK_NET],
        [REPO, REPO_NET],
      ] as const) {
        await w1.executeViaBridge(
          `sudo renet repository down --name ${n} --datastore ${DATA_MOUNT} --network-id ${net} 2>/dev/null; true`
        );
      }
      await w1.executeViaBridge(`sudo renet datastore detach --name ${DATA_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(`sudo renet datastore delete --name ${DATA_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${CTRL_MOUNT} --network-id ${CTRL_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(`sudo renet datastore detach --name ${CTRL_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(`sudo renet datastore delete --name ${CTRL_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(`sudo ip link del rdk${CTRL_NET} 2>/dev/null; true`);
    };

    test.beforeAll(async () => {
      w1 = BridgeTestRunner.forWorker(1);
      await teardownAll();
    });

    test.afterAll(async () => {
      if (process.env.KEEP_CLUSTER === '1') return;
      await teardownAll().catch(() => undefined);
    });

    test('1. anchor cluster: control datastore + kube install → node Ready on a non-loopback IP', async () => {
      // The control plane lives inside a cluster-labeled control datastore.
      expect(
        w1.isSuccess(
          await w1.datastoreCreate({
            name: CTRL_DS,
            backend: 'local',
            size: '10G',
            cluster: CLUSTER,
          })
        )
      ).toBe(true);
      expect(w1.isSuccess(await w1.datastoreAttach({ name: CTRL_DS }))).toBe(true);

      const install = await w1.kubeInstall({
        mountPath: CTRL_MOUNT,
        networkId: CTRL_NET,
        role: 'server',
      });
      expect(w1.isSuccess(install)).toBe(true);
      expect(await poll(() => nodeReady(), 120_000)).toBe(true);

      // S1 verdict 1: the node's InternalIP is the dedicated non-loopback node IP
      // (10.150.x.1), NOT a 127/8 loopback.
      const ip = await kubectl(
        'get nodes -o jsonpath="{.items[0].status.addresses[?(@.type==\\"InternalIP\\")].address}"'
      );
      expect(ip.stdout.trim()).toMatch(/^10\.150\.\d+\.1$/);
    });

    test('2. kube_health ready + kube_kubeconfig server URL is the reachable node IP', async () => {
      expect(
        w1.isSuccess(await w1.kubeHealth({ mountPath: CTRL_MOUNT, networkId: CTRL_NET }))
      ).toBe(true);
      const kc = await w1.kubeKubeconfig({ mountPath: CTRL_MOUNT, networkId: CTRL_NET });
      expect(w1.isSuccess(kc)).toBe(true);
      // The rewritten server URL must be reachable (not k3s's 127.0.0.1 default).
      expect(kc.stdout + kc.stderr).toMatch(/server:\s*https:\/\/10\.150\.\d+\.1:6443/);
    });

    test('3. cluster-attached data datastore + kube repo folder + node-label for local PVs', async () => {
      // A cluster-attached LOCAL data datastore. Its cluster backref makes repos
      // on it dispatch to KubeRuntime.
      expect(
        w1.isSuccess(
          await w1.datastoreCreate({
            name: DATA_DS,
            backend: 'local',
            size: '4G',
            cluster: CLUSTER,
          })
        )
      ).toBe(true);
      expect(w1.isSuccess(await w1.datastoreAttach({ name: DATA_DS }))).toBe(true);

      // Author the repo-as-folder: repos/shop/{Rediaccfile, manifests/app.yaml}.
      const repoPath = `${DATA_MOUNT}/repos/${REPO}`;
      await w1.executeViaBridge(`sudo mkdir -p ${repoPath}/manifests`);
      await writeFile(`${repoPath}/manifests/app.yaml`, APP_MANIFEST);
      await writeFile(`${repoPath}/Rediaccfile`, REDIACCFILE);

      // Carry-in 1: attach does NOT yet auto-label the hosting node, so a local-PV
      // pod stays Pending until the node carries rediacc.io/ds-<ds>=true. Invoke
      // the primitive (the wave3b BUG #2 fix seam).
      const node = await nodeName();
      expect(
        w1.isSuccess(
          await w1.kubeNodeLabel({
            mountPath: CTRL_MOUNT,
            networkId: CTRL_NET,
            node,
            datastore: DATA_DS,
          })
        )
      ).toBe(true);
      const label = await kubectl(
        `get node ${node} -o jsonpath="{.metadata.labels.rediacc\\.io/ds-${DATA_DS}}"`
      );
      expect(label.stdout.trim()).toBe('true');
    });

    test('4. repository up (kube arm): isolation trio + no-provisioner SC + bound local PV + pod + secret', async () => {
      const up = await repoUpWithSecret(REPO);
      expect(up.code, up.stderr).toBe(0);

      // (1) PSA-restricted, repo-labeled namespace.
      const nsLabels = await kubectl(`get ns ${NS} -o jsonpath="{.metadata.labels}"`);
      expect(nsLabels.stdout).toContain('"pod-security.kubernetes.io/enforce":"restricted"');
      expect(nsLabels.stdout).toContain('"rediacc.io/repo-namespace":"true"');
      expect(nsLabels.stdout).toContain(`"rediacc.io/datastore":"${DATA_DS}"`);
      expect(nsLabels.stdout).toContain('"rediacc.io/injected":"true"');

      // (2) three default-deny NetworkPolicies.
      for (const np of [
        'rediacc-default-deny-ingress',
        'rediacc-allow-intra-namespace',
        'rediacc-allow-proxy',
      ]) {
        const got = await kubectl(`-n ${NS} get networkpolicy ${np} --no-headers`);
        expect(got.code, `NetworkPolicy ${np}`).toBe(0);
      }

      // (3) the repo-namespace ValidatingAdmissionPolicy guard.
      const vap = await kubectl(
        'get validatingadmissionpolicy rediacc-repo-namespace-guard --no-headers'
      );
      expect(vap.code, vap.stderr).toBe(0);

      // (4) no-provisioner StorageClass: Retain + WaitForFirstConsumer. Read each
      // field via jsonpath (compact, exact) — `-o json` pretty-prints with `": "`
      // so a compact `"key":"value"` substring never matches.
      const scProvisioner = await kubectl(`get storageclass ${SC} -o jsonpath="{.provisioner}"`);
      expect(scProvisioner.stdout.trim()).toBe('kubernetes.io/no-provisioner');
      const scReclaim = await kubectl(`get storageclass ${SC} -o jsonpath="{.reclaimPolicy}"`);
      expect(scReclaim.stdout.trim()).toBe('Retain');
      const scVbm = await kubectl(`get storageclass ${SC} -o jsonpath="{.volumeBindingMode}"`);
      expect(scVbm.stdout.trim()).toBe('WaitForFirstConsumer');

      // (5)+(6) the declared volume's local PV bound to the PVC.
      expect(
        await poll(
          async () =>
            (await kubectl(`-n ${NS} get pvc data --no-headers`)).stdout.includes('Bound'),
          120_000
        )
      ).toBe(true);
      const pvcSc = await kubectl(`-n ${NS} get pvc data -o jsonpath="{.spec.storageClassName}"`);
      expect(pvcSc.stdout.trim()).toBe(SC);

      // (7) pod Running with the marker in the local PV.
      expect(await poll(() => podRunning(NS), 120_000)).toBe(true);
      expect(await marker(NS)).toBe('original-data');

      // Router contract: the exposed Service carries rediacc.cluster.
      const ann = await kubectl(
        `-n ${NS} get svc web -o jsonpath="{.metadata.annotations.rediacc\\.cluster}"`
      );
      expect(ann.stdout.trim()).toBe(CLUSTER);

      // (8) ROLE ConfigMap.
      const role = await kubectl(
        `-n ${NS} get configmap rediacc-role -o jsonpath="{.data.REDIACC_ROLE}"`
      );
      expect(role.stdout.trim()).toBe('primary');

      // (9) the declared secret landed as the labeled Opaque Secret + is seen in
      // the pod (env transport end to end).
      const secret = await kubectl(
        `-n ${NS} get secret rediacc-env -o jsonpath="{.data.APP_SECRET}"`
      );
      expect(Buffer.from(secret.stdout.trim(), 'base64').toString()).toBe(APP_SECRET_VALUE);
      const seen = await kubectl(`-n ${NS} exec deploy/web -- printenv APP_SECRET`);
      expect(seen.stdout.trim()).toBe(APP_SECRET_VALUE);
    });

    test('5. F5 hazard: stock k3s local-path is the DEFAULT SC; the rediacc SC is not', async () => {
      // The PVC MUST name the rediacc SC or it is silently adopted by local-path
      // (the default), escaping the forkable per-volume LUKS image. Assert the
      // default-SC layout that makes the hazard real, and that our PVC bound to
      // the rediacc SC rather than local-path.
      const defaultSc = await kubectl(
        `get sc -o jsonpath='{.items[?(@.metadata.annotations.storageclass\\.kubernetes\\.io/is-default-class=="true")].metadata.name}'`
      );
      expect(defaultSc.stdout).toContain('local-path');
      expect(defaultSc.stdout).not.toContain(SC);
    });

    test('6. `repository fork` on a kube repo: folder+volumes cloned, own namespace, ROLE=fork, secrets scrubbed (F1, design 06 §3)', async () => {
      // F1 (P4): the kube arm of `repo fork`, which RETIRES the old CT-11 refusal.
      // The parent's PLACEMENT selects the engine — there is no runtime flag. ONE
      // reflink of the repo folder clones the manifests AND every per-volume LUKS
      // image (repos/<repo>/volumes/<pvc>.img is kept mount-boundary-free precisely
      // so the folder forks as a single unit = one snapshot spanning the repo's
      // volumes). The fork then deploys as its OWN repo: its own name → its own
      // namespace, manifests re-rendered to it, ROLE=fork, and its namespace scrubbed
      // fork-empty (F6 at namespace scope, via KubeRuntime.Fork).
      // SEED a value only the PARENT could have written. This is what makes the clone
      // PROVABLE: the app's entrypoint writes 'original-data' whenever the marker file
      // is empty, so a fork whose volume was freshly provisioned (rather than carrying
      // the parent's cloned LUKS image) would ALSO read 'original-data' — the two are
      // indistinguishable. A unique value the fork's own pod would never write is the
      // only assertion that proves the DATA rode the reflink. (Live-caught: the first
      // version of this test could not tell a clone from a fresh volume, and passed
      // while the parent's writes were in fact never reaching the clone.)
      const seeded = `parent-data-${Date.now()}`;
      const seed = await kubectl(
        `-n ${NS} exec deploy/web -- sh -c "echo ${seeded} > /data/marker.txt"`
      );
      expect(seed.code, `seed parent marker: ${seed.stderr}`).toBe(0);
      expect(await marker(NS)).toBe(seeded);

      const fork = await w1.executeViaBridge(
        `sudo renet repository fork --name ${REPO} --tag ${FORK_REPO} --datastore ${DATA_MOUNT} --network-id ${FORK_NET} --up`
      );
      expect(fork.code, `kube repo fork failed: ${(fork.stderr + fork.stdout).slice(-700)}`).toBe(
        0
      );

      // The fork is its OWN repo → its own namespace.
      const forkNs = await kubectl(`get ns ${FORK_REPO} -o jsonpath="{.metadata.name}"`);
      expect(forkNs.stdout.trim()).toBe(FORK_REPO);

      // The DATA rode the reflink: the fork's volume carries the PARENT'S SEEDED value,
      // which the fork's own entrypoint would never write. Wait for the pod to be
      // exec-able first (Running is set before the entrypoint's first read completes).
      expect(await poll(() => podRunning(FORK_REPO))).toBe(true);
      expect(await poll(async () => (await marker(FORK_REPO)).length > 0)).toBe(true);
      expect(await marker(FORK_REPO)).toBe(seeded);

      // ROLE=fork — a fork must never boot claiming primary (02 §1.2 effect isolation).
      const role = await kubectl(
        `-n ${FORK_REPO} get configmap rediacc-role -o jsonpath="{.data.REDIACC_ROLE}"`
      );
      expect(role.stdout.trim()).toBe('fork');

      // F6 at NAMESPACE scope — asserted so it can actually FAIL for the right reason.
      // A bare "the fork's secret is empty" check is unfalsifiable: it also passes when
      // the kubectl call simply fails (missing namespace, broken exec), and it never
      // shows the fork's WORKLOAD is free of the parent's material. So prove absence
      // END TO END, on a channel already proven live: the marker read above establishes
      // that exec into the fork's pod WORKS, so an empty APP_SECRET here is a real
      // absence rather than a failed command. The parent's pod DOES see this value
      // (test 4), which is what makes the fork's not seeing it meaningful.
      const forkEnvVar = await kubectl(`-n ${FORK_REPO} exec deploy/web -- printenv APP_SECRET`);
      expect(forkEnvVar.stdout.trim()).not.toBe(APP_SECRET_VALUE);
      expect(forkEnvVar.stdout.trim()).toBe('');
      // ...and the Secret object itself carries none of the parent's material.
      const forkSecret = await kubectl(
        `-n ${FORK_REPO} get secret rediacc-env -o jsonpath="{.data.APP_SECRET}"`
      );
      expect(forkSecret.stdout.trim()).toBe('');

      // The PARENT is untouched: its seeded data, its secret, AND its role survive.
      // The parent staying `primary` is what makes the fork's `fork` above a real
      // distinction rather than a value that happens to be written everywhere.
      expect(await marker(NS)).toBe(seeded);
      const parentSecret = await kubectl(
        `-n ${NS} get secret rediacc-env -o jsonpath="{.data.APP_SECRET}"`
      );
      expect(Buffer.from(parentSecret.stdout.trim(), 'base64').toString()).toBe(APP_SECRET_VALUE);
      const parentRole = await kubectl(
        `-n ${NS} get configmap rediacc-role -o jsonpath="{.data.REDIACC_ROLE}"`
      );
      expect(parentRole.stdout.trim()).toBe('primary');
    });

    test('7. teardown: repository down (no leak) + cluster + datastores + dummy interface removed', async () => {
      // BOTH repos come down: the FORK first, then the parent. Since F1 landed, test 6
      // creates a real fork — its own namespace with a RUNNING pod holding its own
      // cloned per-volume LUKS mounts. Those are live holders of the data datastore,
      // and a DATA-datastore release must never kill node processes, so the product
      // (correctly) refuses the detach while they exist: the workload has to be
      // stopped before its storage is released. `repository down` on the fork deletes
      // its namespace and releases its volumes; then the parent's does the same.
      // `repository down` releases the per-volume LUKS mounts (CT-07 converge, no leak).
      const downFork = await w1.executeViaBridge(
        `sudo renet repository down --name ${FORK_REPO} --datastore ${DATA_MOUNT} --network-id ${FORK_NET}`
      );
      expect(downFork.code, `down ${FORK_REPO}: ${downFork.stderr}`).toBe(0);
      const down = await w1.executeViaBridge(
        `sudo renet repository down --name ${REPO} --datastore ${DATA_MOUNT} --network-id ${REPO_NET}`
      );
      expect(down.code, `down ${REPO}: ${down.stderr}`).toBe(0);
      // CT-07 no-leak, asserted DIRECTLY: `repository down` released every per-volume
      // LUKS mount the product owns under the repo folder.
      expect(await repoVolumeMounts(), 'LUKS volume mounts leaked by repository down').toEqual([]);

      // What still holds the datastores is node-side residue no lifecycle verb clears:
      // the CSI daemons the product itself started (#26 — the holder that actually
      // blocks the release) and k3s's leftover containerd/kubelet kernel mounts (#20).
      await csiNodeDown(w1);
      await unwindSubmounts(w1, DATA_MOUNT);
      expect(w1.isSuccess(await w1.datastoreDetach(DATA_DS))).toBe(true);
      expect(
        w1.isSuccess(await w1.kubeUninstall({ mountPath: CTRL_MOUNT, networkId: CTRL_NET }))
      ).toBe(true);
      await unwindSubmounts(w1, CTRL_MOUNT);
      expect(w1.isSuccess(await w1.datastoreDetach(CTRL_DS))).toBe(true);
      // The per-cluster dummy interface is removed on uninstall.
      const iface = await w1.executeViaBridge(
        `ip link show rdk${CTRL_NET} 2>/dev/null && echo PRESENT || echo GONE`
      );
      expect(iface.stdout).toContain('GONE');
    });
  });
