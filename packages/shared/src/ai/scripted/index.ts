/** The deterministic AI scripts CI uses in place of a real provider (C42, AP13). */
export {
  SCRIPTED_PROVIDER_ERROR_CODE,
  type ScriptModelPart,
  scriptModelSteps,
  scriptNdjson,
  scriptStreamLines,
} from './render.js';
export {
  type AiScript,
  getScript,
  isScriptId,
  pickScript,
  SCRIPT_IDS,
  SCRIPT_MESSAGE_PREFIX,
  SCRIPTED_LATENCY_MS,
  type ScriptedSmokeResult,
  type ScriptId,
  type ScriptPart,
  type ScriptProviderError,
  type ScriptStep,
  type ScriptToolOutcome,
} from './scripts.js';
