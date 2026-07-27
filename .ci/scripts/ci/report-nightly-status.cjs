// Make a red nightly impossible to ignore, and a recovered one self-clearing.
//
// WHY THIS EXISTS. The nightly is the ONLY thing that validates main: `ci.yml`
// sets `full_suite: github.event_name != 'push'`, so push-to-main deliberately
// skips the expensive suites on the grounds that the PR already validated them.
// That is defensible only while the nightly is genuinely watched. It was not.
//
// Measured 2026-07-27:
//   gh run list --workflow ci.yml --event schedule -L 12
//     -> TWELVE cancelled, ZERO success, unbroken back to 2026-07-16
//
// Nobody noticed for twelve days, for two compounding reasons. First, the
// watchdog force-cancelled each red run, so the conclusion read `cancelled`
// (= "superseded, ignore") rather than `failure` -- fixed separately by
// evaluateCancelExemption in watchdog-monitor.cjs. Second, and the reason this
// file exists: NOTHING EVER REPORTED IT ANYWHERE. A scheduled run that fails at
// 04:00 UTC notifies no one, appears in no PR, and blocks nothing.
//
// So: one rolling GitHub issue, commented on each red night, closed
// automatically on the next green.
//
// WHY ONE ROLLING ISSUE AND NOT ONE PER NIGHT. The observed failure mode is a
// LONG UNBROKEN RUN of red nights, not isolated ones. One issue per night would
// have produced twelve issues for what is really one unattended-CI problem, and
// a wall of twelve identical issues is its own kind of invisible. A single issue
// that keeps growing a comment per night states the duration of the outage
// directly, which is the fact that actually matters.
//
// Env:
//   NIGHTLY_RUN_ID     - the Console CI run being reported on
//   NIGHTLY_CONCLUSION - its conclusion (success / failure / cancelled / ...)
//   NIGHTLY_EVENT      - its triggering event; anything but `schedule` is a no-op
//   NIGHTLY_URL        - html_url of the run
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/report-nightly-status.cjs')({github, context, core})

const ISSUE_LABEL = 'nightly-red';
const ISSUE_TITLE = 'Nightly CI is red';
// `bug` and `automated` already exist and are already used for triage;
// ISSUE_LABEL is created on demand the first time this fires.
const ISSUE_LABELS = ['bug', 'automated', ISSUE_LABEL];

// A run is green ONLY when it says `success`. `cancelled` is NOT green -- that
// conflation is the exact bug this whole file is a response to, so it is
// spelled out as a named predicate rather than left as an inline `!==`.
const isGreen = (conclusion) => conclusion === 'success';

