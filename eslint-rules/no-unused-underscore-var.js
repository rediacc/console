/**
 * custom/no-unused-underscore-var -- flags an UNUSED binding whose name starts
 * with `_`, with the same verdict `@typescript-eslint/no-unused-vars` reaches
 * under this repo's options.
 *
 * WHY THIS RULE EXISTS AT ALL, GIVEN BIOME ALREADY HAS `noUnusedVariables`.
 * Biome's `correctness/noUnusedVariables` (and `noUnusedFunctionParameters`)
 * exempt every `_`-prefixed name UNCONDITIONALLY -- an underscore is Biome's
 * own "deliberately unused" convention. This repo's real
 * `@typescript-eslint/no-unused-vars` config (`eslint.config/typescript.js:172-176`)
 * draws that line in a different place:
 *
 *   argsIgnorePattern: '^_'   -- an unused function ARGUMENT named `_x` is fine
 *   varsIgnorePattern: '^$'   -- but a pattern that matches only the empty
 *                                string ignores NO variable, so an unused
 *                                `_x` is still an error: "STRICT: No underscore
 *                                prefix allowed - if unused, delete it."
 *   caughtErrors: 'all'       -- the ts-eslint v8 DEFAULT, and no
 *                                `caughtErrorsIgnorePattern` is set, so an
 *                                unused `catch (_e)` is an error too.
 *
 * So everything except a function PARAMETER is in scope: var/let/const
 * (including destructured and for-in/of bindings), catch parameters, function
 * and class declarations, imports, enums, namespaces, type aliases, interfaces
 * and type parameters. Biome flags only the `import { x as _y }` case of those
 * (verified in .ci/cache/biome-parity/verify3/bio/), so the rest is the gap
 * this rule closes.
 *
 * HOW "USED" IS DECIDED. A small scope analyser below builds the same model
 * `@typescript-eslint/scope-manager` does: scopes (module, function, block,
 * for, switch, catch, class, class-field-initializer, static block, enum,
 * namespace, and the TS type scopes), variables with their definitions, and
 * references that are each read and/or write and resolved by name up the
 * scope chain in the value or the type namespace. `isUsedVariable` is then a
 * port of ts-eslint's own `collectUnusedVariables.js` verdict:
 *   - a write is not a use (`let _a; _a = 1`), and neither is a read that
 *     only feeds its own update (`_a++`, `_a += 1`, `_a = _a + 1`);
 *   - a reference from inside the variable's own function is not a use
 *     (`const _f = () => _f()`), nor from inside its own type, enum or
 *     namespace declaration;
 *   - `typeof _a` in a type position is not a use of a value (ts-eslint's
 *     "only used as a type"), except for an import, which is then not
 *     reported at all;
 *   - a member read `o._a`, an object key `{ _a: 1 }` and a shorthand
 *     destructure key `{ a, _b } = o` are not references to anything;
 *   - an exported binding, a class's or named function expression's own
 *     inner name, an enum member, a mapped-type key, a signature parameter,
 *     and the direct children of an ambient (`declare`, `.d.ts`) module are
 *     always used; so is a for-in/of binding whose body is a lone `return`.
 * Every case is pinned twice: in the unit spec, and against the real ts-eslint
 * rule by `.ci/cache/biome-parity/verify3/unused-cmp.ts` (the 13 cases that
 * found the wave-2 gaps) and `.ci/cache/biome-parity/wave3/unused-wide.ts`
 * (100 cases, plus every tracked JS/TS file in the console tree and the
 * account submodule compared with NO name filter: 2033 files, 73 findings on
 * each side, 0 files differing, as of 2026-09-24).
 */

import { visitorKeys as jsVisitorKeys } from 'oxc-parser';

const KEYS = /** @type {Record<string, string[]>} */ (/** @type {unknown} */ (jsVisitorKeys));

const FUNCTION_NODE_TYPES = new Set([
  'FunctionDeclaration',
  'FunctionExpression',
  'ArrowFunctionExpression',
]);
const LOOP_TYPES = new Set([
  'ForStatement',
  'ForInStatement',
  'ForOfStatement',
  'WhileStatement',
  'DoWhileStatement',
]);
const LOGICAL_ASSIGNMENT_OPERATORS = new Set(['??=', '&&=', '||=']);
const MERGEABLE_TYPES = new Set([
  'ClassDeclaration',
  'FunctionDeclaration',
  'TSInterfaceDeclaration',
  'TSModuleDeclaration',
  'TSTypeAliasDeclaration',
]);
/** Definition kinds that live only in the type namespace; every other kind is a value (class, enum, namespace and import are both). */
const TYPE_ONLY_DEFS = new Set(['Type']);
const VALUE_ONLY_DEFS = new Set(['Variable', 'FunctionName', 'CatchClause', 'Parameter']);
const TYPE_NODE_RE =
  /^TS.*(Type|TypeAnnotation|TypeReference|TypeLiteral|TypeParameterInstantiation|TypeParameterDeclaration|InterfaceHeritage|ClassImplements|InterfaceBody|TypeOperator|TypePredicate|PropertySignature|IndexSignature)$/;
