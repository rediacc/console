#!/usr/bin/env node
/**
 * Check for "prop relay" anti-patterns in React components.
 *
 * Detects components that receive props and forward them to children unchanged,
 * while being used by only a small number of consumers. This prevents unnecessary
 * abstraction layers that add indirection without value.
 *
 * Usage:
 *   npx tsx scripts/check-prop-relay.ts              # Check for violations
 *   npx tsx scripts/check-prop-relay.ts --verbose    # Show all analyzed components
 *   npx tsx scripts/check-prop-relay.ts --min-props 10
 *   npx tsx scripts/check-prop-relay.ts --min-ratio 0.7
 *   npx tsx scripts/check-prop-relay.ts --max-consumers 2
 *
 * Exit codes:
 *   0 - No violations found (or all allowlisted)
 *   1 - Prop relay violations detected
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from '@typescript-eslint/parser';
import { BLUE, DIM, GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const WEB_SRC = path.join(CONSOLE_ROOT, 'packages/web/src');
const ALLOWLIST_FILE = path.join(CONSOLE_ROOT, '.prop-relay-allowlist');

// CLI arguments
const args = process.argv.slice(2);
const verbose = args.includes('--verbose');

function getArgValue(flag: string, defaultVal: number): number {
  const idx = args.indexOf(flag);
  if (idx === -1 || idx + 1 >= args.length) return defaultVal;
  const val = Number(args[idx + 1]);
  return Number.isNaN(val) ? defaultVal : val;
}

const MIN_PROPS = getArgValue('--min-props', 5);
const MIN_RATIO = getArgValue('--min-ratio', 0.6);
const MAX_CONSUMERS = getArgValue('--max-consumers', 1);

// ─── Types ───────────────────────────────────────────────────────────────────

interface ComponentInfo {
  name: string;
  filePath: string;
  relativePath: string;
  propsTypeName: string | null;
  propNames: string[];
  propCount: number;
}

interface ForwardingInfo {
  component: ComponentInfo;
  forwardedCount: number;
  localCount: number;
  ratio: number;
  targetComponent: string | null;
  method: 'spread' | 'partial-spread' | 'named';
  consumers: string[];
}

// ─── Phase 1: Discovery ─────────────────────────────────────────────────────

function findFiles(dir: string, extensions: string[]): string[] {
  const results: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__' || entry.name === '__mocks__') {
        continue;
      }
      results.push(...findFiles(fullPath, extensions));
    } else if (extensions.some((ext) => entry.name.endsWith(ext)) && !entry.name.includes('.test.')) {
      results.push(fullPath);
    }
  }
  return results;
}

function extractExportedComponents(content: string): Array<{ name: string; propsTypeName: string | null }> {
  const components: Array<{ name: string; propsTypeName: string | null }> = [];

  // export const X: React.FC<Props> = ...
  const fcPattern = /export\s+const\s+(\w+)\s*:\s*React\.FC<(\w+)>/g;
  let match: RegExpExecArray | null;
  while ((match = fcPattern.exec(content)) !== null) {
    components.push({ name: match[1], propsTypeName: match[2] });
  }

  // export const X = (props: Props) => ...
  const arrowPattern = /export\s+const\s+(\w+)\s*=\s*\(\s*(?:\{\s*[^}]*\}|(\w+))\s*:\s*(\w+)/g;
  while ((match = arrowPattern.exec(content)) !== null) {
    const name = match[1];
    if (!components.some((c) => c.name === name)) {
      components.push({ name, propsTypeName: match[3] });
    }
  }

  // export function X(props: Props) ...
  const funcPattern = /export\s+function\s+(\w+)\s*\(\s*(?:\{\s*[^}]*\}|(\w+))\s*:\s*(\w+)/g;
  while ((match = funcPattern.exec(content)) !== null) {
    components.push({ name: match[1], propsTypeName: match[3] });
  }

  // export const X = React.memo<Props>(...)
  const memoPattern = /export\s+const\s+(\w+)\s*=\s*React\.memo<(\w+)>/g;
  while ((match = memoPattern.exec(content)) !== null) {
    if (!components.some((c) => c.name === match![1])) {
      components.push({ name: match[1], propsTypeName: match[2] });
    }
  }

  // export const X = React.forwardRef<Ref, Props>(...)
  const forwardRefPattern = /export\s+const\s+(\w+)\s*=\s*React\.forwardRef<\w+,\s*(\w+)>/g;
  while ((match = forwardRefPattern.exec(content)) !== null) {
    if (!components.some((c) => c.name === match![1])) {
      components.push({ name: match[1], propsTypeName: match[2] });
    }
  }

  return components;
}

function parsePropsFromAST(content: string, propsTypeName: string): string[] {
  try {
    const ast = parse(content, {
      jsx: true,
      range: true,
      loc: true,
    });

    const propNames: string[] = [];

    function visitNode(node: Record<string, unknown>): void {
      if (!node || typeof node !== 'object') return;

      // Match interface X { ... } or type X = { ... }
      const nodeType = node.type as string;

      if (nodeType === 'TSInterfaceDeclaration') {
        const id = node.id as { name?: string } | undefined;
        if (id?.name === propsTypeName) {
          const body = node.body as { body?: Array<Record<string, unknown>> } | undefined;
          if (body?.body) {
            for (const member of body.body) {
              if (member.type === 'TSPropertySignature') {
                const key = member.key as { name?: string; value?: string } | undefined;
                if (key?.name) {
                  propNames.push(key.name);
                } else if (key?.value) {
                  propNames.push(String(key.value));
                }
              }
            }
          }
        }
      }

      if (nodeType === 'TSTypeAliasDeclaration') {
        const id = node.id as { name?: string } | undefined;
        if (id?.name === propsTypeName) {
          const typeAnnotation = node.typeAnnotation as Record<string, unknown> | undefined;
          if (typeAnnotation?.type === 'TSTypeLiteral') {
            const members = typeAnnotation.members as Array<Record<string, unknown>> | undefined;
            if (members) {
              for (const member of members) {
                if (member.type === 'TSPropertySignature') {
                  const key = member.key as { name?: string; value?: string } | undefined;
                  if (key?.name) {
                    propNames.push(key.name);
                  } else if (key?.value) {
                    propNames.push(String(key.value));
                  }
                }
              }
            }
          }
          // Handle intersection types: type Props = BaseProps & { extra: string }
          if (typeAnnotation?.type === 'TSIntersectionType') {
            const types = typeAnnotation.types as Array<Record<string, unknown>> | undefined;
            if (types) {
              for (const t of types) {
                if (t.type === 'TSTypeLiteral') {
                  const members = t.members as Array<Record<string, unknown>> | undefined;
                  if (members) {
                    for (const member of members) {
                      if (member.type === 'TSPropertySignature') {
                        const key = member.key as { name?: string; value?: string } | undefined;
                        if (key?.name) {
                          propNames.push(key.name);
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }

      // Recurse into all child nodes
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) {
          for (const item of value) {
            if (item && typeof item === 'object') {
              visitNode(item as Record<string, unknown>);
            }
          }
        } else if (value && typeof value === 'object') {
          visitNode(value as Record<string, unknown>);
        }
      }
    }

    visitNode(ast as unknown as Record<string, unknown>);
    return propNames;
  } catch (error) {
    if (verbose) {
      console.warn(
        `${YELLOW}AST parsing failed for ${propsTypeName}, falling back to regex. Error: ${(error as Error).message}${NC}`,
      );
    }
    return parsePropsWithRegex(content, propsTypeName);
  }
}

function parsePropsWithRegex(content: string, propsTypeName: string): string[] {
  const propNames: string[] = [];

  // Match interface X { ... } or type X = { ... }
  const interfacePattern = new RegExp(
    `(?:interface|type)\\s+${propsTypeName}\\s*(?:=\\s*)?\\{([^}]*(?:\\{[^}]*\\}[^}]*)*)\\}`,
    's',
  );
  const interfaceMatch = interfacePattern.exec(content);
  if (!interfaceMatch) return propNames;

  const body = interfaceMatch[1];
  // Extract property names (handling multi-line, optional markers, type annotations)
  const propPattern = /^\s*(\w+)\s*[?:]|^\s*readonly\s+(\w+)\s*[?:]/gm;
  let propMatch: RegExpExecArray | null;
  while ((propMatch = propPattern.exec(body)) !== null) {
    const name = propMatch[1] || propMatch[2];
    if (name) propNames.push(name);
  }

  return propNames;
}

function discoverComponents(tsxFiles: string[]): ComponentInfo[] {
  const components: ComponentInfo[] = [];

  for (const filePath of tsxFiles) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const relativePath = path.relative(WEB_SRC, filePath);
    const exported = extractExportedComponents(content);

    for (const { name, propsTypeName } of exported) {
      if (!propsTypeName) continue;

      const propNames = parsePropsFromAST(content, propsTypeName);
      if (propNames.length === 0) continue;

      components.push({
        name,
        filePath,
        relativePath,
        propsTypeName,
        propNames,
        propCount: propNames.length,
      });
    }
  }

  return components;
}

// ─── Phase 2: Import Graph ───────────────────────────────────────────────────

function resolveImportPath(importPath: string, fromFile: string): string | null {
  // Resolve @/ alias
  let resolved: string;
  if (importPath.startsWith('@/')) {
    resolved = path.join(WEB_SRC, importPath.slice(2));
  } else if (importPath.startsWith('.')) {
    resolved = path.resolve(path.dirname(fromFile), importPath);
  } else {
    return null; // external package
  }

  // Try exact file, then with extensions, then index files
  const extensions = ['.tsx', '.ts', '.jsx', '.js'];
  if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
    return resolved;
  }
  for (const ext of extensions) {
    if (fs.existsSync(resolved + ext)) {
      return resolved + ext;
    }
  }
  // Check for index file in directory
  if (fs.existsSync(resolved) && fs.statSync(resolved).isDirectory()) {
    for (const ext of extensions) {
      const indexPath = path.join(resolved, `index${ext}`);
      if (fs.existsSync(indexPath)) {
        return indexPath;
      }
    }
  }
  return null;
}

function resolveBarrelExports(indexFile: string, componentName: string): string | null {
  if (!fs.existsSync(indexFile)) return null;
  const content = fs.readFileSync(indexFile, 'utf-8');

  // export { X } from './X'
  const reExportPattern = new RegExp(
    `export\\s*\\{[^}]*\\b${componentName}\\b[^}]*\\}\\s*from\\s*['"]([^'"]+)['"]`,
  );
  const match = reExportPattern.exec(content);
  if (match) {
    return resolveImportPath(match[1], indexFile);
  }

  // export * from './X' - check if that file exports the component
  const starExportPattern = /export\s*\*\s*from\s*['"]([^'"]+)['"]/g;
  let starMatch: RegExpExecArray | null;
  while ((starMatch = starExportPattern.exec(content)) !== null) {
    const resolvedPath = resolveImportPath(starMatch[1], indexFile);
    if (resolvedPath) {
      const fileContent = fs.readFileSync(resolvedPath, 'utf-8');
      if (new RegExp(`export\\s+(?:const|function|class)\\s+${componentName}\\b`).test(fileContent)) {
        return resolvedPath;
      }
    }
  }

  return null;
}

interface ImportGraphEntry {
  componentFilePath: string;
  consumers: string[];
}

function buildImportGraph(allFiles: string[], components: ComponentInfo[]): Map<string, ImportGraphEntry> {
  // Map component name -> source file path(s)
  const componentFileMap = new Map<string, Set<string>>();
  for (const comp of components) {
    if (!componentFileMap.has(comp.name)) {
      componentFileMap.set(comp.name, new Set());
    }
    componentFileMap.get(comp.name)!.add(comp.filePath);
  }

  // Map: component file path -> consumer file paths
  const graph = new Map<string, ImportGraphEntry>();
  for (const comp of components) {
    if (!graph.has(comp.filePath)) {
      graph.set(comp.filePath, { componentFilePath: comp.filePath, consumers: [] });
    }
  }

  for (const file of allFiles) {
    const content = fs.readFileSync(file, 'utf-8');

    // Match import statements
    const importPattern = /import\s+(?:(?:\{([^}]*)\})|(\w+))\s+from\s+['"]([^'"]+)['"]/g;
    let match: RegExpExecArray | null;
    while ((match = importPattern.exec(content)) !== null) {
      const namedImports = match[1];
      const defaultImport = match[2];
      const importPath = match[3];

      const resolvedPath = resolveImportPath(importPath, file);
      if (!resolvedPath) continue;

      const importedNames: string[] = [];
      if (namedImports) {
        // Parse: { A, B as C, D }
        for (const part of namedImports.split(',')) {
          const name = part.trim().split(/\s+as\s+/)[0].trim();
          if (name) importedNames.push(name);
        }
      }
      if (defaultImport) {
        importedNames.push(defaultImport);
      }

      for (const importedName of importedNames) {
        const sourceFiles = componentFileMap.get(importedName);
        if (!sourceFiles) continue;

        // Check if the resolved path matches one of the component files
        // or if it's a barrel that re-exports from one
        for (const sourceFile of sourceFiles) {
          if (resolvedPath === sourceFile && file !== sourceFile) {
            graph.get(sourceFile)!.consumers.push(file);
          } else if (resolvedPath !== sourceFile) {
            // Check barrel re-export
            const barrelResolved = resolveBarrelExports(resolvedPath, importedName);
            if (barrelResolved === sourceFile && file !== sourceFile) {
              graph.get(sourceFile)!.consumers.push(file);
            }
          }
        }
      }
    }

    // Dynamic imports: React.lazy(() => import('./X'))
    const dynamicPattern = /import\s*\(\s*['"]([^'"]+)['"]\s*\)/g;
    while ((match = dynamicPattern.exec(content)) !== null) {
      const resolvedPath = resolveImportPath(match[1], file);
      if (resolvedPath && graph.has(resolvedPath) && file !== resolvedPath) {
        graph.get(resolvedPath)!.consumers.push(file);
      }
    }
  }

  return graph;
}

// ─── Phase 3: Forwarding Detection ──────────────────────────────────────────

function detectForwarding(component: ComponentInfo): {
  forwardedCount: number;
  localCount: number;
  targetComponent: string | null;
  method: 'spread' | 'partial-spread' | 'named';
} | null {
  const content = fs.readFileSync(component.filePath, 'utf-8');

  // Find the component function body (approximate: from component declaration to end of file)
  const compStart = content.indexOf(component.name);
  if (compStart === -1) return null;
  const bodyContent = content.slice(compStart);

  // Detect spread forwarding: {...props} in JSX
  const spreadPattern = /\{\s*\.\.\.(\w+)\s*\}/g;
  const spreadMatches: Array<{ paramName: string; context: string }> = [];
  let spreadMatch: RegExpExecArray | null;
  while ((spreadMatch = spreadPattern.exec(bodyContent)) !== null) {
    const paramName = spreadMatch[1];
    // Check if it's in a JSX context (preceded by < component or a prop assignment)
    const before = bodyContent.slice(Math.max(0, spreadMatch.index - 200), spreadMatch.index);
    if (/<\w+[\s\S]*$/.test(before) || /\breturn\b/.test(before)) {
      spreadMatches.push({ paramName, context: before });
    }
  }

  // Detect rest destructuring: const { a, b, ...rest } = props
  const restPattern = /(?:const|let)\s*\{([^}]*),\s*\.\.\.(\w+)\s*\}\s*=\s*(\w+)/g;
  let restMatch: RegExpExecArray | null;
  const restDestructures: Array<{ destructured: string[]; restName: string; sourceName: string }> = [];
  while ((restMatch = restPattern.exec(bodyContent)) !== null) {
    const destructuredStr = restMatch[1];
    const restName = restMatch[2];
    const sourceName = restMatch[3];
    const destructured = destructuredStr
      .split(',')
      .map((s) => s.trim().split(/\s*[:=]/)[0].trim())
      .filter(Boolean);
    restDestructures.push({ destructured, restName, sourceName });
  }

  // Detect simple destructuring: const { a, b, c } = props (to find locally used props)
  const simpleDestructurePattern = /(?:const|let)\s*\{([^}]+)\}\s*=\s*props/g;
  let simpleMatch: RegExpExecArray | null;
  const locallyDestructured: string[] = [];
  while ((simpleMatch = simpleDestructurePattern.exec(bodyContent)) !== null) {
    const parts = simpleMatch[1]
      .split(',')
      .map((s) => s.trim().split(/\s*[:=]/)[0].replace('...', '').trim())
      .filter(Boolean);
    locallyDestructured.push(...parts);
  }

  // Find target JSX component for spread
  function findSpreadTarget(paramName: string): string | null {
    const targetPattern = new RegExp(`<(\\w+)[^>]*\\{\\s*\\.\\.\\.${paramName}\\s*\\}`, 'g');
    const targetMatch = targetPattern.exec(bodyContent);
    if (targetMatch) return targetMatch[1];
    return null;
  }

  // Case 1: Full spread of props parameter
  if (spreadMatches.some((m) => m.paramName === 'props')) {
    const target = findSpreadTarget('props');
    const localCount = locallyDestructured.length;
    const forwardedCount = component.propCount - localCount;
    if (forwardedCount > 0) {
      return {
        forwardedCount,
        localCount,
        targetComponent: target,
        method: 'spread',
      };
    }
  }

  // Case 2: Partial spread with rest: const { a, b, ...rest } = props; <Child {...rest} />
  for (const rd of restDestructures) {
    if (rd.sourceName === 'props' && spreadMatches.some((m) => m.paramName === rd.restName)) {
      const target = findSpreadTarget(rd.restName);
      const localCount = rd.destructured.length;
      const forwardedCount = component.propCount - localCount;
      if (forwardedCount > 0) {
        return {
          forwardedCount,
          localCount,
          targetComponent: target,
          method: 'partial-spread',
        };
      }
    }
  }

  // Case 3: Named prop forwarding - detect many propName={propName} patterns
  const namedForwardPattern = /\b(\w+)=\{(\w+)\}/g;
  let namedMatch: RegExpExecArray | null;
  const forwardedByName = new Set<string>();
  while ((namedMatch = namedForwardPattern.exec(bodyContent)) !== null) {
    // prop name equals variable name, and prop name is in the component's props
    if (namedMatch[1] === namedMatch[2] && component.propNames.includes(namedMatch[1])) {
      forwardedByName.add(namedMatch[1]);
    }
  }

  // Also detect propName={props.propName}
  const dotForwardPattern = /\b(\w+)=\{props\.(\w+)\}/g;
  while ((namedMatch = dotForwardPattern.exec(bodyContent)) !== null) {
    if (namedMatch[1] === namedMatch[2] && component.propNames.includes(namedMatch[1])) {
      forwardedByName.add(namedMatch[1]);
    }
  }

  if (forwardedByName.size > 0) {
    const localCount = component.propCount - forwardedByName.size;
    // Find which component receives these props
    const jsxComponentPattern = new RegExp(`<(\\w+)\\s+[^>]*(?:\\b(?:${[...forwardedByName].join('|')})=\\{)`);
    const jsxMatch = jsxComponentPattern.exec(bodyContent);
    return {
      forwardedCount: forwardedByName.size,
      localCount,
      targetComponent: jsxMatch ? jsxMatch[1] : null,
      method: 'named',
    };
  }

  return null;
}

// ─── Phase 4: Reporting ──────────────────────────────────────────────────────

function loadAllowlist(): Set<string> {
  const allowlist = new Set<string>();
  if (!fs.existsSync(ALLOWLIST_FILE)) return allowlist;

  const content = fs.readFileSync(ALLOWLIST_FILE, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const entry = trimmed.includes('#') ? trimmed.slice(0, trimmed.indexOf('#')).trim() : trimmed;
    if (entry) allowlist.add(entry);
  }
  return allowlist;
}

function run(): void {
  console.log('Checking for prop relay anti-patterns...\n');

  // Phase 1: Discovery
  const tsxFiles = findFiles(WEB_SRC, ['.tsx']);
  const components = discoverComponents(tsxFiles);

  console.log(`Scanned ${tsxFiles.length} .tsx component files`);

  // Phase 2: Import Graph
  const allFiles = findFiles(WEB_SRC, ['.ts', '.tsx']);
  const importGraph = buildImportGraph(allFiles, components);

  console.log(`Built import graph: ${components.length} component exports tracked\n`);

  // Phase 3 & 4: Detect forwarding and report
  const allowlist = loadAllowlist();
  const violations: ForwardingInfo[] = [];
  let allowlistedCount = 0;

  for (const component of components) {
    if (component.propCount < MIN_PROPS) continue;

    const entry = importGraph.get(component.filePath);
    const consumers = entry ? [...new Set(entry.consumers)] : [];

    if (consumers.length > MAX_CONSUMERS) continue;

    const forwarding = detectForwarding(component);
    if (!forwarding) continue;

    const ratio = forwarding.forwardedCount / component.propCount;
    if (ratio < MIN_RATIO) continue;

    // Check allowlist
    if (allowlist.has(component.relativePath)) {
      allowlistedCount++;
      continue;
    }

    violations.push({
      component,
      forwardedCount: forwarding.forwardedCount,
      localCount: forwarding.localCount,
      ratio,
      targetComponent: forwarding.targetComponent,
      method: forwarding.method,
      consumers: consumers.map((c) => path.relative(WEB_SRC, c)),
    });
  }

  // Output
  if (violations.length > 0) {
    console.log(`${RED}VIOLATIONS (${violations.length} found):${NC}\n`);

    for (const v of violations) {
      const pct = Math.round(v.ratio * 100);
      const methodStr =
        v.method === 'spread'
          ? `via {...props}`
          : v.method === 'partial-spread'
            ? `via {...rest}`
            : `via named props`;

      console.log(`  ${v.component.relativePath}`);
      console.log(
        `  ${YELLOW}→${NC} ${v.component.name}: ${v.component.propCount} props (${v.localCount} local, ${v.forwardedCount} forwarded = ${pct}%)`,
      );
      if (v.consumers.length === 0) {
        console.log(`  ${YELLOW}→${NC} 0 consumers (unused or dynamically imported)`);
      } else {
        console.log(
          `  ${YELLOW}→${NC} ${v.consumers.length} consumer${v.consumers.length > 1 ? 's' : ''}: ${v.consumers.join(', ')}`,
        );
      }
      if (v.targetComponent) {
        console.log(`  ${YELLOW}→${NC} Forwards to: ${v.targetComponent} ${methodStr}`);
      }
      console.log();
    }
  }

  if (allowlistedCount > 0) {
    if (verbose) {
      console.log(`${DIM}ALLOWLISTED: ${allowlistedCount} entries skipped${NC}\n`);
    } else {
      console.log(`${DIM}ALLOWLISTED: ${allowlistedCount} entries skipped (use --verbose to show)${NC}\n`);
    }
  }

  if (verbose) {
    console.log(`${BLUE}All analyzed components (${components.length}):${NC}\n`);
    for (const comp of components) {
      const entry = importGraph.get(comp.filePath);
      const consumerCount = entry ? new Set(entry.consumers).size : 0;
      console.log(`  ${DIM}${comp.relativePath}${NC}`);
      console.log(`    ${comp.name}: ${comp.propCount} props, ${consumerCount} consumers`);
    }
    console.log();
  }

  if (violations.length > 0) {
    console.log(`${RED}Prop relay check FAILED${NC}`);
    process.exit(1);
  }

  console.log(`${GREEN}Prop relay check passed${NC}`);
  process.exit(0);
}

run();
