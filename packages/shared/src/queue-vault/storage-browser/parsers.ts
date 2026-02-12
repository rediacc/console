/**
 * Parsers for rclone file listing output.
 *
 * Extracted from packages/web RemoteFileBrowserModal/parsers.ts
 * for shared use by both the web app and CLI.
 *
 * The shared parsers produce base RemoteFile entries without
 * GUID-to-repository mapping (that's web-specific).
 */

import { isValidGuid } from '../../validation/index.js';
import type { RcloneEntry, RemoteFile } from './types.js';

// ============================================================================
// Internal Helpers
// ============================================================================

const getStringValue = (value: unknown): string | undefined =>
  typeof value === 'string' ? value : undefined;

const getNumberValue = (value: unknown): number => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
};

const getBooleanValue = (value: unknown): boolean =>
  typeof value === 'boolean' ? value : false;

// ============================================================================
// Individual Parsers
// ============================================================================

/** Parse a JSON array of rclone entries (the standard `rclone lsjson` format). */
export function parseJsonFileList(data: unknown, currentPath: string): RemoteFile[] {
  if (!Array.isArray(data)) return [];

  return data.map((file: RcloneEntry) => {
    const fileName = getStringValue(file.name) ?? getStringValue(file.Name) ?? '';
    const isDirectoryFlag =
      getBooleanValue(file.isDirectory) ||
      getBooleanValue(file.IsDir) ||
      Boolean(getStringValue(file.permissions)?.startsWith('d'));

    return {
      name: fileName,
      size: getNumberValue(file.size ?? file.Size ?? 0),
      isDirectory: isDirectoryFlag,
      modTime:
        file.date && file.time
          ? `${file.date} ${file.time}`
          : getStringValue(file.ModTime),
      path:
        getStringValue(file.Path) ??
        (currentPath && fileName ? `${currentPath}/${fileName}` : fileName),
    };
  });
}

/** Parse rclone output in `{ entries: [...] }` wrapper format. */
export function parseRcloneFileList(
  data: { entries?: RcloneEntry[] },
  currentPath: string
): RemoteFile[] {
  const entries = Array.isArray(data.entries) ? data.entries : [];

  return entries.map((file) => {
    const fileName = getStringValue(file.Name) ?? '';
    return {
      name: fileName,
      size: getNumberValue(file.Size),
      isDirectory: getBooleanValue(file.IsDir),
      modTime: getStringValue(file.ModTime),
      mimeType: getStringValue(file.MimeType),
      path:
        getStringValue(file.Path) ??
        (currentPath && fileName ? `${currentPath}/${fileName}` : fileName),
    };
  });
}

/** Parse plain-text listing output (fallback for non-JSON rclone output). */
export function parsePlainTextFileList(textData: string, currentPath: string): RemoteFile[] {
  const lines = textData
    .trim()
    .split('\n')
    .filter((line) => line.trim());

  const fileLines = lines.filter(
    (line) =>
      !line.startsWith('Listing') &&
      !line.startsWith('Setting up') &&
      !line.startsWith('Error:') &&
      !line.startsWith('DEBUG:') &&
      line.trim() !== ''
  );

  return fileLines.map((line) => {
    const match = /^\s*(\d+)\s+(.+)$/.exec(line);
    if (match) {
      const [, sizeStr, name] = match;
      return {
        name: name.trim(),
        size: Number.parseInt(sizeStr),
        isDirectory: name.endsWith('/'),
        path: currentPath ? `${currentPath}/${name.trim()}` : name.trim(),
      };
    }
    return {
      name: line.trim(),
      size: 0,
      isDirectory: line.endsWith('/'),
      path: currentPath ? `${currentPath}/${line.trim()}` : line.trim(),
    };
  });
}

/** Try to extract individual JSON objects from malformed output. */
export function parseFallbackFormats(dataToProcess: string, currentPath: string): RemoteFile[] {
  if (dataToProcess.includes('"Path":') && dataToProcess.includes('"Name":')) {
    const jsonObjects = dataToProcess.match(/\{[^}]+\}/g);
    if (jsonObjects) {
      const results: RemoteFile[] = [];
      for (const jsonStr of jsonObjects) {
        try {
          const file = JSON.parse(jsonStr);
          results.push({
            name: (file.Name as string) ?? '',
            size: (file.Size as number) ?? 0,
            isDirectory: (file.IsDir as boolean) ?? false,
            modTime: file.ModTime as string | undefined,
            mimeType: file.MimeType as string | undefined,
            path:
              (file.Path as string) ??
              (currentPath ? `${currentPath}/${file.Name}` : file.Name),
          });
        } catch {
          // Skip malformed entries
        }
      }
      return results;
    }
  }
  return [];
}