/** Nodes with nothing that can reference a binding. */
const OPAQUE_TYPES = new Set([
  'BreakStatement',
  'ContinueStatement',
  'MetaProperty',
  'ExportAllDeclaration',
  'TSNamespaceExportDeclaration',
  'JSXClosingElement',
  'JSXNamespacedName',
  'TSEnumMember',
]);

/** oxc keeps `ParenthesizedExpression`; ESTree (and so ESLint's verdicts) has none. */
function parentOf(node) {
  let parent = node.parent;
  while (parent?.type === 'ParenthesizedExpression') parent = parent.parent;
  return parent;
}

function isInside(inner, outer) {
  return inner.range[0] >= outer.range[0] && inner.range[1] <= outer.range[1];
}

function isNode(value) {
  return !!value && typeof value === 'object' && typeof value.type === 'string';
}

/** ts-eslint's `hasOverridingExportStatement`: an explicit export list turns off the ambient "everything is exported" rule. */
function isOverridingExport(s) {
  if (s.type === 'ExportAllDeclaration' || s.type === 'TSExportAssignment') return true;
  if (s.type === 'ExportNamedDeclaration') return s.declaration == null;
  return s.type === 'ExportDefaultDeclaration' && s.declaration?.type === 'Identifier';
}

function hasOverridingExportStatement(statements) {
  return statements.some(isOverridingExport);
}

function refFitsVariable(ref, variable) {
  if (ref.kind === 'any') return true;
  const kinds = variable.defs.map((d) => d.type);
  const onlyIn = ref.kind === 'type' ? VALUE_ONLY_DEFS : TYPE_ONLY_DEFS;
  return !kinds.every((k) => onlyIn.has(k));
}

/** The identifier leaves of a binding pattern, with the non-leaf parts (defaults, computed keys, annotations) handed back to be walked as reads. */
const PATTERN_HANDLERS = {
  Identifier(a, pattern, walkScope, onLeaf, ctx) {
    onLeaf(pattern);
    a.walkType(pattern.typeAnnotation, walkScope, ctx);
    a.walkAll(pattern.decorators, walkScope, ctx);
  },
  ObjectPattern(a, pattern, walkScope, onLeaf, ctx) {
    for (const prop of pattern.properties ?? []) {
      if (prop.type === 'RestElement') {
        a.declarePattern(prop.argument, walkScope, onLeaf, ctx);
        continue;
      }
      if (prop.computed) a.walk(prop.key, walkScope, ctx);
      a.declarePattern(prop.value, walkScope, onLeaf, ctx);
    }
    a.walkType(pattern.typeAnnotation, walkScope, ctx);
  },
  ArrayPattern(a, pattern, walkScope, onLeaf, ctx) {
    for (const el of pattern.elements ?? []) a.declarePattern(el, walkScope, onLeaf, ctx);
    a.walkType(pattern.typeAnnotation, walkScope, ctx);
  },
  AssignmentPattern(a, pattern, walkScope, onLeaf, ctx) {
    a.declarePattern(pattern.left, walkScope, onLeaf, ctx);
    a.walk(pattern.right, walkScope, ctx);
  },
  RestElement(a, pattern, walkScope, onLeaf, ctx) {
    a.declarePattern(pattern.argument, walkScope, onLeaf, ctx);
    a.walkType(pattern.typeAnnotation, walkScope, ctx);
  },
  TSParameterProperty(a, pattern, walkScope, onLeaf, ctx) {
    a.walkAll(pattern.decorators, walkScope, ctx);
    a.declarePattern(pattern.parameter, walkScope, onLeaf, ctx);
  },
};

