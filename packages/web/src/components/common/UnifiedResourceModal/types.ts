import type { GetOrganizationTeams_ResultSet1 } from '@rediacc/shared/types';
import type { Machine, Repository } from '@/types';

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
  Partial<GetOrganizationTeams_ResultSet1> & {
    prefilledMachine?: boolean;
    clusters?: { clusterName: string }[];
    pools?: { poolName: string; clusterName: string }[];
    availableMachines?: {
      machineName: string;
      bridgeName: string;
      regionName: string;
      status?: string;
    }[];
    images?: { imageName: string }[];
    snapshots?: { snapshotName: string }[];
  } & Record<string, unknown>;
