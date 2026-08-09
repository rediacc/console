// Post (and keep current) the label guide on every PR.
//
// WHY THIS EXISTS. The repo carries 26 labels, and several of them are kill
// switches whose effect is invisible unless you already know it exists:
// `full-ci` forces a full round past the scope engine's skips, `no-cancel-push`
// disarms the watchdog, `autopilot-blocked` latches the babysit loop off,
// `rollback` blocks stable promotion. Nobody remembers those, and there is
// nowhere on a PR that says what they do. So each PR gets one comment
// explaining them, rendered from .github/labels.yml.
//
// NOT ALL 26. An entry may carry `guide: false`, and 14 do: GitHub's stock
// defaults, bot-applied labels, and the three with zero consumers in code. The
// complaint that produced this comment was that the roster is too long to
// remember, so listing `duplicate` and `good first issue` would recreate the
// problem it solves. Those still have to be DECLARED -- the inventory gate
// reconciles the whole file against the live repo -- they are just not listed.
// Absent means true, so a new label is visible unless someone opts it out.
//
// WHY IT IS RENDERED, NEVER HAND-WRITTEN. .github/labels.yml is already the
// single source of truth (check:ci-label-refs enforces code -> declaration,
// check:ci-label-inventory enforces declaration <-> the live repo). A guide
// typed by hand becomes a fourth, rotting copy the moment a label changes. This
// module makes the comment a projection of that file, so it cannot disagree
// with it for longer than one CI run.
//
// IDEMPOTENCE IS THE WHOLE DESIGN. A PR gets a CI run per push; a guide posted
// per run would bury the conversation. So: find the existing guide by an HTML
// marker, and write ONLY when the rendered body actually differs. A rerun on an
// unchanged tree performs zero API writes -- see test-label-guide-comment.sh's
// no-op case, which asserts an empty write trace rather than merely asserting
// "one comment exists".
//
// Env:
//   LABEL_GUIDE_LABELS_FILE - test seam; defaults to the repo's .github/labels.yml
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/label-guide-comment.cjs')({github, context, core})

const fs = require('node:fs');
const path = require('node:path');

// The comment's identity. It must be the FIRST bytes of the body so a body
// prefix test is enough to find it -- a marker buried mid-body would also match
// a human quoting this comment in a reply.
const MARKER = '<!-- rediacc:label-guide -->';

const DEFAULT_LABELS_FILE = path.join(__dirname, '..', '..', '..', '.github', 'labels.yml');

// ANTI-VACUITY FLOORS. Strict parsing (below) rejects malformed lines, but it
// cannot notice a file that was TRUNCATED to something still well-formed. A
// guide listing one label is not a guide, so refuse rather than render it.
//
// TWO floors, because there are two ways to end up with an empty guide. The
// second one appeared with `guide: false`: a parser change that mis-read the
// field would mark every entry hidden, and MIN_LABELS would still be satisfied
// by the full declaration set while the rendered table came out empty. So the
// VISIBLE set carries its own floor, checked at render time.
const MIN_LABELS = 2;
const MIN_GUIDE_LABELS = 2;

// Parse .github/labels.yml without a YAML dependency.
//
// DELIBERATELY STRICT. The tempting version is a `grep`-shaped reader that
// picks out the lines it recognises and ignores everything else -- and that
// version degrades SILENTLY: a reindent, a quoting change, or a `- name` on a
// continuation line simply yields fewer labels, and a short table looks like a
// perfectly good table. So every non-blank, non-comment line must match one of
// the two shapes below or this throws. The file is ours and its shape is
// enforced by review; a surprise there is a bug worth stopping on.
const parseLabels = (text, source) => {
  const bad = (line, lineNo, why) => {
    throw new Error(
      `${source}:${lineNo}: ${why} -- refusing to render a partial label guide from a file this reader does not fully understand. Line was: ${JSON.stringify(line)}`
    );
  };

  // `name: "value"` / `name: value`, with optional surrounding double quotes.
  const unquote = (raw) => {
    const v = raw.trim();
    if (v.length >= 2 && v.startsWith('"') && v.endsWith('"')) return v.slice(1, -1);
    if (v.length >= 2 && v.startsWith("'") && v.endsWith("'")) return v.slice(1, -1);
    return v;
  };

  const labels = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;
    if (line.trim() === '' || line.trim().startsWith('#')) continue;

    const entryStart = /^- ([A-Za-z_]+):[ \t]*(.*)$/.exec(line);
    if (entryStart) {
      const [, key, value] = entryStart;
      if (key !== 'name') bad(line, lineNo, `a list entry must start with 'name:', got '${key}:'`);
      const name = unquote(value);
      if (name === '') bad(line, lineNo, 'label name is empty');
      // `guide` defaults to TRUE, and the default direction is deliberate: a
      // label that quietly vanishes from the guide is invisible, while one that
      // appears when it need not is merely a row too many. Fail toward showing.
      labels.push({ name, color: '', description: '', guide: true });
      continue;
    }

    const field = /^[ \t]+([A-Za-z_]+):[ \t]*(.*)$/.exec(line);
    if (field) {
      const [, key, value] = field;
      if (labels.length === 0)
        bad(line, lineNo, `field '${key}' appears before any '- name:' entry`);
      if (!['name', 'color', 'description', 'guide'].includes(key)) {
        bad(line, lineNo, `unknown field '${key}' (expected name, color, description or guide)`);
      }
      if (key === 'guide') {
        // ABSENT means true; a value that is present must be exactly true or
        // false. Anything else (`no`, `0`, `False`, a typo) is a loud parse
        // failure rather than a coerced truthy string, because coercion here
        // silently flips a label's visibility in the direction nobody notices.
        const raw = unquote(value);
        if (raw !== 'true' && raw !== 'false') {
          bad(line, lineNo, `guide must be exactly 'true' or 'false', got '${raw}'`);
        }
        labels[labels.length - 1].guide = raw === 'true';
        continue;
      }
      labels[labels.length - 1][key] = unquote(value);
      continue;
    }

    bad(line, lineNo, 'line is neither a comment, a "- name:" entry, nor an indented field');
  }

  for (const l of labels) {
    if (!l.description) {
      throw new Error(
        `${source}: label '${l.name}' has no description. The PR guide exists to say what each label DOES, so a description is mandatory.`
      );
    }
  }

  if (labels.length < MIN_LABELS) {
    throw new Error(
      `${source}: parsed only ${labels.length} label(s) (floor: ${MIN_LABELS}). The repo carries more than that, so this read is broken, not a short file.`
    );
  }

  return labels;
};

