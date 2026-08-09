// Post (and keep current) the autopilot guide on every PR.
//
// WHY THIS EXISTS. The autopilot can babysit a PR to green on its own, and
// almost nothing about that is discoverable from the PR itself: there are THREE
// ways to arm it, a dozen Actions variables that all fail closed, and three
// stop switches with three different scopes. An engineer who does not already
// know the design has no way to find out that applying one label would have
// done the work for them -- or, worse, no way to find the switch that stops it.
// So each PR gets one short comment saying both.
//
// WHY IT IS NOT RENDERED, AND WHAT REPLACES THAT. The label guide is a
// projection of .github/labels.yml, which is the right design when a machine-
// readable source of truth exists. This guide describes a WORKFLOW: its arming
// paths live in shell `if` branches, its bounds in three different files, and
// no parser turns those into prose. Hand-written prose is exactly the rotting
// fourth copy label-guide-comment.cjs's header warns about, so the mitigation
// is moved into the test: test-autopilot-guide-comment.sh asserts that every
// variable name, label name and numeric bound quoted below still appears in the
// file it was taken from. The prose is human; the FACTS in it are pinned, and a
// rename in autopilot.yml turns this comment red rather than stale.
//
// EVERY CLAIM'S SOURCE, so the next editor can re-verify rather than trust:
//   arming paths, stop scopes, variables .. .github/workflows/autopilot.yml
//                                           (the roster comment at its top)
//   arming ORDER, round cap, stuck sig .... .ci/scripts/autopilot/autopilot-gate.sh
//   round actions (fix/ready-flip/...) .... same file, the conclusion `case`
//   --max-turns per mode ................. .ci/scripts/autopilot/resolve-model-args.sh
//   label names and meanings ............. .github/labels.yml
//
// IDEMPOTENCE IS THE WHOLE DESIGN, and it is copied from the label guide
// deliberately rather than reinvented: find the existing comment by an HTML
// marker, and write ONLY when the body actually differs. A PR gets a CI run per
// push, so a guide posted per run would bury the conversation. A rerun on an
// unchanged tree performs zero API writes.
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/autopilot-guide-comment.cjs')({github, context, core})

// The comment's identity. FIRST bytes of the body, so a prefix test finds it
// and a human quoting this comment in a reply does not match.
const MARKER = '<!-- rediacc:autopilot-guide -->';

// Facts quoted in the body that the gate test re-checks against their sources.
// Exported rather than inlined so the test cannot drift from the prose: it
// asserts these appear BOTH here and in the file each one came from.
const VARIABLES = [
  ['AUTOPILOT_ENABLED', 'master switch'],
  ['AUTOPILOT_ALLOW_STATE', 'may write its state comment'],
  ['AUTOPILOT_ALLOW_FINISH', 'may ready-flip and finish'],
  ['AUTOPILOT_ALLOW_MODEL', 'model rounds run, pushes dry-run. A switch, never a model name'],
  ['AUTOPILOT_ALLOW_PUSH', 'may push for real'],
  ['AUTOPILOT_ALLOW_SUBMODULES', 'may touch submodules; widens its token to 5 repos'],
  ['AUTOPILOT_AUTHOR_ALLOWLIST', 'whose PRs it babysits. Empty allows NOBODY'],
  ['AUTOPILOT_APPLIER_ALLOWLIST', 'who may arm it'],
  ['AUTOPILOT_MAX_ROUNDS', 'round cap'],
  ['AUTOPILOT_EFFORT', 'effort for autonomous rounds; the `effort` input wins'],
];

const ARM_LABEL = 'autopilot';
const BLOCK_LABEL = 'autopilot-blocked';
const DEFAULT_MAX_ROUNDS = 25;

const renderBody = () => {
  const varRows = VARIABLES.map(([name, what]) => `| \`${name}\` | ${what} |`);
  return [
    MARKER,
    '### Autopilot guide',
    '',
    'Babysits this PR to green: fix rounds, ready-flip, review replies.',
    '',
    `**Arm**, in this order: apply \`${ARM_LABEL}\`; or \`gh workflow run Autopilot --ref <branch> -f pr_number=<N>\` (the dispatch IS the arming act: it opens a campaign, so later rounds need no label; inputs \`model\`, \`max_rounds\`, \`effort\`, \`debug-shell\`); or an open campaign in the state comment.`,
    '',
    `**Stop**: cancel the run (one round) · \`${BLOCK_LABEL}\` (whole loop; LATCHES until a human clears it) · remove \`${ARM_LABEL}\` (only the label path; a dispatched campaign keeps running) · \`AUTOPILOT_ENABLED\` not \`true\` (repo-wide).`,
    '',
    '**Variables**: repo/org Actions vars, all fail closed, absent means off.',
    '',
    '| Variable | What it does |',
    '| --- | --- |',
    ...varRows,
    '',
    '**Each round** the gate picks one action: `fix` (CI red), `ready-flip` (green, draft), `review-response` (threads open or Review Gate red), `done` (green, ready, reviewed, clean).',
    '',
    `**Bounds** (it escalates, never loops): round cap default ${DEFAULT_MAX_ROUNDS} · stuck-signature, same failed jobs twice · 30m job timeout · \`--max-turns\` 80 fixing, 60 otherwise. Hitting one applies \`${BLOCK_LABEL}\` for a human.`,
    '',
    // A blockquote rather than <sub>, for the reason spelled out at the same
    // place in label-guide-comment.cjs: this line is the only thing telling a
    // reader their edits get overwritten, and <sub> renders it as tiny
    // subscript text that the eye skips.
    '> Posted by <code>.ci/scripts/ci/autopilot-guide-comment.cjs</code>; edits here are overwritten.',
  ].join('\n');
};

// Only a bot's guide counts as THE guide. Otherwise anyone able to comment
// could suppress it forever by posting an empty comment carrying the marker.
// GitHub reports app and Actions authors as `type: 'Bot'`, which is the
// property to key on -- not the login, which changes with the token in hand.
const isBotAuthored = (comment) => Boolean(comment && comment.user && comment.user.type === 'Bot');

const postAutopilotGuide = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  const prNumber =
    (context.payload && context.payload.pull_request && context.payload.pull_request.number) ||
    (context.issue && context.issue.number);

  if (!prNumber) {
    console.log('No pull request in context -- nothing to comment on.');
    return 'no-pr';
  }

  const body = renderBody();

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
    console.log(`Posted the autopilot guide on #${prNumber}.`);
    return 'created';
  }

  // Newest wins if a duplicate ever slipped through; older ones are left alone
  // rather than deleted, because deleting a comment is not reversible and this
  // module has no business doing it.
  const current = existing[existing.length - 1];

  if (String(current.body) === body) {
    console.log(`The autopilot guide on #${prNumber} is already current -- no API write.`);
    return 'unchanged';
  }

  await github.rest.issues.updateComment({ owner, repo, comment_id: current.id, body });
  console.log(`Updated the autopilot guide on #${prNumber}.`);
  if (core && typeof core.info === 'function') core.info('Autopilot guide refreshed.');
  return 'updated';
};

module.exports = postAutopilotGuide;
module.exports.MARKER = MARKER;
module.exports.VARIABLES = VARIABLES;
module.exports.ARM_LABEL = ARM_LABEL;
module.exports.BLOCK_LABEL = BLOCK_LABEL;
module.exports.DEFAULT_MAX_ROUNDS = DEFAULT_MAX_ROUNDS;
module.exports.renderBody = renderBody;
module.exports.isBotAuthored = isBotAuthored;
