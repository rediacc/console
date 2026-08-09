#!/usr/bin/env node
// Validate the model's handoff file before the harness stages a single byte.
//
// THE INVARIANT THIS SERVES (docs/ci-overhaul/03-v2-autonomy.md section 0):
// the model never holds a write token, so handoff.json is by definition
// UNTRUSTED input to the write path. Everything here fails toward escalation:
// every rejection exits non-zero with an `ESCALATE: <class>: ...` line on
// stderr, and there is deliberately NO silent no-op path. A wedged model (no
// handoff, garbage handoff, half a handoff) must be visible to the operator,
// not quietly absorbed as "nothing to do".
//
// Usage:
//   validate-handoff.cjs --handoff <file> --root <checkout> \
//     --base-head <sha> --status <file> [--allow-submodules true|false]
//
//   --root       the checkout the harness owns; every declared path must
//                realpath-resolve to inside it.
//   --base-head  the sha the HARNESS checked out (git rev-parse HEAD). The
//                handoff's base_head must equal it exactly.
//   --status     capture of `git status --porcelain=v1 -z` taken by the
//                harness. Passed as a file so this validator is pure and
//                offline-testable: it runs no git, no network, no shell.
//   --allow-submodules  the S6 stage flag, as a VALUE rather than an ambient
//                read: absent falls back to AUTOPILOT_ALLOW_SUBMODULES in the
//                environment, and anything other than the literal 'true' is
//                off. A handoff carrying submodules[] while this is off is
//                REJECTED rather than trimmed, because a round that quietly
//                dropped its submodule half would push a console pointer bump
//                with nothing behind it.
//
// Exit: 0 valid (normalized verdict JSON on stdout), 1 escalate (reasons on
// stderr), 2 usage error. There is no exit code meaning "ignore me".

'use strict';

const fs = require('fs');
const path = require('path');

const SCHEMA_FILE = path.join(__dirname, 'handoff.schema.json');
const MAX_HANDOFF_BYTES = 65536;

// Paths the harness must never stage, whatever the model says. `.github/**`
// is its own class: the operator decision (03-v2-autonomy.md wall 2) is that
// workflow fixes ESCALATE with the proposed patch attached as data. The rest
// are blocked outright: they are the agent-config surface that wall 4 exists
// to protect, and a "fix" touching them is indistinguishable from an attack.
const DENY_GITHUB = ['.github'];
const DENY_BLOCKED_PREFIXES = ['.claude', '.husky'];
const DENY_BLOCKED_EXACT = [
  '.mcp.json',
  '.claude.json',
  'CLAUDE.md',
  'CLAUDE.local.md',
  '.gitmodules',
];

// ---------------------------------------------------------------------------
// Minimal interpreter for the subset of JSON Schema handoff.schema.json uses.
// Interpreting the schema file (rather than duplicating its rules in code)
// keeps the published contract and the enforcement from drifting apart.
// ---------------------------------------------------------------------------
function validateNode(value, schema, ptr, errors) {
  if (schema.const !== undefined && value !== schema.const) {
    errors.push(`${ptr}: must equal '${schema.const}'`);
    return;
  }
  if (schema.enum && !schema.enum.includes(value)) {
    errors.push(`${ptr}: must be one of ${schema.enum.join('|')}`);
    return;
  }
  if (schema.type === 'string') {
    if (typeof value !== 'string') return void errors.push(`${ptr}: must be a string`);
    if (schema.minLength !== undefined && value.length < schema.minLength)
      errors.push(`${ptr}: shorter than ${schema.minLength}`);
    if (schema.maxLength !== undefined && value.length > schema.maxLength)
      errors.push(`${ptr}: longer than ${schema.maxLength}`);
    if (schema.pattern && !new RegExp(schema.pattern).test(value))
      errors.push(`${ptr}: does not match ${schema.pattern}`);
    return;
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value)) return void errors.push(`${ptr}: must be an array`);
    if (schema.maxItems !== undefined && value.length > schema.maxItems)
      errors.push(`${ptr}: more than ${schema.maxItems} items`);
    if (schema.items)
      value.forEach((v, i) => validateNode(v, schema.items, `${ptr}[${i}]`, errors));
    return;
  }
  if (schema.type === 'object') {
    if (typeof value !== 'object' || value === null || Array.isArray(value))
      return void errors.push(`${ptr}: must be an object`);
    for (const key of schema.required || []) {
      if (!(key in value)) errors.push(`${ptr}.${key}: required field missing`);
    }
    for (const [key, v] of Object.entries(value)) {
      const sub = (schema.properties || {})[key];
      if (!sub) {
        if (schema.additionalProperties === false) errors.push(`${ptr}.${key}: unknown field`);
        continue;
      }
      validateNode(v, sub, `${ptr}.${key}`, errors);
    }
  }
}

