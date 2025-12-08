import i18n from '@/i18n/config';

type ResourceAction = 'created' | 'updated' | 'deleted' | 'renamed';

/**
 * Creates a standardized success message for resource operations.
 * Falls back to English if translation key doesn't exist.
 */
export const createResourceMessage =
  (action: ResourceAction, resourceType: string, nameKey: string) =>
  (vars: Record<string, unknown>): string => {
    const name = vars[nameKey] as string;
    const key = `common:resource.${action}`;

    // Try to use i18n translation, fallback to English template
    const translated = i18n.t(key, { type: resourceType, name });
    if (translated !== key) {
      return translated;
    }

    // Fallback templates
    const templates: Record<ResourceAction, string> = {
      created: `${resourceType} "${name}" created successfully`,
      updated: `${resourceType} "${name}" updated successfully`,
      deleted: `${resourceType} "${name}" deleted successfully`,
      renamed: `${resourceType} renamed to "${name}" successfully`,
    };

    return templates[action];
  };

/**
 * Pre-built message creators for common resource types
 */
export const resourceMessages = {
  team: {
    created: createResourceMessage('created', 'Team', 'teamName'),
    updated: createResourceMessage('updated', 'Team', 'teamName'),
    deleted: createResourceMessage('deleted', 'Team', 'teamName'),
  },
  machine: {
    created: createResourceMessage('created', 'Machine', 'machineName'),
    updated: createResourceMessage('updated', 'Machine', 'machineName'),
    deleted: createResourceMessage('deleted', 'Machine', 'machineName'),
  },
  bridge: {
    created: createResourceMessage('created', 'Bridge', 'bridgeName'),
    updated: createResourceMessage('updated', 'Bridge', 'bridgeName'),
    deleted: createResourceMessage('deleted', 'Bridge', 'bridgeName'),
  },
  region: {
    created: createResourceMessage('created', 'Region', 'regionName'),
    updated: createResourceMessage('updated', 'Region', 'regionName'),
    deleted: createResourceMessage('deleted', 'Region', 'regionName'),
    renamed: createResourceMessage('renamed', 'Region', 'newRegionName'),
  },
  repo: {
    created: createResourceMessage('created', 'Repository', 'repoName'),
    updated: createResourceMessage('updated', 'Repository', 'repoName'),
    deleted: createResourceMessage('deleted', 'Repository', 'repoName'),
  },
  storage: {
    created: createResourceMessage('created', 'Storage', 'storageName'),
    updated: createResourceMessage('updated', 'Storage', 'storageName'),
    deleted: createResourceMessage('deleted', 'Storage', 'storageName'),
  },
  user: {
    created: createResourceMessage('created', 'User', 'email'),
    updated: createResourceMessage('updated', 'User', 'email'),
    deleted: createResourceMessage('deleted', 'User', 'email'),
  },
} as const;
