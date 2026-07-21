/**
 * Collect every third-party GitHub Action referenced by this repo.
 *
 * Scans BOTH `.github/workflows/*.y{a,}ml` and composite actions at
 * `.github/actions/<name>/action.y{a,}ml`. The composite half matters: for a
 * long time scripts/check-actions.ts read only the workflows directory, which
 * made `actions/create-github-app-token` invisible to the freshness gate — it
 * is referenced solely from `.github/actions/app-token/action.yml`, and that is
 * the action minting every CI token in this repo.
 */

import fs from 'node:fs';
import path from 'node:path';

interface ActionRef {
  /** Path relative to `.github`, e.g. "workflows/ci.yml" or "actions/app-token/action.yml". */
  file: string;
  line: number;
  ref: string;
  comment?: string;
}

/** owner/repo -> every place it is pinned. */
export type ActionRefMap = Map<string, ActionRef[]>;

const USES_RE = /uses:\s*([\w.-]+\/[\w.-]+)@(\S+)(?:\s+#\s*(.+))?/;

function collectFiles(root: string): string[] {
  const githubDir = path.join(root, '.github');
  const files: string[] = [];

  const workflowsDir = path.join(githubDir, 'workflows');
  if (fs.existsSync(workflowsDir)) {
    for (const f of fs.readdirSync(workflowsDir)) {
      if (f.endsWith('.yml') || f.endsWith('.yaml')) files.push(path.join(workflowsDir, f));
    }
  }

  const actionsDir = path.join(githubDir, 'actions');
  if (fs.existsSync(actionsDir)) {
    for (const entry of fs.readdirSync(actionsDir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      for (const name of ['action.yml', 'action.yaml']) {
        const p = path.join(actionsDir, entry.name, name);
        if (fs.existsSync(p)) files.push(p);
      }
    }
  }

  return files;
}

/**
 * Local (`./…`) and first-party (`rediacc/…`) references are excluded: they are
 * not upstream-versioned, so neither the freshness gate nor the liveness probe
 * can say anything useful about them.
 */
export function collectActionRefs(root: string): ActionRefMap {
  const refs: ActionRefMap = new Map();
  const githubDir = path.join(root, '.github');

  for (const filePath of collectFiles(root)) {
    const rel = path.relative(githubDir, filePath);
    const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
    for (let i = 0; i < lines.length; i++) {
      const match = lines[i].match(USES_RE);
      if (!match) continue;
      const [, name, ref, comment] = match;
      if (name.startsWith('.') || name.startsWith('rediacc/')) continue;
      const list = refs.get(name) ?? [];
      list.push({ file: rel, line: i + 1, ref, comment });
      refs.set(name, list);
    }
  }

  return refs;
}
