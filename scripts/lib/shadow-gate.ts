/**
 * SHADOW-GATE CORE (W2.2). Run a ported gate beside its bash twin and rule on
 * whether the port kept the verdict.
 *
 * WHY THIS FILE EXISTS. The `.ci` port moves 74 bash quality gates and 131 gate
 * tests into another language. "It looks right" is not evidence, and the
 * failure mode of a bad port is not a crash -- it is SILENCE. A ported gate that
 * finds nothing looks exactly like a clean tree, and the first thing anyone does
 * with a new green gate is trust it. Program verification proof 1 asks for "a
 * committed differential artifact recording exit-code and normalized-finding
 * equality against its bash twin over K distinct trees"; this module is the
 * thing that produces that artifact, and the thing that refuses to produce it
 * when the comparison would not actually prove anything.
 *
 * THE FOUR RULES THAT MAKE THE COMPARISON MEAN SOMETHING, and each of them is a
 * case a naive comparator scores as a PASS:
 *
 *   1. COMPARE THE FINDING SET, NOT THE BYTES. A port is allowed to reword. It
 *      is not allowed to change WHICH things it objects to. Byte comparison
 *      fails on every legitimate port and therefore gets abandoned; set
 *      comparison survives rewording and still catches a dropped finding.
 *
 *   2. BOTH-EMPTY IS A MISMATCH. Two gates that both find nothing have proved
 *      nothing about each other. This is exactly how a port gets blessed while
 *      being blind: run it on a clean tree, watch both sides say nothing, call
 *      it equivalent. `VACUOUS_BOTH_EMPTY` is a refusal, not a pass, and
 *      `EQUIVALENT` therefore REQUIRES a non-empty agreeing finding set. You
 *      cannot prove a port on a tree where the gate has nothing to say.
 *
 *   3. NEW-SIDE-TRUE IS ITS OWN MISMATCH. When the port reports clean and the
 *      bash twin does not, that is the blindness class, and it must not be
 *      filed under the same heading as "the port is noisier than the original".
 *      A reviewer waves the noisy direction through. Nobody should be able to
 *      wave this one through, so it gets its own verdict name.
 *
 *   4. THE LEDGER ONLY RECORDS A CLEAN TREE. A differential taken over a dirty
 *      tree is not reproducible: nobody can re-run it, and the "port" it
 *      credits may include edits that were never committed. `--record` on a
 *      dirty tree is REFUSED (exit 3), always, with no override flag. In this
 *      repository that fires immediately and on purpose -- the tree normally
 *      holds several sessions' uncommitted work, so the ledger row for a port
 *      is produced AFTER the port is committed, not while it is being written.
 *
 * INVARIANT 5: REPETITION ON ONE TREE DOES NOT COUNT. Running the same
 * comparison forty times on one checkout is one observation, not forty. So a
 * tree is identified by CONTENT -- `git rev-parse HEAD^{tree}`, the tree object
 * sha -- and `--assert --k N` counts DISTINCT tree ids. Content-addressing is
 * deliberate over the commit sha: a rebase or an amended message produces a new
 * commit over an identical tree, and that is not new evidence. The gitlink
 * entries for the four submodules are part of the tree object, so a submodule
 * pointer bump does count as a different tree.
 *
 * AND THE HOLE THAT LEAVES, closed by the DISTINCT-EVIDENCE RULE. K distinct
 * tree ids can still be K re-shadings of one observation: touch an unrelated
 * file, get a new tree sha, run the same comparison over the same findings.
 * That is invariant 5 defeated by whitespace. So when K >= 2 the counted rows
 * must also exhibit at least TWO distinct finding fingerprints. Moving the tree
 * without moving the gate's behaviour is not evidence that the gate's behaviour
 * agrees.
 *
 * A TREE THAT EVER DISAGREED STAYS DISAGREEING. `--assert` disqualifies a tree
 * id outright if ANY row recorded against it is non-equivalent, rather than
 * letting a later green row supersede an earlier red one. The tree id is the
 * content of both implementations, so two different verdicts over one tree id
 * means the comparison is NONDETERMINISTIC, which is a worse finding than a
 * plain mismatch. Clearing it requires changing the code, which changes the
 * tree id. There is no run-until-green.
 *
 * WHAT THIS MODULE DOES NOT DO. It does not know which gates exist, does not
 * read the registry, and does not decide when a port is finished. It compares
 * two commands. W4, W7 and W8 supply the pairs.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

// --------------------------------------------------------------------------- Types ---------------------------------------------------------------------------

/** Every way a comparison can end. Exactly one is a pass. */
export type Verdict =
  /** Exit codes equal, finding multisets equal, and BOTH sides found something. */
  | 'EQUIVALENT'
  /** Neither side reported a finding. Proves nothing. See rule 2. */
  | 'VACUOUS_BOTH_EMPTY'
  /** The port says clean, the twin does not. The blindness class. See rule 3. */
  | 'NEW_SIDE_TRUE'
  /** The twin says clean, the port does not. Noise, still a mismatch. */
  | 'NEW_SIDE_NOISY'
  /** Both sides found things, but disagreed on the exit code. */
  | 'MISMATCH_EXIT'
  /** Exit codes agree; the finding multisets do not. */
  | 'MISMATCH_FINDINGS'
  /** One side did not finish inside the timeout. No verdict is possible. */
  | 'ERROR_TIMEOUT'
  /**
   * A side REFUSED to report a verdict -- "VACUOUS INPUT", "Refusing to report a
   * verdict.", "so no verdict is possible", "scanned nothing". This repo's gates
   * have a whole vocabulary for it, and the shape is the trap: a refusal exits
   * NON-ZERO with ZERO findings, so a comparator that only knows about exit
   * codes and finding sets reads two refusals as "both empty, exits agree" and a
   * refusal-vs-clean as an ordinary mismatch. Neither is a statement about
   * equivalence. Measured examples: `check_inline_python.py:211-212`
   * ("VACUOUS INPUT: %s is not a git work tree", exit 1),
   * `check-swallowed-failures.sh:305-316` ("Refusing to report a verdict."),
   * `check_runner_advice.py:916,944` ("so no verdict is possible").
   */
  | 'ERROR_REFUSAL';

/** The one verdict that counts as evidence. */
export const PASS_VERDICT: Verdict = 'EQUIVALENT';

/** One side of the comparison, as invoked. */
export interface SideSpec {
  /** `old` is the bash twin, `new` is the port. Used in messages and the ledger. */
  label: 'old' | 'new';
  /** A shell command line. Run through `bash -c`, never through a merged pipe. */
  cmd: string;
  /** Working directory. Defaults to the repository root. */
  cwd?: string;
  /** Extra environment. Merged over the determinism base; see `buildEnv`. */
  env?: Record<string, string>;
}

/** What one side actually did. stdout and stderr are NEVER merged. */
export interface SideRun {
  label: 'old' | 'new';
  cmd: string;
  exit: number;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  /** Normalized finding lines, in the order first seen. Compared as a multiset. */
  findings: string[];
  /** Output lines classified as chatter. Recorded, never compared. */
  chatter: string[];
  /** Refusal lines. Their presence suspends the comparison entirely. */
  refusals: string[];
  /** sha256 (16 hex) over the sorted findings. Stable across trees. */
  fingerprint: string;
}

/** Knobs for turning raw output into a finding set. */
export interface NormalizeOptions {
  /** Repository root, masked out of finding text as `<repo>`. */
  repoRoot: string;
  /**
   * Extra matcher for finding lines, on top of the built-in severity markers.
   * Supplied by a caller whose gate prints findings this module cannot recognise.
   */
  findingRe?: RegExp;
  /** Lines matching this are chatter even if they look like a finding. */
  chatterRe?: RegExp;
  /** Mask 40-hex object names as `<sha>`. OFF by default; see MASKS. */
  maskSha?: boolean;
}

/** The full record of one comparison. This is what a ledger row is built from. */
export interface Comparison {
  pair: string;
  verdict: Verdict;
  /** True only for EQUIVALENT. */
  ok: boolean;
  old: SideRun;
  new: SideRun;
  /** Findings both sides produced, sorted. Empty unless the multisets agree. */
  agreed: string[];
  /** Findings only the bash twin produced, with multiplicity, sorted. */
  onlyOld: string[];
  /** Findings only the port produced, with multiplicity, sorted. */
  onlyNew: string[];
  /** One line saying what happened, for a human reading a CI log. */
  summary: string;
}

/** How the tree the comparison ran over is identified. */
export interface TreeIdentity {
  /** `git rev-parse HEAD^{tree}`. Content-addressed; this is the K key. */
  id: string;
  /** `git rev-parse HEAD`. Recorded for archaeology, never used as the K key. */
  head: string;
  branch: string;
  /**
   * `git status --porcelain` is empty, IGNORING the ledger file this run is
   * about to append to. See `treeIdentity` for why that one exclusion is not a
   * weakening of rule 4.
   */
  clean: boolean;
  /** Up to 20 `git status --porcelain` lines, so a refusal names its cause. */
  dirty: string[];
}

/** Driver-contract 5c: a port that summarised the prose destroyed the only copy. */
export interface CommentAudit {
  oldBytes: number;
  newBytes: number;
  /** newBytes / oldBytes. Refused below COMMENT_RATIO_FLOOR by assertEquivalent. */
  ratio: number;
  /** Every original line naming a date, run id, sha or issue number. */
  provenance: string[];
}

