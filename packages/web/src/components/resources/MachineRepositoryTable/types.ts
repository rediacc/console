import type { Machine, PluginContainer } from '@/types';

export interface Repository {
  name: string;
  repositoryTag?: string;
  size: number;
  size_human: string;
  modified: number;
  modified_human: string;
  mounted: boolean;
  mount_path: string;
  image_path: string;
  accessible: boolean;
  has_rediaccfile: boolean;
  docker_available: boolean;
  docker_running: boolean;
  container_count: number;
  plugin_count: number;
  has_services: boolean;
  service_count: number;
  isUnmapped?: boolean;
  originalGuid?: string;
  disk_space?: {
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
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
