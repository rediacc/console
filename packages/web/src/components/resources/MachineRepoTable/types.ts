import type { Machine, PluginContainer } from '@/types';

export interface Repo {
  name: string;
  repoTag?: string;
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

export interface GroupedRepo {
  name: string;
  tags: Repo[];
  grandTag: Repo | null;
  forkTags: Repo[];
  isExpanded: boolean;
}

export interface RepoTableRow extends Repo {
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
  Repo?: string;
  [key: string]: unknown;
}

export interface RepoService {
  Repo?: string;
  service_name?: string;
  unit_file?: string;
  [key: string]: unknown;
}

export interface RepoServicesState {
  services: RepoService[];
  error: string | null;
}

export interface RepoContainersState {
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

export interface MachineRepoTableProps {
  machine: Machine;
  onActionComplete?: () => void;
  hideSystemInfo?: boolean;
  onCreateRepo?: (machine: Machine, repoGuid: string) => void;
  onRepoClick?: (Repo: Repo) => void;
  highlightedRepo?: Repo | null;
  onContainerClick?: (container: Container | PluginContainer) => void;
  highlightedContainer?: Container | PluginContainer | null;
  isLoading?: boolean;
  onRefreshMachines?: () => Promise<void>;
  refreshKey?: number;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
}

export type MenuClickEvent = { key: string; domEvent: React.MouseEvent | React.KeyboardEvent };
