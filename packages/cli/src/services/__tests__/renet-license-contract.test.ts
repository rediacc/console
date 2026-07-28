import {
  parseRenetLicenseFailure,
  RENET_LICENSE_REQUIRED_CODE,
} from '../renet/renet-license-contract.js';

describe('renet-license-contract', () => {


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

  it.each(['cert_expired', 'cert_invalid'])(
    'parses the delegation-cert failure reason %s',
    (reason) => {
      expect(
        parseRenetLicenseFailure(
          `{"code":"${RENET_LICENSE_REQUIRED_CODE}","reason":"${reason}","message":"delegation cert problem"}`
        )
      ).toEqual({
        code: RENET_LICENSE_REQUIRED_CODE,
        reason,
        message: 'delegation cert problem',
      });
    }
  );
});
