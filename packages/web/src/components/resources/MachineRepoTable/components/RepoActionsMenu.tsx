import React from 'react';
import type { MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { LocalActionsMenu } from '@/components/resources/internal/LocalActionsMenu';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  CheckCircleOutlined,
  CopyOutlined,
  CloudUploadOutlined,
  SaveOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  DisconnectOutlined,
  ExpandOutlined,
  ShrinkOutlined,
  FunctionOutlined,
  DeleteOutlined,
  RiseOutlined,
  EditOutlined,
  EyeOutlined,
  KeyOutlined,
  ControlOutlined,
} from '@/utils/optimizedIcons';
import { isFork as coreIsFork, isCredential as coreIsCredential } from '@/platform';
import type { Repo as TeamRepo } from '@rediacc/shared/types';
import type { Machine } from '@/types';
import type { RepoTableRow, RepoContainersState, MenuClickEvent } from '../types';

interface RepoActionsMenuProps {
  record: RepoTableRow;
  teamRepos: TeamRepo[];
  machine: Machine;
  userEmail: string;
  containersData: Record<string, RepoContainersState>;
  isExecuting: boolean;
  onQuickAction: (
    repo: RepoTableRow,
    functionName: string,
    priority: number,
    option?: string
  ) => void;
  onRunFunction: (repo: RepoTableRow, functionName?: string) => void;
  onPromoteToGrand: (repo: RepoTableRow) => void;
  onDeleteFork: (repo: RepoTableRow) => void;
  onRenameTag: (repo: RepoTableRow) => void;
  onRenameRepo: (repo: RepoTableRow) => void;
  onDeleteGrandRepo: (repo: RepoTableRow) => void;
  onRepoClick?: (repo: RepoTableRow) => void;
  onCreateRepo?: (machine: Machine, repoGuid: string) => void;
  t: ReturnType<typeof useTranslation>['t'];
}

export const RepoActionsMenu: React.FC<RepoActionsMenuProps> = ({
  record,
  teamRepos,
  machine,
  userEmail,
  containersData,
  isExecuting,
  onQuickAction,
  onRunFunction,
  onPromoteToGrand,
  onDeleteFork,
  onRenameTag,
  onRenameRepo,
  onDeleteGrandRepo,
  onRepoClick,
  onCreateRepo,
  t,
}) => {
  const RepoData = teamRepos.find(
    (r) => r.repoName === record.name && r.repoTag === record.repoTag
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
    title: repoIsFork ? t('resources:repos.backupForkDisabledTooltip') : undefined,
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
      label: t('resources:repos.mount'),
      icon: <DatabaseOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onQuickAction(record, 'mount', 4);
      },
    });
  } else {
    advancedSubmenuItems.push({
      key: 'unmount',
      label: t('resources:repos.unmount'),
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
      label: t('resources:repos.advanced'),
      icon: <ControlOutlined />,
      children: advancedSubmenuItems,
    });
  }

  if (RepoData && coreIsFork(RepoData)) {
    menuItems.push({
      key: 'promote-to-grand',
      label: t('resources:repos.promoteToGrand'),
      icon: <RiseOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onPromoteToGrand(record);
      },
    });
    menuItems.push({
      key: 'delete-fork',
      label: t('resources:repos.deleteFork'),
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
    label: t('resources:repos.rename'),
    icon: <EditOutlined />,
    onClick: (info: MenuClickEvent) => {
      info.domEvent.stopPropagation();
      onRenameRepo(record);
    },
  });

  if (RepoData && coreIsCredential(RepoData)) {
    menuItems.push({
      key: 'delete-grand',
      label: t('resources:repos.deleteGrand'),
      icon: <DeleteOutlined />,
      onClick: (info: MenuClickEvent) => {
        info.domEvent.stopPropagation();
        onDeleteGrandRepo(record);
      },
      danger: true,
    });
  }

  const actionRecord: RepoTableRow = {
    ...record,
    actionId: `${record.name}-${record.repoTag || 'latest'}`,
  };

  return (
    <ActionButtonGroup
      buttons={[
        {
          type: 'view',
          icon: <EyeOutlined />,
          tooltip: 'common:viewDetails',
          variant: 'default',
          onClick: (row) => onRepoClick?.(row),
          testId: (row) => `machine-repo-view-details-${row.name}-${row.repoTag || 'latest'}`,
        },
        {
          type: 'editTag',
          icon: <EditOutlined />,
          tooltip: 'resources:repos.renameTag',
          variant: 'default',
          onClick: (row) => onRenameTag(row),
          visible: (row) => Boolean(row.repoTag && row.repoTag !== 'latest'),
          testId: (row) => `machine-repo-rename-tag-${row.name}-${row.repoTag || 'latest'}`,
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
              repo={row.name}
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
          tooltip: 'resources:repos.addCredential',
          onClick: (row) => onCreateRepo?.(machine, row.originalGuid || row.name),
          variant: 'default',
          visible: (row) => Boolean(row.isUnmapped && onCreateRepo),
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
