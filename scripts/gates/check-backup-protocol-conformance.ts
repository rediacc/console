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
const REPORT_GO = 'private/renet/cmd/renet/backup_report.go';
const REPORT_FIELDS_GO = 'private/renet/cmd/renet/backup_snapshot_report.go';
const RESTORE_SIZE_TS = 'packages/cli/src/services/executor/repo-license-context.ts';
const RESTORE_TEST_TS = 'packages/cli/src/commands/backup-restore-test.ts';
const RESTORE_SESSION_TS = 'packages/cli/src/commands/backup-image-deps.ts';
const RESOLVE_AT_TS = 'packages/cli/src/commands/backup-restore-chunk.ts';

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
   * stand in for the code that sends the request. `within` narrows it to the body of that Go function, or of a
   * function it defers, so a call in an unused helper does not count.
   */
  callerCall?: { file: string; pattern: RegExp; within?: string };
  /**
   * The files speaking this leg, for one session.go does not send: the report body is built in
   * cmd/renet, and a query string reaches the account from the CLI. Absent means session.go. Each
   * leg names its own file, so the keys of one leg cannot be satisfied by another's speaker.
   */
  clientFiles?: string[];
  /** The request schema is declared in the routes file, not backup.dto.ts (the restore-session body is route-local). */
  requestInRoutes?: boolean;
  /** How the speaker spells a key, for one that is no Go JSON tag. Absent means clientNames. */
  keySpelling?: (key: string) => RegExp;
  /**
   * The slice of the speaker that is this leg's REQUEST, which the request keys are looked for in. A speaker that also
   * holds other objects naming the same key (a response struct, another body) would otherwise keep the gate green after
   * the request drops it. Null means the request cannot be found in the speaker, which is a finding. Absent means the
   * whole speaker.
   */
  requestScope?: (speaker: string) => string | null;
}

/** A key of a TypeScript object literal the CLI sends as a JSON body. */
const bodyKey = (key: string) => new RegExp(`[{,]\\s*${key}\\s*[:,}]`);

/**
 * The index just past the bracket that closes the one at `open` (`{`, `(` or `[`), with quoted text skipped so a brace
 * inside a string does not count; -1 when it never closes.
 */
function closeOf(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    const ch = text[i];
    if (ch === "'" || ch === '"' || ch === '`') {
      const close = text.indexOf(ch, i + 1);
      if (close === -1) return -1;
      i = close;
    } else if (ch === '{' || ch === '(' || ch === '[') depth++;
    else if (ch === '}' || ch === ')' || ch === ']') {
      depth--;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}

/** The top-level properties of an object literal `{...}`: name to value text, a shorthand's value being its name. */
function topLevelProps(object: string): Map<string, string> {
  const props = new Map<string, string>();
  const inner = object.slice(1, -1);
  const segments: string[] = [];
  let from = 0;
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i];
    if (ch === "'" || ch === '"' || ch === '`' || ch === '{' || ch === '(' || ch === '[') {
      const close =
        ch === '{' || ch === '(' || ch === '[' ? closeOf(inner, i) : inner.indexOf(ch, i + 1) + 1;
      if (close <= 0) break;
      i = close - 1;
    } else if (ch === ',') {
      segments.push(inner.slice(from, i));
      from = i + 1;
    }
  }
  segments.push(inner.slice(from));
  for (const segment of segments) {
    const m = /^\s*([A-Za-z_$][\w$]*)\s*(?::([\s\S]*))?$/.exec(segment);
    if (m) props.set(m[1], m[2] ?? m[1]);
  }
  return props;
}

/**
 * The expression the CLI passes as `body:` to the POST to `call`: the route as a quoted string, then an options object
 * read with balanced brackets (so a nested object before `method:` still matches), whose top-level `method` is `'POST'`.
 * The body is that object's own top-level `body` property, so a ternary of two object literals is read whole, and a
 * `body:` of a later call, or a `{ storeId` elsewhere in the file, is never read for a POST that sends none.
 */
