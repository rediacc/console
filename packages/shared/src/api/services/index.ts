import { createAuditService } from './audit';
import { createAuthService } from './auth';
import { createBridgesService } from './bridges';
import { createCephService } from './ceph';
import { createCompanyService } from './company';
import { createMachinesService } from './machines';
import { createPermissionsService } from './permissions';
import { createQueueService } from './queue';
import { createRegionsService } from './regions';
import { createReposService } from './repos';
import { createStorageService } from './storage';
import { createTeamsService } from './teams';
import { createUsersService } from './users';
import type { ApiClient } from './types';

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
export type { PermissionGroupWithParsedPermissions } from './permissions';
