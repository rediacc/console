import React from 'react';
import { useTranslation } from 'react-i18next';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { LocalActionsMenu } from '@/components/resources/internal/LocalActionsMenu';
import { isCredential as coreIsCredential, isFork as coreIsFork } from '@/platform';
import type { Machine } from '@/types';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  ControlOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  EditOutlined,
  ExpandOutlined,
  EyeOutlined,
  FunctionOutlined,
  KeyOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RiseOutlined,
  SaveOutlined,
  ShrinkOutlined,
} from '@/utils/optimizedIcons';
import type { GetTeamRepositories_ResultSet1 as TeamRepo } from '@rediacc/shared/types';
import type { MenuClickEvent, RepositoryContainersState, RepositoryTableRow } from '../types';
import type { MenuProps } from 'antd';

interface RepositoryActionsMenuProps {
  record: RepositoryTableRow;
  teamRepositories: TeamRepo[];
  machine: Machine;
  userEmail: string;
  containersData: Record<string, RepositoryContainersState>;
  isExecuting: boolean;
  onQuickAction: (
    repository: RepositoryTableRow,
    functionName: string,
    priority: number,
    option?: string
  ) => void;
  onRunFunction: (repository: RepositoryTableRow, functionName?: string) => void;
  onPromoteToGrand: (repository: RepositoryTableRow) => void;
  onDeleteFork: (repository: RepositoryTableRow) => void;
  onRenameTag: (repository: RepositoryTableRow) => void;
  onRenameRepository: (repository: RepositoryTableRow) => void;
  onDeleteGrandRepository: (repository: RepositoryTableRow) => void;
  onRepositoryClick?: (repository: RepositoryTableRow) => void;
  onCreateRepository?: (machine: Machine, repositoryGuid: string) => void;
  t: ReturnType<typeof useTranslation>['t'];
}

