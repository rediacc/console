export interface MachineAvailabilitySummaryProps {
  teamFilter?: string | string[];
  onRefresh?: () => void;
}

export interface MachineStats {
  total: number;
  available: number;
  cluster: number;
  image: number;
  clone: number;
}
