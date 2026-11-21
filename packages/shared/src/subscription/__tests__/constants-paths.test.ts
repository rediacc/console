import { describe, expect, it } from 'vitest';
import { ACCOUNT_API_BASE_PATH, DELEGATION_RENEW_PATH, LICENSE_RENEW_PATH } from '../constants.js';

describe('account API paths', () => {
  it('serves the delegation renewal endpoint under the account API mount', () => {
    expect(ACCOUNT_API_BASE_PATH).toBe('/account/api/v1');
    expect(DELEGATION_RENEW_PATH).toBe('/account/api/v1/delegation/renew');
  });

  it('keeps the licence renewal endpoint under the same mount', () => {
    expect(LICENSE_RENEW_PATH.startsWith(`${ACCOUNT_API_BASE_PATH}/`)).toBe(true);
  });
});
