/**
 * Web-specific file list parsers.
 *
 * Wraps the shared base parsers with GUID-to-repository mapping
 * that is only relevant to the web app's RemoteFileBrowserModal.
 */

import {
  cleanJsonOutput,
  FileListParserFactory as BaseFileListParserFactory,
  parseJsonFileList as baseParseJsonFileList,
  parseRcloneFileList as baseParseRcloneFileList,
  type RcloneEntry,
} from "@rediacc/shared/queue-vault/storage-browser";
import type { RemoteFile as BaseRemoteFile } from "@rediacc/shared/queue-vault/storage-browser";
import { isValidGuid } from "@rediacc/shared/validation";
import type { RemoteFile } from "./types";

// Re-export shared utilities used directly by the component
export { cleanJsonOutput };
export {
  parsePlainTextFileList,
  parseFallbackFormats,
} from "@rediacc/shared/queue-vault/storage-browser";

type RepositoryMapper = (guid: string) => {
  displayName: string;
  repositoryName?: string;
  repositoryTag?: string;
  isUnmapped: boolean;
};

function enrichWithGuid(
  file: BaseRemoteFile,
  mapGuidToRepository: RepositoryMapper,
): RemoteFile {
  const isGuid = isValidGuid(file.name);

  if (isGuid && !file.isDirectory) {
    const repoInfo = mapGuidToRepository(file.name);
    return {
      ...file,
      name: repoInfo.displayName,
      originalGuid: file.name,
      repositoryName: repoInfo.repositoryName,
      repositoryTag: repoInfo.repositoryTag,
      isUnmapped: repoInfo.isUnmapped,
    };
  }

  return { ...file, isUnmapped: false };
}

export function parseJsonFileList(
  data: unknown,
  currentPath: string,
  mapGuidToRepository: RepositoryMapper,
): RemoteFile[] {
  const baseFiles = baseParseJsonFileList(data, currentPath);
  return baseFiles.map((f) => enrichWithGuid(f, mapGuidToRepository));
}

export function parseRcloneFileList(
  data: { entries?: RcloneEntry[] },
  currentPath: string,
  mapGuidToRepository: RepositoryMapper,
): RemoteFile[] {
  const baseFiles = baseParseRcloneFileList(data, currentPath);
  return baseFiles.map((f) => enrichWithGuid(f, mapGuidToRepository));
}

/**
 * Web-specific FileListParserFactory that adds GUID-to-repository mapping
 * on top of the shared base parser.
 */
export class FileListParserFactory {
  private baseFactory: BaseFileListParserFactory;

  constructor(
    currentPath: string,
    private readonly mapGuidToRepository: RepositoryMapper,
  ) {
    this.baseFactory = new BaseFileListParserFactory(currentPath);
  }

  parse(dataToProcess: string): RemoteFile[] {
    const baseFiles = this.baseFactory.parse(dataToProcess);
    return baseFiles.map((f) => enrichWithGuid(f, this.mapGuidToRepository));
  }
}