/** One line of the append-only ledger. */
export interface LedgerRow {
  schema: 'shadow-gate/v1';
  pair: string;
  recordedAt: string;
  tree: TreeIdentity;
  verdict: Verdict;
  old: LedgerSide;
  new: LedgerSide;
  agreed: string[];
  onlyOld: string[];
  onlyNew: string[];
  comments?: CommentAudit;
  /**
   * The normalization options this row was recorded under.
   *
   * WITHOUT THIS A ROW CANNOT BE REPRODUCED FROM THE LEDGER ALONE, and that is
   * not theoretical: `--finding-re`, `--chatter-re` and `--mask-sha` each change
   * which lines count as findings, so they change the verdict. An agent
   * re-recording this estate on 2026-09-06 had to reverse-engineer them by
   * fitting candidates against recorded rows, and got there only because one
   * candidate reproduced a 40-finding set exactly while two others added a
   * spurious line. Evidence you cannot re-run is testimony, not evidence.
   *
   * Optional so every row written before this field stays readable.
   */
  opts?: RowOpts;
}

/** The normalization flags a row was recorded under. Absent means defaults. */
export interface RowOpts {
  findingRe?: string;
  chatterRe?: string;
  maskSha?: boolean;
}

export interface LedgerSide {
  cmd: string;
  exit: number;
  findingCount: number;
  chatterCount: number;
  /** Refusal lines. Non-zero means the row records a suspended comparison. */
  refusalCount: number;
  fingerprint: string;
  durationMs: number;
}

// --------------------------------------------------------------------------- Normalization ---------------------------------------------------------------------------

/**
 * ANSI CSI sequences. Colour is decided by `isatty`, so the same gate emits
 * escapes to a developer's terminal and none into a CI log. That is the
 * TERMINAL's decision, not the gate's verdict, so it is stripped rather than
 * compared. `.ci/scripts/lib/emit-advisory.sh:53-63` sets RED/GREEN/YELLOW to
 * empty under `CI=true` and to escapes otherwise, which is the same fact from
 * the other end.
 */
// BUILT FROM A STRING, not written as a regex literal. The literal form carried a raw ESC byte, which `no-control-regex` flags -- correctly in general, since an unnoticed control character in a pattern is almost always a mistake. Here it is the whole point, so the escape is named rather than embedded and the rule has nothing to object to. A
// scoped eslint-disable would have worked and would have taught the next reader that
// this rule is negotiable.
const ESC = String.fromCharCode(27);
const ANSI = new RegExp(`${ESC}\\[[0-?]*[ -/]*[@-~]`, 'g');

/**
 * The repository's severity markers, and this list is not guesswork:
 *
 *   `✗ `        log_error, stderr           .ci/scripts/lib/common.sh:44
 *   `⚠ `        log_warn, stderr            .ci/scripts/lib/common.sh:40
 *   `::error::` ci_error under CI=true      .ci/scripts/lib/emit-advisory.sh:86
 *   `::warning::` ci_warn under CI=true     .ci/scripts/lib/emit-advisory.sh:87
 *   `ERROR:`    the gate-test helper        .ci/scripts/test/lib/test-helpers.sh:35
 *   `FAIL:`     the gate-test helper        .ci/scripts/test/lib/test-helpers.sh:25
 *   `FAIL  `    the control tally           .ci/scripts/lib/gate-controls.sh:23
 *
 * `common.sh` is the canonical logger -- 48 quality gates source it and none
 * sources `emit-advisory.sh` directly -- so its glyph set is the one that
 * matters. `emit-advisory.sh:70-81` re-defines the same four names only when
 * they are not already in scope, which is the fix for the 2026-09-06 stream-swap
 * incident recorded at `emit-advisory.sh:22-52`.
 *
 * THE PREFIX IS STRIPPED, NOT COMPARED. `ci_error` prints `::error::X` when
 * `CI=true` and `✗ X` otherwise, for the SAME finding. Comparing the prefix
 * would make a gate non-equivalent to itself depending on which machine ran it.
 * The severity survives as a `[error]`/`[warn]` tag on the normalized line, so
 * a port that downgrades an error to a warning is still a mismatch.
 */
const MARKERS: ReadonlyArray<{ re: RegExp; sev: 'error' | 'warn' }> = [
  { re: /^::error(?:\s+[^:]*)?::\s*/, sev: 'error' },
  { re: /^::warning(?:\s+[^:]*)?::\s*/, sev: 'warn' },
  { re: /^[✗✖✘]\s*/, sev: 'error' },
  { re: /^ERROR:\s*/, sev: 'error' },
  { re: /^FAIL:\s*/, sev: 'error' },
  { re: /^FAIL\s\s+/, sev: 'error' },
  { re: /^[⚠]\s*/, sev: 'warn' },
  { re: /^WARN(?:ING)?:\s*/, sev: 'warn' },
];

/**
 * Lines that are progress, not verdict: `→ ` (log_step), `✓ ` (log_info AND
 * log_success -- `common.sh:36` uses `✓` for plain info, so the glyph does NOT
 * mean success), `PASS:`/`TEST:`/`INFO:`, the `ok    ` control tally line
 * (`gate-controls.sh:20`), and the GitHub grouping directives.
 *
 * These are RECORDED in the row's chatter count and never compared, because a
 * port is allowed to reword its banner and a comparator that trips on that gets
 * switched off within a day.
 */
const CHATTER =
  /^(?:[→✓]\s|PASS:|PASS\s\s|TEST:|INFO:|DEBUG:|\[DEBUG\]|ok\s\s+|::notice|::group|::endgroup|::add-mask)/;

/**
 * A gate REFUSING to report a verdict. Vocabulary measured across the tree, not
 * invented: `check_inline_python.py:211` ("VACUOUS INPUT:"),
 * `check-swallowed-failures.sh:307,316,337` ("Refusing to report a verdict.",
 * "This gate scanned nothing, so its verdict would be meaningless."),
 * `check_runner_advice.py:916,944` ("so no verdict is possible"),
 * `check-control-vacuity.sh:145` ("the corpus collapsed to zero"),
 * `check-release-key-canonical.sh:71` ("so NOTHING was verified"),
 * `gate-controls.sh:32` ("the battery is not being executed as written").
 *
 * WHY IT NEEDS ITS OWN CLASS. A refusal exits NON-ZERO with ZERO findings. Two
 * refusals therefore look like "both empty, exits agree" and a naive comparator
 * -- including the vacuity rule on its own -- would file them under
 * VACUOUS_BOTH_EMPTY, which reads as "plant a defect" when the truth is "the
 * gate could not run". A refusal on one side against real findings on the other
 * would read as an ordinary mismatch. Neither message sends anyone to the real
 * problem, so a refusal SUSPENDS the comparison instead of colouring it.
 */
const REFUSAL =
  /(?:VACUOUS INPUT|Refusing to report a verdict|no verdict is possible|verdict would be meaningless|scanned nothing|collapsed to zero|NOTHING was verified|nothing here was verified|is not being executed as written|BASELINE UNREADABLE|CANNOT READ)/i;

/**
 * Indented prose that trails a finding: the advisory continuation lines
 * (`emit-advisory.sh:138-145`) and the caveat paragraphs nearly every green
 * verdict prints. These are ADVICE about the finding, not the finding, and a
 * port is allowed to rewrite advice.
 */
const PROSE =
  /^(?:Fix|Action|Summary|Details|Affected|Patched in|Blind spot|Note|Why|control fired|Remedy|Hint)\b/i;

/**
 * Does this line look like a finding on its own, with no marker? The repo's most
 * common finding shape by a distance is grep-style `<path>:<line>: <message>`
 * (`check-silent-failure-patterns.sh:169`, `check-swallowed-failures.sh:405`,
 * `check_inline_python.py:228`). Recognising it directly is what stops a
 * comparison degenerating into "both sides printed 'Found 3 problems:'" while
 * disagreeing about all three.
 */
const PATH_LINE = /^\S*[A-Za-z0-9_./-]+\.[A-Za-z0-9]+:\d+(?::\d+)?[:\s]/;

/**
 * Volatility masks, applied to finding text in this order.
 *
 * WHY MASK AT ALL, since both sides run in the same environment and a shared
 * volatile value cancels out: the ledger compares FINGERPRINTS ACROSS TREES, and
 * that is where a `/tmp/xyz-8Kd1` or a duration makes two identical observations
 * look distinct and satisfy the distinct-evidence rule with noise.
 *
 * WHAT IS DELIBERATELY NOT MASKED. Object names are not masked by default
 * (`--mask-sha` opts in) because several gates report a sha AS the finding, and
 * masking it would collapse two genuinely different findings into one. Line and
 * column numbers are never masked: a finding that moved to a different line is a
 * different finding, and that is the whole point of the comparison.
 */
