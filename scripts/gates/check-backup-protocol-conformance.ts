/**
 * check:ci-backup-protocol-conformance — renet's backup client and the
 * account's backup routes must speak ONE protocol.
 *
 * The class this catches, paid for in full on 2026-08-14: renet's chunkstore
 * client and the account's /backups routes disagreed on EVERY leg. renet
 * required a `baseUrl` the account never sends, so MintSession failed 100% of
 * the time; it authenticated with an Authorization bearer while the route reads
 * X-Backup-Session; it posted `lineage` where zod demands `lineageGuid`; it
 * POSTed to /chunks/exists and /manifests, which do not exist; and it decoded a
 * `missing` array from a response that carries `existing`.
 *
 * That last one is why this gate exists rather than a code review. renet
 * unmarshalled into a struct holding only Missing, so the account's answer left
 * it nil, nil meant "nothing is missing", and a backup run would have uploaded
 * ZERO chunks, committed a manifest, and reported SUCCESS. A backup product
 * whose happy path is a silent no-op is only discovered at restore time.
 *
 * Why no existing gate could see it: each side had unit tests, and each side's
 * tests ran against ITS OWN fake. Both were green for two certified waves. A
 * fake that agrees with its client proves only that the client agrees with
 * itself; nothing in the tree compared the two dialects.
 *
 * The rule enforced: this file declares the protocol ONCE, and BOTH sides are
 * checked against that declaration. A three-way pin beats diffing two files,
 * because it fires when either side drifts and it states the contract in a place
 * a human can read. Retired spellings are checked too, so a revert to the old
 * dialect fails loudly instead of silently.
 *
 * Run: npx tsx scripts/gates/check-backup-protocol-conformance.ts
 *
 * Control-first: every run first proves the detector on a synthetic leg that
 * neither side implements, and refuses to pass on an empty scan.
 *
 * ---- gate ----
 * step: Backup protocol conformance
 * needs: node, submodules
 * ---- end gate ----
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const ROUTES_TS = 'private/account/src/routes/backups.ts';
const DTO_TS = 'private/account/src/dto/backup.dto.ts';
const CLIENT_GO = 'private/renet/pkg/chunkstore/session.go';
const REPAIR_GO = 'private/renet/pkg/chunkstore/repair.go';

interface Leg {
  /** Route path as mounted in the account's backups router. */
  path: string;
  /** Zod request schema name in backup.dto.ts; null for a route that takes no body. */
  requestSchema: string | null;
  /**
   * Zod response schema name in backup.dto.ts. Until 2026-08-14 this did not
   * exist and `responseKeys` was checked against the Go client ONLY, while the
   * comment on it claimed "the account must declare" — half of a three-way pin,
   * silently. The airlock STRIPS anything the response DTO does not declare, so
   * an undeclared response key reaches the machine as absent, which is the same
   * silent-zero-value failure the /exists leg was written to catch.
   */
  responseSchema: string | null;
  /** Request keys renet must send and the account must accept. */
  requestKeys: string[];
  /** Response keys renet must read and the account must declare. */
  responseKeys: string[];
  /**
   * How the client spells a parameterised path, which it composes and so can never
   * hold as one literal. Matched against the client with comments dropped, so prose
   * that mentions the route cannot stand in for the call. Absent means the client
   * must hold `path` itself.
   */
  clientCall?: RegExp;
  /**
   * A second proof for a leg only one caller makes: the pattern must appear, comments
   * dropped, in `file`, so a helper or a log string that merely holds the path cannot
   * stand in for the code that sends the request.
   */
  callerCall?: { file: string; pattern: RegExp };
}

