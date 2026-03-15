import {
  isLicensedRenetFunction,
  parseRenetLicenseFailure,
  RENET_LICENSE_REQUIRED_CODE,
} from '../renet-license-contract.js';

describe('renet-license-contract', () => {
  it('classifies repository and backup bridge functions as licensed', () => {
    expect(isLicensedRenetFunction('repository_list')).toBe(true);
    expect(isLicensedRenetFunction('repository_create')).toBe(true);
    expect(isLicensedRenetFunction('repository_fork')).toBe(true);
    expect(isLicensedRenetFunction('repository_resize')).toBe(true);
    expect(isLicensedRenetFunction('backup_push')).toBe(true);
    expect(isLicensedRenetFunction('datastore_status')).toBe(false);
    expect(isLicensedRenetFunction('machine_info')).toBe(false);
  });

  it('excludes repository_up, repository_up_all, repository_down, repository_delete from licensed', () => {
    expect(isLicensedRenetFunction('repository_up')).toBe(false);
    expect(isLicensedRenetFunction('repository_up_all')).toBe(false);
    expect(isLicensedRenetFunction('repository_down')).toBe(false);
    expect(isLicensedRenetFunction('repository_delete')).toBe(false);
  });

  it('parses the structured license-required payload from stderr', () => {
    expect(
      parseRenetLicenseFailure(
        `warning\n{"code":"${RENET_LICENSE_REQUIRED_CODE}","reason":"missing","message":"license required"}\n`
      )
    ).toEqual({
      code: RENET_LICENSE_REQUIRED_CODE,
      reason: 'missing',
      message: 'license required',
    });
  });

  it('ignores unrelated JSON payloads', () => {
    expect(parseRenetLicenseFailure('{"code":"OTHER","reason":"missing"}')).toBeNull();
  });
});
