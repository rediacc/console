import { describe, expect, it } from 'vitest';
import { FORENSICS_TIMELINE_PATH, forensicsTimelinePath } from '../links.js';

const GUID = 'aaaaaaaa-1111-4111-8111-111111111111';

describe('forensicsTimelinePath', () => {
  it('opens a 2-hour window centred on the detection time', () => {
    const path = forensicsTimelinePath(GUID, '2026-11-25T10:00:00.000Z');
    const url = new URL(path, 'https://account.example');
    expect(url.pathname).toBe(FORENSICS_TIMELINE_PATH);
    expect(url.searchParams.get('repo')).toBe(GUID);
    expect(url.searchParams.get('from')).toBe('2026-11-25T09:00:00.000Z');
    expect(url.searchParams.get('to')).toBe('2026-11-25T11:00:00.000Z');
  });

  it('control: an unparsable time keeps the repository and drops the window', () => {
    expect(forensicsTimelinePath(GUID, 'not a date')).toBe(
      `${FORENSICS_TIMELINE_PATH}?repo=${GUID}`
    );
  });
});
