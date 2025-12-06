import type { ApiClient } from './types';
import { createAuthService } from './auth';
import { createCompanyService } from './company';
import { createUsersService } from './users';
import { createPermissionsService } from './permissions';
import { createTeamsService } from './teams';
import { createRegionsService } from './regions';
import { createBridgesService } from './bridges';
import { createMachinesService } from './machines';
import { createReposService } from './repos';
import { createStorageService } from './storage';
import { createQueueService } from './queue';
import { createCephService } from './ceph';
import { createAuditService } from './audit';

export function createApiServices(client: ApiClient) {
  return {
    auth: createAuthService(client),
    company: createCompanyService(client),
    users: createUsersService(client),
    permissions: createPermissionsService(client),
    teams: createTeamsService(client),
    regions: createRegionsService(client),
    bridges: createBridgesService(client),
    machines: createMachinesService(client),
    repos: createReposService(client),
    storage: createStorageService(client),
    queue: createQueueService(client),
    ceph: createCephService(client),
    audit: createAuditService(client),
  };
}

export type { ApiClient, ApiRequestConfig } from './types';
