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

export interface NetworkInterface {
  name: string;
  state: string;
  mac_address: string;
  mtu: number;
  ipv4_addresses: string[];
  ipv6_addresses: string[];
  default_gateway: string | null;
}

export interface VaultNetwork {
  default_gateway?: string;
  default_interface?: string;
  interfaces: NetworkInterface[];
}

export interface BlockDevicePartition {
  name: string;
  path: string;
  size_bytes: number;
  size_human: string;
  filesystem: string | null;
  mountpoint: string | null;
}

export interface BlockDevice {
  name: string;
  path: string;
  size_bytes: number;
  size_human: string;
  model: string;
  serial: string | null;
  type: string;
  discard_granularity: number;
  physical_sector_size: number;
  logical_sector_size: number;
  partitions: BlockDevicePartition[];
}

export interface Container {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  cpu_percent?: string;
  memory_usage?: string;
  memory_percent?: string;
  net_io?: string;
  block_io?: string;
  pids?: string;
}

export interface VaultData {
  system?: SystemInfo;
  network?: VaultNetwork;
  block_devices?: BlockDevice[];
  system_containers?: Container[];
}