/** Strip debug output and extract clean JSON array from rclone output. */
export function cleanJsonOutput(dataToProcess: string): string {
  if (dataToProcess.includes('DEBUG:')) {
    const jsonStartIndex = dataToProcess.lastIndexOf('[');
    const jsonEndIndex = dataToProcess.lastIndexOf(']');
    if (jsonStartIndex !== -1 && jsonEndIndex !== -1 && jsonStartIndex < jsonEndIndex) {
      return dataToProcess.substring(jsonStartIndex, jsonEndIndex + 1);
    }
  } else if (dataToProcess.includes('[')) {
    const jsonStartIndex = dataToProcess.indexOf('[');
    const jsonEndIndex = dataToProcess.lastIndexOf(']');
    if (jsonStartIndex !== -1 && jsonEndIndex !== -1) {
      const jsonString = dataToProcess.substring(jsonStartIndex, jsonEndIndex + 1);
      return jsonString.replaceAll('\\\\', '\\').replaceAll('\\n', '\n');
    }
  }
  return dataToProcess;
}

// ============================================================================
// GUID Detection
// ============================================================================

/**
 * Annotate files whose names match GUID/UUID format.
 * Sets `isGuid: true` and `originalGuid` on matching entries.
 * Does NOT rename files — that is consumer-specific (e.g. web repository mapping).
 */
export function detectGuidFiles(files: RemoteFile[]): RemoteFile[] {
  return files.map((file) => {
    if (isValidGuid(file.name)) {
      return { ...file, isGuid: true, originalGuid: file.name };
    }
    return file;
  });
}

/**
 * Resolve GUID file names to human-readable repository names.
 * Replaces the `name` field on matching files; the original GUID is
 * preserved in `originalGuid`. Files without a mapping keep their GUID as-is.
 *
 * @param files - Files with `isGuid` already detected (via detectGuidFiles or FileListParserFactory)
 * @param guidMap - Map of GUID -> display name (e.g. "my-repo:latest")
 */
export function resolveGuidFileNames(
  files: RemoteFile[],
  guidMap: Record<string, string>
): RemoteFile[] {
  if (Object.keys(guidMap).length === 0) return files;

  return files.map((file) => {
    if (!file.isGuid || !file.originalGuid) return file;

    const displayName = guidMap[file.originalGuid];
    if (!displayName) return file;

    return { ...file, name: displayName };
  });
}

// ============================================================================
// Factory
// ============================================================================

/** Options for FileListParserFactory. */
export interface FileListParserOptions {
  /** When true, annotate files whose names match GUID format. */
  detectGuids?: boolean;
}

/**
 * Multi-format parser for rclone file listing output.
 * Tries JSON array, rclone entries wrapper, fallback object extraction,
 * and plain text — in that order.
 */
export class FileListParserFactory {
  private readonly options: FileListParserOptions;

  constructor(
    private readonly currentPath: string,
    options?: FileListParserOptions
  ) {
    this.options = options ?? {};
  }

  parse(dataToProcess: string): RemoteFile[] {
    let fileList: RemoteFile[] = [];
    const cleanedData = cleanJsonOutput(dataToProcess);

    try {
      const parsedData = JSON.parse(cleanedData);

      if (Array.isArray(parsedData)) {
        fileList = parseJsonFileList(parsedData, this.currentPath);
      } else if (parsedData.entries) {
        fileList = parseRcloneFileList(parsedData, this.currentPath);
      }
    } catch {
      fileList = parseFallbackFormats(dataToProcess, this.currentPath);
      if (fileList.length === 0) {
        const textData =
          typeof dataToProcess === 'string' ? dataToProcess : JSON.stringify(dataToProcess);
        fileList = parsePlainTextFileList(textData, this.currentPath);
      }
    }

    fileList = fileList.filter((f) => f.name);

    if (this.options.detectGuids) {
      fileList = detectGuidFiles(fileList);
    }

    return fileList;
  }
}