/** One handler per node type whose children are not all plain reads; everything else falls through to `walkChildren`. */
const HANDLERS = {
  Identifier(a, node, scope, ctx) {
    if (node.name === 'undefined' && !ctx.type) return;
    a.addRef(node, scope, {
      read: true,
      kind: ctx.type ? 'type' : 'value',
      typeQuery: !!ctx.typeQuery,
    });
  },
  VariableDeclaration: (a, node, scope, ctx) => a.walkVariableDeclaration(node, scope, ctx),
  FunctionDeclaration: (a, node, scope, ctx) => a.walkFunctionDeclaration(node, scope, ctx),
  TSDeclareFunction: (a, node, scope, ctx) => a.walkFunctionDeclaration(node, scope, ctx),
  FunctionExpression: (a, node, scope, ctx) => a.walkFunction(node, scope, ctx),
  ArrowFunctionExpression: (a, node, scope, ctx) => a.walkFunction(node, scope, ctx),
  TSEmptyBodyFunctionExpression: (a, node, scope, ctx) => a.walkFunction(node, scope, ctx),
  ClassDeclaration: (a, node, scope, ctx) => a.walkClass(node, scope, ctx),
  ClassExpression: (a, node, scope, ctx) => a.walkClass(node, scope, ctx),
  MethodDefinition: (a, node, scope, ctx) => a.walkMethod(node, scope, ctx),
  TSAbstractMethodDefinition: (a, node, scope, ctx) => a.walkMethod(node, scope, ctx),
  PropertyDefinition: (a, node, scope, ctx) => a.walkField(node, scope, ctx),
  AccessorProperty: (a, node, scope, ctx) => a.walkField(node, scope, ctx),
  TSAbstractPropertyDefinition: (a, node, scope, ctx) => a.walkField(node, scope, ctx),
  TSAbstractAccessorProperty: (a, node, scope, ctx) => a.walkField(node, scope, ctx),
  StaticBlock(a, node, scope, ctx) {
    a.walkAll(node.body, a.newScope('class-static-block', node, scope, true), ctx);
  },
  TSPropertySignature(a, node, scope, ctx) {
    if (node.computed) a.walk(node.key, scope, ctx);
    a.walk(node.typeAnnotation, scope, ctx);
  },
  TSIndexSignature(a, node, scope, ctx) {
    for (const p of node.parameters ?? []) a.walk(p.typeAnnotation, scope, ctx);
    a.walk(node.typeAnnotation, scope, ctx);
  },
  TSFunctionType: (a, node, scope, ctx) => a.walkSignature(node, scope, ctx),
  TSConstructorType: (a, node, scope, ctx) => a.walkSignature(node, scope, ctx),
  TSCallSignatureDeclaration: (a, node, scope, ctx) => a.walkSignature(node, scope, ctx),
  TSConstructSignatureDeclaration: (a, node, scope, ctx) => a.walkSignature(node, scope, ctx),
  TSMethodSignature: (a, node, scope, ctx) => a.walkSignature(node, scope, ctx),
  BlockStatement(a, node, scope, ctx) {
    a.walkAll(node.body, a.newScope('block', node, scope), ctx);
  },
  ForStatement(a, node, scope, ctx) {
    const s = a.newScope('for', node, scope);
    for (const part of [node.init, node.test, node.update, node.body]) a.walk(part, s, ctx);
  },
  ForInStatement: (a, node, scope, ctx) => a.walkForInOf(node, scope, ctx),
  ForOfStatement: (a, node, scope, ctx) => a.walkForInOf(node, scope, ctx),
  SwitchStatement(a, node, scope, ctx) {
    a.walk(node.discriminant, scope, ctx);
    a.walkAll(node.cases, a.newScope('switch', node, scope), ctx);
  },
  CatchClause(a, node, scope, ctx) {
    const s = a.newScope('catch', node, scope);
    if (node.param)
      a.declarePattern(node.param, s, (id) => a.declare(s, id, 'CatchClause', node), ctx);
    a.walk(node.body, s, ctx);
  },
  AssignmentExpression(a, node, scope, ctx) {
    const left = node.left;
    if (left.type === 'Identifier')
      a.addRef(left, scope, { write: true, read: node.operator !== '=' });
    else if (left.type === 'ObjectPattern' || left.type === 'ArrayPattern')
      a.assignTargets(left, scope, ctx);
    else a.walk(left, scope, ctx);
    a.walk(node.right, scope, ctx);
  },
  UpdateExpression(a, node, scope, ctx) {
    if (node.argument.type === 'Identifier')
      a.addRef(node.argument, scope, { write: true, read: true });
    else a.walk(node.argument, scope, ctx);
  },
  MemberExpression(a, node, scope, ctx) {
    a.walk(node.object, scope, ctx);
    if (node.computed) a.walk(node.property, scope, ctx);
  },
  Property(a, node, scope, ctx) {
    if (node.computed) a.walk(node.key, scope, ctx);
    a.walk(node.value, scope, ctx);
  },
  LabeledStatement(a, node, scope, ctx) {
    a.walk(node.body, scope, ctx);
  },
  ImportDeclaration(a, node, scope) {
    for (const spec of node.specifiers ?? []) {
      a.declare(scope, spec.local, 'ImportBinding', spec, {
        typeImport: node.importKind === 'type' || spec.importKind === 'type',
      });
    }
  },
  TSImportEqualsDeclaration(a, node, scope, ctx) {
    a.declare(scope, node.id, 'ImportBinding', node, { typeImport: node.importKind === 'type' });
    if (node.moduleReference?.type !== 'TSExternalModuleReference')
      a.walk(node.moduleReference, scope, ctx);
  },
  ExportNamedDeclaration(a, node, scope, ctx) {
    if (node.declaration) {
      a.walk(node.declaration, scope, ctx);
      return;
    }
    if (node.source) return;
    for (const spec of node.specifiers ?? []) {
      if (spec.local?.type === 'Identifier')
        a.addRef(spec.local, scope, { read: true, kind: 'any' });
    }
  },
  ExportDefaultDeclaration(a, node, scope, ctx) {
    if (node.declaration?.type === 'Identifier')
      a.addRef(node.declaration, scope, { read: true, kind: 'any' });
    else a.walk(node.declaration, scope, ctx);
  },
  TSQualifiedName(a, node, scope, ctx) {
    a.walk(node.left, scope, ctx);
  },
  TSTypeQuery(a, node, scope, ctx) {
    a.walk(node.exprName, scope, { ...ctx, type: false, typeQuery: true });
    a.walkType(node.typeArguments, scope, ctx);
  },
  TSImportType(a, node, scope, ctx) {
    a.walkType(node.typeArguments, scope, ctx);
  },
  TSTypePredicate(a, node, scope, ctx) {
    a.walk(node.typeAnnotation, scope, ctx);
  },
  TSInterfaceDeclaration(a, node, scope, ctx) {
    a.declare(scope, node.id, 'Type', node, { ambient: a.ambientFor(node, ctx) });
    const s = a.newScope('type', node, scope);
    const tctx = { ...ctx, type: true };
    a.declareTypeParameters(node.typeParameters, s, tctx);
    a.walkAll(node.extends, s, tctx);
    a.walk(node.body, s, tctx);
  },
  TSTypeAliasDeclaration(a, node, scope, ctx) {
    a.declare(scope, node.id, 'Type', node, { ambient: a.ambientFor(node, ctx) });
    const s = a.newScope('type', node, scope);
    const tctx = { ...ctx, type: true };
    a.declareTypeParameters(node.typeParameters, s, tctx);
    a.walk(node.typeAnnotation, s, tctx);
  },
  TSEnumDeclaration(a, node, scope, ctx) {
    a.declare(scope, node.id, 'TSEnumName', node, { ambient: a.ambientFor(node, ctx) });
    const s = a.newScope('enum', node, scope);
    const members = node.body?.members ?? node.members ?? [];
    for (const m of members) a.declare(s, m.id, 'TSEnumMember', m, { neverReport: true });
    for (const m of members) {
      if (m.computed) a.walk(m.id, s, ctx);
      a.walk(m.initializer, s, ctx);
    }
  },
  TSModuleDeclaration: (a, node, scope, ctx) => a.walkModule(node, scope, ctx),
  TSConditionalType(a, node, scope, ctx) {
    const s = a.newScope('conditional', node, scope);
    for (const part of [node.checkType, node.extendsType, node.trueType]) a.walk(part, s, ctx);
    a.walk(node.falseType, scope, ctx);
  },
  TSInferType(a, node, scope, ctx) {
    a.declare(scope, node.typeParameter.name, 'Type', node.typeParameter);
    a.walk(node.typeParameter.constraint, scope, ctx);
  },
  TSMappedType(a, node, scope, ctx) {
    const s = a.newScope('mappedType', node, scope);
    a.declare(s, node.key ?? node.typeParameter?.name, 'Type', node, { neverReport: true });
    for (const part of [
      node.constraint ?? node.typeParameter?.constraint,
      node.nameType,
      node.typeAnnotation,
    ])
      a.walk(part, s, ctx);
  },
  JSXOpeningElement(a, node, scope, ctx) {
    a.referenceJsxName(node.name, scope);
    a.walkType(node.typeArguments, scope, ctx);
    a.walkAll(node.attributes, scope, ctx);
  },
  JSXAttribute(a, node, scope, ctx) {
    a.walk(node.value, scope, ctx);
  },
};
for (const type of OPAQUE_TYPES) HANDLERS[type] = () => undefined;

