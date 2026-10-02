// Make a red nightly impossible to ignore, and a recovered one self-clearing.
//
// WHY THIS EXISTS. The nightly is the ONLY thing that validates main: `ci.yml`
// sets `full_suite: github.event_name != 'push'`, so push-to-main deliberately
// skips the expensive suites on the grounds that the PR already validated them. That is defensible only while the nightly is genuinely watched. It was not.
//
// Measured 2026-07-27: gh run list --workflow ci.yml --event schedule -L 12 -> TWELVE cancelled, ZERO success, unbroken back to 2026-07-16
//
// Nobody noticed for twelve days, for two compounding reasons. First, the watchdog force-cancelled each red run, so the conclusion read `cancelled`
// (= "superseded, ignore") rather than `failure` -- fixed separately by
// evaluateCancelExemption in watchdog-monitor.cjs. Second, and the reason this file exists: NOTHING EVER REPORTED IT ANYWHERE. A scheduled run that fails at 04:00 UTC notifies no one, appears in no PR, and blocks nothing.
//
// So: one rolling GitHub issue, commented on each red night, closed automatically on the next green.
//
// WHY ONE ROLLING ISSUE AND NOT ONE PER NIGHT. The observed failure mode is a LONG UNBROKEN RUN of red nights, not isolated ones. One issue per night would have produced twelve issues for what is really one unattended-CI problem, and a wall of twelve identical issues is its own kind of invisible. A single issue that keeps growing a comment per night states the duration of the
// outage directly, which is the fact that actually matters.
//
// Env: NIGHTLY_RUN_ID - the Console CI run being reported on NIGHTLY_CONCLUSION - its conclusion (success / failure / cancelled / ...)
//   NIGHTLY_EVENT      - its triggering event; anything but `schedule` is a no-op
// NIGHTLY_URL - html_url of the run
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/report-nightly-status.cjs')({github, context, core})

const ISSUE_LABEL = 'nightly-red';
const ISSUE_TITLE = 'Nightly CI is red';
// `bug` and `automated` already exist and are already used for triage;
// ISSUE_LABEL is created on demand the first time this fires.
const ISSUE_LABELS = ['bug', 'automated', ISSUE_LABEL];

// A run is green ONLY when it says `success`. `cancelled` is NOT green -- that conflation is the exact bug this whole file is a response to, so it is
// spelled out as a named predicate rather than left as an inline `!==`.
const isGreen = (conclusion) => conclusion === 'success';

// WHO GETS PINGED. A comment with no @mention and no assignee notifies nobody: the nightly was red every night 2026-09-22..09-30 and each comment on the rolling issue went unseen. The handles live in ONE config file so this module and report-budget-check.cjs cannot drift apart. CI_ALERTS_CONFIG overrides the path (the test suite uses it for the missing/empty cases).
const path = require('node:path');
const fs = require('node:fs');

const ALERTS_CONFIG = path.join(__dirname, '..', '..', 'config', 'ci-alerts.json');
const HANDLE_RE = /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\/[A-Za-z0-9._-]+)?$/;

