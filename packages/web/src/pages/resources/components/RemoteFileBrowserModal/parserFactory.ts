import {
  parseJsonFileList,
  parseRcloneFileList,
  parsePlainTextFileList,
  parseFallbackFormats,
  cleanJsonOutput,
} from './parsers';
import type { RemoteFile } from './types';

type RepositoryMapper = (guid: string) => {
  displayName: string;
  repositoryName?: string;
  repositoryTag?: string;
  isUnmapped: boolean;
};

export class FileListParserFactory {
  constructor(
    private currentPath: string,
    private mapGuidToRepository: RepositoryMapper
  ) {}

  parse(dataToProcess: string): RemoteFile[] {
    let fileList: RemoteFile[] = [];

    const cleanedData = cleanJsonOutput(dataToProcess);

    try {
      const parsedData = JSON.parse(cleanedData);

      if (Array.isArray(parsedData)) {
        fileList = parseJsonFileList(parsedData, this.currentPath, this.mapGuidToRepository);
      } else if (parsedData.entries) {
        fileList = parseRcloneFileList(parsedData, this.currentPath, this.mapGuidToRepository);
      }
    } catch (parseError) {
      console.warn('Parsing remote file data as plain text format failed:', parseError);
      console.warn('Data that failed to parse:', dataToProcess);

      fileList = parseFallbackFormats(dataToProcess, this.currentPath);
      if (fileList.length === 0) {
        const textData = typeof dataToProcess === 'string' ? dataToProcess : JSON.stringify(dataToProcess);
        fileList = parsePlainTextFileList(textData, this.currentPath);
      }
    }

    return fileList.filter((f) => f.name);
  }
}
