/**
 * AI provider profiles: schema, presets, base URL guard and resolution. Pure and
 * runtime-free, so the account web, the CLI executor and the workers share it.
 */
export {
  type BaseUrlCheck,
  type BaseUrlRefusal,
  validateBaseUrl,
} from './base-url.js';
export {
  buildProfile,
  getPreset,
  PRESETS,
  type Preset,
  type PresetBuild,
  type PresetInput,
  type PresetPlaceholder,
} from './presets.js';
export {
  type AiConfig,
  AiConfigSchema,
  AUTH_SCHEMES,
  type AuthScheme,
  type Capabilities,
  CapabilitiesSchema,
  PROFILE_FORMATS,
  type Profile,
  type ProfileCheck,
  type ProfileFormat,
  type ProfileIssue,
  ProfileSchema,
  validateProfile,
} from './profile.js';
export {
  type AiConfigs,
  type ProfileSource,
  type ResolvedProfile,
  type ResolveFailure,
  resolveProfile,
} from './resolve.js';
