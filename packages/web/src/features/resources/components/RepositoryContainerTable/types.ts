import type { Machine, PluginContainer } from '@/types';
import type { RepositoryInfo } from '@rediacc/shared/queue-vault/data/list-types.generated';

export interface PortMapping {
  host: string;
  host_port: string;
  container_port: string;
  protocol: string;
}

export interface Container {
  id: string;
  name: string;
  state: string;
  status?: string;
  image?: string;
  ports?: string;
  created?: string;
  repository?: string;
  port_mappings?: PortMapping[];
  cpu_percent?: string;
  memory_usage?: string;
  memory_percent?: string;
  net_io?: string;
  block_io?: string;
  pids?: string;
  [key: string]: unknown;
}

// Repository extends generated RepositoryInfo with frontend-computed fields
export interface Repository extends RepositoryInfo {
  /** Repository tag for versioning (frontend-added) */
  repositoryTag?: string;
  /** Plugin container count (computed from containers) */
  plugin_count?: number;
  /** Whether this repository is unmapped from API data (frontend-added) */
  isUnmapped?: boolean;
  /** Original GUID before name resolution (frontend-added) */
  originalGuid?: string;
}

export interface RepositoryContainerTableProps {
  machine: Machine;
  repository: Repository;
  onContainerClick?: (container: Container | PluginContainer) => void;
  highlightedContainer?: Container | PluginContainer | null;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  refreshKey?: number;
}

export interface VaultStatusRepo {
  name?: string;
  mount_path?: string;
  image_path?: string;
}

export interface VaultStatusResult {
  repositories?: VaultStatusRepo[];
  containers?: {
    containers: Container[];
    total_count?: number;
    running_count?: number;
    stopped_count?: number;
    docker_version?: string;
  };
}