// git status --porcelain=v1 -z: `XY <path>\0`, renames/copies add `<orig>\0`.
// Both sides of a rename count as dirty: either appearing undeclared is a
// red flag.
function parseStatusZ(buf) {
  const dirty = new Set();
  const tokens = buf.toString('utf8').split('\0');
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.length < 4) continue;
    const xy = t.slice(0, 2);
    dirty.add(t.slice(3));
    if (xy[0] === 'R' || xy[0] === 'C') {
      i += 1;
      if (tokens[i]) dirty.add(tokens[i]);
    }
  }
  return dirty;
}

function underPrefix(p, base) {
  return p === base || p.startsWith(`${base}/`);
}

// Resolve `rel` under `root` through any symlinked ancestors. A path whose
// real location leaves the checkout is an escape regardless of how it is
// spelled; the deepest EXISTING ancestor is realpathed so a not-yet-created
// file under a symlinked directory is still caught.
function resolvesInsideRoot(root, rel) {
  const rootReal = fs.realpathSync(root);
  let probe = path.resolve(root, rel);
  let remainder = '';
  for (;;) {
    if (fs.existsSync(probe)) break;
    remainder = path.join(path.basename(probe), remainder);
    const parent = path.dirname(probe);
    if (parent === probe) break;
    probe = parent;
  }
  const real = path.join(fs.realpathSync(probe), remainder);
  return real === rootReal || real.startsWith(rootReal + path.sep);
}