/** The protocol, declared once. Both sides are checked against THIS. */
const LEGS: Leg[] = [
  {
    path: '/session',
    requestSchema: 'backupSessionRequest',
    responseSchema: 'backupSessionResponse',
    // `intent` splits the session in two ('backup' | 'restore'). A restore session is the only credential a lapsed-but-retained subscription can get, so a client that cannot spell the field cannot restore at all.
    requestKeys: ['license', 'machineId', 'intent'],
    responseKeys: ['token', 'subscriptionId', 'dataPlaneUrl', 'grantKind'],
  },
  {
    path: '/streams',
    requestSchema: 'backupStreamRequest',
    responseSchema: 'backupStreamResponse',
    requestKeys: ['repositoryGuid', 'lineageGuid'],
    responseKeys: ['streamId', 'previous'],
  },
  {
    path: '/exists',
    requestSchema: 'backupExistsRequest',
    responseSchema: 'backupExistsResponse',
    requestKeys: ['lineageGuid', 'hashes'],
    // NOT `missing`. The server reports what it HOLDS; the client computes the
    // complement, so an absent field can never read as "nothing to upload".
    responseKeys: ['existing'],
  },
  {
    path: '/grants',
    requestSchema: 'backupGrantRequest',
    responseSchema: 'backupGrantResponse',
    // `chunkBytes` (plan S5): the size of every requested hash, so the account signs each presigned PUT with its Content-Length and x-amz-checksum-sha256. A spelling the schema does not accept is stripped silently and every URL goes back to unbounded.
    // `manifestBytes` and `indexBytes` (hardening R1): the exact byte lengths of the manifest and the sealed browse index, required whenever the grant names that key, so the account signs those presigned PUTs with a Content-Length as it does for chunks. A spelling the schema does not accept is stripped silently and the grant refuses or goes unbounded for those two objects.
    requestKeys: [
      'snapshotId',
      'lineageGuid',
      'declaredBytes',
      'hashes',
      'chunkBytes',
      'manifestBytes',
      'indexBytes',
    ],
    // The write grant's own fields (manifestKey, and indexKey/indexPutUrl for the listing object) live in a nested schema this leg's response check does not reach; the listing is pinned where it is read back (/read-grants) and committed (/commit).
    responseKeys: ['grant', 'leaseId'],
  },
  {
    /**
     * The RESTORE leg. Its response is FLAT (no `grant` envelope): a read grant
     * has no lease to report. Every branch carries `manifestChain`, the ordered
     * snapshot ids with the nearest FULL manifest FIRST and the requested
     * snapshot LAST.
     *
     * The two map keyings below are the whole reason this leg is pinned. The
     * server names EVERY object key, and `getUrls` is keyed by BARE HASH while
     * `manifestGetUrls` is keyed by SNAPSHOT ID. The write path already shipped
     * the other choice once: keying by full object key made every client lookup
     * miss while the grant itself looked perfectly well formed.
     */
    path: '/read-grants',
    requestSchema: 'backupReadGrantRequest',
    responseSchema: 'backupReadGrantResponse',
    requestKeys: ['lineageGuid', 'snapshotId', 'hashes'],
    responseKeys: [
      'kind',
      'expiresAt',
      'prefix',
      'manifestChain',
      // r2-temp-creds
      'chunkPrefix',
      'manifestKeys',
      'accessKeyId',
      'secretAccessKey',
      'sessionToken',
      'endpoint',
      'bucket',
      // presigned-s3
      'getUrls',
      'manifestGetUrls',
      // the snapshot's sealed listing, keyed by SNAPSHOT ID like the manifests,
      // present only when the snapshot was committed with one
      'indexKeys',
      'indexGetUrls',
      // direct-https
      'baseUrl',
      'token',
    ],
  },
  {
    path: '/commit',
    requestSchema: 'backupCommitRequest',
    responseSchema: 'backupCommitResponse',
    // hasIndex is the client's claim that the listing object is stored; the server refuses it when the object is absent.
    requestKeys: [
      'snapshotId',
      'lineageGuid',
      'streamId',
      'cellSizeBytes',
      'hasIndex',
      'cellsRoot',
      'luksUuid',
      'luksKeyDigest',
      'identityChangeAccepted',
      'chunksAlreadyPresent',
    ],
    responseKeys: [],
  },
  {
    // Ends a repair's lease, which nothing else ends before its TTL: until then the lineage's GC is suspended and the next repair is refused. No body; the snapshot id is the path parameter. A client that stopped calling it fails nothing at run time, since a failed release only warns, so this leg is what notices.
    path: '/leases/:snapshotId/release',
    requestSchema: null,
    responseSchema: 'backupLeaseReleaseResponse',
    requestKeys: [],
    responseKeys: ['released'],
    clientCall: /"\/leases\/"\s*\+[^\n]*\+\s*"\/release"/,
    // The request reaches the server through ReleaseLease, which RepairUpload calls on its way out.
    callerCall: { file: REPAIR_GO, pattern: /\breleaser\.ReleaseLease\(/ },
  },
];

/** The session header the account authenticates with. */
const SESSION_HEADER = 'X-Backup-Session';

/**
 * Spellings from the old renet dialect. Their reappearance in the client means
 * a revert, and each one was individually fatal.
 */
const RETIRED: { needle: string; why: string }[] = [
  {
    needle: '/chunks/exists',
    why: 'route does not exist; the account mounts /exists',
  },
  {
    needle: '/manifests"',
    why: 'commit posts a field set to /commit, not a document to /manifests',
  },
  {
    needle: '"Authorization", "Bearer "',
    why: `the session authenticates with ${SESSION_HEADER}; a bearer authenticates as nobody`,
  },
  {
    needle: '"lineage":',
    why: 'zod requires lineageGuid; `lineage` is a 400',
  },
];

/**
 * `baseUrl` is legitimate on a direct-https GRANT (the account really does send
 * one there), and fatal on the SESSION (it does not). A whole-file search for
 * the spelling therefore reports the innocent occurrence, which this gate did
 * on its first run: an over-broad needle is how a check earns a reputation for
 * crying wolf and then gets silenced. Scope the search to the Session struct.
 */
/**
 * Drop `//` comments. Without this the gate matched its own explanatory prose:
 * the Session struct carries a comment SAYING the account never sends baseUrl,
 * and a naive substring search read that as the field's return. A gate that
 * fires on the documentation of the bug it prevents is not a gate.
 */
function stripGoComments(source: string): string {
  return source
    .split('\n')
    .map((line) => line.replace(/\/\/.*$/, ''))
    .join('\n');
}

function sessionStructBody(client: string): string | null {
  const at = client.indexOf('type Session struct {');
  if (at === -1) return null;
  const end = client.indexOf('\n}', at);
  return end === -1 ? null : client.slice(at, end);
}

function read(rel: string): string {
  try {
    return readFileSync(join(ROOT, rel), 'utf8');
  } catch (err) {
    console.error(
      `✗ cannot read ${rel}: ${(err as Error).message}\n` +
        '  Both sides must be present; a missing submodule is an UNRUN check, not a pass.'
    );
    process.exit(1);
  }
}

/**
 * Top-level keys of a `export const <name> = z.object({...})` declaration.
 * The formatter splits a refined schema as `z\n  .object({...})\n  .superRefine(fn)`
 * (backupGrantRequest since plan S5), so whitespace around `.object(` is allowed;
 * the walk below still starts at the object literal and ignores the refinement.
 */
function zodKeys(source: string, schema: string): string[] | null {
  const decl = new RegExp(`export const ${schema} = z\\s*\\.object\\(\\{`).exec(source);
  if (!decl) return null;
  // Walk braces from the opening of the object literal so nested objects and unions do not truncate the scan early.
  // The opener is the match's last character: searching for the literal `z.object(` again would skip a split chain and land in the NEXT schema.
  const open = decl.index + decl[0].length - 1;
  let depth = 0;
  let end = open;
  for (let i = open; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  const body = source.slice(open + 1, end);
  const keys: string[] = [];
  let d = 0;
  for (const line of body.split('\n')) {
    const trimmed = line.trim();
    const m = /^([A-Za-z_][A-Za-z0-9_]*)\s*:/.exec(trimmed);
    if (d === 0 && m) keys.push(m[1]);
    for (const ch of line) {
      if (ch === '{' || ch === '[' || ch === '(') d++;
      else if (ch === '}' || ch === ']' || ch === ')') d--;
    }
  }
  return keys;
}

/**
 * The source text of a `const <name> = <expr>` declaration, following one level
 * of aliasing (`export const a = b;`). Response DTOs are not all plain
 * `z.object`: the read grant is a `z.discriminatedUnion` bound to a local and
 * re-exported, and a scanner that only understood `z.object({` would silently
 * find NOTHING there — a check that cannot fail on the newest leg.
 */
function schemaSource(source: string, name: string, depth = 0): string | null {
  if (depth > 4) return null;
  const decl = new RegExp(`(?:export\\s+)?const\\s+${name}\\s*=\\s*`).exec(source);
  if (!decl) return null;
  const start = decl.index + decl[0].length;
  const alias = /^([A-Za-z_][A-Za-z0-9_]*)\s*;/.exec(source.slice(start));
  if (alias) return schemaSource(source, alias[1], depth + 1);

  // Balance brackets from the first opener of the expression.
  let depthCount = 0;
  let started = false;
  for (let i = start; i < source.length; i++) {
    const ch = source[i];
    if (ch === '(' || ch === '{' || ch === '[') {
      depthCount++;
      started = true;
    } else if (ch === ')' || ch === '}' || ch === ']') {
      depthCount--;
      if (started && depthCount === 0) return source.slice(start, i + 1);
    } else if (!started && ch === ';') {
      return source.slice(start, i);
    }
  }
  return null;
}

/**
 * Does the Go client name this wire key?
 *
 * A bare `"key"` substring search misses `json:"key,omitempty"`, which is the
 * normal spelling for an optional field — and both `intent` (the restore
 * session) and `hashes` (both grant legs) are optional. The gate reported
 * `intent` as absent while session.go carried `json:"intent,omitempty"` on the
 * very next line of the struct it was checking. Matching the tag OPTIONS as
 * well is what makes the check see the field instead of the spelling.
 */
function clientNames(client: string, key: string): boolean {
  return new RegExp(`"${key}(?:"|,)`).test(client);
}

/** Every `key:` named anywhere inside a schema declaration, at any depth. */
function declaredKeys(schemaBody: string): Set<string> {
  const keys = new Set<string>();
  for (const m of schemaBody.matchAll(/(^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*:/g)) {
    keys.add(m[2]);
  }
  return keys;
}

/** Whether the client holds the leg's call, comments dropped. */
function clientCalls(leg: Leg, client: string): boolean {
  return leg.clientCall
    ? leg.clientCall.test(stripGoComments(client))
    : client.includes(`"${leg.path}"`);
}

/** Whether the leg's second proof is present: true when the leg declares none. */
function callerCalls(leg: Leg, sources: Record<string, string>): boolean {
  if (!leg.callerCall) return true;
  return leg.callerCall.pattern.test(stripGoComments(sources[leg.callerCall.file] ?? ''));
}

function checkLegs(
  legs: Leg[],
  routes: string,
  dto: string,
  client: string,
  sources: Record<string, string> = {}
): string[] {
  const problems: string[] = [];
  for (const leg of legs) {
    if (!routes.includes(`'${leg.path}'`)) {
      problems.push(`    ${leg.path}\n      declared here but ${ROUTES_TS} mounts no such route.`);
    }
    if (!clientCalls(leg, client)) {
      problems.push(`    ${leg.path}\n      declared here but ${CLIENT_GO} never calls it.`);
    }
    if (!callerCalls(leg, sources) && leg.callerCall) {
      problems.push(
        `    ${leg.path}\n      ${leg.callerCall.file} no longer calls ${leg.callerCall.pattern}, ` +
          'so nothing sends this request.'
      );
    }
    const accepted = leg.requestSchema === null ? [] : zodKeys(dto, leg.requestSchema);
    if (accepted === null) {
      problems.push(
        `    ${leg.path}\n      request schema ${leg.requestSchema} not found in ${DTO_TS}.`
      );
    } else {
      for (const key of leg.requestKeys) {
        if (!accepted.includes(key)) {
          problems.push(
            `    ${leg.path} request key "${key}"\n` +
              `      the client sends it, but ${leg.requestSchema ?? 'this bodyless route'} does not accept it,\n` +
              `      so the route answers 400. Accepted: ${accepted.join(', ')}`
          );
        }
      }
    }
    if (leg.responseSchema !== null) {
      const body = schemaSource(dto, leg.responseSchema);
      if (body === null) {
        problems.push(
          `    ${leg.path}\n      response schema ${leg.responseSchema} not found in ${DTO_TS}.`
        );
      } else {
        const declared = declaredKeys(body);
        for (const key of leg.responseKeys) {
          if (!declared.has(key)) {
            problems.push(
              `    ${leg.path} response key "${key}"\n` +
                `      the client reads it, but ${leg.responseSchema} does not declare it.\n` +
                '      The responds() airlock STRIPS undeclared fields, so the key never\n' +
                '      reaches the machine and decodes to its zero value, silently.'
            );
          }
        }
      }
    }
    for (const key of [...leg.requestKeys, ...leg.responseKeys]) {
      if (!clientNames(client, key)) {
        problems.push(
          `    ${leg.path} field "${key}"\n` +
            `      part of the protocol, but ${CLIENT_GO} never names it. A field the\n` +
            `      client does not send is a 400; one it does not read decodes to the\n` +
            `      zero value, and a zero-valued work list is the silent no-op.`
        );
      }
    }
  }
  return problems;
}

// ── Control: a leg neither side implements MUST be reported ────────────────
const CONTROL: Leg = {
  path: '/control-not-a-real-route',
  requestSchema: 'controlNotARealSchema',
  responseSchema: 'controlNotARealResponse',
  requestKeys: ['controlNotARealKey'],
  responseKeys: [],
};
if (checkLegs([CONTROL], '', '', '').length === 0) {
  console.error(
    '✗ instrument control did not fire: a synthetic leg implemented by neither side\n' +
      '  was not reported. The detector is blind, so a green run below would mean nothing.'
  );
  process.exit(1);
}

/**
 * Second control, for the response-declaration check specifically. The whole
 * point of adding it is that the old gate could not fail on a response key, so
 * proving the NEW arm fires needs its own synthetic: a DTO that declares the
 * schema but not the key, with a client that reads it and a route that exists.
 * A union form is used so the resolver's alias/discriminatedUnion path is the
 * one under test — that is the shape the newest real leg uses.
 */
const CONTROL_DTO = `
const controlUnion = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('a'), declaredKey: z.string() }),
]);
export const controlResponseSchema = controlUnion;
export const controlRequestSchema = z.object({ ask: z.string() });
`;
const CONTROL_RESPONSE: Leg = {
  path: '/control-response',
  requestSchema: 'controlRequestSchema',
  responseSchema: 'controlResponseSchema',
  requestKeys: ['ask'],
  responseKeys: ['declaredKey', 'undeclaredKey'],
};
const controlProblems = checkLegs(
  [CONTROL_RESPONSE],
  `'/control-response'`,
  CONTROL_DTO,
  `"/control-response" "ask" "declaredKey" "undeclaredKey"`
);
/**
 * Third control, for the omitempty tolerance above. `omitemptyKey` is named by
 * the synthetic client ONLY as `"omitemptyKey,omitempty"`, so it must NOT be
 * reported; `absentKey` is named nowhere, so it MUST be. Without both halves
 * the loosened matcher could have been loosened into never firing.
 */
const CONTROL_TAGS: Leg = {
  path: '/control-response',
  requestSchema: 'controlRequestSchema',
  responseSchema: null,
  requestKeys: ['omitemptyKey', 'absentKey'],
  responseKeys: [],
};
const tagProblems = checkLegs(
  [CONTROL_TAGS],
  `'/control-response'`,
  'export const controlRequestSchema = z.object({ omitemptyKey: z.string(), absentKey: z.string() });',
  `"/control-response" json:"omitemptyKey,omitempty"`
);
if (!tagProblems.some((p) => p.includes('"absentKey"'))) {
  console.error('✗ tag control did not fire: a key the client never names went unreported.');
  process.exit(1);
}
if (tagProblems.some((p) => p.includes('"omitemptyKey"'))) {
  console.error(
    '✗ tag control over-fired: a key the client names as `json:"k,omitempty"` was\n' +
      '  reported absent. That false positive is what this tolerance removes.'
  );
  process.exit(1);
}

if (!controlProblems.some((p) => p.includes('undeclaredKey'))) {
  console.error(
    '✗ response-declaration control did not fire: a response key the DTO does not\n' +
      '  declare went unreported, so this arm of the gate is blind.'
  );
  process.exit(1);
}
if (controlProblems.some((p) => p.includes('"declaredKey"'))) {
  console.error(
    '✗ response-declaration control over-fired: a key the DTO DOES declare was\n' +
      '  reported. A gate that cries wolf on correct code gets silenced.'
  );
  process.exit(1);
}

/**
 * Fourth control, for the whitespace-tolerant declaration match in zodKeys. A refined schema is
 * formatted as `z\n  .object({...})\n  .superRefine(fn)`; a regression back to the literal
 * `z.object(` search would not find it and would land in the NEXT schema's body.
 */
const SPLIT_CHAIN_DTO = `
export const splitSchema = z
  .object({ onlyKey: z.string() })
  .superRefine((v, ctx) => v);
export const nextSchema = z.object({ nextKey: z.string() });
`;
const splitKeys = zodKeys(SPLIT_CHAIN_DTO, 'splitSchema');
if (splitKeys === null || splitKeys.join(',') !== 'onlyKey') {
  console.error(
    `✗ split-chain control did not fire: a schema declared as z\\n.object({...}) read as [${splitKeys}], expected [onlyKey].`
  );
  process.exit(1);
}

/**
 * Fifth control, for a parameterised route with no body. The call has to be found
 * in code (a comment naming it is the same as no call), a bodyless route must not
 * report a missing request schema, and a key declared on one must still be reported.
 */
const PARAM_CALL = /"\/control\/"\s*\+[^\n]*\+\s*"\/go"/;
const CONTROL_PARAM: Leg = {
  path: '/control/:id/go',
  requestSchema: null,
  responseSchema: null,
  requestKeys: [],
  responseKeys: [],
  clientCall: PARAM_CALL,
};
const paramRoute = `'/control/:id/go'`;
const paramCall = 'c.endpoint("/control/" + id + "/go")';
if (checkLegs([CONTROL_PARAM], paramRoute, '', paramCall).length !== 0) {
  console.error(
    '✗ parameterised control over-fired: a bodyless route whose call exists was reported.'
  );
  process.exit(1);
}
if (checkLegs([CONTROL_PARAM], paramRoute, '', `// ${paramCall}`).length === 0) {
  console.error('✗ parameterised control did not fire: a comment stood in for the client call.');
  process.exit(1);
}
if (checkLegs([CONTROL_PARAM], '', '', paramCall).length === 0) {
  console.error('✗ parameterised control did not fire: a route nobody mounts went unreported.');
  process.exit(1);
}
const bodylessKey = checkLegs(
  [{ ...CONTROL_PARAM, requestKeys: ['bodyKey'] }],
  paramRoute,
  '',
  `${paramCall} "bodyKey"`
);
if (!bodylessKey.some((p) => p.includes('"bodyKey"'))) {
  console.error('✗ parameterised control did not fire: a bodyless route took a request key.');
  process.exit(1);
}

/**
 * Sixth control, on the REAL release leg rather than a synthetic one: its own patterns
 * must accept the code that sends the request and refuse a comment, a log string and a
 * lookalike. A regex nobody exercised can match nothing, or everything, and stay green.
 */
const releaseLeg = LEGS.find((leg) => leg.path === '/leases/:snapshotId/release');
if (!releaseLeg?.clientCall || !releaseLeg.callerCall) {
  console.error('✗ release-leg control: the leg lost its clientCall or callerCall proof.');
  process.exit(1);
}
const releaseSend = 'c.endpoint("/leases/"+url.PathEscape(snapshotID)+"/release")';
const releaseCaller = 'released, err := releaser.ReleaseLease(ctx, snapshotID)';
const releaseSources = (text: string) => ({ [releaseLeg.callerCall?.file ?? '']: text });
if (
  !clientCalls(releaseLeg, releaseSend) ||
  !callerCalls(releaseLeg, releaseSources(releaseCaller))
) {
  console.error('✗ release-leg control over-fired: the real call shapes were not recognised.');
  process.exit(1);
}
for (const decoy of [
  `// ${releaseCaller}`,
  'log.Printf("ReleaseLease failed")',
  'func (c *X) ReleaseLease(ctx context.Context) {}',
  'releaseLease(ctx, snapshotID)',
]) {
  if (callerCalls(releaseLeg, releaseSources(decoy))) {
    console.error(`✗ release-leg control did not fire: ${decoy} counted as the call.`);
    process.exit(1);
  }
}
if (clientCalls(releaseLeg, `// ${releaseSend}`) || clientCalls(releaseLeg, 'log("/release")')) {
  console.error('✗ release-leg control did not fire: a comment or log string counted as the send.');
  process.exit(1);
}

// ── Real run ────────────────────────────────────────────────────────────────
const routes = read(ROUTES_TS);
const dto = read(DTO_TS);
const client = read(CLIENT_GO);

if (routes.length === 0 || dto.length === 0 || client.length === 0) {
  console.error('✗ nothing scanned: one of the three protocol files is empty.');
  process.exit(1);
}

const problems = checkLegs(LEGS, routes, dto, client, { [REPAIR_GO]: read(REPAIR_GO) });

if (!routes.includes(`'${SESSION_HEADER}'`)) {
  problems.push(`    auth\n      ${ROUTES_TS} no longer reads ${SESSION_HEADER}.`);
}
if (!client.includes(`"${SESSION_HEADER}"`)) {
  problems.push(`    auth\n      ${CLIENT_GO} no longer sends ${SESSION_HEADER}.`);
}

for (const { needle, why } of RETIRED) {
  if (client.includes(needle)) {
    problems.push(`    retired spelling ${needle}\n      back in ${CLIENT_GO}: ${why}`);
  }
}

const sessionBody = sessionStructBody(client);
if (sessionBody === null) {
  problems.push(
    `    Session\n      type Session struct not found in ${CLIENT_GO}; this gate cannot\n` +
      '      verify the field that made MintSession fail 100% of the time.'
  );
} else if (stripGoComments(sessionBody).includes('json:"baseUrl"')) {
  problems.push(
    '    Session.baseUrl\n' +
      `      back on the Session struct in ${CLIENT_GO}. The account's session\n` +
      '      response carries no baseUrl, so requiring one fails every mint. It is\n' +
      '      legitimate only on a direct-https grant, which is a different type.'
  );
}

if (problems.length > 0) {
  console.error(
    `✗ backup protocol conformance (${problems.length}):\n${problems.join('\n')}\n\n` +
      '  renet and the account must speak one protocol. Each side has its own unit\n' +
      '  tests against its own fake, so both stay green while agreeing on nothing;\n' +
      '  that is exactly how this shipped through two certified waves.'
  );
  process.exit(1);
}

console.log(
  `✓ backup protocol conformance ` +
    `(${LEGS.length} legs pinned across routes, DTOs and the Go client; ` +
    `${RETIRED.length} retired spellings absent; control fired)`
);
