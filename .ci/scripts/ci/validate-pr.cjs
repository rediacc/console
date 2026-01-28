// PR Validation for GitHub Actions
// Validates PR title (Conventional Commits), description, linked issues, and size.
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/validate-pr.cjs')({github, context, core})

module.exports = async ({ github, context, core }) => {
  const pr = context.payload.pull_request;
  const errors = [];
  const warnings = [];

  // Check PR title format (Conventional Commits)
  const titlePattern = /^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\(.+\))?: .+/;
  if (!titlePattern.test(pr.title)) {
    errors.push(
      'PR title must follow Conventional Commits format:\n' +
      'type(scope): description\n\n' +
      'Types: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert\n' +
      'Example: feat(ui): add dark mode toggle'
    );
  }

  // Check PR description length
  const body = pr.body || '';
  if (body.length < 20) {
    errors.push('PR description is too short. Please provide a detailed description.');
  }

  // Check for linked issues (warning only)
  const issuePattern = /(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved|ref|refs)\s+#\d+/i;
  if (!issuePattern.test(body)) {
    warnings.push('PR does not reference any issues. Consider linking related issues.');
  }

  // Check PR size
  const { data: files } = await github.rest.pulls.listFiles({
    owner: context.repo.owner,
    repo: context.repo.repo,
    pull_number: pr.number,
  });
  const additions = files.reduce((sum, file) => sum + file.additions, 0);
  const deletions = files.reduce((sum, file) => sum + file.deletions, 0);
  const totalChanges = additions + deletions;
  const fileCount = files.length;

  if (totalChanges > 1000) {
    warnings.push(`Large PR detected (${totalChanges} lines changed). Consider breaking it into smaller PRs.`);
  }
  if (fileCount > 30) {
    warnings.push(`Many files changed (${fileCount} files). Consider breaking it into smaller PRs.`);
  }

  // Note: Merge conflicts and rebase checks are handled by Quality / Branch job

  // Write summary
  let summary = `## PR Validation\n\n`;
  summary += `- **Files changed:** ${fileCount}\n`;
  summary += `- **Lines added:** ${additions}\n`;
  summary += `- **Lines deleted:** ${deletions}\n`;
  summary += `- **Total changes:** ${totalChanges}\n\n`;

  if (warnings.length > 0) {
    summary += `### Warnings\n`;
    warnings.forEach(w => {
      core.warning(w);
      summary += `- ⚠️ ${w}\n`;
    });
    summary += '\n';
  }

  if (errors.length > 0) {
    summary += `### Errors\n`;
    errors.forEach(e => summary += `- ❌ ${e}\n`);
    core.summary.addRaw(summary).write();
    core.setFailed(errors.join('\n\n'));
  } else {
    summary += `✅ All PR checks passed\n`;
    core.summary.addRaw(summary).write();
  }
};
