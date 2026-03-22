import type {
  RepositoryInfo,
  ServiceInfo,
  SystemInfo,
} from '@rediacc/shared/queue-vault/data/list-types.generated';
import type { Machine } from '@/types';

// RepositoryVaultData extends generated RepositoryInfo
// (kept for backward compatibility with existing code)
export interface RepositoryVaultData extends RepositoryInfo {
  // All fields now come from RepositoryInfo
}

// ServiceData extends the generated ServiceInfo with optional fields
export interface ServiceData extends Partial<ServiceInfo> {
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
  systemData?: SystemInfo;
  services: ServiceData[];
}
