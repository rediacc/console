// Open (or comment on) a GitHub issue when the skip-ci scope sweeper detects
// commits that used [skip ci] while touching files outside the allowlist.
//
// Usage (from actions/github-script):
//   env:
//     REPORT_PATH: /tmp/violations.md
//   script: return await require('./.ci/scripts/ci/open-skip-ci-violation-issue.cjs')({github, context, core})

module.exports = async ({ github, context }) => {
  const fs = require('node:fs');
  const reportPath = process.env.REPORT_PATH;
  if (!reportPath) {
    throw new Error('REPORT_PATH env var is required');
  }
  const report = fs.readFileSync(reportPath, 'utf8');
  const title = 'skip-ci scope violation(s) detected';

  // Avoid duplicate issues — append a comment to an existing open one instead.
  const existing = await github.rest.issues.listForRepo({
    owner: context.repo.owner,
    repo: context.repo.repo,
    state: 'open',
    labels: 'ci-gate-violation',
    per_page: 10,
  });
  const dup = existing.data.find((i) => i.title === title);

  const body = [
    'The skip-ci scope gate detected commit(s) that used `[skip ci]` while touching files outside the allowlist.',
    '',
    'Allowlist: submodule pointers under `private/`, `CHANGELOG*`, `*.csproj`, and the `version` field of `package.json`.',
    '',
    report,
    '',
    '_Opened by `.github/workflows/check-skip-ci-scope.yml`._',
  ].join('\n');

  if (dup) {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: dup.number,
      body,
    });
    return { action: 'commented', issue: dup.number };
  }

  const created = await github.rest.issues.create({
    owner: context.repo.owner,
    repo: context.repo.repo,
    title,
    body,
    labels: ['ci-gate-violation'],
  });
  return { action: 'created', issue: created.data.number };
};
