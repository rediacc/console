import type { RsyncChanges } from './rsync.js';

/**
 * Formats changes summary for display
 *
 * @param changes - Rsync changes
 * @returns Formatted summary string
 */
export function formatChangesSummary(changes: RsyncChanges): string {
  const lines: string[] = [];

  if (changes.newFiles.length > 0) {
    lines.push(`New files: ${changes.newFiles.length}`);
  }
  if (changes.modifiedFiles.length > 0) {
    lines.push(`Modified files: ${changes.modifiedFiles.length}`);
  }
  if (changes.deletedFiles.length > 0) {
    lines.push(`Deleted files: ${changes.deletedFiles.length}`);
  }
  if (changes.newDirs.length > 0) {
    lines.push(`New directories: ${changes.newDirs.length}`);
  }

  const total =
    changes.newFiles.length +
    changes.modifiedFiles.length +
    changes.deletedFiles.length +
    changes.newDirs.length;

  if (total === 0) {
    return 'No changes - everything is in sync!';
  }

  lines.push(`Total changes: ${total}`);
  return lines.join('\n');
}

/**
 * Color function type for formatting output
 */
type ColorFn = (text: string) => string;

/**
 * Options for formatting detailed changes
 */
export interface FormatDetailedChangesOptions {
  /** Maximum items to show per category (default: 10) */
  maxItems?: number;
  /** Color function for new files/dirs (green) */
  colorNew?: ColorFn;
  /** Color function for modified files (yellow) */
  colorModified?: ColorFn;
  /** Color function for deleted files (red) */
  colorDeleted?: ColorFn;
  /** Color function for "... and X more" text (dim/gray) */
  colorDim?: ColorFn;
}

/**
 * Formats detailed changes for display (matching Python CLI behavior)
 * Shows first 10 items of each category with "... and X more" if truncated
 *
 * @param changes - Rsync changes
 * @param options - Formatting options including color functions
 * @returns Detailed formatted string
 */
export function formatDetailedChanges(
  changes: RsyncChanges,
  options: FormatDetailedChangesOptions = {}
): string {
  const {
    maxItems = 10,
    colorNew = (t: string) => t,
    colorModified = (t: string) => t,
    colorDeleted = (t: string) => t,
    colorDim = (t: string) => t,
  } = options;

  const sections: string[] = [];

  const formatSection = (
    title: string,
    items: string[],
    prefix: string,
    colorFn: ColorFn
  ): void => {
    if (items.length === 0) return;

    const lines: string[] = [`\n${title}:`];
    const displayItems = items.slice(0, maxItems);

    for (const item of displayItems) {
      lines.push(`  ${colorFn(prefix)} ${item}`);
    }

    if (items.length > maxItems) {
      lines.push(colorDim(`  ... and ${items.length - maxItems} more`));
    }

    sections.push(lines.join('\n'));
  };

  formatSection('New files', changes.newFiles, '+', colorNew);
  formatSection('Modified files', changes.modifiedFiles, '~', colorModified);
  formatSection('Deleted files', changes.deletedFiles, '-', colorDeleted);
  formatSection('New directories', changes.newDirs, '/', colorNew);

  if (sections.length === 0) {
    return 'No changes to display.';
  }

  return sections.join('\n');
}
