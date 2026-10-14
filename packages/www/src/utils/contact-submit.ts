/** Shared network and analytics half of the two contact forms (page form and modal). */

/** POST the contact payload; throws the server's error text, or `fallbackError` when it sent none. */
async function postContact(payload: Record<string, unknown>, fallbackError: string): Promise<void> {
  const res = await fetch(`${window.location.origin}/account/api/v1/contact/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.error ?? fallbackError);
  }
}

/** Report a successful submission to Plausible, carrying the UTM props and the last solution seen. */
function trackContactSubmit(subject: string, source: string): void {
  const utm = window.__pa_get_utm?.() ?? {};
  const lastSolution = sessionStorage.getItem('__pa_last_solution') ?? undefined;
  window.plausible?.('contact_submit', {
    props: {
      subject,
      source,
      ...utm,
      ...(lastSolution && { last_solution: lastSolution }),
    },
  });
}

export interface ContactSubmission {
  name: string;
  email: string;
  subject: string;
  message: string;
  lang: string;
  /** Raw honeypot value; an empty string is dropped from the payload, as the server expects. */
  honeypot: string | undefined;
  /** Raw captcha token; null is dropped from the payload. */
  turnstileToken: string | null | undefined;
}

/**
 * Send the submission, run `onSuccess` once the server accepted it, then report it to analytics.
 * A failure is handed to `onFailure` as the message the visitor should see.
 */
export async function sendContact(
  submission: ContactSubmission,
  source: string,
  fallbackError: string,
  handlers: { onSuccess: () => void; onFailure: (message: string) => void }
): Promise<void> {
  const { honeypot, turnstileToken, ...fields } = submission;
  try {
    await postContact(
      {
        ...fields,
        source,
        company_url: honeypot === '' ? undefined : honeypot,
        turnstileToken: turnstileToken ?? undefined,
      },
      fallbackError
    );
    handlers.onSuccess();
    trackContactSubmit(fields.subject, source);
  } catch (err) {
    handlers.onFailure(err instanceof Error ? err.message : fallbackError);
  }
}
