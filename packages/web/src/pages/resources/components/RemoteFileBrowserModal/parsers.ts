import type { RemoteFile } from './types';

interface RcloneEntry {
  name?: string;
  Name?: string;
  size?: number | string;
  Size?: number | string;
  isDirectory?: boolean;
  IsDir?: boolean;
  permissions?: string;
  date?: string;
  time?: string;
  ModTime?: string;
  Path?: string;
  MimeType?: string;
}

const getStringValue = (value: unknown): string | undefined =>
  typeof value === 'string' ? value : undefined;

const getNumberValue = (value: unknown): number => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
};

const getBooleanValue = (value: unknown): boolean => (typeof value === 'boolean' ? value : false);

type RepositoryMapper = (guid: string) => {
  displayName: string;
  repositoryName?: string;
  repositoryTag?: string;
  isUnmapped: boolean;
};

const isGuidFormat = (fileName: string): boolean => {
  const guidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return guidPattern.test(fileName);
};

export function parseJsonFileList(
  data: unknown,
  currentPath: string,
  mapGuidToRepository: RepositoryMapper
): RemoteFile[] {
  if (!Array.isArray(data)) {
    return [];
  }

  return data.map((file: RcloneEntry) => {
    const fileName = getStringValue(file.name) ?? getStringValue(file.Name) ?? '';
    const isGuid = isGuidFormat(fileName);

    let displayName = fileName;
    let repoInfo = null;

    const isDirectoryFlag =
      getBooleanValue(file.isDirectory) ||
      getBooleanValue(file.IsDir) ||
      Boolean(getStringValue(file.permissions)?.startsWith('d'));

    if (isGuid && !isDirectoryFlag) {
      repoInfo = mapGuidToRepository(fileName);
      displayName = repoInfo.displayName;
    }

    return {
      name: displayName,
      originalGuid: isGuid && !isDirectoryFlag ? fileName : undefined,
      repositoryName: repoInfo?.repositoryName,
      repositoryTag: repoInfo?.repositoryTag,
      isUnmapped: repoInfo?.isUnmapped || false,
      size: getNumberValue(file.size ?? file.Size ?? 0),
      isDirectory: isDirectoryFlag,
      modTime:
        file.date && file.time ? `${file.date} ${file.time}` : getStringValue(file.ModTime),
      path:
        getStringValue(file.Path) ||
        (currentPath && fileName ? `${currentPath}/${fileName}` : fileName),
    };
  });
}

export function parseRcloneFileList(
  data: { entries?: RcloneEntry[] },
  currentPath: string,
  mapGuidToRepository: RepositoryMapper
): RemoteFile[] {
  const entries = Array.isArray(data.entries) ? data.entries : [];

  return entries.map((file) => {
    const fileName = getStringValue(file.Name) || '';
    const isGuid = isGuidFormat(fileName);

    let displayName = fileName;
    let repoInfo = null;

    const isDirectoryFlag = getBooleanValue(file.IsDir);
    if (isGuid && !isDirectoryFlag) {
      repoInfo = mapGuidToRepository(fileName);
      displayName = repoInfo.displayName;
    }

    return {
      name: displayName,
      originalGuid: isGuid && !isDirectoryFlag ? fileName : undefined,
      repositoryName: repoInfo?.repositoryName,
      repositoryTag: repoInfo?.repositoryTag,
      isUnmapped: repoInfo?.isUnmapped || false,
      size: getNumberValue(file.Size),
      isDirectory: isDirectoryFlag,
      modTime: getStringValue(file.ModTime),
      mimeType: getStringValue(file.MimeType),
      path:
        getStringValue(file.Path) ||
        (currentPath && fileName ? `${currentPath}/${fileName}` : fileName),
    };
  });
}

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
    const match = line.match(/^\s*(\d+)\s+(.+)$/);
    if (match) {
      const [, sizeStr, name] = match;
      return {
        name: name.trim(),
        size: parseInt(sizeStr),
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

export function parseFallbackFormats(dataToProcess: string, currentPath: string): RemoteFile[] {
  if (dataToProcess.includes('"Path":') && dataToProcess.includes('"Name":')) {
    const jsonObjects = dataToProcess.match(/\{[^}]+\}/g);
    if (jsonObjects) {
      return jsonObjects
        .map((jsonStr) => {
          try {
            const file = JSON.parse(jsonStr);
            return {
              name: file.Name || '',
              size: file.Size || 0,
              isDirectory: file.IsDir || false,
              modTime: file.ModTime,
              mimeType: file.MimeType,
              path: file.Path || (currentPath ? `${currentPath}/${file.Name}` : file.Name),
            };
          } catch {
            return null;
          }
        })
        .filter((f) => f !== null) as RemoteFile[];
    }
  }
  return [];
}

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
      return jsonString.replace(/\\\\/g, '\\').replace(/\\n/g, '\n');
    }
  }
  return dataToProcess;
}
