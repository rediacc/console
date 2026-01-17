import type { Machine, PluginContainer } from '@/types';
import type { RepositoryInfo } from '@rediacc/shared/queue-vault/data/list-types.generated';

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

export interface GroupedRepository {
  name: string;
  tags: Repository[];
  grandTag: Repository | null;
  forkTags: Repository[];
  isExpanded: boolean;
}

export interface RepositoryTableRow extends Repository {
  key?: string;
  actionId?: string;
}

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
  port_mappings?: PortMapping[];
  Repository?: string;
  [key: string]: unknown;
}

export interface RepositoryService {
  Repository?: string;
  service_name?: string;
  unit_file?: string;
  [key: string]: unknown;
}

export interface RepositoryServicesState {
  services: RepositoryService[];
  error: string | null;
}

export interface RepositoryContainersState {
  containers: Container[];
  error: string | null;
}

export interface SystemInfo {
  hostname: string;
  kernel: string;
  os_name: string;
  uptime: string;
  system_time: number;
  system_time_human: string;
  timezone: string;
  cpu_count: number;
  cpu_model: string;
  memory: {
    total: string;
    used: string;
    available: string;
  };
  disk: {
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
  datastore: {
    path: string;
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
}

export interface MachineRepositoryTableProps {
  machine: Machine;
  onActionComplete?: () => void;
  hideSystemInfo?: boolean;
  onCreateRepository?: (machine: Machine, repositoryGuid: string) => void;
  onRepositoryClick?: (Repository: Repository) => void;
  highlightedRepository?: Repository | null;
  onContainerClick?: (container: Container | PluginContainer) => void;
  highlightedContainer?: Container | PluginContainer | null;
  isLoading?: boolean;
  onRefreshMachines?: () => Promise<void>;
  refreshKey?: number;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
}

export type MenuClickEvent = { key: string; domEvent: React.MouseEvent | React.KeyboardEvent };
