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

// Helper to create menu labels with consistent data-testid
const createActionLabel = (actionKey: string, label: React.ReactNode) => (
  <Typography.Text data-testid={`repo-action-${actionKey.replaceAll('_', '-')}`}>
    {label}
  </Typography.Text>
);

// Helper to create a standard menu item with click handler
const createMenuItem = (
  key: string,
  label: React.ReactNode,
  icon: React.ReactNode,
  _record: RepositoryTableRow,
  handler: () => void,
  danger?: boolean
): NonNullable<MenuProps['items']>[number] => ({
  key,
  label: createActionLabel(key, label),
  icon,
  onClick: (info: MenuClickEvent) => {
    info.domEvent.stopPropagation();
    handler();
  },
  danger,
});

// Build main menu items
const buildMainMenuItems = (
  record: RepositoryTableRow,
  t: ReturnType<typeof useTranslation>['t'],
  onQuickAction: RepositoryActionsMenuProps['onQuickAction'],
  onRunFunction: RepositoryActionsMenuProps['onRunFunction']
): MenuProps['items'] => {
  const items: MenuProps['items'] = [];

  items.push(
    createMenuItem(
      'repository_up',
      t('functions:functions.repository_up.name'),
      <PlayCircleOutlined />,
      record,
      () => onQuickAction(record, 'repository_up', 4, 'mount')
    )
  );

  if (record.mounted) {
    items.push(
      createMenuItem(
        'repository_down',
        t('functions:functions.repository_down.name'),
        <PauseCircleOutlined />,
        record,
        () => onQuickAction(record, 'repository_down', 4, 'unmount')
      )
    );
  }

  if (!record.mounted) {
    items.push(
      createMenuItem(
        'repository_validate',
        t('functions:functions.repository_validate.name'),
        <CheckCircleOutlined />,
        record,
        () => onRunFunction(record, 'repository_validate')
      )
    );
  }

  items.push(
    createMenuItem('fork', t('functions:functions.fork.name'), <CopyOutlined />, record, () =>
      onRunFunction(record, 'fork')
    ),
    createMenuItem(
      'backup_push',
      t('functions:functions.backup_push.name'),
      <CloudUploadOutlined />,
      record,
      () => onRunFunction(record, 'backup_push')
    ),
    createMenuItem(
      'backup_pull',
      t('functions:functions.backup_pull.name'),
      <CloudDownloadOutlined />,
      record,
      () => onRunFunction(record, 'backup_pull')
    ),
    createMenuItem(
      'repository_template_apply',
      t('functions:functions.repository_template_apply.name'),
      <AppstoreOutlined />,
      record,
      () => onRunFunction(record, 'repository_template_apply')
    )
  );

  return items;
};

// Build advanced submenu items
const buildAdvancedSubmenuItems = (
  record: RepositoryTableRow,
  t: ReturnType<typeof useTranslation>['t'],
  onQuickAction: RepositoryActionsMenuProps['onQuickAction'],
  onRunFunction: RepositoryActionsMenuProps['onRunFunction']
): MenuProps['items'] => {
  const items: MenuProps['items'] = [];

  if (record.mounted) {
    items.push(
      createMenuItem(
        'repository_unmount',
        t('resources:repositories.unmount'),
        <DisconnectOutlined />,
        record,
        () => onQuickAction(record, 'repository_unmount', 4)
      ),
      createMenuItem(
        'repository_expand',
        t('functions:functions.repository_expand.name'),
        <ExpandOutlined />,
        record,
        () => onRunFunction(record, 'repository_expand')
      )
    );
  } else {
    items.push(
      createMenuItem(
        'repository_mount',
        t('resources:repositories.mount'),
        <DatabaseOutlined />,
        record,
        () => onQuickAction(record, 'repository_mount', 4)
      ),
      createMenuItem(
        'repository_resize',
        t('functions:functions.repository_resize.name'),
        <ShrinkOutlined />,
        record,
        () => onRunFunction(record, 'repository_resize')
      )
    );
  }

  if (items.length > 0) {
    items.push({ type: 'divider' as const });
  }

  items.push(
    createMenuItem('experimental', t('machines:experimental'), <FunctionOutlined />, record, () =>
      onRunFunction(record)
    )
  );

  return items;
};

// Build fork-specific menu items
const buildForkMenuItems = (
  record: RepositoryTableRow,
  t: ReturnType<typeof useTranslation>['t'],
  onPromoteToGrand: RepositoryActionsMenuProps['onPromoteToGrand'],
  onDeleteFork: RepositoryActionsMenuProps['onDeleteFork']
): MenuProps['items'] => [
  createMenuItem(
    'promote-to-grand',
    t('resources:repositories.promoteToGrand'),
    <RiseOutlined />,
    record,
    () => onPromoteToGrand(record)
  ),
  createMenuItem(
    'delete-fork',
    t('resources:repositories.deleteFork'),
    <DeleteOutlined />,
    record,
    () => onDeleteFork(record),
    true
  ),
];

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
  const RepoData = teamRepositories.find(
    (r) => r.repositoryName === record.name && r.repositoryTag === record.repositoryTag
  );

  // Build menu items using helper functions
  const menuItems: NonNullable<MenuProps['items']> = [
    ...(buildMainMenuItems(record, t, onQuickAction, onRunFunction) ?? []),
  ];

  // Add advanced submenu
  const advancedSubmenuItems = buildAdvancedSubmenuItems(record, t, onQuickAction, onRunFunction);
  if (advancedSubmenuItems && advancedSubmenuItems.length > 0) {
    menuItems.push({
      key: 'advanced',
      label: t('resources:repositories.advanced'),
      icon: <ControlOutlined />,
      children: advancedSubmenuItems,
    });
  }

  // Add fork-specific items
  if (RepoData && coreIsFork(RepoData)) {
    menuItems.push(...(buildForkMenuItems(record, t, onPromoteToGrand, onDeleteFork) ?? []));
  }

  // Add divider and rename option
  if (menuItems.length > 0) {
    menuItems.push({ type: 'divider' as const });
  }

  menuItems.push(
    createMenuItem('rename', t('resources:repositories.rename'), <EditOutlined />, record, () =>
      onRenameRepository(record)
    )
  );

  // Add delete grand option for credentials
  if (RepoData && coreIsCredential(RepoData)) {
    menuItems.push(
      createMenuItem(
        'delete-grand',
        t('resources:repositories.deleteGrand'),
        <DeleteOutlined />,
        record,
        () => onDeleteGrandRepository(record),
        true
      )
    );
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
