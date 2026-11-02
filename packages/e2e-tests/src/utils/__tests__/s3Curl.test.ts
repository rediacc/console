import { describe, expect, it } from 'vitest';
import { buildS3CurlCommand, parseS3CurlOutput, xmlValues } from '../storage/s3-curl';

const CONFIG = {
  endpoint: 'http://10.0.0.1:9000/',
  accessKey: 'access',
  secretKey: 'secret',
  bucket: 'default',
};

describe('buildS3CurlCommand', () => {
  it('signs with SigV4 and keeps the credentials off argv', () => {
    const command = buildS3CurlCommand(CONFIG, { method: 'GET', path: 'b?list-type=2' });
    const [argv, ...stdin] = command.split('\n');
    expect(argv).toContain("--aws-sigv4 'aws:amz:us-east-1:s3'");
    expect(argv).toContain('-K -');
    expect(argv).toContain("'http://10.0.0.1:9000/b?list-type=2'");
    expect(argv).not.toContain('secret');
    expect(stdin.join('\n')).toContain('user = "access:secret"');
  });

  it('uploads a file as a hashed body and downloads into a file', () => {
    expect(
      buildS3CurlCommand(CONFIG, { method: 'PUT', path: 'b/k', bodyFile: '/tmp/a b' })
    ).toContain("--data-binary @'/tmp/a b'");
    expect(
      buildS3CurlCommand(CONFIG, { method: 'GET', path: 'b/k', outputFile: '/tmp/out' })
    ).toContain("-o '/tmp/out'");
  });

  it('uses a header-only request for HEAD', () => {
    expect(buildS3CurlCommand(CONFIG, { method: 'HEAD', path: 'b/k' })).toContain('curl -sS -I ');
  });
});

describe('parseS3CurlOutput', () => {
  const get = { method: 'GET' } as const;

  it('splits the body from the trailing status code', () => {
    const parsed = parseS3CurlOutput({ code: 0, stdout: '<a>x</a>\n200' }, get);
    expect(parsed).toEqual({ ok: true, status: 200, body: '<a>x</a>' });
  });

  it('is not ok on a non-2xx status or a curl failure', () => {
    expect(parseS3CurlOutput({ code: 0, stdout: '\n403' }, get).ok).toBe(false);
    expect(parseS3CurlOutput({ code: 7, stdout: '' }, get)).toEqual({
      ok: false,
      status: 0,
      body: '',
    });
  });

  it('reads only the status for a file download', () => {
    expect(parseS3CurlOutput({ code: 0, stdout: '200' }, get)).toEqual({
      ok: true,
      status: 200,
      body: '',
    });
  });
});

describe('xmlValues', () => {
  it('returns every tag value in order', () => {
    expect(xmlValues('<K>a</K><X>1</X><K>b</K>', 'K')).toEqual(['a', 'b']);
  });
});
