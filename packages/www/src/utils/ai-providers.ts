/**
 * The Ask Assistant provider table, in ONE place.
 *
 * Adding a provider is one entry here; the docs page-actions menu renders whatever this
 * table holds. ZERO API SPEND is the operator-locked constraint: every entry deep-links
 * the prompt into the USER'S OWN provider account via a prefill URL, and nothing here
 * may ever call a model API or send anything to our servers.
 *
 * `urlTemplate` is data rather than a function on purpose: the menu is rendered by an
 * Astro component and acted on by an inline script, so the contract has to survive being
 * serialized into a data attribute. `{q}` is replaced with the URL-ENCODED prompt.
 *
 * Prefill parameters are undocumented vendor surface and can be dropped without notice
 * (one source says Claude web's `q` was removed in Oct 2025; it could not be verified
 * headlessly because both providers serve a Cloudflare challenge to automation). The
 * menu therefore ALWAYS copies the prompt to the clipboard before opening the provider,
 * so a dead parameter degrades to paste instead of to a broken feature.
 *
 * Deliberately absent, do not add without revisiting the reasons:
 * - Microsoft Copilot: its prefill URL auto-executes with no user interaction, which is
 *   CVE-2026-24307. Excluded even though it works.
 * - Gemini, AI Studio, Mistral: no native prefill URL exists.
 */
export interface AiProviderDef {
  /** Stable identifier, also the localStorage value for the last-used provider. */
  id: string;
  /** Product name, shown as-is in every locale. Never translated. */
  label: string;
  /** Absolute URL template; `{q}` is replaced with the URL-encoded prompt. */
  urlTemplate: string;
}

export const AI_PROVIDERS: readonly AiProviderDef[] = [
  {
    id: 'chatgpt',
    label: 'ChatGPT',
    urlTemplate: 'https://chatgpt.com/?q={q}',
  },
  {
    id: 'claude',
    label: 'Claude',
    urlTemplate: 'https://claude.ai/new?q={q}',
  },
];

/** localStorage key remembering the reader's last-used provider. */
export const AI_PROVIDER_STORAGE_KEY = 'rediacc_docs_ask_provider';