class ScopeAnalyzer {
  constructor(filename) {
    this.variables = [];
    this.references = [];
    this.forInOfLoops = [];
    this.isDefinitionFile = /\.d\.[cm]?ts$/.test(filename ?? '');
  }

  newScope(type, block, upper, isVariableScope = false) {
    const scope = { type, block, upper, set: new Map(), variableScope: null };
    scope.variableScope = isVariableScope || !upper ? scope : upper.variableScope;
    return scope;
  }

  declare(scope, id, defType, defNode, extra = {}) {
    if (id?.type !== 'Identifier') return;
    let variable = scope.set.get(id.name);
    if (!variable) {
      variable = {
        name: id.name,
        scope,
        defs: [],
        identifiers: [],
        references: [],
        used: false,
        neverReport: false,
      };
      scope.set.set(id.name, variable);
      this.variables.push(variable);
    }
    variable.defs.push({ type: defType, name: id, node: defNode, ...extra });
    variable.identifiers.push(id);
    if (extra.neverReport) variable.neverReport = true;
    if (extra.ambient) variable.used = true;
  }

  addRef(
    identifier,
    scope,
    { read = false, write = false, kind = 'value', typeQuery = false } = {}
  ) {
    this.references.push({ identifier, from: scope, read, write, kind, typeQuery, resolved: null });
  }

