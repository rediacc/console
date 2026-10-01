// Post a CI time budget check failure (PLAN-ci-time-budget T3.3) to the SAME rolling "nightly is red" issue thread report-nightly-status.cjs already keeps -- reusing its label/title constants (read-only import; this file never edits that one) rather than opening a second thread for what is really one "CI health" surface.
//
// WHY A SEPARATE POSTER AND NOT reportNightlyStatus ITSELF. That function reads NIGHTLY_RUN_ID/CONCLUSION/EVENT from a `workflow_run: completed` payload of "Console CI"; housekeeping.yml's own 03:00 cron is a DIFFERENT trigger with no such payload, so this posts its own dated section onto the same issue instead of forcing an unrelated trigger shape through that function's env contract.
//
// Env: BUDGET_CHECK_SUMMARY_PATH - a file holding budget_report.py --check's own stdout+stderr
//
// Usage (from actions/github-script):
//   script: return await require('./scripts/ci/report-budget-check.cjs')({github, context, core})

const fs = require('node:fs');
const { WK_GH_ORIGIN } = require('./well-known.cjs');
const {
  ISSUE_LABEL,
  ISSUE_TITLE,
  ISSUE_LABELS,
  loadMentions,
  withMentions,
} = require('../../.ci/scripts/ci/report-nightly-status.cjs');

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
  // Anchored on the markdown link's closing bracket, the same dedupe technique report-nightly-status.cjs uses for its own `run <id>]` marker: a bare substring match would also hit a LONGER run id that happens to start with these digits.
  const marker = `budget-check run ${runId}]`;

  // This module posts only on failure, so every post mentions the handles in .ci/config/ci-alerts.json: a comment with no @mention notifies nobody.
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
      '<sub>Posted automatically by PLAN-ci-time-budget T3.3 (housekeeping.yml, daily 03:00 UTC).',
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
