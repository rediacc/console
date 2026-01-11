import React from 'react';
import { Space, Typography } from 'antd';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { ResourceType } from '../index';

type ExistingResourceData = Record<string, unknown>;

interface ModalHeaderRendererProps {
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  uiMode: string;
  isExpertMode: boolean;
  isTeamPreselected: boolean;
  existingData?: ExistingResourceData;
  teamFilter?: string | string[];
  creationContext?: 'credentials-only' | 'normal';
  getFormValue: (field: string) => string | undefined;
  t: TypedTFunction;
}

const RESOURCE_CONFIG = {
  storage: { key: 'storage', createKey: 'resources:storage.createStorage' },
  repository: { key: 'repositories', createKey: 'resources:repositories.createRepository' },
  machine: { key: 'machines', createKey: 'machines:createMachine' },
  team: { key: 'teams', createKey: 'resources:teams.createTeam' },
  region: { key: 'regions', createKey: 'resources:regions.createRegion' },
  bridge: { key: 'bridges', createKey: 'resources:bridges.createBridge' },
  cluster: { key: 'clusters', createKey: 'ceph:clusters.createCluster' },
  pool: { key: 'pools', createKey: 'ceph:pools.createPool' },
  image: { key: 'images', createKey: 'ceph:images.createImage' },
  snapshot: { key: 'snapshots', createKey: 'ceph:snapshots.createSnapshot' },
  clone: { key: 'clones', createKey: 'ceph:clones.createClone' },
} as const;

const getResourceTranslationKey = (resourceType: ResourceType) => {
  return RESOURCE_CONFIG[resourceType].key;
};

export const resolveTeamName = (
  getFormValue: (field: string) => string | undefined,
  existingData?: ExistingResourceData,
  teamFilter?: string | string[]
): string => {
  const formTeam = getFormValue('teamName');
  if (formTeam) return formTeam;
  const teamNameValue = existingData?.teamName;
  if (teamNameValue && typeof teamNameValue === 'string') return teamNameValue;
  if (teamFilter) {
    const filterValue = Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
    if (typeof filterValue === 'string' && filterValue) {
      return filterValue;
    }
  }
  return 'Private Team';
};

export const getBridgeName = (getFormValue: (field: string) => string | undefined): string => {
  const formBridge = getFormValue('bridgeName');
  if (formBridge) return formBridge;
  return 'Global Bridges';
};

export const createFunctionSubtitle = (
  resourceType: ResourceType,
  existingData: ExistingResourceData | undefined,
  t: TypedTFunction
): React.ReactNode => {
  if (!existingData) {
    return null;
  }

  const teamLabel: string =
    typeof existingData.teamName === 'string' ? existingData.teamName : t('common:unknown');

  const resourceNameKey = `${resourceType}Name`;
  const resourceNameValue = (existingData as Record<string, unknown>)[resourceNameKey];
  const resourceName: string = typeof resourceNameValue === 'string' ? resourceNameValue : '';

  return (
    <Space size="small">
      <Typography.Text>{t('machines:team')}:</Typography.Text>
      <Typography.Text strong>{teamLabel}</Typography.Text>
      {['machine', 'repository', 'storage'].includes(resourceType) && resourceName && (
        <>
          <Typography.Text>
            {(() => {
              if (resourceType === 'machine') {
                return t('machines:machine');
              } else if (resourceType === 'storage') {
                return t('resources:storage.storage');
              }
              return t('repositories.repository');
            })()}:
          </Typography.Text>
          <Typography.Text strong>{resourceName}</Typography.Text>
        </>
      )}
    </Space>
  );
};

const resolveTeamFromFilter = (
  uiMode: string,
  teamFilter?: string | string[]
): string | undefined => {
  if (uiMode === 'simple') return 'Private Team';
  if (Array.isArray(teamFilter)) return teamFilter[0];
  return teamFilter;
};

const getRepositoryCreateTitle = (
  createText: string,
  creationContext: string | undefined,
  uiMode: string,
  existingData?: ExistingResourceData,
  teamFilter?: string | string[]
): string | null => {
  if (creationContext === 'credentials-only') {
    const teamNameValue = existingData?.teamName;
    const fallbackTeam = resolveTeamFromFilter(uiMode, teamFilter);
    const team = (typeof teamNameValue === 'string' ? teamNameValue : null) ?? fallbackTeam;
    return `Create Repository (Credentials) in ${team}`;
  }

  if (existingData?.machineName) {
    const machineNameValue = existingData.machineName;
    return `${createText} for ${typeof machineNameValue === 'string' ? machineNameValue : ''}`;
  }

  return null;
};

const resolveTeamForTitle = (uiMode: string, teamFilter?: string | string[]): string => {
  if (uiMode !== 'expert' || !teamFilter) return 'Private Team';
  return Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
};

const getPreselectedTeamTitle = (
  createText: string,
  uiMode: string,
  teamFilter?: string | string[]
): string => {
  const team = resolveTeamForTitle(uiMode, teamFilter);
  return `${createText} in ${team}`;
};

const getModalTitle = ({
  resourceType,
  mode,
  uiMode,
  isTeamPreselected,
  existingData,
  teamFilter,
  creationContext,
  t,
}: Omit<ModalHeaderRendererProps, 'getFormValue' | 'isExpertMode'>): string => {
  if (mode !== 'create') {
    return `${t('resources:general.edit')} ${t(`resources:${getResourceTranslationKey(resourceType)}.${resourceType}Name`)}`;
  }

  const createKey = RESOURCE_CONFIG[resourceType].createKey;
  const createText = t(createKey);

  if (resourceType === 'repository') {
    const repoTitle = getRepositoryCreateTitle(
      createText,
      creationContext,
      uiMode,
      existingData,
      teamFilter
    );
    if (repoTitle) return repoTitle;
  }

  if (resourceType === 'machine') return createText;

  if (isTeamPreselected) {
    return getPreselectedTeamTitle(createText, uiMode, teamFilter);
  }

  return createText;
};

export const getFunctionTitle = (resourceType: ResourceType, t: TypedTFunction): string => {
  if (resourceType === 'machine') {
    return t('machines:systemFunctions');
  } else if (resourceType === 'storage') {
    return t('resources:storage.storageFunctions');
  }
  return t(`${getResourceTranslationKey(resourceType)}.${resourceType}Functions`);
};

export const ModalTitleRenderer: React.FC<ModalHeaderRendererProps> = (props) => {
  const baseTitle = getModalTitle(props);
  return <>{baseTitle}</>;
};
