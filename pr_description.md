## Description
This PR adds E2E tests for credential editing and deletion in the console application. It also updates the Playwright configuration to ensure tests run smoothly.

## Type of Change
- [x] New feature (non-breaking change that adds functionality)
- [x] Refactoring (no functional changes)

## Related Issues
Fixes # (No specific issue linked)

## Changes Made
- Added `02-09-01-credential-edit.test.ts` to test credential editing.
- Added `02-09-03-credential-delete.test.ts` to test credential deletion.
- Updated `playwright.config.ts` for E2E environment consistency.

## Screenshots
N/A (Automated E2E tests)

## Testing
- [x] Integration tests pass (Tested locally)
- [x] Manual testing completed (Verified through test script)

### Test Coverage
- [x] Integration tests pass

### Browser Testing
- [x] Chrome

### Responsive Testing
- [x] Desktop (1440px)

## Performance Impact
- [x] No performance impact

## Security Checklist
- [x] No sensitive data exposed in code or logs
- [x] Input validation implemented
- [x] API calls properly authenticated
- [x] No hardcoded credentials or secrets
- [x] Vault encryption maintained

## Code Quality
- [x] Code follows project style guidelines
- [x] TypeScript types properly defined
- [x] No ESLint warnings/errors

## Documentation
- [x] Code comments added where necessary

## Deployment Notes
- [x] No deployment changes needed

## Checklist
- [x] I have performed a self-review of my code
- [x] I have commented my code in hard-to-understand areas
- [x] My changes generate no new warnings
- [x] I have added tests that prove my fix/feature works
- [x] New and existing unit tests pass locally

## Additional Notes
The tests use dynamic values (random numbers) to avoid conflicts during parallel or repeated runs.