export const RepositoryActionsMenu: React.FC<RepositoryActionsMenuProps> = ({
  record,
  teamRepositories,
  machine,
  userEmail,
  containersData,
  isExecuting,
  onQuickAction,
  onRunFunction,
  onPromoteToGrand,
  onDeleteFork,
  onRenameTag,
  onRenameRepository,
  onDeleteGrandRepository,
  onRepositoryClick,
  onCreateRepository,
  t,
}) => {
  const RepoData = teamRepositories.find(
    (r) => r.repositoryName === record.name && r.repositoryTag === record.repositoryTag
  );

  const menuItems: MenuProps['items'] = [];

  menuItems.push({
    key: 'up',
    label: t('functions:functions.up.name'),
    icon: <PlayCircleOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onQuickAction(record, 'up', 4, 'mount');
    },
  });

  if (record.mounted) {
    menuItems.push({
      key: 'down',
      label: t('functions:functions.down.name'),
      icon: <PauseCircleOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'down', 4, 'unmount');
      },
    });
  }

  if (!record.mounted) {
    menuItems.push({
      key: 'validate',
      label: t('functions:functions.validate.name'),
      icon: <CheckCircleOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onRunFunction(record, 'validate');
      },
    });
  }

  menuItems.push({
    key: 'fork',
    label: t('functions:functions.fork.name'),
    icon: <CopyOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'fork');
    },
  });

  menuItems.push({
    key: 'deploy',
    label: t('functions:functions.deploy.name'),
    icon: <CloudUploadOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'deploy');
    },
  });

  const repoIsFork = RepoData ? coreIsFork(RepoData) : false;
  menuItems.push({
    key: 'backup',
    label: t('functions:functions.backup.name'),
    icon: <SaveOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'backup');
    },
    disabled: repoIsFork,
    title: repoIsFork ? t('resources:repositories.backupForkDisabledTooltip') : undefined,
  });

  menuItems.push({
    key: 'apply_template',
    label: t('functions:functions.apply_template.name'),
    icon: <AppstoreOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'apply_template');
    },
  });

  const advancedSubmenuItems: MenuProps['items'] = [];

  if (!record.mounted) {
    advancedSubmenuItems.push({
      key: 'mount',
      label: t('resources:repositories.mount'),
      icon: <DatabaseOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'mount', 4);
      },
    });
  } else {
    advancedSubmenuItems.push({
      key: 'unmount',
      label: t('resources:repositories.unmount'),
      icon: <DisconnectOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'unmount', 4);
      },
    });
  }

  if (!record.mounted) {
    advancedSubmenuItems.push({
      key: 'resize',
      label: t('functions:functions.resize.name'),
      icon: <ShrinkOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onRunFunction(record, 'resize');
      },
    });
  }

  if (record.mounted) {
    advancedSubmenuItems.push({
      key: 'expand',
      label: t('functions:functions.expand.name'),
      icon: <ExpandOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onRunFunction(record, 'expand');
      },
    });
  }

  if (advancedSubmenuItems.length > 0) {
    advancedSubmenuItems.push({ type: 'divider' as const });
  }

  advancedSubmenuItems.push({
    key: 'experimental',
    label: t('machines:experimental'),
    icon: <FunctionOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record);
    },
  });

  if (advancedSubmenuItems.length > 0) {
    menuItems.push({
      key: 'advanced',
      label: t('resources:repositories.advanced'),
      icon: <ControlOutlined />,
      children: advancedSubmenuItems,
    });
  }

  if (RepoData && coreIsFork(RepoData)) {
    menuItems.push({
      key: 'promote-to-grand',
      label: t('resources:repositories.promoteToGrand'),
      icon: <RiseOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onPromoteToGrand(record);
      },
    });
    menuItems.push({
      key: 'delete-fork',
      label: t('resources:repositories.deleteFork'),
      icon: <DeleteOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onDeleteFork(record);
      },
      danger: true,
    });
  }

  if (menuItems.length > 0) {
    menuItems.push({ type: 'divider' as const });
  }

  menuItems.push({
    key: 'rename',
    label: t('resources:repositories.rename'),
    icon: <EditOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRenameRepository(record);
    },
  });

  if (RepoData && coreIsCredential(RepoData)) {
    menuItems.push({
      key: 'delete-grand',
      label: t('resources:repositories.deleteGrand'),
      icon: <DeleteOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onDeleteGrandRepository(record);
      },
      danger: true,
    });
  }

  const actionRecord: RepositoryTableRow = {
    ...record,
    actionId: `${record.name}-${record.repositoryTag || 'latest'}`,
  };

  return (
    <ActionButtonGroup
      buttons={[
        {
          type: 'view',
          icon: <EyeOutlined />,
          tooltip: 'common:viewDetails',
          variant: 'default',
          onClick: (row) => onRepositoryClick?.(row),
          testId: (row) => `machine-repo-view-details-${row.name}-${row.repositoryTag || 'latest'}`,
        },
        {
          type: 'editTag',
          icon: <EditOutlined />,
          tooltip: 'resources:repositories.renameTag',
          variant: 'default',
          onClick: (row) => onRenameTag(row),
          visible: (row) => Boolean(row.repositoryTag && row.repositoryTag !== 'latest'),
          testId: (row) => `machine-repo-rename-tag-${row.name}-${row.repositoryTag || 'latest'}`,
        },
        {
          type: 'remote',
          icon: <FunctionOutlined />,
          tooltip: 'machines:remote',
          variant: 'primary',
          dropdownItems: menuItems,
          loading: isExecuting,
          testId: (row) => `machine-repo-list-repo-actions-${row.name}`,
        },
        {
          type: 'custom',
          visible: (row) => row.mounted,
          render: (row) => (
            <LocalActionsMenu
              machine={machine.machineName}
              repository={row.name}
              teamName={machine.teamName}
              userEmail={userEmail}
              pluginContainers={(containersData[row.name]?.containers || []).map((container) => ({
                ...container,
                name: container.name ?? '',
                image: container.image ?? '',
                status: container.status ?? container.state ?? '',
              }))}
            />
          ),
        },
        {
          type: 'vault',
          icon: <KeyOutlined />,
          tooltip: 'resources:repositories.addCredential',
          onClick: (row) => onCreateRepository?.(machine, row.originalGuid || row.name),
          variant: 'default',
          visible: (row) => Boolean(row.isUnmapped && onCreateRepository),
          testId: (row) => `machine-repo-list-add-credential-${row.name}`,
        },
      ]}
      record={actionRecord}
      idField="actionId"
      t={t}
      reserveSpace
    />
  );
};
