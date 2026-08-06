/**
 * `.py` files import as their raw text, matching esbuild's `loader: {'.py':
 * 'text'}` in packages/cli/bundle.mjs.
 *
 * The point is not convenience. A Python program that lives in a .py file is
 * seen by ruff (lint + format); the same program in a TypeScript template
 * literal is invisible to every tool in this repo, which is how a 130-line
 * script grew a code-injection hole nobody could have linted.
 */
declare module '*.py' {
  const content: string;
  export default content;
}
