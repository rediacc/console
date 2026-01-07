import type { RepositoryInfo } from '@rediacc/shared/queue-vault/data/list-types.generated';

export interface ContainerData {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  port_mappings?: {
    host?: string;
    host_port?: string;
    container_port: string;
    protocol: string;
  }[];
  labels: string;
  mounts: string;
  networks: string;
  size: string;
  repository: string;
  cpu_percent: string;
  memory_usage: string;
  memory_percent: string;
  net_io: string;
  block_io: string;
  pids: string;
}

export interface RepositoryRowData {
  name: string;
  repositoryTag?: string;
  originalGuid?: string;
}

// Repository interface derived from vaultStatus (runtime data)
// Extends the generated RepositoryInfo with frontend-computed fields
export interface RepositoryContainerData extends RepositoryInfo {
  /** Repository tag for versioning (frontend-added) */
  repositoryTag?: string;
  /** Plugin container count (computed from containers) */
  plugin_count?: number;
  /** Whether this repository is unmapped from API data (frontend-added) */
  isUnmapped?: boolean;
  /** Original GUID before name resolution (frontend-added) */
  originalGuid?: string;
}
