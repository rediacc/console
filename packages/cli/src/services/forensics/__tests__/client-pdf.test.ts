/**
 * The PDF leg of `downloadReport` (review 4606b6bb.1): the `/pdf-base64` answer decodes only when
 * it is canonical base64 of a whole PDF. A corrupted, truncated or non-string body is a clear
 * report error, never a short or wrong file written with exit 0.
 */
import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import { ForensicsClient, type ForensicsFetch } from '../client.js';

const PDF = Buffer.from(
  `%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n${'x'.repeat(2000)}\ntrailer\n<<>>\n%%EOF\n`,
  'latin1'
);
const GOOD = PDF.toString('base64');

function clientAnswering(body: unknown): ForensicsClient {
  const fetchFn = ((path: string) =>
    Promise.resolve(path.endsWith('/pdf-base64') ? body : {})) as ForensicsFetch;
  return new ForensicsClient(fetchFn);
}

const download = (body: unknown) =>
  clientAnswering(body).downloadReport('incident-1', 'report-1', 'pdf');

describe('downloadReport pdf', () => {
  it('decodes canonical base64 of a whole PDF to the same bytes (control)', async () => {
    const bytes = await download({ fileName: 'r.pdf', base64: GOOD });
    expect(Buffer.from(bytes as Uint8Array).equals(PDF)).toBe(true);
  });

  it.each([
    ['a character outside the alphabet', `${GOOD.slice(0, 40)}*${GOOD.slice(41)}`],
    ['whitespace inside the body', `${GOOD.slice(0, 40)}\n${GOOD.slice(40)}`],
    ['a cut that is no multiple of 4', GOOD.slice(0, -3)],
    ['a cut on a 4-character boundary that drops the end-of-file marker', GOOD.slice(0, -40)],
    ['bytes that are no PDF', Buffer.from('<html>not a pdf</html>').toString('base64')],
    ['an empty string', ''],
  ])('refuses %s', async (_label, base64) => {
    await expect(download({ fileName: 'r.pdf', base64 })).rejects.toBeInstanceOf(CliExitError);
  });

  it.each([
    ['a number', 42],
    ['a missing field', undefined],
    ['null', null],
  ])(
    'refuses a base64 field that is %s with a report error, not a TypeError',
    async (_l, value) => {
      await expect(download({ fileName: 'r.pdf', base64: value })).rejects.toBeInstanceOf(
        CliExitError
      );
    }
  );

  it('refuses a null body', async () => {
    await expect(download(null)).rejects.toBeInstanceOf(CliExitError);
  });

  it('names the report in the error', async () => {
    await expect(download({ base64: 'AAAA' })).rejects.toThrow(/report-1/);
  });
});
