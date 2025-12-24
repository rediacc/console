import type { Machine } from '@/types';

export interface RepositoryVaultData {
  name: string;
  size: number;
  size_human: string;
  modified: number;
  modified_human: string;
  image_path: string;
  mounted: boolean;
  mount_path: string;
  accessible: boolean;
  disk_space?: {
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
  has_rediaccfile: boolean;
  docker_running: boolean;
  container_count: number;
  has_services: boolean;
  service_count: number;
  total_volumes?: number;
  internal_volumes?: number;
  external_volumes?: number;
  external_volume_names?: string[];
  volume_status?: 'safe' | 'warning' | 'none';
}

export interface ServiceData {
  name: string;
  active_state: string;
  memory_human?: string;
  main_pid?: number;
  uptime_human?: string;
  restarts?: number;
  repository?: string;
  service_name?: string;
  unit_file?: string;
}

export interface RepositoryPanelData {
  machine: Machine;
  repositoryData: RepositoryVaultData;
  systemData?: Record<string, unknown>;
  services: ServiceData[];
}