  walk(node, scope, ctx) {
    if (!isNode(node)) return;
    const nodeCtx = !ctx.type && TYPE_NODE_RE.test(node.type) ? { ...ctx, type: true } : ctx;
    const handler = HANDLERS[node.type];
    if (handler) handler(this, node, scope, nodeCtx);
    else this.walkChildren(node, scope, nodeCtx);
  }

  walkChildren(node, scope, ctx) {
    for (const key of KEYS[node.type] ?? []) {
      const value = node[key];
      if (Array.isArray(value)) this.walkAll(value, scope, ctx);
      else this.walk(value, scope, ctx);
    }
  }

  walkAll(nodes, scope, ctx) {
    for (const child of nodes ?? []) this.walk(child, scope, ctx);
  }

  walkType(node, scope, ctx) {
    this.walk(node, scope, { ...ctx, type: true });
  }

  declarePattern(pattern, walkScope, onLeaf, ctx) {
    if (!pattern) return;
    const handler = PATTERN_HANDLERS[pattern.type];
    // Anything else is an assignment target such as a member expression: an ordinary read of its parts.
    if (handler) handler(this, pattern, walkScope, onLeaf, ctx);
    else this.walk(pattern, walkScope, ctx);
  }

  /** Assignment-target leaves (not declarations): each one a write reference. */
  assignTargets(pattern, scope, ctx) {
    this.declarePattern(pattern, scope, (id) => this.addRef(id, scope, { write: true }), ctx);
  }

  nearestVariableScope(scope) {
    return scope.variableScope ?? scope;
  }

  /** A statement-level declaration is ambiently used when it is a direct child (possibly under `export`) of an ambient block. */
  ambientFor(node, ctx) {
    if (!ctx.ambient) return false;
    let parent = parentOf(node);
    if (parent?.type === 'ExportNamedDeclaration') parent = parentOf(parent);
    return ctx.ambientBlock === parent;
  }

  declareTypeParameters(decl, scope, ctx) {
    const params = decl?.params ?? [];
    for (const tp of params) this.declare(scope, tp.name, 'Type', tp);
    for (const tp of params) {
      this.walkType(tp.constraint, scope, ctx);
      this.walkType(tp.default, scope, ctx);
    }
  }

  walkVariableDeclaration(node, scope, ctx) {
    const ambient = this.ambientFor(node, ctx);
    const target = node.kind === 'var' ? this.nearestVariableScope(scope) : scope;
    const parent = parentOf(node);
    const isForInOf =
      (parent?.type === 'ForInStatement' || parent?.type === 'ForOfStatement') &&
      parent.left === node;
    for (const declarator of node.declarations) {
      const writes = !!declarator.init || isForInOf;
      this.declarePattern(
        declarator.id,
        scope,
        (id) => {
          this.declare(target, id, 'Variable', declarator, { parent: node, ambient });
          if (writes) this.addRef(id, scope, { write: true });
        },
        ctx
      );
      this.walk(declarator.init, scope, ctx);
    }
  }

  walkFunctionDeclaration(node, scope, ctx) {
    const ambient = node.type === 'TSDeclareFunction' && this.ambientFor(node, ctx);
    this.declare(scope, node.id, 'FunctionName', node, { ambient });
    this.walkFunction(node, scope, ctx);
  }

