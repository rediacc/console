import React from 'react';
import { Flex, Space, Typography } from 'antd';
import { TFunction } from 'i18next';
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
  t: TFunction;
}

const RESOURCE_CONFIG = {
  storage: { key: 'storage', createKey: 'resources:storage.createStorage' },
  repository: { key: 'repositories', createKey: 'resources:repositories.createRepository' },
  machine: { key: 'machines', createKey: 'machines:createMachine' },
  team: { key: 'teams', createKey: 'resources:teams.createTeam' },
  region: { key: 'regions', createKey: 'system:regions.createRegion' },
  bridge: { key: 'bridges', createKey: 'system:bridges.createBridge' },
  cluster: { key: 'clusters', createKey: 'ceph:clusters.createCluster' },
  pool: { key: 'pools', createKey: 'ceph:pools.createPool' },
  image: { key: 'images', createKey: 'ceph:images.createImage' },
  snapshot: { key: 'snapshots', createKey: 'ceph:snapshots.createSnapshot' },
  clone: { key: 'clones', createKey: 'ceph:clones.createClone' },
} as const;

const getResourceTranslationKey = (resourceType: ResourceType) => {
  return RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.key || `${resourceType}s`;
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
  t: TFunction
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
            {t(
              resourceType === 'machine'
                ? 'machines:machine'
                : resourceType === 'storage'
                  ? 'resources:storage.storage'
                  : 'repositories.repository'
            )}
            :
          </Typography.Text>
          <Typography.Text strong>{resourceName}</Typography.Text>
        </>
      )}
    </Space>
  );
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
  if (mode === 'create') {
    const createKey = RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.createKey;
    const createText = createKey ? t(createKey) : '';

    // Special case for repository creation
    if (resourceType === 'repository') {
      // Check if this is credential-only mode (either from Add Credential button or Repository Credentials tab)
      const isCredentialOnlyMode =
        (existingData?.repositoryGuid &&
          typeof existingData.repositoryGuid === 'string' &&
          existingData.repositoryGuid.trim() !== '') ||
        creationContext === 'credentials-only';

      if (isCredentialOnlyMode) {
        // For credential-only mode, show "Create Repository (Credentials) in [team]"
        const teamNameValue = existingData?.teamName;
        const team =
          (typeof teamNameValue === 'string' ? teamNameValue : null) ||
          (uiMode === 'simple'
            ? 'Private Team'
            : Array.isArray(teamFilter)
              ? teamFilter[0]
              : teamFilter);
        return `Create Repository (Credentials) in ${team}`;
      } else if (existingData?.machineName) {
        // For repository creation from machine
        const machineNameValue = existingData.machineName;
        return `${createText} for ${typeof machineNameValue === 'string' ? machineNameValue : ''}`;
      }
    }

    if (resourceType === 'machine') {
      return createText;
    }

    if (isTeamPreselected) {
      const team =
        uiMode === 'expert' && teamFilter
          ? Array.isArray(teamFilter)
            ? teamFilter[0]
            : teamFilter
          : 'Private Team';
      return `${createText} in ${team}`;
    }
    return createText;
  }
  return `${t('resources:general.edit')} ${t(`resources:${getResourceTranslationKey(resourceType)}.${resourceType}Name`)}`;
};

const getModalSubtitle = ({
  resourceType,
  mode,
  isExpertMode,
  existingData,
  teamFilter,
  getFormValue,
}: Pick<
  ModalHeaderRendererProps,
  'resourceType' | 'mode' | 'isExpertMode' | 'existingData' | 'teamFilter' | 'getFormValue'
>): string => {
  if (!(mode === 'create' && resourceType === 'machine')) return '';

  const formTeam = getFormValue('teamName');
  if (formTeam) return formTeam;

  const teamNameValue = existingData?.teamName;
  if (teamNameValue && typeof teamNameValue === 'string') return teamNameValue;

  // Simple mode always shows "Private Team"
  if (!isExpertMode) return 'Private Team';

  // Expert mode: show team filter if available
  if (teamFilter) {
    return Array.isArray(teamFilter) ? teamFilter[0] : teamFilter;
  }

  return isExpertMode ? '' : 'Private Team';
};

export const getFunctionTitle = (resourceType: ResourceType, t: TFunction): string => {
  if (resourceType === 'machine') return t('machines:systemFunctions');
  if (resourceType === 'storage') return t('resources:storage.storageFunctions');
  return t(`${getResourceTranslationKey(resourceType)}.${resourceType}Functions`);
};

export const renderModalTitle = (props: ModalHeaderRendererProps): React.ReactNode => {
  const baseTitle = getModalTitle(props);

  if (props.mode === 'create' && props.resourceType === 'machine') {
    const subtitle = getModalSubtitle(props);
    return (
      <Flex vertical gap={4}>
        {/* eslint-disable-next-line no-restricted-syntax */}
        <Typography.Text strong style={{ fontSize: 16 }}>
          {baseTitle}
        </Typography.Text>
        {subtitle && (
          <>
            {/* eslint-disable-next-line no-restricted-syntax */}
            <Typography.Text style={{ fontSize: 12 }}>
              {props.t('general.team')}: {subtitle}
            </Typography.Text>
          </>
        )}
      </Flex>
    );
  }

  return baseTitle;
};