const MASKS: ReadonlyArray<[RegExp, string]> = [
  // Absolute temp paths, including the mktemp suffix. Before the repo-root mask, because TMPDIR can legitimately sit inside a worktree.
  [/\/(?:tmp|var\/folders)\/[^\s'"),:]*/g, '<tmp>'],
  // ISO-8601, with or without a zone.
  [/\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g, '<ts>'],
  // Durations. `12ms`, `1.4s`, `3 seconds`.
  [/\b\d+(?:\.\d+)?\s?(?:ms|s|sec|secs|seconds|m|min|mins)\b/g, '<dur>'],
  // Process ids, which appear in shell trap messages.
  [/\bpid\s+\d+\b/gi, 'pid <n>'],
];

const SHA_MASK: [RegExp, string] = [/\b[0-9a-f]{40}\b/g, '<sha>'];

/**
 * Turn one side's two streams into a finding multiset plus chatter.
 *
 * BOTH STREAMS ARE READ, and they are read SEPARATELY into this function rather
 * than merged by the caller. The 2026-09-06 emit-advisory incident was a stream
 * SWAP -- log_info moved from stderr to stdout -- and `2>&1` hides it
 * completely (`.ci/scripts/test/gates/test-emit-advisory.sh:100-102`). Findings
 * are compared as a set that ignores which stream carried them, because the
 * repo's own helpers split error to stderr and warn to stdout; the STREAM
 * question is a different gate's job, and `test-emit-advisory.sh` is that gate.
 */
export function classify(
  stdout: string,
  stderr: string,
  opts: NormalizeOptions
): { findings: string[]; chatter: string[]; refusals: string[] } {
  const findings: string[] = [];
  const chatter: string[] = [];
  const refusals: string[] = [];
  const masks = opts.maskSha ? [...MASKS, SHA_MASK] : MASKS;

  const normalize = (s: string): string => {
    let text = s.trim();
    // Repo root first: it is the longest prefix, and a later mask would otherwise eat a fragment of it and leave an unmatchable tail.
    if (opts.repoRoot) text = text.split(opts.repoRoot).join('<repo>');
    for (const [re, to] of masks) text = text.replace(re, to);
    // Collapse internal whitespace runs. A port that re-indents its continuation lines has not changed which thing it objects to.
    return text.replace(/\s+/g, ' ').trim();
  };

  /**
   * EACH STREAM IS SCANNED SEPARATELY, and that is not an optimisation. The
   * continuation rule below is positional -- "the indented lines under a finding
   * header belong to it" -- and interleaving two independently buffered pipes
   * destroys position. Reading them one after the other would attach stderr's
   * findings to whatever stdout happened to print last.
   *
   * THE CASE THIS GETS WRONG, stated rather than hidden:
   * `check-swallowed-failures.sh:405-406` writes the identifying half of one
   * finding to stderr and its quoted source line to stdout, so per-stream
   * scanning splits that finding in two. The stderr half carries the
   * `<path>:<line>: <var>: <reason>` identity, which is the half that decides
   * equivalence, so the split costs precision rather than soundness.
   */
  for (const stream of [stderr, stdout]) {
    // Severity of the finding the following indented lines belong to, if any.
    let carrying: 'error' | 'warn' | null = null;

    for (const raw of stream.split('\n')) {
      const line = raw.replace(/\r/g, '').replace(ANSI, '').trimEnd();
      const lead = line.trimStart();
      const indented = line !== lead && line.trim() !== '';

      // A blank line ends a finding's continuation block.
      if (line.trim() === '') {
        carrying = null;
        continue;
      }

      if (REFUSAL.test(lead)) {
        refusals.push(normalize(lead));
        carrying = null;
        continue;
      }

      if (opts.chatterRe?.test(lead) || CHATTER.test(lead)) {
        chatter.push(lead.trim());
        carrying = null;
        continue;
      }

      let sev: 'error' | 'warn' | null = null;
      let body = lead;
      for (const m of MARKERS) {
        if (m.re.test(lead)) {
          sev = m.sev;
          body = lead.replace(m.re, '');
          break;
        }
      }

      // An unmarked line still counts when the caller taught the extractor its gate's shape, or when it is the repo's grep-style finding shape.
      if (sev === null && (opts.findingRe?.test(line) || PATH_LINE.test(lead))) {
        sev = 'error';
      }

      // THE CONTINUATION RULE. Findings in this tree are overwhelmingly printed as a marked HEADER ("✗ Found 3 unguarded pipelines:") followed by the three actual findings on unmarked indented lines. Treating only the header as the finding is how a comparator scores two gates as equivalent
      // while they disagree about every instance: both print "Found 3".
      // Indentation varies across gates -- ` %s`, ` %s`, ` - %s`, ` %s` -- so the rule is any indent, and the leading bullet is stripped so the same finding under two different bullet styles matches.
      if (sev === null && indented && carrying !== null && !PROSE.test(lead)) {
        sev = carrying;
        body = lead.replace(/^[-*•]\s+/, '');
      }

      if (sev === null) {
        chatter.push(lead.trim());
        // Prose does not end a continuation block: `emit_advisory` prints ` Fix:` BETWEEN a header and further detail lines.
        if (!(indented && PROSE.test(lead))) carrying = null;
        continue;
      }

      carrying = sev;
      const text = normalize(body);
      if (text === '') continue;
      findings.push(`[${sev}] ${text}`);
    }
  }
  return { findings, chatter, refusals };
}

/** sha256 over the SORTED findings. Order-independent, multiplicity-preserving. */
export function fingerprint(findings: string[]): string {
  return createHash('sha256')
    .update([...findings].sort().join('\n'))
    .digest('hex')
    .slice(0, 16);
}

// --------------------------------------------------------------------------- Execution ---------------------------------------------------------------------------

/**
 * The environment a side runs under: the caller's, plus determinism pins.
 *
 * EXTEND RATHER THAN REPLACE, which is the opposite of what
 * `.ci/rediacc_ci/tests/differential.py` does, and the difference is the
 * subject. That module compares LIBRARY functions, which need almost nothing.
 * This one drives whole gates: they resolve `node`, `git`, `jq` and `python3`
 * through PATH, read `~/.gitconfig`, and several read `GITHUB_*`. A tiny base
 * environment would make most of them fail identically on both sides, which
 * scores as EQUIVALENT while proving nothing -- exactly the vacuity this module
 * exists to refuse.
 *
 * The pins that ARE forced, and why each: LC_ALL/LANG=C because `git ls-files`
 * output compared against a program's own sort diverges under a collating
 * locale, and that is a difference in the harness rather than in the subject;
 * TZ=UTC because a gate that prints a date must print the same one on both
 * sides; COLUMNS because some tools wrap to the terminal width and a rewrap
 * changes the bytes. Colour is NOT pinned: forcing NO_COLOR would take a branch
 * the developer does not take, and the escapes are stripped in normalization
 * anyway.
 */
export function buildEnv(extra?: Record<string, string>): NodeJS.ProcessEnv {
  return {
    ...process.env,
    LC_ALL: 'C',
    LANG: 'C',
    TZ: 'UTC',
    COLUMNS: '200',
    ...(extra ?? {}),
  };
}

/**
 * Run one side. `bash -c` with piped, SEPARATE stdout and stderr.
 *
 * NO SHELL:TRUE. `spawnSync(cmd, { shell: true })` is the same thing with less
 * control over which shell, and this repo's gates are bash, not sh.
 */
export function runSide(spec: SideSpec, opts: NormalizeOptions, timeoutMs: number): SideRun {
  const started = Date.now();
  const r = spawnSync('bash', ['-c', spec.cmd], {
    cwd: spec.cwd ?? opts.repoRoot,
    env: buildEnv(spec.env),
    encoding: 'utf8',
    timeout: timeoutMs,
    maxBuffer: 64 * 1024 * 1024,
  });
  const durationMs = Date.now() - started;
  const stdout = r.stdout ?? '';
  const stderr = r.stderr ?? '';
  const timedOut = r.error !== undefined && (r.error as NodeJS.ErrnoException).code === 'ETIMEDOUT';
  // A signalled child has a null status. Report it as 128+signal, the shell's own convention, rather than as 0 -- which would read as a clean pass.
  const exit = r.status ?? (r.signal ? 128 + signalNumber(r.signal) : 255);
  const { findings, chatter, refusals } = classify(stdout, stderr, opts);
  return {
    label: spec.label,
    cmd: spec.cmd,
    exit,
    stdout,
    stderr,
    durationMs,
    timedOut,
    findings,
    chatter,
    refusals,
    fingerprint: fingerprint(findings),
  };
}

function signalNumber(sig: NodeJS.Signals): number {
  const table: Record<string, number> = {
    SIGHUP: 1,
    SIGINT: 2,
    SIGQUIT: 3,
    SIGKILL: 9,
    SIGTERM: 15,
  };
  return table[sig] ?? 0;
}

// --------------------------------------------------------------------------- The ruling ---------------------------------------------------------------------------

/** Multiset difference: elements of `a` not covered by `b`, with multiplicity. */
function multisetMinus(a: string[], b: string[]): string[] {
  const counts = new Map<string, number>();
  for (const x of b) counts.set(x, (counts.get(x) ?? 0) + 1);
  const out: string[] = [];
  for (const x of a) {
    const n = counts.get(x) ?? 0;
    if (n > 0) counts.set(x, n - 1);
    else out.push(x);
  }
  return out.sort();
}

/**
 * Rule on one pair of runs.
 *
 * THE ORDER OF THE TESTS IS THE CONTRACT, not an implementation detail:
 *
 *   timeout   -> no verdict is possible, so it must not fall through to a
 *                comparison of two truncated outputs.
 *   vacuity   -> BEFORE any equality test, because both-empty-and-both-zero is
 *                precisely the case an equality test scores as EQUIVALENT.
 *                Rule 2. This is the load-bearing line in the file.
 *   new-true  -> BEFORE the exit comparison, so the blindness class is named as
 *                itself rather than filed under MISMATCH_EXIT where a reviewer
 *                reads it as a numeric quibble. Rule 3.
 *   new-noisy -> its mirror, kept separate for the same reason: it is the
 *                direction a reviewer is tempted to wave through.
 *   exit      -> only reached when both sides said something.
 *   findings  -> only reached when the exits already agree.
 *
 * MULTISET, NOT SET. The contract asks for a set; a multiset is strictly
 * stronger and costs nothing. It still ignores ORDER, which is the reason a set
 * was asked for, while refusing to call "three occurrences" equal to "one".
 */
export function decide(pair: string, oldRun: SideRun, newRun: SideRun): Comparison {
  const onlyOld = multisetMinus(oldRun.findings, newRun.findings);
  const onlyNew = multisetMinus(newRun.findings, oldRun.findings);
  const equalFindings = onlyOld.length === 0 && onlyNew.length === 0;
  const oldClean = oldRun.exit === 0 && oldRun.findings.length === 0;
  const newClean = newRun.exit === 0 && newRun.findings.length === 0;

  const mk = (verdict: Verdict, summary: string): Comparison => ({
    pair,
    verdict,
    ok: verdict === PASS_VERDICT,
    old: oldRun,
    new: newRun,
    agreed: verdict === PASS_VERDICT ? [...oldRun.findings].sort() : [],
    onlyOld,
    onlyNew,
    summary,
  });

  if (oldRun.timedOut || newRun.timedOut) {
    const who = [oldRun.timedOut ? 'old' : null, newRun.timedOut ? 'new' : null]
      .filter(Boolean)
      .join(' and ');
    return mk('ERROR_TIMEOUT', `${who} side timed out; no verdict is possible`);
  }

  if (oldRun.refusals.length > 0 || newRun.refusals.length > 0) {
    const who = [
      oldRun.refusals.length ? `old: ${oldRun.refusals[0]}` : null,
      newRun.refusals.length ? `new: ${newRun.refusals[0]}` : null,
    ]
      .filter(Boolean)
      .join(' | ');
    return mk(
      'ERROR_REFUSAL',
      `a side refused to report a verdict, so there is nothing to compare -- ${who}`
    );
  }

  if (oldRun.findings.length === 0 && newRun.findings.length === 0) {
    return mk(
      'VACUOUS_BOTH_EMPTY',
      'neither side reported a finding, so this comparison proves nothing. ' +
        'Either the tree holds no instance of the defect class (plant one) or the ' +
        "finding extractor does not recognise this gate's output (pass --finding-re)."
    );
  }

  if (newClean && !oldClean) {
    return mk(
      'NEW_SIDE_TRUE',
      `the port reported CLEAN while the bash twin reported ${oldRun.findings.length} ` +
        `finding(s) and exit ${oldRun.exit}. This is the blindness class: a port that ` +
        'sees nothing is indistinguishable from a clean tree.'
    );
  }

  if (oldClean && !newClean) {
    return mk(
      'NEW_SIDE_NOISY',
      `the bash twin reported CLEAN while the port reported ${newRun.findings.length} ` +
        `finding(s) and exit ${newRun.exit}.`
    );
  }

  if (oldRun.exit !== newRun.exit) {
    return mk('MISMATCH_EXIT', `exit ${oldRun.exit} (old) vs ${newRun.exit} (new)`);
  }

  if (!equalFindings) {
    return mk(
      'MISMATCH_FINDINGS',
      `exit codes agree at ${oldRun.exit}, but ${onlyOld.length} finding(s) are ` +
        `old-only and ${onlyNew.length} are new-only`
    );
  }

  return mk(
    'EQUIVALENT',
    `exit ${oldRun.exit} on both sides over ${oldRun.findings.length} agreeing finding(s)`
  );
}

/** Run both sides and rule. The one call most consumers want. */
export function shadow(
  pair: string,
  oldCmd: string,
  newCmd: string,
  opts: NormalizeOptions & {
    timeoutMs?: number;
    oldEnv?: Record<string, string>;
    newEnv?: Record<string, string>;
  }
): Comparison {
  const timeout = opts.timeoutMs ?? 300_000;
  const oldRun = runSide({ label: 'old', cmd: oldCmd, env: opts.oldEnv }, opts, timeout);
  const newRun = runSide({ label: 'new', cmd: newCmd, env: opts.newEnv }, opts, timeout);
  return decide(pair, oldRun, newRun);
}

// --------------------------------------------------------------------------- Tree identity ---------------------------------------------------------------------------

function git(repoRoot: string, args: string[]): { out: string; code: number } {
  const r = spawnSync('git', args, { cwd: repoRoot, encoding: 'utf8', env: buildEnv() });
  return { out: (r.stdout ?? '').trim(), code: r.status ?? 1 };
}

/**
 * Identify the tree a comparison ran over.
 *
 * `HEAD^{tree}` and not `HEAD`: the K key must be the CONTENT. The driver
 * contract uses the same idiom for the same reason -- after the git-history
 * rewrite "the check that matters is that a fresh clone's `HEAD^{tree}` still
 * equals what it was before" (CLAUDE.md, Media Assets).
 *
 * CLEANLINESS IS `git status` BEING EMPTY, untracked files included. Not "clean
 * with respect to the paths the comparison touches", which is the weakening
 * everyone reaches for and which cannot be computed anyway: a gate enumerates
 * through `git ls-files`, so an untracked file three directories away is inside
 * its subject.
 *
 * THE ONE EXCLUSION, and it is narrow on purpose. `ignoreRelPaths` carries the
 * ledger file this run is about to append to. Without it the FIRST recorded row
 * makes the tree dirty and every subsequent `--record` is refused because of a
 * file the comparator itself wrote -- which is not rule 4 catching an
 * unreproducible differential, it is the tool tripping over its own output.
 *
 * WHY IT BUYS NO EVIDENCE. The tree id is `HEAD^{tree}`, which contains no
 * untracked files at all, so the ledger's presence cannot change the identity
 * of the tree an observation is attributed to. Recording twice without
 * committing therefore produces TWO ROWS ON ONE TREE ID, which
 * `assertEquivalent` counts as the single observation it is.
 */
export function treeIdentity(repoRoot: string, ignoreRelPaths: string[] = []): TreeIdentity {
  const tree = git(repoRoot, ['rev-parse', 'HEAD^{tree}']);
  const head = git(repoRoot, ['rev-parse', 'HEAD']);
  const branch = git(repoRoot, ['rev-parse', '--abbrev-ref', 'HEAD']);
  // `-uall` and a pathspec exclusion rather than filtering the output as text.
  //
  // THE TRAP THAT FORCED THIS, measured 2026-09-06. `git status --porcelain` COLLAPSES an untracked directory to a single entry: with `.ci/shadow/` the only new thing in the tree, it prints `?? .ci/` -- not the ledger's path. A text filter looking for `.ci/shadow/k.jsonl` therefore matches nothing, the tree reads dirty, and every `--record` after the first is refused because of
  // the file the previous one wrote. Worse, "fixing" that by matching the collapsed prefix would silently excuse every untracked file anywhere under `.ci/`. `-uall` stops the collapse and the pathspec excludes exactly one path, so git does the matching and no prefix is guessed.
  const statusArgs = ['status', '--porcelain', '-uall'];
  if (ignoreRelPaths.length > 0) {
    statusArgs.push('--', '.', ...ignoreRelPaths.map((p) => `:(exclude)${p}`));
  }
  const status = git(repoRoot, statusArgs);
  const dirty = status.out === '' ? [] : status.out.split('\n');
  return {
    id: tree.code === 0 ? tree.out : 'UNKNOWN',
    head: head.code === 0 ? head.out : 'UNKNOWN',
    branch: branch.code === 0 ? branch.out : 'UNKNOWN',
    clean: status.code === 0 && dirty.length === 0,
    dirty: dirty.slice(0, 20),
  };
}

// --------------------------------------------------------------------------- Driver-contract 5c: comment preservation ---------------------------------------------------------------------------

/** Comment bytes in a bash / Python / TypeScript file. Docstrings count. */
export function commentBytes(file: string): number {
  const text = fs.readFileSync(file, 'utf8');
  let total = 0;
  let inBlock = false;
  let inDoc: string | null = null;
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (inDoc !== null) {
      total += line.length + 1;
      if (t.includes(inDoc)) inDoc = null;
      continue;
    }
    if (inBlock) {
      total += line.length + 1;
      if (t.includes('*/')) inBlock = false;
      continue;
    }
    const doc = /^(?:[rbfu]*)("""|''')/.exec(t);
    if (doc) {
      total += line.length + 1;
      const q = doc[1];
      // A one-line docstring opens and closes on the same line.
      if (t.slice(doc[0].length).includes(q)) continue;
      inDoc = q;
      continue;
    }
    if (t.startsWith('/*')) {
      total += line.length + 1;
      if (!t.includes('*/')) inBlock = true;
      continue;
    }
    // `#!` is not a comment, it is an interpreter directive.
    if (t.startsWith('#') && !t.startsWith('#!')) total += line.length + 1;
    else if (t.startsWith('//') || t.startsWith('*')) total += line.length + 1;
  }
  return total;
}

/**
 * Every original line naming a date, a run id, a sha or an issue number.
 *
 * Driver contract 5c states what the ratio CANNOT see: an agent can satisfy a
 * comment-byte ratio by padding with generic prose while dropping the one
 * paragraph that names a dated incident. This list is short, mechanical, and is
 * the part worth a human's eye.
 */
export function provenanceLines(file: string): string[] {
  // THE `\b` USED TO SIT OUTSIDE THE GROUP, and that made the issue-number branch
  // UNREACHABLE. `\b` before `#` is a non-word-to-non-word boundary, so a `#576`
  // preceded by a space never matched, while the date branch (starting with a digit)
  // always did. Driver contract 5c demands that "date, run id, sha or ISSUE NUMBER"
  // survive a port, and this function silently reported none of the issue numbers:
  // check-release-bump-skip.sh names #576 three times and the audit found zero.
  //
  // A tool that under-reports its own subject is worse than no tool, because the port
  // it blesses looks audited. The anchor now lives inside each branch that needs one.
  const pat = /(?:\b20\d{2}-\d{2}-\d{2}\b|#\d{3,}\b|\b[0-9a-f]{7,40}\b|\bCI job \d+|\brun id \d+)/i;
  return fs
    .readFileSync(file, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => /^(?:#|\/\/|\*|"""|''')/.test(l) || l.startsWith('*'))
    .filter((l) => pat.test(l));
}

export function auditComments(oldFile: string, newFile: string): CommentAudit {
  const oldBytes = commentBytes(oldFile);
  const newBytes = commentBytes(newFile);
  return {
    oldBytes,
    newBytes,
    ratio: oldBytes === 0 ? 1 : Number((newBytes / oldBytes).toFixed(4)),
    provenance: provenanceLines(oldFile),
  };
}

// ---------------------------------------------------------------------------
// The ledger
// ---------------------------------------------------------------------------

/** Default ledger home. Tracked, because the artifact is evidence, not cache. */
export const LEDGER_DIR = '.ci/shadow';

/**
 * Driver contract section 5c: a port whose comment bytes fall below this
 * fraction of the original's is refused. One constant, so the number the
 * --record path PRINTS and the number assertEquivalent RULES on cannot drift.
 */
export const COMMENT_RATIO_FLOOR = 0.9;

export function ledgerPath(repoRoot: string, pair: string, override?: string): string {
  if (override) return override;
  // `<pair>.observations.jsonl` FIRST, because that is what every ledger in this repo is actually called. This defaulted to `<pair>.jsonl`, which exists for no pair, so the invocation printed in this tool's own USAGE string reported `0 row(s), 0 distinct clean tree(s)` for ALL FOURTEEN pairs. That reads as "not enough evidence recorded yet" rather than "you are pointing at a file
  // that is not there", so a reviewer following the help text would conclude the whole W7 P2 evidence base was missing. Nothing gated on it and nobody noticed because every real caller passes --ledger.
  const observations = path.join(repoRoot, LEDGER_DIR, `${pair}.observations.jsonl`);
  if (fs.existsSync(observations)) return observations;
  return path.join(repoRoot, LEDGER_DIR, `${pair}.jsonl`);
}

export function toRow(
  cmp: Comparison,
  tree: TreeIdentity,
  comments?: CommentAudit,
  opts?: RowOpts
): LedgerRow {
  const side = (s: SideRun): LedgerSide => ({
    cmd: s.cmd,
    exit: s.exit,
    findingCount: s.findings.length,
    chatterCount: s.chatter.length,
    refusalCount: s.refusals.length,
    fingerprint: s.fingerprint,
    durationMs: s.durationMs,
  });
  return {
    schema: 'shadow-gate/v1',
    pair: cmp.pair,
    recordedAt: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    tree,
    verdict: cmp.verdict,
    old: side(cmp.old),
    new: side(cmp.new),
    agreed: cmp.agreed,
    onlyOld: cmp.onlyOld,
    onlyNew: cmp.onlyNew,
    ...(comments ? { comments } : {}),
    ...(opts && (opts.findingRe || opts.chatterRe || opts.maskSha) ? { opts } : {}),
  };
}

/**
 * Does a command reach OUTSIDE `repoRoot` for the code it runs?
 *
 * THE TREE ID IS A CLAIM ABOUT BOTH IMPLEMENTATIONS, and this is what made that
 * claim false. `--record` verified `--repo` was CLEAN and never checked that the
 * commands read anything inside it, so a row could be recorded while both sides
 * were invoked out of a different checkout entirely. The tree id then names a
 * fixture holding only the SUBJECT, and the row attests to code that tree never
 * contained.
 *
 * That is not hypothetical: w7p2-stagingtag carries three tree ids recorded that
 * way, and because assertEquivalent disqualifies an id UNCONDITIONALLY, they can
 * never be cleared. Re-recording mints a new id and leaves the old one red. Six
 * more ledgers reach their port through an absolute `PYTHONPATH`, which is the
 * same hole staying quiet because those rows happen to agree.
 *
 * Detection is deliberately crude and errs toward refusing: any absolute path in
 * the command that is not under `repoRoot`. It catches both observed shapes, a
 * bare `/abs/other/checkout/...` invocation and `PYTHONPATH=/abs/other/...`, and
 * it cannot be silently defeated by a relative path, which resolves under the
 * repo by definition.
 */
export function reachesOutside(cmd: string, repoRoot: string): string[] {
  const root = path.resolve(repoRoot);
  const out: string[] = [];
  for (const m of cmd.matchAll(/(^|[\s=:"'])(\/[^\s:"';|&)]+)/g)) {
    const abs = m[2];
    if (abs === undefined) continue;
    // System paths are the INTERPRETER, not the code under comparison, so they are
    // exempt. `/tmp` is deliberately NOT on this list even though it looks like it
    // belongs: fixture repos are built under /tmp, so code read from /tmp outside
    // the fixture is precisely the escape this refuses. A redirect to /tmp is
    // caught too, which is a false refusal, and that is the direction to err in:
    // a false refusal costs one edit, while a row recorded through this hole can
    // never be cleared afterward.
    if (/^\/(dev|proc|sys|usr|bin|sbin|lib|etc|opt|var)\b/.test(abs)) continue;
    const rel = path.relative(root, abs);
    if (rel.startsWith('..') || path.isAbsolute(rel)) out.push(abs);
  }
  return [...new Set(out)];
}

/** Why a ledger write was refused, or null when it is allowed. */
export function ledgerRefusal(
  tree: TreeIdentity,
  cmds?: { old: string; new: string; repoRoot: string }
): string | null {
  if (tree.id === 'UNKNOWN') return 'the working directory is not a git repository with a HEAD';
  if (cmds) {
    const escapes = [
      ...reachesOutside(cmds.old, cmds.repoRoot).map((p) => `old: ${p}`),
      ...reachesOutside(cmds.new, cmds.repoRoot).map((p) => `new: ${p}`),
    ];
    if (escapes.length > 0) {
      return (
        'a command reads from OUTSIDE the recorded tree, so the tree id would not ' +
        'describe the code that produced this row. The tree id is the content of BOTH ' +
        'implementations; a row recorded this way attests to code the tree never held, ' +
        'and assertEquivalent can never clear it afterward. Copy both implementations ' +
        'into the fixture and invoke them by relative path.\n  ' +
        escapes.join('\n  ')
      );
    }
  }
  if (!tree.clean) {
    return (
      'the working tree is DIRTY, so this differential is not reproducible and is not ' +
      'evidence. Rule 4: the ledger records a result only from a clean tree. Commit the ' +
      'port and re-run.\n  ' +
      tree.dirty.join('\n  ')
    );
  }
  return null;
}

/** Append one row. Refuses on a dirty tree; there is deliberately no override. */
export function appendLedger(repoRoot: string, row: LedgerRow, override?: string): void {
  const refusal = ledgerRefusal(row.tree, {
    old: row.old.cmd,
    new: row.new.cmd,
    repoRoot,
  });
  if (refusal) throw new Error(refusal);
  const file = ledgerPath(repoRoot, row.pair, override);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(file, `${JSON.stringify(row)}\n`, 'utf8');
}

export function readLedger(repoRoot: string, pair: string, override?: string): LedgerRow[] {
  const file = ledgerPath(repoRoot, pair, override);
  if (!fs.existsSync(file)) return [];
  return fs
    .readFileSync(file, 'utf8')
    .split('\n')
    .filter((l) => l.trim() !== '')
    .map((l) => JSON.parse(l) as LedgerRow);
}

// ---------------------------------------------------------------------------
// K distinct trees
// ---------------------------------------------------------------------------

export interface AssertResult {
  ok: boolean;
  /** Distinct clean tree ids carrying an EQUIVALENT row and no contradicting row. */
  distinctTrees: string[];
  /** Tree ids disqualified because some row against them was not EQUIVALENT. */
  disqualified: Array<{ tree: string; verdict: Verdict }>;
  /** Distinct finding fingerprints across the counted rows. */
  fingerprints: string[];
  reasons: string[];
}

/**
 * Rule on whether a ledger proves equivalence over K distinct trees.
 *
 * Three refusals, and each one closes a way of manufacturing a green:
 *
 *   NOT ENOUGH TREES      -- invariant 5. Forty runs on one checkout is one
 *                            observation. K counts distinct `tree.id`.
 *   A TREE THAT DISAGREED -- a non-equivalent row against a tree id disqualifies
 *                            that id permanently. Since the id IS the content of
 *                            both implementations, a later green row over the
 *                            same id means the comparison is nondeterministic,
 *                            which is worse than the mismatch. There is no
 *                            run-until-green.
 *   ONE OBSERVATION, K SHADES -- the distinct-evidence rule. K tree ids whose
 *                            findings are all identical is one observation
 *                            re-shaded by touching an unrelated file. When
 *                            K >= 2 the counted rows must show at least two
 *                            distinct fingerprints.
 *
 * A dirty row is never counted; `appendLedger` refuses to write one, so its
 * presence would mean a hand-edited ledger, and it is filtered here as well
 * rather than trusted.
 */
export function assertEquivalent(rows: LedgerRow[], k: number): AssertResult {
  const reasons: string[] = [];

  // A ROW WITH NO `tree` AT ALL, which the `tree.clean` filter below cannot see.
  // The comment above anticipates a hand-edited ledger and handles exactly one
  // shape of it -- `clean=false` -- so a row missing the field crashed the whole
  // run with `TypeError: Cannot read properties of undefined (reading 'clean')`
  // and a stack trace naming neither the pair nor the row. Found 2026-09-08 when
  // a DIFFERENT kind of ledger was written into `.ci/shadow/` under the
  // `*.observations.jsonl` name this tool enumerates: the standing sweep reported
  // `RED twin-parity` for a file that was working perfectly, and the message said
  // nothing about which file or why. A malformed row is a finding to report, not
  // an exception to throw.
  const shaped = rows.filter((r) => r && typeof r.tree === 'object' && r.tree !== null);
  if (shaped.length !== rows.length) {
    reasons.push(
      `${rows.length - shaped.length} row(s) carry no \`tree\` object and were ignored; ` +
        'this ledger was hand-edited, truncated, or is not a shadow-pair ledger at all ' +
        '(every file matching .ci/shadow/*.observations.jsonl is read as one)'
    );
  }
  const clean = shaped.filter((r) => r.tree.clean);
  if (clean.length !== shaped.length) {
    reasons.push(
      `${shaped.length - clean.length} row(s) carry tree.clean=false and were ignored; ` +
        'appendLedger cannot write those, so the ledger has been hand-edited'
    );
  }

  const byTree = new Map<string, LedgerRow[]>();
  for (const r of clean) {
    const list = byTree.get(r.tree.id) ?? [];
    list.push(r);
    byTree.set(r.tree.id, list);
  }

  const disqualified: Array<{ tree: string; verdict: Verdict }> = [];
  const counted: LedgerRow[] = [];
  for (const [id, list] of byTree) {
    const bad = list.find((r) => r.verdict !== PASS_VERDICT);
    if (bad) {
      disqualified.push({ tree: id, verdict: bad.verdict });
      continue;
    }
    counted.push(list[list.length - 1]);
  }

  const distinctTrees = counted.map((r) => r.tree.id).sort();
  const fingerprints = [...new Set(counted.map((r) => r.old.fingerprint))].sort();

  if (disqualified.length > 0) {
    for (const d of disqualified) {
      reasons.push(
        `tree ${d.tree.slice(0, 12)} is DISQUALIFIED: a row against it recorded ${d.verdict}. ` +
          'The tree id is the content of both implementations, so this cannot be cleared by ' +
          're-running -- only by changing the code, which changes the tree id.'
      );
    }
  }
  if (distinctTrees.length < k) {
    reasons.push(
      `${distinctTrees.length} distinct tree(s) carry an EQUIVALENT row; ${k} are required. ` +
        'Invariant 5: repetition on one tree is one observation, not many.'
    );
  }
  if (k >= 2 && distinctTrees.length >= k && fingerprints.length < 2) {
    reasons.push(
      `all ${distinctTrees.length} counted tree(s) produced the same finding fingerprint ` +
        `${fingerprints[0] ?? '(none)'}. That is one observation re-shaded, not ${k} of them. ` +
        'At least two distinct finding sets are required.'
    );
  }

  // THE COMMENT FLOOR WAS PRINTED AND NEVER ENFORCED, and the box that claimed
  // otherwise said "closed". Driver contract section 5c states "A port whose
  // comment bytes fall below 90 percent of the original's is refused", every
  // ledger row carries the ratio, and the --record path prints
  // `✗ below the 0.90 floor` when it is short. But assertEquivalent -- the ONLY
  // ruling function -- never read row.comments, so --assert returned 0 with
  // every row below the floor. The word "refused" in 5c described a human.
  //
  // Not masking a live violation today: the worst ratio across all 100 recorded
  // rows is 2.95, comfortably clear. That is exactly why it stayed invisible,
  // and exactly why it is worth closing now rather than after a port pads prose
  // to get past a reviewer who is reading a number nothing checks.
  //
  // Only rows that COUNT are judged. A row against a disqualified tree is
  // already refused above, and failing it twice for a second reason would make
  // the first message harder to act on.
  const countedTrees = new Set(distinctTrees);
  const thin = rows.filter(
    (r) =>
      r.comments !== undefined &&
      r.comments.ratio < COMMENT_RATIO_FLOOR &&
      countedTrees.has(r.tree.id)
  );
  if (thin.length > 0) {
    const worst = thin.reduce((a, b) =>
      (a.comments?.ratio ?? 1) <= (b.comments?.ratio ?? 1) ? a : b
    );
    reasons.push(
      `${thin.length} counted row(s) fall below the ${COMMENT_RATIO_FLOOR} comment-byte floor ` +
        `(driver contract 5c); worst is ratio ${worst.comments?.ratio} on tree ` +
        `${worst.tree.id.slice(0, 12)}. Comment archaeology is the half of a port that ` +
        'cannot be recovered from the code, so a thin port passes its differential and ' +
        'still loses the reason the original existed.'
    );
  }

  return { ok: reasons.length === 0, distinctTrees, disqualified, fingerprints, reasons };
}

// ---------------------------------------------------------------------------
// Selftest: the comparator must be able to FIRE, and must be able to be QUIET
// ---------------------------------------------------------------------------

/**
 * A comparator that cannot report a mismatch launders every port that follows,
 * and a comparator that reports one for everything gets switched off on day two.
 * So the selftest proves BOTH directions, over real subprocesses, and it plants
 * a real divergence rather than asserting against a hand-built object.
 */
function selftest(repoRoot: string): number {
  const opts: NormalizeOptions = { repoRoot };
  let failures = 0;
  const ck = (name: string, cond: boolean, detail?: unknown): void => {
    if (cond) {
      console.log(`PASS: ${name}`);
    } else {
      failures += 1;
      console.error(`FAIL: ${name}`);
      if (detail !== undefined) console.error(`      ${JSON.stringify(detail)}`);
    }
  };

  // EVERY fixture path in this selftest is ASSEMBLED at runtime rather than written as a literal, and that is not a dodge of gate-test:gate-paths-exist. That gate reads a path-shaped literal inside a gate script as a real path constant and reds when the file does not exist, which is the right rule: such a constant is usually a rename nobody finished. These name nothing on disk ON
  // PURPOSE, because the comparator under test is pure string handling and never opens them. Same treatment and same reasoning as check-em-dash-surfaces.ts and check-typecheck-scope-coverage.ts, which each hit this.
  const fx = (stem: string): string => `${'packages'}/${stem}.ts`;

  // Two implementations of one gate. They differ in language, in the order they report, in their banner text, and in which stream each finding lands on -- every axis a port is ALLOWED to differ on.
  const twinBash = `
    echo "→ scanning 3 files"
    echo "✗ ${fx('a')}:14 missing BLOCKER reason" >&2
    echo "⚠ ${fx('b')}:2 stale allowlist entry"
    echo "✓ done"
  `;
  const twinPortEquivalent = `
    echo "⚠ ${fx('b')}:2 stale allowlist entry" >&2
    echo "→ 3 files inspected in 42ms"
    echo "::error::${fx('a')}:14 missing BLOCKER reason"
  `;

  /**
   * Append an explicit exit to a multi-line script.
   *
   * WHY THIS IS A FUNCTION AND NOT `${script}; exit 1`. That concatenation was
   * the first version and it is a real trap, caught by exactly one of the cases
   * below. The templates above end with a NEWLINE and indentation, so an
   * appended `; exit 1` lands at the start of its own line and bash rejects it
   * -- `syntax error near unexpected token ';'` -- AFTER having already run
   * every preceding line. The side then exits 2 with all of its findings
   * intact, which is close enough to the intended shape that the NEW_SIDE_TRUE
   * and NEW_SIDE_NOISY cases still reported the verdict they were asserting,
   * for the wrong reason. Only the exit-code case noticed, and only because
   * 2-vs-2 is equal where 1-vs-2 is not. A helper that owns the newline removes
   * the whole class.
   */
  const exitWith = (script: string, code: number): string => `${script}\nexit ${code}\n`;

  const control = shadow('selftest-control', twinBash, twinPortEquivalent, opts);
  ck(
    'CONTROL: a genuine match is EQUIVALENT across language, order, stream and marker',
    control.verdict === 'EQUIVALENT' && control.agreed.length === 2,
    {
      verdict: control.verdict,
      agreed: control.agreed,
      onlyOld: control.onlyOld,
      onlyNew: control.onlyNew,
    }
  );

  // THE PLANT. One finding removed from the port. Nothing else changes.
  const twinPortBlind = `
    echo "→ 3 files inspected"
    echo "::error::${fx('a')}:14 missing BLOCKER reason"
  `;
  const planted = shadow('selftest-planted', twinBash, twinPortBlind, opts);
  ck(
    'PLANT: a dropped finding is MISMATCH_FINDINGS and is named in onlyOld',
    planted.verdict === 'MISMATCH_FINDINGS' &&
      planted.onlyOld.length === 1 &&
      planted.onlyOld[0].includes('stale allowlist entry') &&
      planted.onlyNew.length === 0,
    { verdict: planted.verdict, onlyOld: planted.onlyOld, onlyNew: planted.onlyNew }
  );

  // Rule 2. Both silent, both exit 0. An equality test calls this a pass.
  const vacuous = shadow('selftest-vacuous', 'echo "✓ nothing to report"', 'echo "→ clean"', opts);
  ck(
    'RULE 2: both-empty is VACUOUS_BOTH_EMPTY, never EQUIVALENT',
    vacuous.verdict === 'VACUOUS_BOTH_EMPTY' && !vacuous.ok,
    vacuous.verdict
  );

  // Rule 3. The port sees nothing where the twin fails. The blindness class.
  const blind = shadow('selftest-blind', exitWith(twinBash, 1), 'echo "✓ clean"; exit 0', opts);
  ck(
    'RULE 3: a port that reports clean while the twin fails is NEW_SIDE_TRUE',
    blind.verdict === 'NEW_SIDE_TRUE' && !blind.ok,
    blind.verdict
  );

  const noisy = shadow('selftest-noisy', 'echo "✓ clean"; exit 0', exitWith(twinBash, 1), opts);
  ck(
    'MIRROR: a port that objects where the twin is clean is NEW_SIDE_NOISY, not EQUIVALENT',
    noisy.verdict === 'NEW_SIDE_NOISY' && !noisy.ok,
    noisy.verdict
  );

  const exits = shadow(
    'selftest-exit',
    exitWith(twinBash, 1),
    exitWith(twinPortEquivalent, 2),
    opts
  );
  ck(
    'EXIT: identical findings under different exit codes is MISMATCH_EXIT',
    exits.verdict === 'MISMATCH_EXIT' && exits.onlyOld.length === 0,
    exits.verdict
  );

  // A crash is not a clean pass. Exit 127 with a shell diagnostic on stderr.
  const crash = shadow('selftest-crash', exitWith(twinBash, 1), 'definitely-not-a-command', opts);
  ck('CRASH: a port that does not exist is not EQUIVALENT', !crash.ok && crash.new.exit === 127, {
    verdict: crash.verdict,
    exit: crash.new.exit,
  });

  // Chatter must not be able to carry a verdict. If the banner counted as a finding, the vacuity rule would be defeated by every gate that prints one.
  const banner = shadow('selftest-banner', 'echo "→ 10 files"', 'echo "→ 11 files"', opts);
  ck(
    'CHATTER: differing progress lines do not manufacture a finding',
    banner.verdict === 'VACUOUS_BOTH_EMPTY' && banner.old.chatter.length === 1,
    { verdict: banner.verdict, chatter: banner.old.chatter }
  );

  // Multiplicity. A set would call these equal.
  const dup = shadow(
    'selftest-multiplicity',
    'echo "✗ x.ts:1 bad" >&2; echo "✗ x.ts:1 bad" >&2; exit 1',
    'echo "✗ x.ts:1 bad" >&2; exit 1',
    opts
  );
  ck(
    'MULTISET: two occurrences are not equal to one',
    dup.verdict === 'MISMATCH_FINDINGS' && dup.onlyOld.length === 1,
    { verdict: dup.verdict, onlyOld: dup.onlyOld }
  );

  // A LEDGER ROW THAT IS NOT A LEDGER ROW. Anything matching `.ci/shadow/*.observations.jsonl` is read as a shadow-pair ledger, so a
  // foreign or truncated file lands here; before 2026-09-08 it threw a raw
  // TypeError naming neither the pair nor the row.
  const malformed = assertEquivalent([{ subject: 'x', agreed: true } as unknown as LedgerRow], 1);
  ck(
    'MALFORMED: a row with no `tree` is REPORTED, not thrown',
    malformed.ok === false && malformed.reasons.some((r) => r.includes('no `tree` object')),
    { ok: malformed.ok, reasons: malformed.reasons }
  );
  const mixed = assertEquivalent(
    [{ subject: 'x', agreed: true } as unknown as LedgerRow, ...([] as LedgerRow[])],
    1
  );
  ck('MALFORMED: and the run continues to a verdict', typeof mixed.ok === 'boolean', {
    ok: mixed.ok,
  });

  // Severity is part of the finding. A port that downgrades error to warning has changed the verdict even though the text is identical.
  const sev = shadow(
    'selftest-severity',
    'echo "✗ a.ts:1 thing" >&2; exit 1',
    'echo "⚠ a.ts:1 thing"; exit 1',
    opts
  );
  ck('SEVERITY: error downgraded to warning is a mismatch', sev.verdict === 'MISMATCH_FINDINGS', {
    verdict: sev.verdict,
    onlyOld: sev.onlyOld,
    onlyNew: sev.onlyNew,
  });

  // Refusals. A gate that could not run says so in a documented vocabulary and exits NON-ZERO with ZERO findings, which is the exact shape the vacuity rule would otherwise mislabel.
  const bothRefuse = shadow(
    'selftest-refusal',
    'echo "VACUOUS INPUT: /x is not a git work tree" >&2; exit 1',
    'echo "✗ this gate scanned nothing, so its verdict would be meaningless" >&2; exit 1',
    opts
  );
  ck(
    'REFUSAL: two gates that refused to report are ERROR_REFUSAL, not VACUOUS_BOTH_EMPTY',
    bothRefuse.verdict === 'ERROR_REFUSAL' && !bothRefuse.ok,
    { verdict: bothRefuse.verdict, old: bothRefuse.old.refusals, new: bothRefuse.new.refusals }
  );
  const oneRefuses = shadow(
    'selftest-refusal-one',
    exitWith(twinBash, 1),
    'echo "Refusing to report a verdict." >&2; exit 1',
    opts
  );
  ck(
    'REFUSAL: one side refusing suspends the comparison rather than reading as a mismatch',
    oneRefuses.verdict === 'ERROR_REFUSAL',
    oneRefuses.verdict
  );

  // The continuation rule. Both sides say "Found 2", and they disagree about
  // both. A header-only comparator calls this EQUIVALENT; it is the single most
  // likely way this module could launder a port, because the header is the only line carrying a severity marker.
  const contOld =
    `echo "✗ Found 2 problem(s):" >&2; echo "    ${fx('a')}:3: bad thing" >&2; ` +
    `echo "    ${fx('b')}:9: other thing" >&2; exit 1`;
  const contNew =
    `echo "✗ Found 2 problem(s):" >&2; echo "  - ${fx('a')}:3: bad thing" >&2; ` +
    `echo "  - ${fx('c')}:9: other thing" >&2; exit 1`;
  const cont = shadow('selftest-continuation', contOld, contNew, opts);
  ck(
    'CONTINUATION: indented findings under one header are compared individually',
    cont.verdict === 'MISMATCH_FINDINGS' &&
      cont.onlyOld.some((f) => f.includes(`${fx('b')}:9`)) &&
      cont.onlyNew.some((f) => f.includes(`${fx('c')}:9`)),
    { verdict: cont.verdict, onlyOld: cont.onlyOld, onlyNew: cont.onlyNew }
  );
  const contMatch = shadow(
    'selftest-continuation-ok',
    contOld,
    contOld.replace(/    /g, '  - '),
    opts
  );
  ck(
    'CONTINUATION CONTROL: the same findings under a different bullet style still match',
    contMatch.verdict === 'EQUIVALENT' && contMatch.agreed.length === 3,
    { verdict: contMatch.verdict, agreed: contMatch.agreed }
  );

  // Trailing advice is not a finding. A port is allowed to rewrite its Fix line.
  const advice = shadow(
    'selftest-prose',
    'echo "✗ a.ts:1 thing" >&2; echo "  Fix: do the old thing" >&2; exit 1',
    'echo "✗ a.ts:1 thing" >&2; echo "  Fix: do the completely rewritten thing" >&2; exit 1',
    opts
  );
  ck(
    'PROSE: a reworded Fix: line does not manufacture a mismatch',
    advice.verdict === 'EQUIVALENT' && advice.agreed.length === 1,
    { verdict: advice.verdict, agreed: advice.agreed, onlyNew: advice.onlyNew }
  );

  // Volatility. Same finding, different tmp dir and different duration.
  const volatile1 = 'echo "✗ /tmp/build-a1b2/x.ts:1 broken after 41ms" >&2; exit 1';
  const volatile2 = 'echo "✗ /tmp/build-z9y8/x.ts:1 broken after 812ms" >&2; exit 1';
  const vol = shadow('selftest-volatility', volatile1, volatile2, opts);
  ck(
    'MASKS: a temp path and a duration are environment, not verdict',
    vol.verdict === 'EQUIVALENT',
    { verdict: vol.verdict, onlyOld: vol.onlyOld, onlyNew: vol.onlyNew }
  );

  // --- K distinct trees -----------------------------------------------------
  const row = (tree: string, verdict: Verdict, fp: string): LedgerRow => ({
    schema: 'shadow-gate/v1',
    pair: 'p',
    recordedAt: '2026-09-06T00:00:00Z',
    tree: { id: tree, head: `h-${tree}`, branch: 'b', clean: true, dirty: [] },
    verdict,
    old: {
      cmd: 'o',
      exit: 1,
      findingCount: 1,
      chatterCount: 0,
      refusalCount: 0,
      fingerprint: fp,
      durationMs: 1,
    },
    new: {
      cmd: 'n',
      exit: 1,
      findingCount: 1,
      chatterCount: 0,
      refusalCount: 0,
      fingerprint: fp,
      durationMs: 1,
    },
    agreed: ['[error] x'],
    onlyOld: [],
    onlyNew: [],
  });

  const oneTreeThrice = assertEquivalent(
    [row('t1', 'EQUIVALENT', 'f1'), row('t1', 'EQUIVALENT', 'f1'), row('t1', 'EQUIVALENT', 'f1')],
    3
  );
  ck(
    'INVARIANT 5: three runs on ONE tree do not satisfy K=3',
    !oneTreeThrice.ok && oneTreeThrice.distinctTrees.length === 1,
    oneTreeThrice.reasons
  );

  const threeShades = assertEquivalent(
    [row('t1', 'EQUIVALENT', 'f1'), row('t2', 'EQUIVALENT', 'f1'), row('t3', 'EQUIVALENT', 'f1')],
    3
  );
  ck(
    'DISTINCT EVIDENCE: three trees with one finding set is one observation re-shaded',
    !threeShades.ok && threeShades.reasons.some((r) => r.includes('re-shaded')),
    threeShades.reasons
  );

  const threeReal = assertEquivalent(
    [row('t1', 'EQUIVALENT', 'f1'), row('t2', 'EQUIVALENT', 'f2'), row('t3', 'EQUIVALENT', 'f3')],
    3
  );
  ck('CONTROL: three trees with three finding sets satisfy K=3', threeReal.ok, threeReal.reasons);

  const poisoned = assertEquivalent(
    [
      row('t1', 'EQUIVALENT', 'f1'),
      row('t2', 'MISMATCH_FINDINGS', 'f2'),
      row('t2', 'EQUIVALENT', 'f2'),
      row('t3', 'EQUIVALENT', 'f3'),
    ],
    3
  );
  ck(
    'NO RUN-UNTIL-GREEN: a later EQUIVALENT cannot clear an earlier mismatch on the same tree',
    !poisoned.ok && poisoned.disqualified.some((d) => d.tree === 't2'),
    poisoned.reasons
  );

  const vacuousRow = { ...row('t9', 'VACUOUS_BOTH_EMPTY', 'f0') };
  const vacuousCounted = assertEquivalent([vacuousRow], 1);
  ck(
    'A VACUOUS row is not evidence and does not count toward K',
    !vacuousCounted.ok && vacuousCounted.distinctTrees.length === 0,
    vacuousCounted.reasons
  );

  // --- Rule 4: the ledger refuses a dirty tree ------------------------------
  const dirtyTree: TreeIdentity = {
    id: 'tD',
    head: 'hD',
    branch: 'b',
    clean: false,
    dirty: [' M scripts/lib/shadow-gate.ts'],
  };
  ck(
    'RULE 4: a dirty tree is refused by name',
    (ledgerRefusal(dirtyTree) ?? '').includes('DIRTY'),
    ledgerRefusal(dirtyTree)
  );
  ck(
    'RULE 4 CONTROL: a clean tree is not refused',
    ledgerRefusal(row('tC', 'EQUIVALENT', 'f').tree) === null
  );

  // PROVENANCE, every branch, both directions. The issue-number branch was UNREACHABLE until 2026-09-06 -- `\b` before `#` is non-word-to-non-word, so `#576` never matched
  // while dates always did. Contract 5c names issue numbers explicitly, so the audit was
  // under-reporting its own subject and every port it blessed looked audited.
  const provDir = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'sg-prov-'));
  const provFile = path.join(provDir, 'p.sh');
  const PROV: [string, boolean][] = [
    ['# see #576 for the merge', true],
    ['# on 2026-08-26 we saw', true],
    ['# run id 12345678', true],
    ['# CI job 100870135489', true],
    ['# a1b2c3d4e5f commit', true],
    ['# ordinary prose with no provenance', false],
    ['# issue #12 is too short to be an id', false],
  ];
  for (const [line, want] of PROV) {
    fs.writeFileSync(provFile, `${line}\n`);
    ck(
      `provenance ${want ? 'matches' : 'CONTROL: ignores'}: ${line.slice(0, 44)}`,
      provenanceLines(provFile).length > 0 === want
    );
  }
  fs.rmSync(provDir, { recursive: true, force: true });

  console.log(
    failures === 0 ? '\nselftest: all checks passed' : `\nselftest: ${failures} check(s) failed`
  );
  return failures === 0 ? 0 : 1;
}

// --------------------------------------------------------------------------- CLI ---------------------------------------------------------------------------

const USAGE = `shadow-gate -- compare a ported gate against its bash twin

  Observe (never writes):
    tsx scripts/lib/shadow-gate.ts --pair <id> --old '<cmd>' --new '<cmd>' [--json]

  Record one observation into .ci/shadow/<pair>.jsonl (REFUSES a dirty tree):
    ... --record [--old-file <path> --new-file <path>]

  Rule on the accumulated ledger:
    tsx scripts/lib/shadow-gate.ts --pair <id> --assert --k <N>

  Prove the comparator can fire and can be quiet:
    tsx scripts/lib/shadow-gate.ts --selftest

  Options:
    --finding-re <re>   extra matcher for finding lines this gate emits
    --chatter-re <re>   lines to treat as progress even if they look like findings
    --mask-sha          mask 40-hex object names (off: some gates report a sha)
    --timeout-ms <n>    per side, default 300000
    --ledger <path>     override the ledger file
    --repo <path>       override the repository root

  Exit: 0 equivalent / assertion holds, 1 mismatch or assertion fails,
        2 usage error, 3 ledger write refused (dirty tree).`;

function arg(argv: string[], name: string): string | undefined {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : undefined;
}

export function main(argv: string[]): number {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(USAGE);
    return 0;
  }
  const repoRoot =
    arg(argv, '--repo') ??
    (() => {
      const r = spawnSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' });
      return (r.stdout ?? '').trim() || process.cwd();
    })();

  if (argv.includes('--selftest')) return selftest(repoRoot);

  const pair = arg(argv, '--pair');
  if (!pair) {
    console.error('shadow-gate: --pair <id> is required\n');
    console.error(USAGE);
    return 2;
  }

  if (argv.includes('--assert')) {
    const k = Number(arg(argv, '--k') ?? '1');
    if (!Number.isInteger(k) || k < 1) {
      console.error('shadow-gate: --k must be a positive integer');
      return 2;
    }
    // A LEDGER THAT DOES NOT EXIST IS NOT AN UNDER-RECORDED ONE. readLedger returns [] for a missing path, so a typo'd --pair used to print `0 row(s), 0 distinct clean tree(s)` and `5 are required`, which reads as "keep recording" rather than "you are pointing at nothing". The default name is `<pair>.jsonl` while every real ledger here is `<pair>.observations.jsonl`, so this is
    // the EASY typo to make and it was made: an agent's first run of all four asserts reported four under-recorded pairs that were in fact four wrong filenames.
    const ledgerFile = ledgerPath(repoRoot, pair, arg(argv, '--ledger'));
    if (!fs.existsSync(ledgerFile)) {
      console.error(`✗ ${pair}: no ledger at ${path.relative(repoRoot, ledgerFile)}`);
      console.error('  This is a MISSING FILE, not an empty one. Nothing was compared, so');
      console.error('  the absence of a verdict here is not evidence of anything.');
      const near = fs.existsSync(path.join(repoRoot, LEDGER_DIR))
        ? fs
            .readdirSync(path.join(repoRoot, LEDGER_DIR))
            .filter((f) => f.startsWith(pair) || f.includes(pair))
        : [];
      if (near.length > 0) {
        console.error(`  Did you mean one of: ${near.join(', ')}`);
      }
      return 2;
    }
    const rows = readLedger(repoRoot, pair, arg(argv, '--ledger'));
    const res = assertEquivalent(rows, k);
    console.log(
      `shadow-gate assert ${pair}: ${rows.length} row(s), ${res.distinctTrees.length} distinct clean tree(s), ${res.fingerprints.length} distinct finding set(s)`
    );
    for (const t of res.distinctTrees) console.log(`  tree ${t.slice(0, 12)}`);
    for (const r of res.reasons) console.error(`✗ ${r}`);
    console.log(
      res.ok
        ? `✓ ${pair}: equivalence holds over ${res.distinctTrees.length} distinct trees`
        : `✗ ${pair}: equivalence NOT established`
    );
    return res.ok ? 0 : 1;
  }

  const oldCmd = arg(argv, '--old');
  const newCmd = arg(argv, '--new');
  if (!oldCmd || !newCmd) {
    console.error('shadow-gate: --old and --new are both required\n');
    console.error(USAGE);
    return 2;
  }

  const findingRe = arg(argv, '--finding-re');
  const chatterRe = arg(argv, '--chatter-re');
  const opts: NormalizeOptions & { timeoutMs: number } = {
    repoRoot,
    maskSha: argv.includes('--mask-sha'),
    timeoutMs: Number(arg(argv, '--timeout-ms') ?? '300000'),
    ...(findingRe ? { findingRe: new RegExp(findingRe) } : {}),
    ...(chatterRe ? { chatterRe: new RegExp(chatterRe) } : {}),
  };

  // Recorded into the row VERBATIM as the operator typed them, not as compiled RegExp objects, so the ledger carries something a reader can paste back into a command line and re-run.
  const rowOpts: RowOpts = {
    ...(findingRe ? { findingRe } : {}),
    ...(chatterRe ? { chatterRe } : {}),
    ...(argv.includes('--mask-sha') ? { maskSha: true } : {}),
  };

  const cmp = shadow(pair, oldCmd, newCmd, opts);

  const oldFile = arg(argv, '--old-file');
  const newFile = arg(argv, '--new-file');
  const comments = oldFile && newFile ? auditComments(oldFile, newFile) : undefined;

  const ledgerFile = ledgerPath(repoRoot, pair, arg(argv, '--ledger'));
  const ledgerRel = path.relative(repoRoot, ledgerFile);
  const tree = treeIdentity(repoRoot, ledgerRel.startsWith('..') ? [] : [ledgerRel]);

  if (argv.includes('--json')) {
    console.log(JSON.stringify(toRow(cmp, tree, comments, rowOpts), null, 2));
  } else {
    const icon = cmp.ok ? '✓' : '✗';
    console.log(`${icon} ${pair}: ${cmp.verdict} -- ${cmp.summary}`);
    console.log(
      `  old  exit=${cmp.old.exit} findings=${cmp.old.findings.length} chatter=${cmp.old.chatter.length} fp=${cmp.old.fingerprint} ${cmp.old.durationMs}ms`
    );
    console.log(
      `  new  exit=${cmp.new.exit} findings=${cmp.new.findings.length} chatter=${cmp.new.chatter.length} fp=${cmp.new.fingerprint} ${cmp.new.durationMs}ms`
    );
    for (const r of cmp.old.refusals) console.log(`  refusal-old  ${r}`);
    for (const r of cmp.new.refusals) console.log(`  refusal-new  ${r}`);
    for (const f of cmp.onlyOld) console.log(`  only-old  ${f}`);
    for (const f of cmp.onlyNew) console.log(`  only-new  ${f}`);
    if (comments) {
      console.log(
        `  comments  old=${comments.oldBytes}B new=${comments.newBytes}B ratio=${comments.ratio}${comments.ratio < COMMENT_RATIO_FLOOR ? '  ✗ below the 0.90 floor (driver contract 5c)' : ''}`
      );
      for (const p of comments.provenance) console.log(`  provenance  ${p}`);
    }
  }

  if (argv.includes('--record')) {
    // The commands are passed HERE as well as inside appendLedger, because this preflight is the message the operator actually reads. Without them the escape check ran only in the library and the CLI reported whichever other refusal happened to come first, which on a shared checkout is always the dirty-tree one.
    const refusal = ledgerRefusal(tree, { old: oldCmd, new: newCmd, repoRoot });
    if (refusal) {
      console.error(`✗ ${pair}: ledger write REFUSED -- ${refusal}`);
      return 3;
    }
    appendLedger(repoRoot, toRow(cmp, tree, comments, rowOpts), ledgerFile);
    console.log(`  recorded ${cmp.verdict} for tree ${tree.id.slice(0, 12)} in ${ledgerRel}`);
  }

  return cmp.ok ? 0 : 1;
}

// `import.meta.url` under tsx is the file URL; process.argv[1] is the path.
const invoked = process.argv[1] && import.meta.url === `file://${path.resolve(process.argv[1])}`;
if (invoked) process.exit(main(process.argv.slice(2)));