  walkFunction(node, scope, ctx) {
    let fnParentScope = scope;
    if (node.type === 'FunctionExpression' && node.id) {
      fnParentScope = this.newScope('function-expression-name', node, scope);
      this.declare(fnParentScope, node.id, 'FunctionName', node, { neverReport: true });
    }
    const fnScope = this.newScope('function', node, fnParentScope, true);
    this.declareTypeParameters(node.typeParameters, fnScope, ctx);
    // A body-less signature's parameters can never be read, so they are never reported (ts-eslint's visitFunctionTypeSignature).
    const neverReport = !node.body;
    for (const param of node.params ?? []) {
      this.declarePattern(
        param,
        fnScope,
        (id) => this.declareParameter(fnScope, id, node, neverReport),
        ctx
      );
    }
    this.walkType(node.returnType, fnScope, ctx);
    if (node.body?.type === 'BlockStatement') this.walkAll(node.body.body, fnScope, ctx);
    else this.walk(node.body, fnScope, ctx);
  }

  declareParameter(scope, id, fn, neverReport) {
    if (id.name !== 'this') this.declare(scope, id, 'Parameter', fn, { neverReport });
  }

  walkSignature(node, scope, ctx) {
    const sigScope = this.newScope('function-type', node, scope);
    if (node.computed) this.walk(node.key, scope, ctx);
    this.declareTypeParameters(node.typeParameters, sigScope, ctx);
    const tctx = { ...ctx, type: true };
    for (const param of node.params ?? []) {
      this.declarePattern(
        param,
        sigScope,
        (id) => this.declare(sigScope, id, 'Parameter', node, { neverReport: true }),
        tctx
      );
    }
    this.walk(node.returnType, sigScope, tctx);
  }

  walkClass(node, scope, ctx) {
    this.walkAll(node.decorators, scope, ctx);
    if (node.type === 'ClassDeclaration')
      this.declare(scope, node.id, 'ClassName', node, { ambient: this.ambientFor(node, ctx) });
    const classScope = this.newScope('class', node, scope);
    // The class's own inner name: references from inside its body resolve here, never to the outer binding.
    this.declare(classScope, node.id, 'ClassName', node, { neverReport: true });
    this.declareTypeParameters(node.typeParameters, classScope, ctx);
    this.walk(node.superClass, classScope, ctx);
    this.walkType(node.superTypeArguments, classScope, ctx);
    for (const impl of node.implements ?? []) this.walkType(impl, classScope, ctx);
    this.walkAll(node.body.body, classScope, ctx);
  }

  walkMethod(node, scope, ctx) {
    this.walkAll(node.decorators, scope, ctx);
    if (node.computed) this.walk(node.key, scope, ctx);
    if (node.value) this.walkFunction(node.value, scope, ctx);
  }

  walkField(node, scope, ctx) {
    this.walkAll(node.decorators, scope, ctx);
    if (node.computed) this.walk(node.key, scope, ctx);
    this.walkType(node.typeAnnotation, scope, ctx);
    if (node.value)
      this.walk(node.value, this.newScope('class-field-initializer', node.value, scope, true), ctx);
  }

  walkForInOf(node, scope, ctx) {
    const s = this.newScope('for', node, scope);
    if (node.left.type === 'VariableDeclaration') this.walk(node.left, s, ctx);
    else this.assignTargets(node.left, s, ctx);
    this.walk(node.right, s, ctx);
    this.walk(node.body, s, ctx);
    this.forInOfLoops.push({ node, scope: s });
  }

  walkModule(node, scope, ctx) {
    let id = node.id;
    while (id?.type === 'TSQualifiedName') id = id.left;
    if (node.kind !== 'global')
      this.declare(scope, id, 'TSModuleName', node, { ambient: this.ambientFor(node, ctx) });
    let body = node.body;
    // `namespace A.B {}` may arrive as a nested declaration rather than a qualified id.
    while (body?.type === 'TSModuleDeclaration') body = body.body;
    if (body?.type !== 'TSModuleBlock') return;
    const inAmbient = node.declare || ctx.ambient || this.isDefinitionFile;
    const inner = {
      ...ctx,
      ambient: inAmbient && !hasOverridingExportStatement(body.body),
      ambientBlock: body,
    };
    this.walkAll(body.body, this.newScope('tsModule', node, scope, true), inner);
  }

  referenceJsxName(name, scope) {
    if (name.type === 'JSXIdentifier') {
      // An intrinsic element (`<div>`) is lowercase; ts-eslint's referencer resolves only the rest.
      if (name.name[0].toUpperCase() === name.name[0] || name.name === 'this')
        this.addRef(name, scope, { read: true });
      return;
    }
    let object = name;
    while (object.type === 'JSXMemberExpression') object = object.object;
    if (object.type === 'JSXIdentifier') this.addRef(object, scope, { read: true });
  }

  run(program) {
    const moduleScope = this.newScope('module', program, null, true);
    const ambient = this.isDefinitionFile && !hasOverridingExportStatement(program.body);
    this.walkAll(program.body, moduleScope, {
      type: false,
      typeQuery: false,
      ambient,
      ambientBlock: program,
    });
    for (const ref of this.references) this.resolve(ref);
    for (const loop of this.forInOfLoops) this.markForInOfReturn(loop);
    return this.variables;
  }

