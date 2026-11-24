// Post a CI time budget check failure (PLAN-ci-time-budget T3.3) to a rolling "nightly is red" issue thread, labelled `nightly-red` and closed by hand: nothing closes it automatically since the nightly-status workflow was retired (PLAN-health-checks-local R3).
//
// WHY A SEPARATE POSTER. ops-housekeeping.yml's own 03:00 cron has no `workflow_run` payload, so this posts its own dated section onto the open issue, or opens one when none is open.
//
// Env: BUDGET_CHECK_SUMMARY_PATH - a file holding budget_report.py --check's own stdout+stderr
//      OPS_HEALTH_CONFIG - overrides the path of .ci/config/ops-health.json (the test suite uses it for the missing/empty cases)
//
// Usage (from actions/github-script):
//   script: return await require('./scripts/ci/report-budget-check.cjs')({github, context, core})

const fs = require('node:fs');
const nodePath = require('node:path');
const { WK_GH_ORIGIN } = require('./well-known.cjs');

const ISSUE_LABEL = 'nightly-red';
const ISSUE_TITLE = 'Nightly CI is red';
// `bug` and `automated` already exist and are already used for triage; ISSUE_LABEL is created on demand the first time this fires.
const ISSUE_LABELS = ['bug', 'automated', ISSUE_LABEL];

// WHO GETS PINGED. A comment with no @mention and no assignee notifies nobody. The handles are `github_mentions` in .ci/config/ops-health.json, the one ops alert config.
const ALERTS_CONFIG = nodePath.join(__dirname, '..', '..', '.ci', 'config', 'ops-health.json');
const HANDLE_RE = /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\/[A-Za-z0-9._-]+)?$/;

// Returns the `@handle` strings to mention. Never throws: a broken config must not stop the report itself from posting, but it must not pass silently either, so every degraded path logs a warning naming the file.
const loadMentions = (core) => {
  const file = process.env.OPS_HEALTH_CONFIG || ALERTS_CONFIG;
  const warn = (msg) => {
    const line = `ops-health: ${msg} -- this report mentions nobody.`;
    console.log(`WARNING ${line}`);
    if (core && typeof core.warning === 'function') core.warning(line);
  };
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch (e) {
    warn(`could not read ${file} (${e.message})`);
    return [];
  }
  const list = Array.isArray(parsed?.github_mentions) ? parsed.github_mentions : [];
  const handles = [];
  for (const raw of list) {
    const handle = String(raw ?? '')
      .trim()
      .replace(/^@/, '');
    if (HANDLE_RE.test(handle)) handles.push(`@${handle}`);
    else warn(`ignoring invalid handle ${JSON.stringify(raw)} in ${file}`);
  }
  if (handles.length === 0) warn(`${file} lists no handle under "github_mentions"`);
  return handles;
};

// Prefix a body with the mention line, or return it unchanged when there is nobody to mention.
const withMentions = (mentions, reason, body) =>
  mentions.length === 0 ? body : `${mentions.join(' ')} ${reason}\n\n${body}`;

const readSummary = (path) => {
  if (!path) return '(no summary captured)';
  try {
    const text = fs.readFileSync(path, 'utf-8').trim();
    return text === '' ? '(budget_report.py --check produced no output)' : text;
  } catch (e) {
    return `(could not read ${path}: ${e.message})`;
  }
};

const reportBudgetCheck = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  const runId = process.env.GITHUB_RUN_ID || '';
  const serverUrl = process.env.GITHUB_SERVER_URL || WK_GH_ORIGIN;
  const url = `${serverUrl}/${owner}/${repo}/actions/runs/${runId}`;
  const summary = readSummary(process.env.BUDGET_CHECK_SUMMARY_PATH);
  const today = new Date().toISOString().slice(0, 10);
  // Anchored on the markdown link's closing bracket, so a bare substring match would also hit a LONGER run id that happens to start with these digits.
  const marker = `budget-check run ${runId}]`;

  // This module posts only on failure, so every post mentions the `github_mentions` handles: a comment with no @mention notifies nobody.
  const body = withMentions(
    loadMentions(core),
    'the CI time budget check failed.',
    [
      `### ${today} -- CI time budget check failed ([budget-check run ${runId}](${url}))`,
      '',
      '```',
      summary,
      '```',
      '',
      '<sub>Posted automatically by PLAN-ci-time-budget T3.3 (ops-housekeeping.yml, daily 03:00 UTC).',
      'A leg over 12 minutes, or a committed estimate drifting more than 25% from measured,',
      'means .ci/config/lane-durations.json needs `budget_report.py --refresh`; a gate-cost',
      'finding (the `gate_costs` lines) means .ci/config/gate-costs.json needs `gate_costs.py --refresh`.</sub>',
    ].join('\n')
  );

  const open = (
    await github.paginate(github.rest.issues.listForRepo, {
      owner,
      repo,
      state: 'open',
      labels: ISSUE_LABEL,
      per_page: 100,
    })
  ).filter((i) => !i.pull_request);

  if (open.length > 0) {
    const issue = open[0];
    let alreadyReported = String(issue.body || '').includes(marker);
    if (!alreadyReported) {
      try {
        const comments = await github.paginate(github.rest.issues.listComments, {
          owner,
          repo,
          issue_number: issue.number,
          per_page: 100,
        });
        alreadyReported = comments.some((c) => String(c.body || '').includes(marker));
      } catch (e) {
        console.log(`Could not read existing comments (${e.message}); reporting anyway.`);
      }
    }
    if (alreadyReported) {
      console.log(`#${issue.number} already reports ${marker}; not commenting twice.`);
      core.warning(`CI time budget check failed; see issue #${issue.number}.`);
      return;
    }
    await github.rest.issues.createComment({ owner, repo, issue_number: issue.number, body });
    console.log(`Commented on #${issue.number}: the CI time budget check failed.`);
    core.warning(`CI time budget check failed; see issue #${issue.number}.`);
    return;
  }

  // First failure in this streak. Ensure the label exists before using it: createIssue with an unknown label fails the whole call.
  try {
    await github.rest.issues.getLabel({ owner, repo, name: ISSUE_LABEL });
  } catch {
    try {
      await github.rest.issues.createLabel({
        owner,
        repo,
        name: ISSUE_LABEL,
        color: 'b60205',
        description: 'The scheduled nightly CI run is failing (opened and closed automatically)',
      });
      console.log(`Created the ${ISSUE_LABEL} label.`);
    } catch (e) {
      console.log(`Could not create the ${ISSUE_LABEL} label: ${e.message}`);
    }
  }

  const created = await github.rest.issues.create({
    owner,
    repo,
    title: ISSUE_TITLE,
    labels: ISSUE_LABELS,
    body,
  });
  console.log(`Opened #${created.data.number}: the CI time budget check failed.`);
  core.warning(`CI time budget check failed; opened issue #${created.data.number}.`);
};

module.exports = reportBudgetCheck;
