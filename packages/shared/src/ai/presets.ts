/**
 * Provider presets (D4 of PLAN-console-ai-providers).
 *
 * A preset fixes the wire format, the auth scheme, a base URL template and the
 * default capability flags of a well-known endpoint. The model stays free text
 * with a suggested default. A template may hold `{placeholders}` (an account id,
 * a self-hosted host name); each declares the pattern its value must match, so a
 * substituted value can never add path, query or credential text.
 */
import type { AuthScheme, Capabilities, Profile, ProfileFormat } from './profile.js';
import { WK_OPENAI_API_BASE } from '../config/well-known.generated.js';
import { type ProfileIssue, validateProfile } from './profile.js';

export interface PresetPlaceholder {
  name: string;
  label: string;
  pattern: RegExp;
}

export interface Preset {
  id: string;
  label: string;
  format: ProfileFormat;
  authScheme: AuthScheme;
  /** Base URL with `{name}` placeholders, each declared in `placeholders`. */
  baseURLTemplate: string;
  placeholders: readonly PresetPlaceholder[];
  suggestedModel: string;
  capabilities: Capabilities;
  /** The gateway holds the provider key; the profile carries no `key`. */
  byokOnly?: boolean;
  /** Header names the endpoint needs the operator to fill in, as a hint for the form. */
  headerHints?: readonly string[];
}

const ALL: Capabilities = { tools: true, streaming: true, parallelToolCalls: true, vision: true };
const ACCOUNT_SEGMENT = /^[A-Za-z0-9_-]{1,64}$/;
const PUBLIC_HOST =
  /^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*(?::\d{1,5})?$/;

export const PRESETS: readonly Preset[] = [
  {
    id: 'anthropic',
    label: 'Anthropic',
    format: 'anthropic-messages',
    authScheme: 'x-api-key',
    baseURLTemplate: 'https://api.anthropic.com/v1',
    placeholders: [],
    suggestedModel: 'claude-sonnet-5-5',
    capabilities: ALL,
  },
  {
    id: 'openai',
    label: 'OpenAI',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: WK_OPENAI_API_BASE,
    placeholders: [],
    suggestedModel: 'gpt-4.1',
    capabilities: ALL,
  },
  {
    id: 'gemini',
    label: 'Google Gemini (OpenAI-compatible endpoint)',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://generativelanguage.googleapis.com/v1beta/openai',
    placeholders: [],
    suggestedModel: 'gemini-2.5-pro',
    capabilities: ALL,
  },
  {
    id: 'mistral',
    label: 'Mistral',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://api.mistral.ai/v1',
    placeholders: [],
    suggestedModel: 'mistral-large-latest',
    capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: false },
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://api.deepseek.com/v1',
    placeholders: [],
    suggestedModel: 'deepseek-chat',
    capabilities: { tools: true, streaming: true, parallelToolCalls: false, vision: false },
  },
  {
    id: 'cloudflare-ai-gateway',
    label: 'Cloudflare AI Gateway (BYOK)',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://gateway.ai.cloudflare.com/v1/{accountId}/{gatewayId}/compat',
    placeholders: [
      { name: 'accountId', label: 'Cloudflare account id', pattern: ACCOUNT_SEGMENT },
      { name: 'gatewayId', label: 'Gateway id', pattern: ACCOUNT_SEGMENT },
    ],
    suggestedModel: 'anthropic/claude-sonnet-4-5',
    capabilities: ALL,
    byokOnly: true,
    headerHints: ['cf-aig-authorization'],
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://openrouter.ai/api/v1',
    placeholders: [],
    suggestedModel: 'anthropic/claude-sonnet-4.5',
    capabilities: ALL,
  },
  {
    id: 'vercel-ai-gateway',
    label: 'Vercel AI Gateway',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://ai-gateway.vercel.sh/v1',
    placeholders: [],
    suggestedModel: 'anthropic/claude-sonnet-4.5',
    capabilities: ALL,
  },
  {
    id: 'litellm',
    label: 'LiteLLM proxy (self-hosted, public https)',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://{host}/v1',
    placeholders: [{ name: 'host', label: 'Host name of the proxy', pattern: PUBLIC_HOST }],
    suggestedModel: 'gpt-4.1',
    capabilities: ALL,
  },
  {
    id: 'portkey',
    label: 'Portkey gateway',
    format: 'openai-chat',
    authScheme: 'bearer',
    baseURLTemplate: 'https://{host}/v1',
    placeholders: [
      { name: 'host', label: 'Gateway host (api.portkey.ai when hosted)', pattern: PUBLIC_HOST },
    ],
    suggestedModel: 'gpt-4.1',
    capabilities: ALL,
    headerHints: ['x-portkey-api-key', 'x-portkey-provider'],
  },
];

export function getPreset(id: string): Preset | undefined {
  return PRESETS.find((p) => p.id === id);
}

export interface PresetInput {
  /** Values for the preset's placeholders. */
  params?: Record<string, string>;
  key?: string;
  /** Model name; the preset's suggested model when omitted. */
  model?: string;
  headers?: Record<string, string>;
}

export type PresetBuild = { ok: true; profile: Profile } | { ok: false; issues: ProfileIssue[] };

/** Substitute the preset's placeholders into its template, reporting every missing or malformed value. */
function fillTemplate(
  preset: Preset,
  params: Record<string, string> | undefined
): { baseURL: string; issues: ProfileIssue[] } {
  const issues: ProfileIssue[] = [];
  let baseURL = preset.baseURLTemplate;
  for (const placeholder of preset.placeholders) {
    const value = params?.[placeholder.name];
    if (value !== undefined && placeholder.pattern.test(value)) {
      baseURL = baseURL.replaceAll(`{${placeholder.name}}`, value);
      continue;
    }
    issues.push({
      path: `/params/${placeholder.name}`,
      message:
        value === undefined
          ? `${placeholder.label} is required`
          : `${placeholder.label} has characters a ${placeholder.name} cannot hold`,
    });
  }
  return { baseURL, issues };
}

/** Fill a preset into a validated profile. Every problem is returned, none is guessed around. */
export function buildProfile(presetId: string, input: PresetInput = {}): PresetBuild {
  const preset = getPreset(presetId);
  if (!preset) {
    return { ok: false, issues: [{ path: '/preset', message: `unknown preset "${presetId}"` }] };
  }
  const { baseURL, issues } = fillTemplate(preset, input.params);
  if (issues.length > 0) return { ok: false, issues };

  return validateProfile({
    format: preset.format,
    baseURL,
    ...(input.key === undefined ? {} : { key: input.key }),
    authScheme: preset.authScheme,
    model: input.model ?? preset.suggestedModel,
    ...(input.headers === undefined ? {} : { headers: input.headers }),
    capabilities: preset.capabilities,
    preset: preset.id,
    ...(preset.byokOnly ? { byokOnly: true } : {}),
  });
}