// validate(handoffRaw, opts) -> { ok, verdict?, reasons[] }. Pure given its
// inputs; fs is touched only for the symlink check against opts.root.
function validate(raw, opts) {
  const reasons = [];
  const fail = (cls, msg) => reasons.push(`${cls}: ${msg}`);

  if (raw === null) {
    fail(
      'handoff-missing',
      `no handoff at '${opts.handoffPath}' - the model exited without leaving one; a wedged model must be visible, never a silent no-op`
    );
    return { ok: false, reasons };
  }
  if (raw.length > MAX_HANDOFF_BYTES) {
    fail('handoff-oversize', `${raw.length} bytes exceeds the ${MAX_HANDOFF_BYTES}-byte cap`);
    return { ok: false, reasons };
  }
  let handoff;
  try {
    handoff = JSON.parse(raw.toString('utf8'));
  } catch (e) {
    fail('handoff-unparseable', e.message);
    return { ok: false, reasons };
  }
  const schema = JSON.parse(fs.readFileSync(SCHEMA_FILE, 'utf8'));
  if (
    !handoff ||
    typeof handoff !== 'object' ||
    handoff.schema !== schema.properties.schema.const
  ) {
    fail(
      'schema-unknown',
      `expected schema '${schema.properties.schema.const}', got '${handoff && handoff.schema}'`
    );
    return { ok: false, reasons };
  }

  const schemaErrors = [];
  validateNode(handoff, schema, 'handoff', schemaErrors);
  for (const e of schemaErrors) fail('schema-violation', e);

  // Conditional rules the schema subset cannot express.
  const files = Array.isArray(handoff.files) ? handoff.files : [];
  if (handoff.outcome === 'push') {
    if (files.length === 0)
      fail('schema-violation', 'handoff.files: outcome push requires a non-empty files[]');
    if (typeof handoff.commit_message !== 'string' || handoff.commit_message.length === 0)
      fail('schema-violation', 'handoff.commit_message: outcome push requires a commit message');
  }
  if (handoff.outcome === 'escalate' && !(handoff.escalation && handoff.escalation.reason)) {
    fail('schema-violation', 'handoff.escalation.reason: outcome escalate requires a reason');
  }
  const submodules = Array.isArray(handoff.submodules) ? handoff.submodules : [];
  if (submodules.length > 0) {
    // The stage flag, checked before anything about the entries is believed.
    if (!opts.allowSubmodules) {
      fail(
        'submodules-disabled',
        `handoff.submodules: ${submodules.length} submodule change(s) declared while AUTOPILOT_ALLOW_SUBMODULES is not 'true'; refusing the whole round rather than pushing the console half of it`
      );
    }
    // A submodule push only makes sense on a push round: escalate and
    // no-change stage nothing, so the submodule commits would be minted and
    // then stranded with no pointer advance to carry them.
    if (handoff.outcome !== 'push') {
      fail(
        'schema-violation',
        `handoff.submodules: outcome '${handoff.outcome}' never pushes, so submodule work cannot ride on it`
      );
    }
  }
  // block-commit-meta.sh bans attribution trailers repo-wide; refusing them
  // here keeps the harness from minting a commit its own hooks would reject.
  if (
    typeof handoff.commit_message === 'string' &&
    /co-authored-by/i.test(handoff.commit_message)
  ) {
    fail(
      'commit-meta-banned',
      'commit_message carries an attribution trailer (banned repo-wide by block-commit-meta.sh)'
    );
  }
  if (reasons.length > 0) return { ok: false, reasons };

  if (handoff.base_head !== opts.baseHead) {
    fail(
      'base-head-mismatch',
      `handoff built against ${handoff.base_head}, harness checked out ${opts.baseHead}`
    );
    return { ok: false, reasons };
  }

  const dirty = parseStatusZ(opts.statusBuf);

  // The SHAPE rules, shared by console files[] and every submodule's files[].
  // Extracted rather than copied: a submodule whose paths were policed by a
  // second, slightly different copy of these rules is a hole that opens the day
  // one copy is updated and the other is not. Returns the normalized path, or
  // null when it failed (reasons already recorded).
  const checkPathShape = (entry, rootDir, label) => {
    const where = label ? `${label}/${entry}` : entry;
    if (path.posix.isAbsolute(entry) || path.isAbsolute(entry) || /^[A-Za-z]:/.test(entry)) {
      fail('path-absolute', where);
      return null;
    }
    if (entry.includes('\\') || entry.includes('\u0000')) {
      fail('path-traversal', `${where} (backslash or NUL)`);
      return null;
    }
    const norm = path.posix.normalize(entry);
    if (norm !== entry || entry.startsWith('./')) {
      fail('path-not-normalized', `'${where}' is not in normalized repo-relative form`);
      return null;
    }
    if (norm.split('/').includes('..')) {
      fail('path-traversal', where);
      return null;
    }
    if (DENY_GITHUB.some((b) => underPrefix(norm, b))) {
      fail(
        'denylist-github',
        `${where} - workflow-surface changes are never pushed by the harness; escalating with the proposed patch attached as data (03-v2-autonomy.md wall 2)`
      );
      return null;
    }
    if (
      DENY_BLOCKED_PREFIXES.some((b) => underPrefix(norm, b)) ||
      DENY_BLOCKED_EXACT.includes(norm)
    ) {
      fail(
        'denylist-blocked',
        `${where} - agent-config surface; blocked outright, quarantine for inspection as data (wall 4)`
      );
      return null;
    }
    if (!resolvesInsideRoot(rootDir, norm)) {
      fail('path-symlink-escape', `${where} resolves outside ${rootDir}`);
      return null;
    }
    return norm;
  };

  const declared = new Set();
  for (const entry of files) {
    const norm = checkPathShape(entry, opts.root, '');
    if (norm === null) continue;
    if (!dirty.has(norm)) {
      fail('path-not-dirty', `${norm} declared but git status shows no change to it`);
      continue;
    }
    declared.add(norm);
  }

  // Staged-set equality, the other direction: an edit the model did not
  // declare is a red flag, not a rounding error.
  for (const d of dirty) {
    if (!declared.has(d))
      fail('undeclared-dirty', `${d} changed in the tree but is not declared in files[]`);
  }

  // Submodule entries, once the stage flag has already been checked above.
  const seenSubmodules = new Set();
  for (const sm of submodules) {
    if (!sm || typeof sm !== 'object' || typeof sm.path !== 'string') continue; // schema said so already
    if (seenSubmodules.has(sm.path)) {
      fail(
        'submodule-duplicate',
        `${sm.path} appears twice; one entry per submodule, in the order the harness must perform them`
      );
      continue;
    }
    seenSubmodules.add(sm.path);

    const smFiles = Array.isArray(sm.files) ? sm.files : [];
    if (smFiles.length === 0) {
      fail('schema-violation', `handoff.submodules[${sm.path}].files: must not be empty`);
    }
    if (typeof sm.message !== 'string' || sm.message.trim().length === 0) {
      fail('schema-violation', `handoff.submodules[${sm.path}].message: required and non-empty`);
    }
    if (typeof sm.message === 'string' && /co-authored-by/i.test(sm.message)) {
      fail(
        'commit-meta-banned',
        `handoff.submodules[${sm.path}].message carries an attribution trailer (banned repo-wide by block-commit-meta.sh)`
      );
    }

    // THE GITLINK MUST BE DECLARED. A submodule commit is only reachable from
    // console through the pointer, so a round that pushes the submodule
    // without advancing the pointer has published a commit nothing references
    // and left the console PR describing a tree it does not contain.
    if (!declared.has(sm.path)) {
      fail(
        'submodule-gitlink-undeclared',
        `${sm.path} has submodule changes but the gitlink '${sm.path}' is not in the top-level files[]; the pointer advance is a console change and must be declared like one`
      );
    }

    // Paths are relative to the SUBMODULE, so they are resolved against the
    // submodule's own directory. A file naming its way back out of the
    // submodule is the interesting attack, and it fails as a symlink escape
    // or a traversal exactly as it would in console.
    const smRoot = path.join(opts.root, sm.path);
    let smRootUsable = true;
    try {
      smRootUsable = fs.statSync(smRoot).isDirectory();
    } catch {
      smRootUsable = false;
    }
    if (!smRootUsable) {
      fail(
        'submodule-missing',
        `${sm.path} is declared but is not a directory in this checkout; the harness cannot write a submodule it does not have`
      );
      continue;
    }
    for (const entry of smFiles) {
      checkPathShape(entry, smRoot, sm.path);
    }
  }

  if (reasons.length > 0) return { ok: false, reasons };
  return {
    ok: true,
    verdict: {
      verdict: 'ok',
      outcome: handoff.outcome,
      files: [...declared].sort(),
      commit_message: handoff.commit_message || '',
      ledger_line: handoff.ledger_line,
      ruled_out: handoff.ruled_out || [],
      decisions: handoff.decisions || [],
      escalation: handoff.escalation || null,
      submodules: submodules.map((sm) => ({
        path: sm.path,
        files: [...sm.files].sort(),
        message: sm.message,
      })),
    },
    reasons: [],
  };
}