// Markdown table. Pipes inside a description would break the row, so escape
// them; nothing else in a description is table-significant.
//
// `guide: false` entries are declared but not listed. The guide exists because
// the roster got too long to remember, so padding it with GitHub's stock
// defaults and bot-applied labels would recreate the problem it solves. They
// still have to be DECLARED -- check-label-inventory.sh reconciles the whole
// file against the live repo -- which is why the two sets differ.
const visibleLabels = (labels) => labels.filter((l) => l.guide !== false);

const renderBody = (labels) => {
  const shown = visibleLabels(labels);
  if (shown.length < MIN_GUIDE_LABELS) {
    throw new Error(
      `only ${shown.length} of ${labels.length} label(s) are marked for the guide (floor: ${MIN_GUIDE_LABELS}). An empty or near-empty guide is a broken read of the 'guide' field, not a deliberate state.`
    );
  }
  const rows = shown.map(
    (l) => `| \`${l.name}\` | ${String(l.description).replace(/\|/g, '\\|')} |`
  );
  return [
    MARKER,
    '### Label guide',
    '',
    `The ${shown.length} labels a human usefully applies on this repo, and what applying one actually does:`,
    '',
    '| Label | What it does |',
    '| --- | --- |',
    ...rows,
    '',
    // A BLOCKQUOTE, not <sub>. The trailer is the only place that tells a
    // reader their hand-edits will be overwritten and where to change the
    // wording instead, so it has to be readable: <sub> renders it as tiny
    // subscript text, which is where a reader's eye skips. A blockquote reads
    // as a footer at normal size. Every line carries its own '>' rather than
    // relying on markdown's lazy continuation, which is easy to break by
    // editing one line.
    '> Generated from <code>.github/labels.yml</code> by <code>.ci/scripts/ci/label-guide-comment.cjs</code>,',
    '> and rewritten in place whenever that file changes. Editing this comment by hand does nothing:',
    '> the next CI run overwrites it. Add or reword a label there instead.',
    `> ${labels.length - shown.length} further label(s) exist and are deliberately left off this list`,
    '> (GitHub stock defaults, bot-applied labels, and labels with no consumer in code); they carry',
    '> <code>guide: false</code> in that file.',
  ].join('\n');
};

// Only a bot's guide counts as THE guide.
//
// Otherwise anyone able to comment on a PR could suppress the guide forever by
// posting an empty comment carrying the marker. GitHub reports app and Actions
// authors as `type: 'Bot'`, which is the property to key on -- not the login,
// which changes with whichever token the job happens to hold.
const isBotAuthored = (comment) => Boolean(comment && comment.user && comment.user.type === 'Bot');

const postLabelGuide = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  const prNumber =
    (context.payload && context.payload.pull_request && context.payload.pull_request.number) ||
    (context.issue && context.issue.number);

  if (!prNumber) {
    console.log('No pull request in context -- nothing to comment on.');
    return 'no-pr';
  }

  const source = process.env.LABEL_GUIDE_LABELS_FILE || DEFAULT_LABELS_FILE;
  // Read and parse BEFORE any API call: a malformed labels file must fail the
  // job loudly, never half-post a truncated guide.
  const labels = parseLabels(fs.readFileSync(source, 'utf8'), source);
  const body = renderBody(labels);

  const comments = await github.paginate(github.rest.issues.listComments, {
    owner,
    repo,
    issue_number: prNumber,
    per_page: 100,
  });

  const existing = comments.filter(
    (c) => String(c.body || '').startsWith(MARKER) && isBotAuthored(c)
  );

  if (existing.length === 0) {
    await github.rest.issues.createComment({ owner, repo, issue_number: prNumber, body });
    console.log(
      `Posted the label guide on #${prNumber} (${visibleLabels(labels).length} of ${labels.length} labels listed).`
    );
    return 'created';
  }

  // Newest wins if a duplicate ever slipped through; the older ones are left
  // alone rather than deleted, because deleting a comment is not reversible and
  // this module has no business doing it.
  const current = existing[existing.length - 1];

  if (String(current.body) === body) {
    console.log(`The label guide on #${prNumber} is already current -- no API write.`);
    return 'unchanged';
  }

  await github.rest.issues.updateComment({ owner, repo, comment_id: current.id, body });
  console.log(`Updated the label guide on #${prNumber} (${labels.length} labels).`);
  if (core && typeof core.info === 'function')
    core.info('Label guide refreshed from .github/labels.yml.');
  return 'updated';
};

module.exports = postLabelGuide;
module.exports.MARKER = MARKER;
module.exports.MIN_LABELS = MIN_LABELS;
module.exports.MIN_GUIDE_LABELS = MIN_GUIDE_LABELS;
module.exports.visibleLabels = visibleLabels;
module.exports.parseLabels = parseLabels;
module.exports.renderBody = renderBody;
module.exports.isBotAuthored = isBotAuthored;
