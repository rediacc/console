import React from 'react';
import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { LocalActionsMenu } from '@/components/resources/internal/LocalActionsMenu';
import { isCredential as coreIsCredential, isFork as coreIsFork } from '@/platform';
import type { Machine } from '@/types';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  CloudUploadOutlined,
  ContainerOutlined,
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
  ShrinkOutlined,
} from '@/utils/optimizedIcons';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import type { MenuClickEvent, RepositoryContainersState, RepositoryTableRow } from '../types';
import type { MenuProps } from 'antd';

interface RepositoryActionsMenuProps {
  record: RepositoryTableRow;
  teamRepositories: GetTeamRepositories_ResultSet1[];
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
  onViewContainers?: (repository: RepositoryTableRow) => void;
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
  onViewContainers,
  onCreateRepository,
  t,
}) => {
  // Helper to create menu labels with consistent data-testid
  const createActionLabel = (actionKey: string, label: React.ReactNode) => (
    <Typography.Text data-testid={`repo-action-${actionKey.replace(/_/g, '-')}`}>
      {label}
    </Typography.Text>
  );

  const RepoData = teamRepositories.find(
    (r) => r.repositoryName === record.name && r.repositoryTag === record.repositoryTag
  );

  const menuItems: MenuProps['items'] = [];

  menuItems.push({
    key: 'repository_up',
    label: createActionLabel('repository_up', t('functions:functions.repository_up.name')),
    icon: <PlayCircleOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onQuickAction(record, 'repository_up', 4, 'mount');
    },
  });

  if (record.mounted) {
    menuItems.push({
      key: 'repository_down',
      label: createActionLabel('repository_down', t('functions:functions.repository_down.name')),
      icon: <PauseCircleOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'repository_down', 4, 'unmount');
      },
    });
  }

  if (!record.mounted) {
    menuItems.push({
      key: 'repository_validate',
      label: createActionLabel(
        'repository_validate',
        t('functions:functions.repository_validate.name')
      ),
      icon: <CheckCircleOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onRunFunction(record, 'repository_validate');
      },
    });
  }

  menuItems.push({
    key: 'fork',
    label: createActionLabel('fork', t('functions:functions.fork.name')),
    icon: <CopyOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'fork');
    },
  });

  // TODO: Refactor to use backup_push submenu with target selection (machine/storage)
  // See plan: cached-whistling-hopcroft.md for full UI design
  // Current: backup_deploy → backup_push with destinationType=machine
  menuItems.push({
    key: 'backup_push',
    label: createActionLabel('backup_push', t('functions:functions.backup_push.name')),
    icon: <CloudUploadOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'backup_push');
    },
  });

  // TODO: Refactor to use backup_pull submenu with source selection (machine/storage)
  // Current: New menu item for pulling repositories
  menuItems.push({
    key: 'backup_pull',
    label: createActionLabel('backup_pull', t('functions:functions.backup_pull.name')),
    icon: <CloudDownloadOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'backup_pull');
    },
  });

  menuItems.push({
    key: 'repository_template_apply',
    label: createActionLabel(
      'repository_template_apply',
      t('functions:functions.repository_template_apply.name')
    ),
    icon: <AppstoreOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRunFunction(record, 'repository_template_apply');
    },
  });

  const advancedSubmenuItems: MenuProps['items'] = [];

  if (!record.mounted) {
    advancedSubmenuItems.push({
      key: 'repository_mount',
      label: createActionLabel('repository_mount', t('resources:repositories.mount')),
      icon: <DatabaseOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'repository_mount', 4);
      },
    });
  } else {
    advancedSubmenuItems.push({
      key: 'repository_unmount',
      label: createActionLabel('repository_unmount', t('resources:repositories.unmount')),
      icon: <DisconnectOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'repository_unmount', 4);
      },
    });
  }

  if (!record.mounted) {
    advancedSubmenuItems.push({
      key: 'repository_resize',
      label: createActionLabel(
        'repository_resize',
        t('functions:functions.repository_resize.name')
      ),
      icon: <ShrinkOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onRunFunction(record, 'repository_resize');
      },
    });
  }

  if (record.mounted) {
    advancedSubmenuItems.push({
      key: 'repository_expand',
      label: createActionLabel(
        'repository_expand',
        t('functions:functions.repository_expand.name')
      ),
      icon: <ExpandOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onRunFunction(record, 'repository_expand');
      },
    });
  }

  if (advancedSubmenuItems.length > 0) {
    advancedSubmenuItems.push({ type: 'divider' as const });
  }

  advancedSubmenuItems.push({
    key: 'experimental',
    label: createActionLabel('experimental', t('machines:experimental')),
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
      label: createActionLabel('promote-to-grand', t('resources:repositories.promoteToGrand')),
      icon: <RiseOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onPromoteToGrand(record);
      },
    });
    menuItems.push({
      key: 'delete-fork',
      label: createActionLabel('delete-fork', t('resources:repositories.deleteFork')),
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
    label: createActionLabel('rename', t('resources:repositories.rename')),
    icon: <EditOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRenameRepository(record);
    },
  });

  if (RepoData && coreIsCredential(RepoData)) {
    menuItems.push({
      key: 'delete-grand',
      label: createActionLabel('delete-grand', t('resources:repositories.deleteGrand')),
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
    actionId: `${record.name}-${record.repositoryTag ?? 'latest'}`,
  };

  return (
    <ActionButtonGroup
      buttons={[
        {
          type: 'viewContainers',
          icon: <ContainerOutlined />,
          tooltip: 'resources:repositories.viewContainers',
          variant: 'default',
          onClick: (row) => onViewContainers?.(row),
          testId: (row) =>
            `machine-repo-view-containers-${row.name}-${row.repositoryTag ?? 'latest'}`,
        },
        {
          type: 'view',
          icon: <EyeOutlined />,
          tooltip: 'common:viewDetails',
          variant: 'default',
          onClick: (row) => onRepositoryClick?.(row),
          testId: (row) => `machine-repo-view-details-${row.name}-${row.repositoryTag ?? 'latest'}`,
        },
        {
          type: 'editTag',
          icon: <EditOutlined />,
          tooltip: 'resources:repositories.renameTag',
          variant: 'default',
          onClick: (row) => onRenameTag(row),
          visible: (row) => Boolean(row.repositoryTag && row.repositoryTag !== 'latest'),
          testId: (row) => `machine-repo-rename-tag-${row.name}-${row.repositoryTag ?? 'latest'}`,
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
              machine={machine.machineName ?? ''}
              repository={row.name}
              teamName={machine.teamName ?? undefined}
              userEmail={userEmail}
              pluginContainers={(() => {
                const containerData = containersData[row.name] as
                  | { containers?: (typeof containersData)[string]['containers'] }
                  | undefined;
                const containers = containerData?.containers ?? [];
                return containers.map((container) => ({
                  ...container,
                  name: container.name,
                  image: container.image ?? '',
                  // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty strings should fall through
                  status: container.status || container.state || '',
                }));
              })()}
            />
          ),
        },
        {
          type: 'vault',
          icon: <KeyOutlined />,
          tooltip: 'resources:repositories.addCredential',
          onClick: (row) => onCreateRepository?.(machine, row.originalGuid ?? row.name),
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