const report = async ({ github, context, core }) => {
  const runId = process.env.NIGHTLY_RUN_ID || '';
  const conclusion = process.env.NIGHTLY_CONCLUSION || '';
  const event = process.env.NIGHTLY_EVENT || '';
  const url = process.env.NIGHTLY_URL || '';
  const { owner, repo } = context.repo;

  // Defensive: the workflow `if:` already filters to schedule runs. This is the
  // second lock, because a future trigger change must not silently start
  // opening issues for every PR run.
  if (event !== 'schedule') {
    console.log(`Run ${runId} was triggered by "${event}", not "schedule" -- nothing to report.`);
    return;
  }

  // The rolling issue is identified by LABEL, not by title: a human may retitle
  // it while investigating, and that must not orphan the tracking.
  //
  // `.pull_request` filter: GitHub's issues API returns PULL REQUESTS as issues.
  // A PR that happened to carry this label would otherwise be treated as the
  // tracking issue and get commented on, or closed on the next green nightly.
  const open = (await github.paginate(github.rest.issues.listForRepo, {
    owner, repo, state: 'open', labels: ISSUE_LABEL, per_page: 100,
  })).filter(i => !i.pull_request);

  if (isGreen(conclusion)) {
    if (open.length === 0) {
      console.log(`Nightly ${runId} is green and no ${ISSUE_LABEL} issue is open -- nothing to do.`);
      return;
    }
    for (const issue of open) {
      await github.rest.issues.createComment({
        owner, repo, issue_number: issue.number,
        body: `Nightly CI is green again: [run ${runId}](${url}). Closing automatically.`,
      });
      await github.rest.issues.update({ owner, repo, issue_number: issue.number, state: 'closed' });
      console.log(`Closed #${issue.number}: the nightly recovered.`);
    }
    return;
  }

  // Red. Name the jobs, because "the nightly failed" is not actionable and the
  // run link alone means opening a 90-job run to find the two that matter.
  let failedList = '_(could not read the job list)_';
  try {
    const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
      owner, repo, run_id: Number(runId), per_page: 100,
    });
    const bad = jobs.filter(j => j.conclusion && j.conclusion !== 'success' && j.conclusion !== 'skipped');
    failedList = bad.length
      ? bad.map(j => `- **${j.name}** -- \`${j.conclusion}\`${j.html_url ? ` ([log](${j.html_url}))` : ''}`).join('\n')
      : '_(no job reported a non-success conclusion; the run itself concluded ' + `\`${conclusion}\`)_`;
  } catch (e) {
    console.log(`Could not list jobs for run ${runId}: ${e.message}`);
  }

  const today = new Date().toISOString().slice(0, 10);
  const body = [
    `### ${today} -- nightly [run ${runId}](${url}) concluded \`${conclusion}\``,
    '',
    failedList,
    '',
    '<sub>Posted automatically. This issue closes itself on the next green nightly.',
    'The nightly is the only suite that validates `main`: push-to-main sets',
    '`full_suite: false` and skips the expensive jobs.</sub>',
  ].join('\n');

  if (open.length > 0) {
    const issue = open[0];

    // Dedupe by run id. `workflow_run: completed` fires once per ATTEMPT, and a
    // run keeps its id across attempts, so a nightly whose failed jobs are
    // re-run reaches this code twice for the same night. Without this check the
    // issue collects a duplicate comment per attempt, which makes a streak look
    // longer than it is -- and the streak length is the one number this issue
    // exists to communicate.
    let alreadyReported = String(issue.body || '').includes(`run ${runId}`);
    if (!alreadyReported) {
      try {
        const comments = await github.paginate(github.rest.issues.listComments, {
          owner, repo, issue_number: issue.number, per_page: 100,
        });
        alreadyReported = comments.some(c => String(c.body || '').includes(`run ${runId}`));
      } catch (e) {
        // Fail toward reporting: a duplicate comment is noise, a missing one is
        // the silence this whole workflow exists to break.
        console.log(`Could not read existing comments (${e.message}); reporting anyway.`);
      }
    }
    if (alreadyReported) {
      console.log(`#${issue.number} already reports run ${runId}; not commenting twice.`);
      core.warning(`Nightly CI is still red (${conclusion}); see issue #${issue.number}.`);
      return;
    }

    await github.rest.issues.createComment({ owner, repo, issue_number: issue.number, body });
    console.log(`Commented on #${issue.number}: the nightly is still red.`);
    core.warning(`Nightly CI is still red (${conclusion}); see issue #${issue.number}.`);
    return;
  }

  // First red night in this streak. Ensure the label exists before using it:
  // createIssue with an unknown label fails the whole call.
  try {
    await github.rest.issues.getLabel({ owner, repo, name: ISSUE_LABEL });
  } catch {
    try {
      await github.rest.issues.createLabel({
        owner, repo, name: ISSUE_LABEL, color: 'b60205',
        description: 'The scheduled nightly CI run is failing (opened and closed automatically)',
      });
      console.log(`Created the ${ISSUE_LABEL} label.`);
    } catch (e) {
      console.log(`Could not create the ${ISSUE_LABEL} label: ${e.message}`);
    }
  }

  const created = await github.rest.issues.create({
    owner, repo, title: ISSUE_TITLE, labels: ISSUE_LABELS, body,
  });
  console.log(`Opened #${created.data.number}: the nightly is red.`);
  core.warning(`Nightly CI is red (${conclusion}); opened issue #${created.data.number}.`);
};

module.exports = report;
module.exports.isGreen = isGreen;
module.exports.ISSUE_LABEL = ISSUE_LABEL;
module.exports.ISSUE_TITLE = ISSUE_TITLE;
module.exports.ISSUE_LABELS = ISSUE_LABELS;
