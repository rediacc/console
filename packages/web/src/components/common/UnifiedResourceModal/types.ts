import type { Machine, Repository } from '@/types';
import type { GetCompanyTeams_ResultSet1 } from '@rediacc/shared/types';

export type ResourceType =
  | 'machine'
  | 'repository'
  | 'storage'
  | 'team'
  | 'region'
  | 'bridge'
  | 'cluster'
  | 'pool'
  | 'image'
  | 'snapshot'
  | 'clone';

export type ResourceFormValues = Record<string, unknown>;

export type ExistingResourceData = Partial<Machine> &
  Partial<Repository> &
  Partial<GetCompanyTeams_ResultSet1> & {
    prefilledMachine?: boolean;
    clusters?: Array<{ clusterName: string }>;
    pools?: Array<{ poolName: string; clusterName: string }>;
    availableMachines?: Array<{
      machineName: string;
      bridgeName: string;
      regionName: string;
      status?: string;
    }>;
    images?: Array<{ imageName: string }>;
    snapshots?: Array<{ snapshotName: string }>;
  } & Record<string, unknown>;