function main(argv) {
  const args = argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--handoff') opts.handoff = args[++i];
    else if (args[i] === '--root') opts.root = args[++i];
    else if (args[i] === '--base-head') opts.baseHead = args[++i];
    else if (args[i] === '--status') opts.status = args[++i];
    else if (args[i] === '--allow-submodules') opts.allowSubmodulesArg = args[++i];
    else {
      process.stderr.write(`validate-handoff: unknown argument '${args[i]}'\n`);
      return 2;
    }
  }
  if (!opts.handoff || !opts.root || !opts.baseHead || !opts.status) {
    process.stderr.write(
      'usage: validate-handoff.cjs --handoff <file> --root <dir> --base-head <sha> --status <file>\n'
    );
    return 2;
  }
  let raw = null;
  try {
    raw = fs.readFileSync(opts.handoff);
  } catch {
    raw = null;
  }
  let statusBuf;
  try {
    statusBuf = fs.readFileSync(opts.status);
  } catch (e) {
    process.stderr.write(
      `ESCALATE: status-capture-missing: cannot read '${opts.status}': ${e.message}\n`
    );
    return 1;
  }
  // Explicit flag beats the ambient environment; both fail closed on anything
  // that is not the literal 'true'.
  const allowSubmodules =
    opts.allowSubmodulesArg !== undefined
      ? opts.allowSubmodulesArg === 'true'
      : process.env.AUTOPILOT_ALLOW_SUBMODULES === 'true';
  const result = validate(raw, {
    handoffPath: opts.handoff,
    root: opts.root,
    baseHead: opts.baseHead,
    statusBuf,
    allowSubmodules,
  });
  if (!result.ok) {
    for (const r of result.reasons) process.stderr.write(`ESCALATE: ${r}\n`);
    process.stderr.write(
      'validate-handoff: handoff REJECTED - the harness must escalate, not push.\n'
    );
    return 1;
  }
  process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
  return 0;
}

if (require.main === module) {
  process.exit(main(process.argv));
}

module.exports = { validate, parseStatusZ, resolvesInsideRoot, main };
