import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { TEST_TEAM, TEST_USER } from '../src/constants';
import {
  accountPrereqs,
  bothChannels,
  type CliEnvelope,
  DS,
  engineVerbPresent,
  ensureDatastore,
  localHelp,
  loginCli,
  M1,
  type ProvisionedRepo,
  parseEnvelope,
  parseSnapshotRecord,
  provisionRepo,
  registerMachines,
  restoreLedger,
  workers,
} from '../src/utils/backup/chunkCliHarness';
import {
  type BackupManifest,
  type BackupUsage,
  chunkVerbs,
  type SnapshotRecord,
  verbIsRegistered,
} from '../src/utils/backupStorage';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';
import { CliRunner } from '../src/utils/CliRunner';
import {
  announcePrerequisites,
  type PrerequisiteVerdict,
  resolvePrerequisites,
} from '../src/utils/declaredSkip';
import { VaultBuilder } from '../src/utils/vault/VaultBuilder';

/**
 * Suite 27 -- `rdc backup browse --at <snapshot>` against a real chunk store.
 *
 * Split out of suite 26 so a workflow can run it alone: it needs one worker VM, an account server whose gateway carries the backup plane (S3 presign) and an api token with `backup:read`. Suite 26's other tiers need two workers and stay hand-run. Its own config, `playwright.backup-browse-at.config.ts`, has no globalSetup for the reasons that config's header gives.
 *
 * Run it with:
 *   BACKUP_BROWSE_AT_SUITE=1 REDIACC_ACCOUNT_SERVER=http://<host>:<port> \
 *     E2E_ACCOUNT_API_TOKEN=<token with backup:read> VM_WORKERS="11" \
 *     E2E_BACKUP_S3_KEY=<store key> E2E_BACKUP_S3_SECRET=<store secret> \
 *     npx playwright test --config playwright.backup-browse-at.config.ts
 */

const stamp = Date.now();
/** Own config namespace: suite 26 and suites 23/24 must not see these mutations. */
const CFG = 'e2e-backup-browse-at';

/**
 * The BROWSE-AT tier (Stage 3 of the chunk-store browse plan): `rdc backup browse
 * --at <snapshot>` lists a snapshot from its sealed listing in the chunk store.
 *
 * Its own tier because it needs one thing the others do not: the local renet
 * must register `backup browse-at`, which is newer than the run and restore
 * verbs. Folding it into a tier that is otherwise green would let an older
 * binary hide this proof behind the rest.
 *
 * Leg 3b drives the `backup_browse_at` FUNCTION through a vault, the way suite 25 drives `backup_verify`; suite 25 carries the refusals that need no account server.
 */
const browseAtVerbPresent = verbIsRegistered(localHelp, 'browse-at');
const browseAtVerdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'snapshot browse from the chunk store (BROWSE-AT tier)',
  declareVar: 'E2E_EXPECT_NO_CHUNK_BROWSE_AT',
  prerequisites: [
    ...accountPrereqs,
    {
      name: 'VM_WORKERS (one worker VM)',
      satisfied: workers.length >= 1,
      how: 'bring the fleet up: `./rdc.sh ops up --basic`',
    },
    {
      name: `the local renet registers \`${chunkVerbs().run}\``,
      satisfied: engineVerbPresent,
      how: 'build renet (`cd private/renet && ./build.sh dev`). Check: `private/renet/bin/renet backup --help`',
    },
    {
      name: 'the local renet registers `browse-at`',
      satisfied: browseAtVerbPresent,
      how: 'rebuild renet from a tree that has cmd/renet/backup_browse_at.go. Check: `private/renet/bin/renet backup --help`',
    },
  ],
});

/**
 * `curl` against the dev plane's S3 (RustFS on the host) for one object key, SigV4-signed. The credentials ride a curl config on stdin, never argv.
 */
const storeCurl = (objectKey: string): ((extra: string[]) => Buffer) => {
  const env = process.env;
  const url = `${env.E2E_BACKUP_S3_ENDPOINT || 'http://127.0.0.1:9100'}/${env.E2E_BACKUP_S3_BUCKET || 'rediacc-backups-probe'}/${objectKey}`;
  const accessKey = env.E2E_BACKUP_S3_KEY;
  const secretKey = env.E2E_BACKUP_S3_SECRET;
  if (!accessKey || !secretKey) {
    throw new Error(
      'E2E_BACKUP_S3_KEY and E2E_BACKUP_S3_SECRET must be set to the dev plane store credentials; no default is sent to the endpoint'
    );
  }
  const creds = `user = "${accessKey}:${secretKey}"\n`;
  return (extra) =>
    execFileSync(
      'curl',
      ['-sS', '--fail', '--aws-sigv4', 'aws:amz:us-east-1:s3', '-K', '-', ...extra, url],
      { input: creds, maxBuffer: 64 * 1024 * 1024 }
    );
};

