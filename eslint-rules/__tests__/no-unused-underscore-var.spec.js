/**
 * custom/no-unused-underscore-var.
 *
 * The one gap Biome's `noUnusedVariables` leaves open per
 * PLAN-biome-only-lint.md (H3a): Biome exempts every `_`-prefixed name
 * unconditionally, while this repo's real `@typescript-eslint/no-unused-vars`
 * config (`varsIgnorePattern: '^$'`) still flags an unused `_x` var/let/const.
 * Only function PARAMETERS are exempt (`argsIgnorePattern: '^_'`); a catch
 * parameter is not (ts-eslint v8 defaults to `caughtErrors: 'all'`), and nor
 * are functions, classes, imports and types. Every `invalid` case below is one
 * ts-eslint also reports, checked against the real rule by
 * .ci/cache/biome-parity/wave3/unused-wide.ts.
 */

export const ruleId = 'custom/no-unused-underscore-var';

export default async ({ sourceRuleTester, runCases }) => {
  const { noUnusedUnderscoreVar } = await import('../no-unused-underscore-var.js');

  return [
    runCases(sourceRuleTester(), ruleId, noUnusedUnderscoreVar, {
      valid: [
        // A non-underscore unused var is Biome's business, not this rule's.
        { code: 'const y = 1;\n' },
        // Read anywhere in the file counts, regardless of distance from the declaration.
        { code: 'const _used = 1;\nconsole.log(_used);\n' },
        // An unused function PARAMETER named `_x` is exempt (`argsIgnorePattern: '^_'`).
        { code: 'export function f(_a) {\n  return 1;\n}\n' },
        // A catch parameter that IS read.
        {
          code: 'export function f() {\n  try {\n    doThing();\n  } catch (_err) {\n    return _err;\n  }\n}\n',
        },
        // Shorthand object literal `{ _a }` reads `_a`.
        { code: 'export function g() {\n  const _a = 1;\n  return { _a };\n}\n' },
        // A read-modify-write whose result is used is a real read.
        { code: 'export function g() {\n  let _i = 0;\n  return (_i += 1);\n}\n' },
        // A write inside a loop can be read by the next iteration.
        { code: 'export function g() {\n  let _i = 0;\n  for (;;) {\n    _i = _i + 1;\n  }\n}\n' },
        // `for (k in o) return` is ESLint's historic exemption (eslint#2342).
        {
          code: 'export function g(o) {\n  for (const _k in o) return true;\n  return false;\n}\n',
        },
        // A class used only as a type is used; so is a type alias.
        { code: 'class _C {}\nexport let v: _C | undefined;\n', filename: 'probe.ts' },
        { code: 'type _T = string;\nexport const x: _T = "";\n', filename: 'probe.ts' },
        // An import used only under `typeof` is not reported (ts-eslint skips imports "only used as a type").
        {
          code: "import { X as _X } from './x';\nexport type T = typeof _X;\n",
          filename: 'probe.ts',
        },
        // A named function expression's and a class expression's own inner names are never reported.
        {
          code: 'export const f = function _inner() {\n  return 1;\n};\nexport const K = class _K {};\n',
        },
        // A JSX element name is a read.
        {
          code: 'const _Comp = () => null;\nexport const el = <_Comp />;\n',
          filename: 'probe.tsx',
        },
        // Direct children of a `declare module` are ambiently exported.
        {
          code: "declare module 'm' {\n  const _a: number;\n}\nexport const x = 1;\n",
          filename: 'probe.ts',
        },
        // `var` hoists out of the block to the function scope.
        { code: 'export function g() {\n  if (true) {\n    var _v = 1;\n  }\n  return _v;\n}\n' },
        // Exported bindings are read by whatever imports the module -- ESLint's own no-unused-vars never reports these, and neither does this rule.
        { code: 'export const _testing = { a: 1 };\n' },
        // `export { name }` reads the LOCAL name the same way a direct `export const` does.
        { code: 'const _x = 1;\nexport { _x };\n' },
        // Destructured and used.
        { code: 'const obj = { x: 1 };\nconst { x: _x } = obj;\nconsole.log(_x);\n' },
      ],
      invalid: [
        {
          code: 'const _unused = 1;\n',
          errors: [{ messageId: 'unused', data: { name: '_unused' } }],
        },
        {
          code: 'function f() {\n  let _tmp = 1;\n  return 2;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_tmp' } }],
        },
        {
          // Destructured and never read.
          code: 'const obj = { x: 1 };\nconst { x: _x } = obj;\n',
          errors: [{ messageId: 'unused', data: { name: '_x' } }],
        },
        {
          // One exported (exempt), one not (still an error) -- exporting one binding does not launder a sibling declaration.
          code: 'export const _testing = 1;\nconst _other = 2;\n',
          errors: [{ messageId: 'unused', data: { name: '_other' } }],
        },
        // verify3/unused-cmp.ts: the eleven cases the wave-2 rule missed.
        {
          // A member read `o._a` is not a read of the binding `_a`.
          code: 'export function g(o) {\n  const _a = 1;\n  return o._a;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_a' } }],
        },
        {
          // Nor is an object KEY named `_a`.
          code: 'export function g() {\n  const _a = 1;\n  return { _a: 2 };\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_a' } }],
        },
        {
          // Shorthand destructure: the key is not a read, `_b` is simply unused.
          code: 'export function g(o) {\n  const { a, _b } = o;\n  return a;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_b' } }],
        },
        {
          // A same-named inner binding shadows; its read does not reach the outer `_a`.
          code: 'export function g() {\n  const _a = 1;\n  function f() {\n    const _a = 2;\n    return _a;\n  }\n  return f;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_a' } }],
        },
        {
          // Write-only.
          code: 'export function g() {\n  let _a;\n  _a = 1;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_a' } }],
        },
        {
          // A self-reference from inside its own function body is not a use.
          code: 'export function g() {\n  const _f = () => _f();\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_f' } }],
        },
        {
          // `typeof _a` in a type is "only used as a type".
          code: 'export function g() {\n  const _a = 1;\n  type T = typeof _a;\n  const t: T = 1;\n  return t;\n}\n',
          filename: 'probe.ts',
          errors: [{ messageId: 'unused', data: { name: '_a' } }],
        },
        {
          // ts-eslint v8 defaults to caughtErrors: 'all', and no caughtErrorsIgnorePattern is set.
          code: 'export function g() {\n  try {\n    g();\n  } catch (_e) {\n    return 1;\n  }\n  return 0;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_e' } }],
        },
        {
          code: 'function _helper() {\n  return 1;\n}\nexport const x = 1;\n',
          errors: [{ messageId: 'unused', data: { name: '_helper' } }],
        },
        {
          code: "import { join as _join } from 'node:path';\nexport const x = 1;\n",
          errors: [{ messageId: 'unused', data: { name: '_join' } }],
        },
        {
          code: 'class _C {}\nexport const x = 1;\n',
          errors: [{ messageId: 'unused', data: { name: '_C' } }],
        },
        {
          // A class referenced only from its own body.
          code: 'class _C {\n  static make() {\n    return new _C();\n  }\n}\nexport const x = 1;\n',
          errors: [{ messageId: 'unused', data: { name: '_C' } }],
        },
        {
          // Update-only: `_i++` as a statement feeds nothing but itself.
          code: 'export function g() {\n  let _i = 0;\n  _i++;\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_i' } }],
        },
        {
          code: 'export function g(xs) {\n  for (const _x of xs) {\n    g(xs);\n  }\n}\n',
          errors: [{ messageId: 'unused', data: { name: '_x' } }],
        },
        {
          code: 'type _T = string;\ninterface _I {\n  next: _I;\n}\nexport function g<_P>() {\n  return 1;\n}\n',
          filename: 'probe.ts',
          errors: [
            { messageId: 'unused', data: { name: '_T' } },
            { messageId: 'unused', data: { name: '_I' } },
            { messageId: 'unused', data: { name: '_P' } },
          ],
        },
        {
          code: 'enum _E {\n  A,\n}\nnamespace _N {\n  export const a = 1;\n}\nexport const x = 1;\n',
          filename: 'probe.ts',
          errors: [
            { messageId: 'unused', data: { name: '_E' } },
            { messageId: 'unused', data: { name: '_N' } },
          ],
        },
      ],
    }),
  ];
};
