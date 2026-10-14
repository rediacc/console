import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { type ContactSubmission, sendContact } from '../contact-submit';

const submission: ContactSubmission = {
  name: 'Ada',
  email: 'ada@example.test',
  subject: 'Pricing',
  message: 'Hello',
  lang: 'en',
  honeypot: '',
  turnstileToken: null,
};

const plausible = vi.fn();

function stubBrowser(response: { ok: boolean; body?: unknown }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: response.ok,
    json: () =>
      response.body === undefined
        ? Promise.reject(new Error('no body'))
        : Promise.resolve(response.body),
  });
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('window', {
    location: { origin: 'https://site.test' },
    plausible,
    __pa_get_utm: () => ({ utm_source: 'news' }),
  });
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => (key === '__pa_last_solution' ? 'backup' : null),
  });
  return fetchMock;
}

describe('sendContact', () => {
  beforeEach(() => plausible.mockClear());
  afterEach(() => vi.unstubAllGlobals());

  it('drops an empty honeypot and a null token from the payload, then reports success and analytics', async () => {
    const fetchMock = stubBrowser({ ok: true });
    const handlers = { onSuccess: vi.fn(), onFailure: vi.fn() };
    await sendContact(submission, 'contact-page', 'fallback', handlers);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://site.test/account/api/v1/contact/submit');
    const sent = JSON.parse(init.body);
    expect(sent).toMatchObject({ name: 'Ada', source: 'contact-page' });
    expect(sent).not.toHaveProperty('company_url');
    expect(sent).not.toHaveProperty('turnstileToken');
    expect(handlers.onSuccess).toHaveBeenCalledOnce();
    expect(handlers.onFailure).not.toHaveBeenCalled();
    expect(plausible).toHaveBeenCalledWith('contact_submit', {
      props: {
        subject: 'Pricing',
        source: 'contact-page',
        utm_source: 'news',
        last_solution: 'backup',
      },
    });
  });

  it('keeps a filled honeypot and a real token in the payload', async () => {
    const fetchMock = stubBrowser({ ok: true });
    await sendContact({ ...submission, honeypot: 'bot', turnstileToken: 'tok' }, 's', 'fallback', {
      onSuccess: vi.fn(),
      onFailure: vi.fn(),
    });
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent).toMatchObject({ company_url: 'bot', turnstileToken: 'tok' });
  });

  it('hands the server error text to onFailure and sends no analytics', async () => {
    stubBrowser({ ok: false, body: { error: 'Too many requests' } });
    const handlers = { onSuccess: vi.fn(), onFailure: vi.fn() };
    await sendContact(submission, 's', 'fallback', handlers);
    expect(handlers.onFailure).toHaveBeenCalledWith('Too many requests');
    expect(handlers.onSuccess).not.toHaveBeenCalled();
    expect(plausible).not.toHaveBeenCalled();
  });

  it('falls back to the given message when the failure body is not JSON', async () => {
    stubBrowser({ ok: false });
    const handlers = { onSuccess: vi.fn(), onFailure: vi.fn() };
    await sendContact(submission, 's', 'fallback', handlers);
    expect(handlers.onFailure).toHaveBeenCalledWith('fallback');
  });
});