// Returns the `@handle` strings to mention. Never throws: a broken config must not stop the report itself from posting, but it must not pass silently either, so every degraded path logs a warning naming the file.
const loadMentions = (core) => {
  const file = process.env.CI_ALERTS_CONFIG || ALERTS_CONFIG;
  const warn = (msg) => {
    const line = `ci-alerts: ${msg} -- this report mentions nobody.`;
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
  const list = Array.isArray(parsed?.mention) ? parsed.mention : [];
  const handles = [];
  for (const raw of list) {
    const handle = String(raw ?? '')
      .trim()
      .replace(/^@/, '');
    if (HANDLE_RE.test(handle)) handles.push(`@${handle}`);
    else warn(`ignoring invalid handle ${JSON.stringify(raw)} in ${file}`);
  }
  if (handles.length === 0) warn(`${file} lists no handle under "mention"`);
  return handles;
};

// Prefix a body with the mention line, or return it unchanged when there is nobody to mention.
const withMentions = (mentions, reason, body) =>
  mentions.length === 0 ? body : `${mentions.join(' ')} ${reason}\n\n${body}`;

// The conclusion the LAST nightly report on the issue recorded, or null when none is found. Reads the issue body (the first red night's report) and then the comments in order, keeping the last `nightly [run <id>](<url>) concluded \`<c>\`` header; budget-check comments carry no such header and are skipped.
const NIGHTLY_HEADER_RE = /nightly \[run \d+\]\([^)]*\) concluded `([^`]*)`/g;
const lastNightlyConclusion = (bodies) => {
  let last = null;
  for (const body of bodies) {
    for (const m of String(body || '').matchAll(NIGHTLY_HEADER_RE)) last = m[1];
  }
  return last;
};

// Green. Close every open rolling issue with a note. Recovery notice: mention once, only when the last nightly report on the issue was red. An issue the budget check opened while the nightly stayed green closes silently. An unreadable comment list fails toward mentioning: an extra ping is noise, a missed recovery is not.
const closeOnGreen = async ({ github, core, owner, repo, open, runId, url }) => {
  if (open.length === 0) {
    console.log(`Nightly ${runId} is green and no ${ISSUE_LABEL} issue is open -- nothing to do.`);
    return;
  }
  for (const issue of open) {
    let recovered;
    try {
      const comments = await github.paginate(github.rest.issues.listComments, {
        owner,
        repo,
        issue_number: issue.number,
        per_page: 100,
      });
      const previous = lastNightlyConclusion([issue.body, ...comments.map((c) => c.body)]);
      recovered = previous !== null && !isGreen(previous);
    } catch (e) {
      recovered = true;
      console.log(`Could not read comments on #${issue.number} (${e.message}); mentioning anyway.`);
    }
    const greenBody = `Nightly CI is green again: [run ${runId}](${url}). Closing automatically.`;
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: issue.number,
      body: recovered
        ? withMentions(loadMentions(core), 'the nightly recovered.', greenBody)
        : greenBody,
    });
    await github.rest.issues.update({ owner, repo, issue_number: issue.number, state: 'closed' });
    console.log(`Closed #${issue.number}: the nightly recovered.`);
  }
};

// SHAPE-AGNOSTIC on purpose. `github.paginate` sometimes yields the flattened
// job objects and sometimes an array of RESPONSE objects (`{total_count,
// jobs}`), depending on whether it recognises the endpoint's collection key.
// Observed live on nightly 30327872124: the call threw nothing, but every element lacked `.conclusion`, so the filter matched zero of NINE failed jobs and the issue said no job had failed. Normalise instead of assuming.
const flattenJobs = (page) => {
  if (Array.isArray(page)) {
    return page.flatMap((entry) => (entry && Array.isArray(entry.jobs) ? entry.jobs : [entry]));
  }
  return Array.isArray(page?.jobs) ? page.jobs : [];
};

// CI time budget violations (T1.5). The watchdog's own budget mode is REPORT-ONLY and the nightly is CANCEL-EXEMPT by construction (evaluateCancelExemption, CANCEL_EXEMPT_EVENTS at watchdog-monitor.cjs:54) -- nothing else surfaces an over-budget scheduled run, which is exactly the class of silence report-nightly-status.cjs already exists to close for a red conclusion. Reuses the job list already fetched above rather than a second API call. `context.payload.workflow_run.run_started_at` is the real webhook payload's field, absent from ad-hoc/local invocations and from this suite's own test harness, so an absent value simply skips the section rather than failing the whole report.
const budgetSectionFor = ({ context, usable, runId }) => {
  try {
    const runStartedAt = context.payload?.workflow_run?.run_started_at;
    if (!runStartedAt) return '';
    const { evaluateBudget } = require('./watchdog-monitor.cjs');
    const updatedAt = context.payload?.workflow_run?.updated_at;
    const budget = evaluateBudget({
      jobs: usable,
      run: { run_started_at: runStartedAt },
      nowMs: updatedAt ? new Date(updatedAt).getTime() : Date.now(),
      jobBudgetMin: Number(process.env.NIGHTLY_JOB_BUDGET_MIN || '15'),
      runBudgetMin: Number(process.env.NIGHTLY_RUN_BUDGET_MIN || '20'),
      excludePatterns: (
        process.env.NIGHTLY_BUDGET_EXCLUDE_PATTERNS ||
        'Watchdog,CI Complete,CI Verdict'
      )
        .split(',')
        .map((s) => s.trim()),
      mode: 'report',
    });
    if (!budget.hasViolation) return '';
    const lines = budget.jobViolations.map(
      (v) => `- **${v.name}** -- ${v.minutes.toFixed(1)}m (budget ${v.budgetMin}m)`
    );
    if (budget.runViolation) {
      lines.push(
        `- **whole pipeline** -- ${budget.runViolation.minutes.toFixed(1)}m (budget ${budget.runViolation.budgetMin}m)`
      );
    }
    return ['', '### CI time budget violations (report-only)', '', ...lines].join('\n');
  } catch (e) {
    console.log(`Could not evaluate the CI time budget for run ${runId}: ${e.message}`);
    return '';
  }
};