  /** Resolve by name, innermost scope first, in the namespace the reference was made in. */
  resolve(ref) {
    for (let scope = ref.from; scope; scope = scope.upper) {
      const variable = scope.set.get(ref.identifier.name);
      if (variable && refFitsVariable(ref, variable)) {
        ref.resolved = variable;
        variable.references.push(ref);
        return;
      }
    }
  }

  lookup(name, scope) {
    for (let s = scope; s; s = s.upper) {
      const variable = s.set.get(name);
      if (variable) return variable;
    }
    return null;
  }

  /** ts-eslint's `visitForInForOf`: `for (x in o) return;` marks x used (ESLint issue #2342 compat). */
  markForInOfReturn({ node, scope }) {
    let body = node.body;
    if (body.type === 'BlockStatement') body = body.body.length === 1 ? body.body[0] : null;
    if (body?.type !== 'ReturnStatement') return;
    const left =
      node.left.type === 'VariableDeclaration' ? node.left.declarations[0]?.id : node.left;
    if (left?.type !== 'Identifier') return;
    const variable = this.lookup(left.name, scope);
    if (variable) variable.used = true;
  }
}

/**
 * Build scopes, variables and resolved references for `program` (an oxc ESTree whose
 * `.parent` links the rule host has already set).
 */
export function analyzeScopes(program, filename) {
  return { variables: new ScopeAnalyzer(filename).run(program) };
}

function isExported(variable) {
  return variable.defs.some((def) => {
    if (def.type === 'Parameter') return false;
    const node = def.node.type === 'VariableDeclarator' ? def.node.parent : def.node;
    return !!parentOf(node)?.type.startsWith('Export');
  });
}

function isMergeableExported(variable) {
  return variable.defs.some((def) => {
    if (def.type === 'Parameter') return false;
    const parentType = parentOf(def.node)?.type;
    if (parentType === 'ExportDefaultDeclaration') return true;
    return MERGEABLE_TYPES.has(def.node.type) && parentType === 'ExportNamedDeclaration';
  });
}

function isUnusedExpression(node) {
  const parent = parentOf(node);
  if (parent?.type === 'ExpressionStatement') return true;
  if (parent?.type !== 'SequenceExpression') return false;
  if (parent.expressions.at(-1) !== node) return true;
  return isUnusedExpression(parent);
}

function isInLoop(node) {
  for (let current = node; current; current = current.parent) {
    if (FUNCTION_NODE_TYPES.has(current.type)) return false;
    if (LOOP_TYPES.has(current.type)) return true;
  }
  return false;
}

function getRhsNode(ref, prevRhsNode) {
  const id = ref.identifier;
  if (prevRhsNode && isInside(id, prevRhsNode)) return prevRhsNode;
  const parent = parentOf(id);
  if (parent?.type !== 'AssignmentExpression' || id !== parent.left || !isUnusedExpression(parent))
    return null;
  const canBeUsedLater =
    ref.from.variableScope !== ref.resolved.scope.variableScope || isInLoop(id);
  return canBeUsedLater ? null : parent.right;
}

/** One step of ts-eslint's `isStorableFunction` walk: true/false is a verdict, undefined means keep climbing. */
function storableVerdict(node, parent) {
  switch (parent.type) {
    case 'SequenceExpression':
      return parent.expressions.at(-1) === node ? undefined : false;
    case 'CallExpression':
    case 'NewExpression':
      return parent.callee !== node;
    case 'AssignmentExpression':
    case 'TaggedTemplateExpression':
    case 'YieldExpression':
      return true;
    default:
      return parent.type.endsWith('Statement') || parent.type.endsWith('Declaration')
        ? true
        : undefined;
  }
}

function isStorableFunction(funcNode, rhsNode) {
  let node = funcNode;
  for (
    let parent = parentOf(funcNode);
    parent && isInside(parent, rhsNode);
    parent = parentOf(parent)
  ) {
    const verdict = storableVerdict(node, parent);
    if (verdict !== undefined) return verdict;
    node = parent;
  }
  return false;
}

function isInsideOfStorableFunction(id, rhsNode) {
  let funcNode = id;
  while (funcNode && !FUNCTION_NODE_TYPES.has(funcNode.type)) funcNode = funcNode.parent;
  return !!funcNode && isInside(funcNode, rhsNode) && isStorableFunction(funcNode, rhsNode);
}

