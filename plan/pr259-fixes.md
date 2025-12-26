# PR #259 Review Fixes Plan

## 1. Fix Security Issue: Activation Code Generation (HIGH)

**File**: `packages/cli/src/commands/user.ts`

**Problem**: CLI generates activation code client-side and displays it to user.

**Reality**: The middleware already handles this securely:
- `StoredProcedureController.Protected.cs:131` overwrites any client-provided code
- `GenerateActivationCode()` uses `RandomNumberGenerator.GetInt32` for cryptographic security
- Server returns the actual activation code in the response

**Fix**:
1. Remove client-side activation code generation (lines 62-65)
2. Remove `activationCode` from the `CreateNewUser` payload
3. Parse the response using `parseCreateUser` to get server-generated code
4. Display the server-returned activation code

## 2. Replace `as never` Type Assertions (MEDIUM)

**Files**: Multiple CLI and web files (~50 occurrences)

**Problem**: Using `as never` bypasses type checking entirely.

**Fix**: Make `withSpinner` generic to preserve return type:

```typescript
// Before
async function withSpinner<T>(msg: string, fn: () => Promise<T>, done: string): Promise<T>

// Usage (no cast needed)
const apiResponse = await withSpinner('...', () => typedApi.GetAuditLogs({...}), '...');
const logs = parseGetAuditLogs(apiResponse); // Type flows through
```

For parser calls, use `as ApiResponse` instead of `as never`.

## 3. Fix Audit History/Trace Inconsistency (MEDIUM)

**File**: `packages/cli/src/commands/audit.ts`

**Problem**:
- `trace` command prints `trace.records` (line 57)
- `history` command prints full `trace` object (line 80)

**Fix**: Change line 80 to print `trace.records` for consistency:
```typescript
outputService.print(trace.records, format);
```

## 4. Fix vaultConfig.fetch Inconsistency (MEDIUM)

**File**: `packages/cli/src/commands/region.ts`

**Problem**: Returns `{ vaults: [...] }` object instead of array directly like `bridge.ts`.

**Fix**: Change line 41 to return array directly:
```typescript
return vaults as unknown as (CompanyVaultRecord & { vaultType?: string })[];
```

## 5. Update Web Queries to Use Shared Parsers (MEDIUM)

**File**: `packages/web/src/api/queries/audit.ts`

**Problem**: Uses local `extractByIndex` instead of shared `parseGetAuditLogs`.

**Fix**: Replace lines 35 and 58 with shared parser:
```typescript
import { parseGetAuditLogs } from '@rediacc/shared/api';
// ...
return parseGetAuditLogs(response as ApiResponse);
```

---

## Implementation Order

1. **audit.ts fixes** (items 3 & 5) - Quick wins, low risk
2. **region.ts fix** (item 4) - Quick win, low risk
3. **user.ts security fix** (item 1) - Important, moderate complexity
4. **Type assertion cleanup** (item 2) - Larger scope, can be partial

## Commit Message

```
fix(cli): address PR review feedback

- Fix user create to use server-generated activation code
- Fix audit history to print records consistently with trace
- Fix region vaultConfig.fetch to return array directly
- Update web audit queries to use shared parsers
```
