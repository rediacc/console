/**
 * Shared types for remote storage file browsing.
 * Used by both the web app (RemoteFileBrowserModal) and the CLI (storage browse).
 */

/** A file or directory entry from a remote storage listing. */
export interface RemoteFile {
  name: string;
  size: number;
  isDirectory: boolean;
  modTime?: string;
  mimeType?: string;
  path?: string;
  /** True when the file name matches GUID/UUID format (backup file). */
  isGuid?: boolean;
  /** Original GUID filename, preserved when name is replaced with a display name. */
  originalGuid?: string;
}

/**
 * Raw rclone lsjson entry.
 * Supports both camelCase and PascalCase field names that rclone may output.
 */
export interface RcloneEntry {
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