function postBodyOf(call: string): (speaker: string) => string | null {
  const escaped = call.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return (speaker) => {
    // An earlier mention of the route (a comment, a constant, a GET) is passed over: only a POST's options count.
    for (const hit of speaker.matchAll(new RegExp(`${escaped}['"\`]\\s*,\\s*\\{`, 'g'))) {
      const open = hit.index + hit[0].length - 1;
      const close = closeOf(speaker, open);
      if (close === -1) continue;
      const props = topLevelProps(speaker.slice(open, close));
      if (!/^\s*['"]POST['"]\s*$/.test(props.get('method') ?? '')) continue;
      const body = props.get('body');
      return body === undefined ? null : `body: ${body}`;
    }
    return null;
  };
}

/**
 * The bodies of the named top-level TypeScript functions, joined: the slice of a speaker that builds one query, so a key
 * named elsewhere in the file cannot stand in for it. Null when any of them is not defined.
 */
function tsFunctionBodies(...names: string[]): (speaker: string) => string | null {
  return (speaker) => {
    const bodies: string[] = [];
    for (const name of names) {
      const head = new RegExp(`^(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`, 'm').exec(
        speaker
      );
      if (!head) return null;
      const paramsEnd = closeOf(speaker, head.index + head[0].length - 1);
      if (paramsEnd === -1) return null;
      const open = speaker.indexOf('{', paramsEnd);
      const close = open === -1 ? -1 : closeOf(speaker, open);
      if (close === -1) return null;
      bodies.push(speaker.slice(open, close));
    }
    return bodies.join('\n');
  };
}

/** The Go struct that is the session request body, comments dropped. */
function sessionRequestStruct(speaker: string): string | null {
  const at = speaker.indexOf('type sessionRequest struct {');
  if (at === -1) return null;
  const end = speaker.indexOf('\n}', at);
  return end === -1 ? null : stripGoComments(speaker.slice(at, end));
}

/** A key of a query string the CLI composes. */
const queryKey = (key: string) => new RegExp(`[?&]${key}=`);

/** The protocol, declared once. Both sides are checked against THIS. */
const LEGS: Leg[] = [
  {
    path: '/session',
    requestSchema: 'backupSessionRequest',
    responseSchema: 'backupSessionResponse',
    // `intent` splits the session in two ('backup' | 'restore'). A restore session is the only credential a lapsed-but-retained subscription can get, so a client that cannot spell the field cannot restore at all.
    // `storeId` names the backup store the session is for (PLAN-backup-multi-target R2; renet sends it for a store other than home). A spelling the schema does not accept is stripped silently and every session opens on `home`.
    requestKeys: ['license', 'machineId', 'intent', 'storeId'],
    requestScope: sessionRequestStruct,
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
    // `purpose` decides whether the answer writes a pin. A spelling the schema does not accept is stripped silently, and every sample then pins.
    requestKeys: ['lineageGuid', 'hashes', 'purpose'],
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
      // PLAN-backup-critical-tier D-exists and D-lease: the base is what protects a changed-only run's unasked chunks from a prune, so a stripped spelling leaves them unprotected with no error. The stream is what counts one lease per stream, and the server falls back to the session's when it is stripped.
      'streamId',
      'baseSnapshotId',
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
      // PLAN-backup-critical-tier: the base the commit re-checks, what the run did to the application, and the deliberate skip that keeps an hourly seal from reading as a lost index.
      'baseSnapshotId',
      'consistency',
      'indexSkipped',
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
    // The request reaches the server through ReleaseLease, which RepairUpload defers on its way out.
    callerCall: { file: REPAIR_GO, pattern: /\breleaser\.ReleaseLease\(/, within: 'RepairUpload' },
  },
  {
    // The run's report. A spelling the schema does not accept is stripped silently, and hookFailures and hookFinish are the only way the account learns an application's prepare keeps failing or may still be held: nothing would alert, and no run would fail.
    path: '/reports',
    requestSchema: 'backupReportRequest',
    responseSchema: 'backupReportResponse',
    requestKeys: [
      'kind',
      'snapshotId',
      'level',
      'status',
      'reason',
      'nextExpectedAt',
      'targetSeconds',
      'achievedRpoMs',
      'ticksMissed',
      'targetMet',
      'hookFailures',
      'hookFinish',
    ],
    responseKeys: [],
    clientCall: /\.APIBase\(\)\s*\+\s*"\/reports"/,
    clientFiles: [REPORT_GO, REPORT_FIELDS_GO],
  },
  // PLAN-backup-multi-target A3: the restore session names its store. The CLI sends `storeId` only on `download --store --from <id>`; a spelling the schema does not accept is stripped silently and the download reads `home` whatever the operator chose. The body schema is route-local, and the CLI does not read the echoed storeId, so no response key is pinned.
  {
    path: '/restore-session',
    requestSchema: 'backupRestoreSessionRequest',
    requestInRoutes: true,
    responseSchema: null,
    requestKeys: ['lineageGuid', 'storeId'],
    responseKeys: [],
    clientCall: /\/backups\/restore-session/,
    clientFiles: [RESTORE_SESSION_TS],
    keySpelling: bodyKey,
    requestScope: postBodyOf('/backups/restore-session'),
  },
  // A time resolves inside the store a restore reads (PLAN-backup-multi-target C3 follow-up, item #acd03b8a): `storeId` rides the query resolveSnapshotAt builds, so a snapshot only another store holds is never handed to this one. A spelling the query schema does not accept is stripped silently and the resolve spans every store again, with no error.
  {
    path: '/snapshots/resolve',
    requestSchema: 'backupSnapshotResolveQuery',
    responseSchema: 'backupSnapshotResolveResponse',
    requestKeys: ['lineage', 'storeId'],
    responseKeys: [],
    clientCall: /RESOLVE_ROUTE = '\/account\/api\/v1\/backups\/snapshots\/resolve'/,
    clientFiles: [RESOLVE_AT_TS],
    keySpelling: bodyKey,
    requestScope: tsFunctionBodies('fetchResolved', 'resolveSnapshotAt'),
  },
  // A delayed delete still restores until its time, and the resolve route hides it unless asked. The two by-id size reads ask: without it a restore of one is licensed at the minimum size, and a restore test refuses it for an unknown size.
  ...[RESTORE_SIZE_TS, RESTORE_TEST_TS].map(
    (file): Leg => ({
      path: '/snapshots/resolve',
      requestSchema: 'backupSnapshotResolveQuery',
      responseSchema: 'backupSnapshotResolveResponse',
      requestKeys: ['lineage', 'anchorSnapshotId', 'includeDeleted'],
      responseKeys: [],
      clientCall: /\/backups\/snapshots\/resolve\?/,
      clientFiles: [file],
      keySpelling: queryKey,
    })
  ),
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
 * Top-level keys of a `const <name> = z.object({...})` declaration, exported or not (the restore-session body is a
 * route-local const).
 * The formatter splits a refined schema as `z\n  .object({...})\n  .superRefine(fn)`
 * (backupGrantRequest since plan S5), so whitespace around `.object(` is allowed;
 * the walk below still starts at the object literal and ignores the refinement.
 */
function zodKeys(source: string, schema: string): string[] | null {
  const decl = new RegExp(`(?:export\\s+)?const ${schema} = z\\s*\\.object\\(\\{`).exec(source);
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
  const source = stripGoComments(sources[leg.callerCall.file] ?? '');
  const { pattern, within } = leg.callerCall;
  if (within === undefined) return pattern.test(source);
  const body = goFuncBody(source, within);
  if (body === null) return false;
  if (pattern.test(body)) return true;
  for (const m of body.matchAll(/\bdefer\s+([A-Za-z_]\w*)\(/g)) {
    const deferred = goFuncBody(source, m[1]);
    if (deferred !== null && pattern.test(deferred)) return true;
  }
  return false;
}

/** The text between the braces of a top-level Go function (or method) by name, or null when it is not defined. */
function goFuncBody(source: string, name: string): string | null {
  const head = new RegExp(`^func\\s+(?:\\([^)]*\\)\\s*)?${name}\\(`, 'm').exec(source);
  if (!head) return null;
  const open = source.indexOf('{', head.index);
  if (open === -1) return null;
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}' && --depth === 0) return source.slice(open + 1, i);
  }
  return null;
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
    const speaker = leg.clientFiles
      ? leg.clientFiles.map((file) => sources[file] ?? '').join('\n')
      : client;
    const speakerName = leg.clientFiles?.join(', ') ?? CLIENT_GO;
    if (!clientCalls(leg, speaker)) {
      problems.push(`    ${leg.path}\n      declared here but ${speakerName} never calls it.`);
    }
    if (!callerCalls(leg, sources) && leg.callerCall) {
      problems.push(
        `    ${leg.path}\n      ${leg.callerCall.file} no longer calls ${leg.callerCall.pattern}, ` +
          'so nothing sends this request.'
      );
    }
    const accepted =
      leg.requestSchema === null
        ? []
        : zodKeys(leg.requestInRoutes ? routes : dto, leg.requestSchema);
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
    const requestText = leg.requestScope ? leg.requestScope(speaker) : speaker;
    if (requestText === null) {
      problems.push(
        `    ${leg.path}\n      the request body is not found in ${speakerName}, so its keys are unchecked.`
      );
    }
    // Independent checks: a key in both lists is looked for in the request slice AND in the whole speaker.
    const keyChecks = [
      ...leg.requestKeys.map((key) => ({ key, text: requestText ?? '' })),
      ...leg.responseKeys.map((key) => ({ key, text: speaker })),
    ];
    for (const { key, text } of keyChecks) {
      const named = leg.keySpelling ? leg.keySpelling(key).test(text) : clientNames(text, key);
      if (!named) {
        problems.push(
          `    ${leg.path} field "${key}"\n` +
            `      part of the protocol, but ${speakerName} never names it. A field the\n` +
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
const releaseCaller =
  'func RepairUpload() {\n\tdefer release()\n}\nfunc release() {\n\treleased, err := releaser.ReleaseLease(ctx, snapshotID)\n}';
const releaseSources = (text: string) => ({ [releaseLeg.callerCall?.file ?? '']: text });
if (
  !clientCalls(releaseLeg, releaseSend) ||
  !callerCalls(releaseLeg, releaseSources(releaseCaller))
) {
  console.error('✗ release-leg control over-fired: the real call shapes were not recognised.');
  process.exit(1);
}
for (const decoy of [
  `// ${releaseCaller}`.replace(/\n/g, '\n// '),
  'log.Printf("ReleaseLease failed")',
  'func (c *X) ReleaseLease(ctx context.Context) {}',
  'releaseLease(ctx, snapshotID)',
  // The call sits in a helper RepairUpload neither calls directly nor defers.
  'func RepairUpload() {\n\tdefer other()\n}\nfunc unused() {\n\treleaser.ReleaseLease(ctx, id)\n}',
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

/**
 * Seventh control, on the REAL legs another file speaks: each must pass on its own file holding
 * the keys, and fail when the key is gone from it, whatever session.go says. The keys sit in a
 * session.go text here so a leg falling back to that file reads as a blind arm.
 */
const reportLeg = LEGS.find((leg) => leg.path === '/reports');
const resolveLegs = LEGS.filter(
  (leg) => leg.path === '/snapshots/resolve' && leg.requestKeys.includes('includeDeleted')
);
if (!reportLeg || resolveLegs.length !== 2) {
  console.error('✗ speaker control: the /reports leg or a /snapshots/resolve leg is gone.');
  process.exit(1);
}
for (const [leg, key, spell] of [
  [reportLeg, 'hookFailures', 'json:"hookFailures,omitempty"'],
  [reportLeg, 'hookFinish', 'json:"hookFinish,omitempty"'],
  [resolveLegs[0], 'includeDeleted', '&includeDeleted=1'],
  [resolveLegs[1], 'includeDeleted', '&includeDeleted=1'],
] as const) {
  const lone: Leg = { ...leg, responseSchema: null, requestSchema: 'ctrl', requestKeys: [key] };
  const accepts = `export const ctrl = z.object({\n  ${key}: z.string(),\n});`;
  const call = leg === reportLeg ? 'x.APIBase()+"/reports"' : '/backups/snapshots/resolve?';
  const files = leg.clientFiles ?? [];
  const route = `'${leg.path}'`;
  const speak = (text: string) => Object.fromEntries(files.map((f) => [f, text]));
  if (checkLegs([lone], route, accepts, '', speak(`${call} ${spell}`)).length !== 0) {
    console.error(`✗ speaker control over-fired: ${leg.path} did not see ${spell}.`);
    process.exit(1);
  }
  const gone = speak(`${call} ${spell.replace(key, 'x')}`);
  if (
    checkLegs([lone], route, accepts, `"${key}" ${spell}`, speak(call)).length === 0 ||
    checkLegs([lone], route, accepts, '', gone).length === 0
  ) {
    console.error(`✗ speaker control did not fire: ${leg.path} accepted a speaker without ${key}.`);
    process.exit(1);
  }
}

/**
 * Eighth control, the restore-session body: its schema is route-local, so a scan of
 * backup.dto.ts alone finds nothing. It must pass with the key in both the route schema and
 * the CLI body, and fail when either side drops it.
 */
const restoreLeg = LEGS.find((leg) => leg.path === '/restore-session');
if (!restoreLeg) {
  console.error('✗ restore-session control: the /restore-session leg is gone.');
  process.exit(1);
}
{
  const route = "'/restore-session'";
  const schema = (keys: string) => `const ${restoreLeg.requestSchema} = z.object({\n${keys}});`;
  const both = schema('  lineageGuid: z.string(),\n  storeId: z.string().optional(),\n');
  const noStore = schema('  lineageGuid: z.string(),\n');
  const call = '/backups/restore-session';
  const post = (options: string) => `fetch('${call}', { method: 'POST', ${options} })`;
  const speak = (body: string) => ({ [RESTORE_SESSION_TS]: post(`body: { ${body} }`) });
  const run = (routeText: string, dtoText: string, body: string) =>
    checkLegs([restoreLeg], routeText, dtoText, '', speak(body));
  if (
    run(`${route}\n${both}`, '', 'lineageGuid, storeId: store').length !== 0 ||
    run(`${route}\n${noStore}`, '', 'lineageGuid, storeId: store').length === 0 ||
    run(`${route}\n${both}`, '', 'lineageGuid').length === 0 ||
    // storeId named elsewhere in the speaker (another body) must not stand in for the restore-session body.
    checkLegs([restoreLeg], `${route}\n${both}`, '', '', {
      [RESTORE_SESSION_TS]: `other: { storeId: x }\n${post('body: { lineageGuid }, headers: {}')}\nlater: { storeId: y }`,
    }).length === 0 ||
    // an earlier mention of the route (comment, constant, a GET with its own body) must not anchor the body: the real POST body lacks storeId.
    checkLegs([restoreLeg], `${route}\n${both}`, '', '', {
      [RESTORE_SESSION_TS]: `// the ${call} route\nconst u = '${call}';\nget(u, { body: { storeId: x } });\n${post('body: { lineageGuid }')}`,
    }).length === 0 ||
    // the same earlier mention must not hide a real body that does name it.
    checkLegs([restoreLeg], `${route}\n${both}`, '', '', {
      [RESTORE_SESSION_TS]: `// the ${call} route\nget('${call}', { body: { x: 1 } });\n${post('body: { lineageGuid, storeId: s }')}`,
    }).length !== 0 ||
    // the ternary of two literals the real client sends is read whole.
    checkLegs([restoreLeg], `${route}\n${both}`, '', '', {
      [RESTORE_SESSION_TS]: post(
        'body: s === undefined ? { lineageGuid } : { lineageGuid, storeId: s }, x: 1'
      ),
    }).length !== 0 ||
    // a nested object before `method:` must not hide the POST (1a0788d8.4).
    checkLegs([restoreLeg], `${route}\n${both}`, '', '', {
      [RESTORE_SESSION_TS]: `fetch('${call}', { headers: { a: '{' }, method: 'POST', body: { lineageGuid, storeId: s } })`,
    }).length !== 0 ||
    // a POST with no body must not borrow the body of a later, unrelated call (1a0788d8.3).
    checkLegs([restoreLeg], `${route}\n${both}`, '', '', {
      [RESTORE_SESSION_TS]: `${post('headers: {}')}\nother('/x', { method: 'POST', body: { lineageGuid, storeId: s } });`,
    }).length === 0 ||
    run(`${route}`, both, 'lineageGuid, storeId: store').length === 0
  ) {
    console.error('✗ restore-session control: storeId not pinned on both sides of the leg.');
    process.exit(1);
  }
}

/**
 * Ninth control, the /session request slice (the sessionRequest struct): it must pass with every request key in
 * the struct, and fail when the struct is missing, or lacks a key that another struct in the speaker names.
 */
const sessionLeg = LEGS.find((leg) => leg.path === '/session');
if (!sessionLeg) {
  console.error('✗ session-request control: the /session leg is gone.');
  process.exit(1);
}
{
  const lone: Leg = {
    ...sessionLeg,
    requestSchema: 'ctrl',
    responseSchema: null,
    responseKeys: [],
  };
  const accepts = `export const ctrl = z.object({\n${lone.requestKeys.map((key) => `  ${key}: z.string(),`).join('\n')}\n});`;
  const field = (key: string) =>
    `\t${key[0].toUpperCase()}${key.slice(1)} string \`json:"${key}"\``;
  const struct = (name: string, keys: string[]) =>
    `type ${name} struct {\n${keys.map(field).join('\n')}\n}\n`;
  const run = (speaker: string) =>
    checkLegs([lone], `'${lone.path}'`, accepts, `"${lone.path}"\n${speaker}`);
  const all = struct('sessionRequest', lone.requestKeys);
  const response = struct('sessionResponse', lone.requestKeys);
  const dropped = lone.requestKeys.filter((key) => key !== 'storeId');
  if (
    run(all).length !== 0 ||
    // the struct is gone, its keys named by another struct only.
    run(response).length === 0 ||
    // the struct is renamed (the slice anchor misses), keys named elsewhere.
    run(`${struct('sessionBody', lone.requestKeys)}${response}`).length === 0 ||
    // the struct lost storeId while a later struct still names it.
    run(`${struct('sessionRequest', dropped)}${response}`).length === 0
  ) {
    console.error(
      '✗ session-request control: a missing or mis-sliced sessionRequest struct went unreported.'
    );
    process.exit(1);
  }
}

/**
 * Tenth control, a key in both requestKeys and responseKeys of a requestScope leg: the request check reads the
 * request slice and the response check reads the whole speaker, independently. A key named only outside the slice
 * is one finding (the request's), not two.
 */
{
  const both: Leg = {
    path: '/control-both',
    requestSchema: 'ctrl',
    responseSchema: null,
    requestKeys: ['shared'],
    responseKeys: ['shared'],
    requestScope: (speaker) => speaker.split('RESPONSE')[0],
  };
  const run = (speaker: string) =>
    checkLegs(
      [both],
      `'/control-both'`,
      'export const ctrl = z.object({ shared: z.string() });',
      `"/control-both" ${speaker}`
    );
  if (
    run('"shared" RESPONSE').length !== 0 ||
    run('"other" RESPONSE "shared"').length !== 1 ||
    run('"other" RESPONSE "other"').length !== 2
  ) {
    console.error(
      '✗ key-scope control: a key in both request and response keys was not checked independently.'
    );
    process.exit(1);
  }
}

/**
 * Eleventh control, the store a time resolves in: the leg must pass with `storeId` in the query resolveSnapshotAt
 * builds, and fail when the query schema drops it, when the speaker names it only outside the two functions that build
 * the query, and when either function is gone.
 */
{
  const leg = LEGS.find(
    (l) => l.path === '/snapshots/resolve' && (l.clientFiles ?? []).includes(RESOLVE_AT_TS)
  );
  if (!leg) {
    console.error('✗ resolve-store control: the /snapshots/resolve storeId leg is gone.');
    process.exit(1);
  }
  const route = "'/snapshots/resolve'";
  const query = (keys: string) =>
    `export const backupSnapshotResolveQuery = z.object({\n${keys}});`;
  const accepts = query('  lineage: guidSchema,\n  storeId: backupStoreIdSchema.optional(),\n');
  const constant = "const RESOLVE_ROUTE = '/account/api/v1/backups/snapshots/resolve';";
  const fetcher =
    'async function fetchResolved(lineage: string, q: Q): Promise<E> {\n  const params = new URLSearchParams({ lineage });\n}';
  const resolver = (stream: string) =>
    `export async function resolveSnapshotAt(\n  lineage: string,\n  options: O = {}\n): Promise<string> {\n  const stream = { ${stream} };\n  return fetchResolved(lineage, stream);\n}`;
  const speak = (text: string) => ({ [RESOLVE_AT_TS]: `${constant}\n${text}` });
  const check = (dtoText: string, text: string) =>
    checkLegs([{ ...leg, responseSchema: null }], route, dtoText, '', speak(text));
  if (
    check(accepts, `${fetcher}\n${resolver("anyStream: '1', storeId: options.store")}`).length !==
      0 ||
    check(
      query('  lineage: guidSchema,\n'),
      `${fetcher}\n${resolver("anyStream: '1', storeId: options.store")}`
    ).length === 0 ||
    check(accepts, `${fetcher}\n${resolver("anyStream: '1'")}\nconst other = { storeId: x };`)
      .length === 0 ||
    check(accepts, `${resolver("anyStream: '1', storeId: options.store")}`).length === 0
  ) {
    console.error(
      '✗ resolve-store control: storeId on the resolve query is not pinned on both sides.'
    );
    process.exit(1);
  }
}

// ── Real run ────────────────────────────────────────────────────────────────
const routes = read(ROUTES_TS);
const dto = read(DTO_TS);
const client = read(CLIENT_GO);

if (routes.length === 0 || dto.length === 0 || client.length === 0) {
  console.error('✗ nothing scanned: one of the three protocol files is empty.');
  process.exit(1);
}

const problems = checkLegs(LEGS, routes, dto, client, {
  [REPAIR_GO]: read(REPAIR_GO),
  [REPORT_GO]: read(REPORT_GO),
  [REPORT_FIELDS_GO]: read(REPORT_FIELDS_GO),
  [RESTORE_SIZE_TS]: read(RESTORE_SIZE_TS),
  [RESTORE_TEST_TS]: read(RESTORE_TEST_TS),
  [RESTORE_SESSION_TS]: read(RESTORE_SESSION_TS),
  [RESOLVE_AT_TS]: read(RESOLVE_AT_TS),
});

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
