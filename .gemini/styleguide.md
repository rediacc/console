# Code Review Guidelines

This document guides Gemini Code Assist reviews to be focused and actionable.

## Review Scope

- Focus ONLY on the changed lines in the diff
- Do NOT suggest changes to surrounding or unmodified code
- Avoid nitpicking existing patterns that predate this PR
- Accept the codebase's established conventions

## Priority Order

Review comments should prioritize issues in this order:

1. **Security vulnerabilities** - Authentication, authorization, injection, XSS, etc.
2. **Runtime bugs** - Logic errors, null/undefined access, race conditions
3. **Performance issues** - N+1 queries, memory leaks, inefficient algorithms
4. **Missing error handling** - Unhandled exceptions, missing edge cases
5. **Type safety issues** - Incorrect types, unsafe casts, missing null checks

## What NOT to Comment On

- Style preferences already handled by linters (ESLint, Prettier)
- Minor naming suggestions unless genuinely confusing
- "Consider" suggestions without clear benefit
- Alternative approaches that aren't objectively better
- Comments on code that wasn't changed in this PR

## Follow-up Commits

When reviewing commits that address previous feedback:

- Focus on whether the original concern was properly resolved
- Don't raise new unrelated issues
- Acknowledge when feedback has been addressed
- Keep follow-up reviews minimal

## Comment Quality

- Be specific about what needs to change and why
- Provide code examples when suggesting fixes
- Explain the impact/risk if the issue is not addressed
- One actionable item per comment
