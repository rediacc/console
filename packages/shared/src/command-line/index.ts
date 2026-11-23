/**
 * The console command line core: pure functions over a CliContract and a
 * ResourceSource, shared by the web command box, the panel prompt, Cmd+K
 * command mode, recipes and `rdc __complete`.
 */
export { complete, matchRank, type Suggestion, type SuggestionKind } from './complete.js';
export {
  editDistance,
  findFlag,
  GLOBAL_OPTIONS,
  nearest,
  optionKinds,
  positionalKinds,
  shellQuote,
} from './contract-index.js';
export { type Diagnostic, type DiagnosticCode, diagnose } from './diagnose.js';
export { HistoryCursor } from './history.js';
export {
  type ParsedFlag,
  type ParsedLine,
  type ParsedPositional,
  parse,
} from './parse.js';
export {
  fillVariables,
  type ParsedRecipe,
  parseRecipe,
  type RecipeProblem,
  type RecipeProblemCode,
  type RecipeStep,
  type RecipeVariable,
  renderStep,
} from './recipe.js';
export {
  analyze,
  type CommandLineEnv,
  type LineState,
  type ResourceContext,
  type ResourceSource,
} from './state.js';
export { isFlagLike, type QuoteChar, type Token, tokenize, unclosedQuote } from './tokenize.js';