// The failed-job roster for a red run, as markdown.
const describeFailedJobs = ({ jobs, usable, runId, conclusion }) => {
  const bad = usable.filter(
    (j) => j.conclusion && j.conclusion !== 'success' && j.conclusion !== 'skipped'
  );
  if (bad.length > 0) {
    return bad
      .map(
        (j) =>
          `- **${j.name}** -- \`${j.conclusion}\`${j.html_url ? ` ([log](${j.html_url}))` : ''}`
      )
      .join('\n');
  }
  if (usable.length === 0) {
    // ANTI-VACUITY. Zero readable jobs is not evidence that nothing failed, it is evidence that the read failed. Saying "no job reported a non-success conclusion" there is the same defect this whole programme is about: reporting empty data as clean data. Fail toward "I could not tell".
    console.log(
      `Job list for run ${runId} was unreadable (${jobs.length} entries, none with a conclusion).`
    );
    return `_(could not read the job list: the API returned ${jobs.length} entr${jobs.length === 1 ? 'y' : 'ies'}, none carrying a conclusion. The run itself concluded \`${conclusion}\`.)_`;
  }
  // Genuinely readable and genuinely all-green at job level. This does happen: a run can conclude `failure` because a job was cancelled by the 6h limit or a required check failed outside the job list.
  return `_(read ${usable.length} job(s); none reported a non-success conclusion, yet the run concluded \`${conclusion}\`.)_`;
};

// Red. Name the jobs, because "the nightly failed" is not actionable and the run link alone means opening a 90-job run to find the two that matter.
const redRunSections = async ({ github, context, owner, repo, runId, conclusion }) => {
  try {
    const page = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
      owner,
      repo,
      run_id: Number(runId),
      per_page: 100,
    });
    const jobs = flattenJobs(page);
    const usable = jobs.filter((j) => j && typeof j.conclusion !== 'undefined');
    return {
      budgetSection: budgetSectionFor({ context, usable, runId }),
      failedList: describeFailedJobs({ jobs, usable, runId, conclusion }),
    };
  } catch (e) {
    console.log(`Could not list jobs for run ${runId}: ${e.message}`);
    return { failedList: '_(could not read the job list)_', budgetSection: '' };
  }
};

// Dedupe by run id. `workflow_run: completed` fires once per ATTEMPT, and a run keeps its id across attempts, so a nightly whose failed jobs are re-run reaches this code twice for the same night. Without this check the issue collects a duplicate comment per attempt, which makes a streak look longer than it is -- and the streak length is the one number this issue exists to
// communicate. Anchored on the markdown link's closing bracket, not a bare substring. Every posted body writes the run as `[run <id>](<url>)`, so matching `run <id>]` pins both ends. A bare `includes('run ' + runId)` would also match a LONGER id that happens to start with these digits, which run ids eventually will as they gain a digit -- and a false dedupe is silent, so it
// would drop a night from the streak with nothing to show for it. Flagged as a non-blocking nit in review of PR #541.
const alreadyReportedOn = async ({ github, owner, repo, issue, runId }) => {
  const runMarker = `run ${runId}]`;
  if (String(issue.body || '').includes(runMarker)) return true;
  try {
    const comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: issue.number,
      per_page: 100,
    });
    return comments.some((c) => String(c.body || '').includes(runMarker));
  } catch (e) {
    // Fail toward reporting: a duplicate comment is noise, a missing one is the silence this whole workflow exists to break.
    console.log(`Could not read existing comments (${e.message}); reporting anyway.`);
    return false;
  }
};