function isSelfUpdate(id) {
  const parent = parentOf(id);
  if (parent?.type === 'UpdateExpression') return isUnusedExpression(parent);
  if (parent?.type !== 'AssignmentExpression' || parent.left !== id) return false;
  return !LOGICAL_ASSIGNMENT_OPERATORS.has(parent.operator) && isUnusedExpression(parent);
}

function isReadForItself(ref, rhsNode) {
  if (!ref.read) return false;
  if (isSelfUpdate(ref.identifier)) return true;
  return (
    !!rhsNode &&
    isInside(ref.identifier, rhsNode) &&
    !isInsideOfStorableFunction(ref.identifier, rhsNode)
  );
}

function isSelfReference(ref, nodes) {
  for (let scope = ref.from; scope; scope = scope.upper) {
    if (nodes.has(scope.block)) return true;
  }
  return false;
}

const SELF_SCOPED_DECLARATIONS = new Set(['TSModuleDeclaration', 'TSEnumDeclaration']);
const TYPE_DECLARATIONS = new Set(['TSInterfaceDeclaration', 'TSTypeAliasDeclaration']);

/** The scope-creating node a reference from inside of is a SELF-reference: a function, a function-valued variable's initializer, a namespace, an enum. */
function selfScopeBlock(def) {
  if (def.type === 'FunctionName' || SELF_SCOPED_DECLARATIONS.has(def.node.type)) return def.node;
  const init = def.type === 'Variable' ? def.node.init : null;
  return init && FUNCTION_NODE_TYPES.has(init.type) ? init : null;
}

/** The declaration nodes a reference must come from OUTSIDE of to count as a use. */
function ownDeclarationNodes(variable) {
  const scopeBlocks = new Set(variable.defs.map(selfScopeBlock).filter(Boolean));
  const typeDecls = variable.defs
    .map((def) => def.node)
    .filter((node) => TYPE_DECLARATIONS.has(node.type));
  return { scopeBlocks, typeDecls };
}

function isUsedVariable(variable) {
  const { scopeBlocks, typeDecls } = ownDeclarationNodes(variable);
  const isImportedAsType = variable.defs.every((def) => def.typeImport);
  let rhsNode = null;
  return variable.references.some((ref) => {
    const forItself = isReadForItself(ref, rhsNode);
    rhsNode = getRhsNode(ref, rhsNode);
    if (!ref.read || forItself) return false;
    if (ref.typeQuery && !isImportedAsType) return false;
    if (isSelfReference(ref, scopeBlocks)) return false;
    return !typeDecls.some((n) => isInside(ref.identifier, n));
  });
}

function isReportable(variable) {
  if (variable.neverReport || variable.used || variable.scope.type === 'function-expression-name')
    return false;
  const defType = variable.defs[0].type;
  if (defType === 'Parameter' || defType === 'TSEnumMember') return false;
  if (isExported(variable) || isMergeableExported(variable) || isUsedVariable(variable))
    return false;
  // ts-eslint skips an import that is "only used as a type" rather than reporting it.
  return !(defType === 'ImportBinding' && variable.references.some((r) => r.typeQuery));
}

/** ts-eslint reports at the LAST write made from the variable's own variable scope, else at the declaration. */
function reportLocation(variable) {
  const writes = variable.references.filter(
    (r) => r.write && r.from.variableScope === variable.scope.variableScope
  );
  return writes.length ? writes.at(-1).identifier : variable.identifiers[0];
}

/**
 * Every variable ts-eslint's `no-unused-vars` would report under
 * `{ args: 'after-used', argsIgnorePattern: '^_', varsIgnorePattern: '^$', caughtErrors: 'all' }`,
 * IGNORING the name filter and skipping parameters entirely (a `_` parameter is exempt, and
 * a non-`_` one is Biome's business). Each entry carries the identifier ts-eslint reports at.
 */
export function findUnusedVariables(program, filename) {
  return analyzeScopes(program, filename)
    .variables.filter(isReportable)
    .map((variable) => ({ variable, at: reportLocation(variable) }))
    .sort((x, y) => x.at.range[0] - y.at.range[0]);
}

/** @type {import('../scripts/lib/rule-host.ts').RuleModule} */
export const noUnusedUnderscoreVar = {
  meta: {
    messages: {
      unused:
        "'{{name}}' is declared with an underscore prefix but never used. This repo's policy is stricter than Biome's: an unused `_`-prefixed variable, catch parameter, function, class, import or type is still an error -- delete it, or use it. (Only function parameters named `_x` are exempt.)",
    },
  },
  create(context) {
    return {
      Program(program) {
        for (const { variable, at } of findUnusedVariables(program, context.filename)) {
          if (variable.name.startsWith('_'))
            context.report({ node: at, messageId: 'unused', data: { name: variable.name } });
        }
      },
    };
  },
};

export default noUnusedUnderscoreVar;
