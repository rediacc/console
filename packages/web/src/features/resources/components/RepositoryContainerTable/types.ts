import type { Machine, PluginContainer } from '@/types';

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