// First red night in this streak. Ensure the label exists before using it: createIssue with an unknown label fails the whole call.
const ensureLabel = async ({ github, owner, repo }) => {
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
};

const report = async ({ github, context, core }) => {
  const runId = process.env.NIGHTLY_RUN_ID || '';
  const conclusion = process.env.NIGHTLY_CONCLUSION || '';
  const event = process.env.NIGHTLY_EVENT || '';
  const url = process.env.NIGHTLY_URL || '';
  const { owner, repo } = context.repo;

  // Defensive: the workflow `if:` already filters to schedule runs. This is the second lock, because a future trigger change must not silently start opening issues for every PR run.
  if (event !== 'schedule') {
    console.log(`Run ${runId} was triggered by "${event}", not "schedule" -- nothing to report.`);
    return;
  }

  // The rolling issue is identified by LABEL, not by title: a human may retitle it while investigating, and that must not orphan the tracking.
  //
  // `.pull_request` filter: GitHub's issues API returns PULL REQUESTS as issues. A PR that happened to carry this label would otherwise be treated as the tracking issue and get commented on, or closed on the next green nightly.
  const open = (
    await github.paginate(github.rest.issues.listForRepo, {
      owner,
      repo,
      state: 'open',
      labels: ISSUE_LABEL,
      per_page: 100,
    })
  ).filter((i) => !i.pull_request);

  if (isGreen(conclusion)) {
    await closeOnGreen({ github, core, owner, repo, open, runId, url });
    return;
  }

  const { failedList, budgetSection } = await redRunSections({
    github,
    context,
    owner,
    repo,
    runId,
    conclusion,
  });

  const today = new Date().toISOString().slice(0, 10);
  // Every red night mentions: the operator ruling (2026-09-30) is to hear about each red, not only the first of a streak.
  const body = withMentions(
    loadMentions(core),
    'the nightly is red.',
    [
      `### ${today} -- nightly [run ${runId}](${url}) concluded \`${conclusion}\``,
      '',
      failedList,
      budgetSection,
      '',
      '<sub>Posted automatically. This issue closes itself on the next green nightly.',
      'The nightly is the only suite that validates `main`: push-to-main sets',
      '`full_suite: false` and skips the expensive jobs.</sub>',
    ].join('\n')
  );

  if (open.length > 0) {
    const issue = open[0];
    if (await alreadyReportedOn({ github, owner, repo, issue, runId })) {
      console.log(`#${issue.number} already reports run ${runId}; not commenting twice.`);
      core.warning(`Nightly CI is still red (${conclusion}); see issue #${issue.number}.`);
      return;
    }
    await github.rest.issues.createComment({ owner, repo, issue_number: issue.number, body });
    console.log(`Commented on #${issue.number}: the nightly is still red.`);
    core.warning(`Nightly CI is still red (${conclusion}); see issue #${issue.number}.`);
    return;
  }

  await ensureLabel({ github, owner, repo });
  const created = await github.rest.issues.create({
    owner,
    repo,
    title: ISSUE_TITLE,
    labels: ISSUE_LABELS,
    body,
  });
  console.log(`Opened #${created.data.number}: the nightly is red.`);
  core.warning(`Nightly CI is red (${conclusion}); opened issue #${created.data.number}.`);
};

module.exports = report;
module.exports.isGreen = isGreen;
module.exports.ISSUE_LABEL = ISSUE_LABEL;
module.exports.ISSUE_TITLE = ISSUE_TITLE;
module.exports.ISSUE_LABELS = ISSUE_LABELS;
module.exports.loadMentions = loadMentions;
module.exports.withMentions = withMentions;
module.exports.lastNightlyConclusion = lastNightlyConclusion;