/**
 * Put the saved listing bytes back after the tamper test. A failure is returned, not thrown, so the
 * caller removes its temp copies first; the stored listing is then still the tampered one, and later
 * tests read it, so the caller surfaces it.
 */
function restoreListing(
  original: string,
  curl: (args: string[]) => unknown,
  objectKey: string
): Error | undefined {
  if (!existsSync(original)) return undefined;
  try {
    curl(['-X', 'PUT', '-T', original]);
    return undefined;
  } catch (err) {
    return new Error(`could not restore the tampered listing object ${objectKey}: ${String(err)}`);
  }
}

// --------------------------------------------------------------------------- BROWSE-AT tier — a stored snapshot lists without being restored ---------------------------------------------------------------------------

test.describe
  .serial('snapshot browse from the chunk store @cli @backup @browse-at', () => {
    if (browseAtVerdict.kind === 'undeclared') {
      test('BROWSE-AT tier prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(browseAtVerdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(browseAtVerdict);
      if (gate.skip) {
        process.stderr.write(
          [
            '',
            '  Declared skip: the prerequisites are missing. To run by hand:',
            '',
            '    ./run.sh account dev     # note the gateway URL it prints',
            '    BACKUP_BROWSE_AT_SUITE=1 REDIACC_ACCOUNT_SERVER=http://<host>:<port> \\',
            '      E2E_ACCOUNT_API_TOKEN=<token with backup:read> VM_WORKERS="11" \\',
            '      npx playwright test --config playwright.backup-browse-at.config.ts',
            '',
          ].join('\n')
        );
      }
      test.skip(gate.skip, gate.reason);
      test.setTimeout(1_800_000);

      const verbs = chunkVerbs();
      const REPO_NAME = `e2ebk-browse-${String(stamp).slice(-8)}`;

      let cli: CliRunner;
      let w1: BridgeTestRunner;
      let repo: ProvisionedRepo;
      let subscriptionId = '';
      /** Taken while the repository's TOC key was absent: carries no listing. */
      let bareSnapshotId = '';
      /** Taken after a password mount wrote the key: carries a sealed listing. */
      let listedSnapshotId = '';

      const tocKeyPath = (): string => `${DS}/.credentials/toc/${repo.guid}.pub`;

      const snapshot = async (): Promise<string> => {
        const run = await w1.executeViaBridge(
          `sudo renet ${verbs.run} --repo "${repo.guid}" --datastore "${DS}"`
        );
        expect(run.code, `snapshot run: ${w1.getCombinedOutput(run).slice(-800)}`).toBe(0);
        const record = run.stdout
          .split('\n')
          .map((line) => parseSnapshotRecord(line))
          .find((r): r is SnapshotRecord => r !== undefined);
        expect(
          record?.snapshotId,
          `no snapshot record on stdout:\n${run.stdout.slice(-800)}`
        ).toBeTruthy();
        return record?.snapshotId ?? '';
      };

      /** Rows of an `-o json` browse, reduced to what a local and a remote listing must agree on. */
      const comparable = (rows: unknown): string[] =>
        (Array.isArray(rows) ? (rows as { name: string; type: string }[]) : [])
          .map((row) => `${row.type} ${row.name}`)
          .sort();

      const disableAutostart = async (): Promise<void> => {
        await w1.executeViaBridge(
          `sudo renet repository autostart disable --name "${repo.guid}" --datastore "${DS}"`
        );
      };

      /** The machine-side `browse-at` verb's own JSON record, whose `listingSource` the CLI's row output does not carry. */
      const storedListingSource = async (snapshotId: string): Promise<string | undefined> => {
        const out = await w1.executeViaBridge(
          `printf '%s\\n' '${repo.credential}' | sudo renet backup browse-at --datastore "${DS}" ` +
            `--repo "${repo.guid}" --lineage "${repo.guid}" --at '${snapshotId}' --password-stdin`
        );
        expect(out.code, `browse-at verb: ${w1.getCombinedOutput(out).slice(-800)}`).toBe(0);
        const parsed = JSON.parse(out.stdout.trim().split('\n').pop() ?? '{}') as {
          listingSource?: string;
        };
        return parsed.listingSource;
      };

      /** Lowercase, drop ANSI colour codes and collapse whitespace: the CLI colours each wrapped line of the note and wraps it at the terminal width. */
      const ANSI_COLOUR = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, 'g');
      const squash = (text: string): string =>
        text.toLowerCase().replace(ANSI_COLOUR, '').replace(/\s+/g, ' ');

      /** The human note's stable middle, lowercased because getCombinedOutput-style matching is case-blind here. */
      const LIVE_NOTE = 'listing was read from the live mount close to when it was taken';

      test.beforeAll(async () => {
        w1 = BridgeTestRunner.forWorker(1);
        cli = await loginCli(CFG);
        await w1.ensureDatastoreReady(DS);
        await ensureDatastore(w1, M1);
        await registerMachines(cli);
        repo = await provisionRepo(cli, w1, REPO_NAME, M1);
        const usage = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
        subscriptionId = usage.json?.data?.subscriptionId ?? '';
      });

      test.afterAll(async () => {
        await restoreLedger(cli, subscriptionId);
        // Test 2c enables autostart on its own; this is the net for a failure between its enable and its own disable.
        await disableAutostart().catch(() => undefined);
        await cli.run(['repo', 'delete', REPO_NAME, '-y']).catch(() => undefined);
      });

      test('1. a snapshot taken before the key exists answers exit 18 NO_LISTING', async () => {
        // `repo create` already password-mounted the repo, which wrote the TOC key. Removing it recreates the state of a repository whose key was never written (an older machine, a repo restored without a password mount), the one in which the snapshot stores without a listing.
        const removed = await w1.executeViaBridge(`sudo rm -f "${tocKeyPath()}"`);
        expect(removed.code, `removing the TOC key: ${w1.getCombinedOutput(removed)}`).toBe(0);
        bareSnapshotId = await snapshot();

        const browse = await cli.run([
          'backup',
          'browse',
          `${REPO_NAME}@${M1}`,
          '--at',
          bareSnapshotId,
        ]);
        // The CLI propagates the verb's 18 verbatim and says WHY, so a script can tell "no listing there" from "it broke" (exit 1).
        expect(browse.code, `browse --at (no listing): ${bothChannels(browse).slice(-800)}`).toBe(
          18
        );
        expect(bothChannels(browse), 'the refusal must name the snapshot').toContain(
          bareSnapshotId
        );
        // Non-TTY output is the JSON envelope even for a failure (`success:false, data:null`), so stdout is not empty; what must be empty is the DATA.
        const refused = parseEnvelope(browse.stdout);
        expect(refused.success, 'a snapshot with no listing reported success').toBe(false);
        expect(refused.data ?? null, 'a snapshot with no listing printed rows').toBeNull();
      });

      test('2. `rdc backup browse --at <id>` equals a local `backup browse` of the same content', async () => {
        // The snapshot builds its listing by reading the image, which it can only do through a LIVE mount of the repository with no autostart keyfile (this repo has none): the staged copy cannot be opened, so the listing is walked from the live mount and sealed as `listingSource: "live-mount"` (cmd/renet/backup_snapshot_toc.go snapshotTOCListing). An UNMOUNTED repo still stores WITHOUT a listing. So the repo stays mounted from the write, through the snapshot, to the local read: the password mount also writes the key, so this snapshot carries a sealed listing, and nothing changes between it and the local read.
        const mounted = await w1.repositoryMount(repo.guid, repo.credential, DS, repo.networkId);
        expect(mounted.code, `mounting: ${w1.getCombinedOutput(mounted).slice(-800)}`).toBe(0);
        let local: string[];
        try {
          const fileName = `browse-at-${stamp}.txt`;
          const write = await w1.executeViaBridge(
            `sudo sh -c 'echo ${fileName} > "${DS}/mounts/${repo.guid}/${fileName}"' && sync`
          );
          expect(write.code, `planting ${fileName}: ${w1.getCombinedOutput(write)}`).toBe(0);
          expect(
            (
              await w1.executeViaBridge(
                `sudo test -f "${tocKeyPath()}" && echo present || echo absent`
              )
            ).stdout,
            'the password mount did not write the TOC key'
          ).toContain('present');
          listedSnapshotId = await snapshot();
          expect(listedSnapshotId, 'the second snapshot reused the first id').not.toBe(
            bareSnapshotId
          );

          const l = await cli.runJson<CliEnvelope<unknown>>([
            'backup',
            'browse',
            `${REPO_NAME}@${M1}`,
          ]);
          expect(l.result.code, `local browse: ${bothChannels(l.result).slice(-800)}`).toBe(0);
          local = comparable(l.json?.data);
        } finally {
          await w1.repositoryUnmount(repo.guid, DS).catch(() => undefined);
        }

        const r = await cli.runJson<CliEnvelope<unknown>>([
          'backup',
          'browse',
          `${REPO_NAME}@${M1}`,
          '--at',
          listedSnapshotId,
        ]);
        expect(r.result.code, `browse --at: ${bothChannels(r.result).slice(-800)}`).toBe(0);
        const remote = comparable(r.json?.data);

        expect(local, 'the local listing is empty; the comparison would pass vacuously').toContain(
          `file /browse-at-${stamp}.txt`
        );
        expect(remote, 'the stored listing differs from the image it was taken from').toEqual(
          local
        );

        // The stored listing is marked as walked from the live mount, not the staged image.
        expect(
          await storedListingSource(listedSnapshotId),
          'a non-autostart snapshot must report its listing as read from the live mount'
        ).toBe('live-mount');

        // The human surface prints the note exactly once. `-o table` is required: a non-TTY spawn defaults to json.
        const human = await cli.run([
          '-o',
          'table',
          'backup',
          'browse',
          `${REPO_NAME}@${M1}`,
          '--at',
          listedSnapshotId,
        ]);
        expect(human.code, `browse --at (table): ${bothChannels(human).slice(-800)}`).toBe(0);
        expect(
          squash(bothChannels(human)).split(LIVE_NOTE).length - 1,
          `the live-mount note must print exactly once:\n${bothChannels(human).slice(-800)}`
        ).toBe(1);
      });

      test('2b. `GET /backups/manifests` reports hasIndex false for the snapshot with no listing and true for the listed one', async () => {
        // The listing leg of the browse index: the commit stores `hasIndex` and the list route surfaces it, so a client can tell "no listing there" before it asks for one. The pair is the control: a route that always said false (or true) fails one of the two.
        const { result, json } = await cli.runJson<CliEnvelope<{ manifests: BackupManifest[] }>>([
          'backup',
          'manifests',
          `${REPO_NAME}@${M1}`,
        ]);
        expect(result.code, `backup manifests: ${bothChannels(result).slice(-800)}`).toBe(0);
        const rows = json?.data?.manifests ?? [];
        const bare = rows.find((m) => m.snapshotId === bareSnapshotId);
        const listed = rows.find((m) => m.snapshotId === listedSnapshotId);
        expect(bare, `snapshot ${bareSnapshotId} is not in the manifests listing`).toBeDefined();
        expect(
          listed,
          `snapshot ${listedSnapshotId} is not in the manifests listing`
        ).toBeDefined();
        expect(bare?.hasIndex, 'a snapshot stored with no listing claims one').toBe(false);
        expect(listed?.hasIndex, 'a snapshot stored with a listing does not claim it').toBe(true);
      });

      test('2c. control: a snapshot of a repository WITH an autostart keyfile reports listingSource staged and prints no live-mount note', async () => {
        const mounted = await w1.repositoryMount(repo.guid, repo.credential, DS, repo.networkId);
        expect(mounted.code, `mounting: ${w1.getCombinedOutput(mounted).slice(-800)}`).toBe(0);
        let stagedSnapshotId = '';
        try {
          const autostart = await w1.executeViaBridge(
            `printf '%s\\n' '${repo.credential}' | sudo renet repository autostart enable --name "${repo.guid}" ` +
              `--datastore "${DS}" --network-id ${repo.networkId} --password-stdin`
          );
          expect(
            autostart.code,
            `autostart enable: ${w1.getCombinedOutput(autostart).slice(-800)}`
          ).toBe(0);
          stagedSnapshotId = await snapshot();
        } finally {
          await disableAutostart().catch(() => undefined);
          await w1.repositoryUnmount(repo.guid, DS).catch(() => undefined);
        }
        expect(await storedListingSource(stagedSnapshotId)).toBe('staged');
        const human = await cli.run([
          '-o',
          'table',
          'backup',
          'browse',
          `${REPO_NAME}@${M1}`,
          '--at',
          stagedSnapshotId,
        ]);
        expect(human.code, `browse --at (staged): ${bothChannels(human).slice(-800)}`).toBe(0);
        expect(
          bothChannels(human).toLowerCase(),
          'a staged listing printed the live-mount note'
        ).not.toContain(LIVE_NOTE);
      });

      test('3. a wrong passphrase fails closed: no listing, no hint of the content', async () => {
        // The CLI always sends the config's credential, so the wrong one is driven through the verb on the machine. Same arguments as the CLI's call; only the passphrase differs.
        const lineage = repo.guid;
        const wrong = await w1.executeViaBridge(
          `printf '%s\\n' 'not-the-passphrase' | sudo renet backup browse-at --datastore "${DS}" ` +
            `--repo "${repo.guid}" --lineage "${lineage}" --at '${listedSnapshotId}' --password-stdin`
        );
        expect(wrong.code, 'a wrong passphrase opened the listing').not.toBe(0);
        expect(wrong.code, 'a wrong passphrase must not read as NO_LISTING').not.toBe(18);
        expect(wrong.stdout.trim(), 'a failed open printed something on stdout').toBe('');
        const text = w1.getCombinedOutput(wrong);
        expect(text, 'the refusal leaked a file name').not.toContain(`browse-at-${stamp}`);

        // Control: the right passphrase opens the same snapshot, so test 3 refused on the passphrase and not on a broken fixture.
        const right = await w1.executeViaBridge(
          `printf '%s\\n' '${repo.credential}' | sudo renet backup browse-at --datastore "${DS}" ` +
            `--repo "${repo.guid}" --lineage "${lineage}" --at '${listedSnapshotId}' --password-stdin`
        );
        expect(right.code, `right passphrase: ${w1.getCombinedOutput(right).slice(-800)}`).toBe(0);
        expect(right.stdout).toContain(`browse-at-${stamp}.txt`);
      });

      test('3b. the backup_browse_at FUNCTION, driven through a vault, lists the stored snapshot', async () => {
        // The way rdc and the bridge reach the verb: the FunctionDef, with the lineage, the snapshot and the passphrase supplied by the vault (suite 25 does the same for backup_verify).
        const vault = new VaultBuilder()
          .withFunction('backup_browse_at')
          .withTeam(TEST_TEAM)
          .withRepository(repo.guid, repo.guid)
          .withRepositoryCredential(repo.guid, repo.credential)
          .withMachine(w1.getTargetVM(), TEST_USER, DS)
          .withDatastore(DS)
          .withParams({ lineage: repo.guid, at: listedSnapshotId });
        const result = await w1.executeWithVault('backup_browse_at', vault);
        expect(
          result.code,
          `backup_browse_at exited ${result.code}:\n${(result.stdout + result.stderr).slice(-800)}`
        ).toBe(0);
        // The record may arrive wrapped on stderr (functions once re-emits the verb's stdout), so both channels are read.
        expect(
          result.stdout + result.stderr,
          'the function listing does not name the planted file'
        ).toContain(`browse-at-${stamp}.txt`);
      });

      test('4. a tampered stored listing fails closed: no rows, no content, and the original still opens', async () => {
        // The sealed listing lives in the bucket at t/<subscription>/l/<lineage>/i/<snapshot>. Flip one byte in the middle of it, as a hostile or corrupted store would, and ask for it back. The dev plane's S3 is RustFS on the host (the same one the account server presigns for), so the object is reached with SigV4 over curl; the credentials ride a curl config on stdin, never argv.
        const curl = storeCurl(`t/${subscriptionId}/l/${repo.guid}/i/${listedSnapshotId}`);
        const dir = mkdtempSync(path.join(os.tmpdir(), 'browse-at-tamper-'));
        const original = path.join(dir, 'original');
        const tampered = path.join(dir, 'tampered');
        let restored = false;
        try {
          const body = curl([]);
          expect(
            body.length,
            'the stored listing is implausibly small; wrong object key?'
          ).toBeGreaterThan(32);
          writeFileSync(original, body);
          const flipped = Buffer.from(body);
          flipped[Math.floor(flipped.length / 2)] ^= 0xff;
          writeFileSync(tampered, flipped);

          curl(['-X', 'PUT', '-T', tampered]);
          const bad = await cli.runJson<CliEnvelope<unknown>>([
            'backup',
            'browse',
            `${REPO_NAME}@${M1}`,
            '--at',
            listedSnapshotId,
          ]);
          expect(bad.result.code, 'a tampered listing was opened').not.toBe(0);
          expect(bad.result.code, 'tampering must not read as NO_LISTING').not.toBe(18);
          expect(bad.json?.success, 'a tampered listing reported success').toBe(false);
          expect(bad.json?.data ?? null, 'a tampered listing printed rows').toBeNull();
          expect(bothChannels(bad.result), 'the refusal leaked a file name').not.toContain(
            `browse-at-${stamp}`
          );

          // Control: the original bytes open again, so the refusal above was the tamper and not a dead store.
          curl(['-X', 'PUT', '-T', original]);
          restored = true;
          const good = await cli.runJson<CliEnvelope<unknown>>([
            'backup',
            'browse',
            `${REPO_NAME}@${M1}`,
            '--at',
            listedSnapshotId,
          ]);
          expect(
            good.result.code,
            `restored listing: ${bothChannels(good.result).slice(-800)}`
          ).toBe(0);
          expect(comparable(good.json?.data)).toContain(`file /browse-at-${stamp}.txt`);
        } finally {
          const restoreError = restored
            ? undefined
            : restoreListing(
                original,
                curl,
                `t/${subscriptionId}/l/${repo.guid}/i/${listedSnapshotId}`
              );
          // The temp copies go on every path, the failed restore included.
          rmSync(dir, { recursive: true, force: true });
          if (restoreError) throw restoreError;
        }
      });

      test('5. regression: `backup browse` WITHOUT --at makes zero storage or licence calls to the account server', async () => {
        // A counting server stands in for the account server. The local verb must never touch it; the same server, asked for a remote listing, must be hit, which proves the counter and the redirect are live (a counter nothing can reach would pass for free).
        let hits = 0;
        const seen: string[] = [];
        const sink = http.createServer((req, res) => {
          hits += 1;
          seen.push(`${req.method} ${req.url}`);
          res.statusCode = 503;
          res.end('{}');
        });
        await new Promise<void>((resolve) => sink.listen(0, '127.0.0.1', resolve));
        const address = sink.address();
        const sinkUrl = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : 0}`;
        const sinkCli = CliRunner.create({
          configName: CFG,
          licensing: true,
          env: { REDIACC_ACCOUNT_SERVER: sinkUrl },
        });
        // The stored token's serverUrl outranks REDIACC_ACCOUNT_SERVER for every account fetch (account-client.ts resolveServerUrl), so the env alone never redirects a logged-in config. The redirect is the stored token file, restored in finally.
        const tokenFile = path.join(path.dirname(cli.configPath), `api-token-${CFG}.json`);
        const tokenOriginal = readFileSync(tokenFile, 'utf8');
        writeFileSync(
          tokenFile,
          JSON.stringify({ ...JSON.parse(tokenOriginal), serverUrl: sinkUrl }),
          { mode: 0o600 }
        );
        try {
          const mounted = await w1.repositoryMount(repo.guid, repo.credential, DS, repo.networkId);
          expect(mounted.code, `mounting: ${w1.getCombinedOutput(mounted).slice(-800)}`).toBe(0);
          const local = await sinkCli.runJson<CliEnvelope<unknown>>([
            'backup',
            'browse',
            `${REPO_NAME}@${M1}`,
          ]);
          expect(local.result.code, `local browse: ${bothChannels(local.result).slice(-800)}`).toBe(
            0
          );
          expect(comparable(local.json?.data), 'the local listing is empty').toContain(
            `file /browse-at-${stamp}.txt`
          );
          // Every rdc command asks the server for its public key (`.well-known/server-info`, the E2E-key discovery of b5147eec); that is startup, not the browse. What the browse itself must not do is reach any storage or licence route.
          const beyondStartup = (): string[] =>
            seen.filter((r) => !r.includes('/.well-known/server-info'));
          expect(beyondStartup(), 'the local browse called a server route beyond startup').toEqual(
            []
          );

          const startupHits = hits;
          const remote = await sinkCli.run([
            'backup',
            'browse',
            `${REPO_NAME}@${M1}`,
            '--at',
            // A snapshot id goes straight to the machine; only a TIME is resolved through the account server's manifest index, which is the call the sink must see.
            '2999-01-01T00:00:00Z',
          ]);
          expect(
            hits,
            `control: --at made no call beyond the local browse's ${startupHits} (seen: ${seen.join(', ')}; --at rc=${remote.code}: ${bothChannels(remote).slice(-500)})`
          ).toBeGreaterThan(startupHits);
        } finally {
          writeFileSync(tokenFile, tokenOriginal, { mode: 0o600 });
          await w1.repositoryUnmount(repo.guid, DS).catch(() => undefined);
          await new Promise<void>((resolve) => sink.close(() => resolve()));
        }
      });
    }
  });
