import React, { useState } from 'react';
import { Repo } from '@/api/queries/repos';
import { Space, Dropdown, Tooltip, Tag } from 'antd';
import type { MenuProps } from 'antd';

// Type for menu item click event
type MenuClickEvent = { key: string; domEvent: React.MouseEvent | React.KeyboardEvent };
import {
  FolderOutlined,
  CloudUploadOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  AppstoreOutlined,
  FunctionOutlined,
} from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { UnifiedDetailPanel } from '../../UnifiedDetailPanel';
import type { ColumnsType } from 'antd/es/table';
import { createSorter } from '@/core';
import { createActionColumn, createTruncatedColumn } from '@/components/common/columns';
import {
  ActionsButton,
  EmptyState,
  GuidText,
  Header,
  HeaderTitle,
  LeftPanel,
  PrimaryButton,
  RepoLink,
  RepoTable,
  SplitViewContainer,
  TableSection,
  TeamFilterTag,
  TitleRow,
} from './styles';
import { IconWrapper } from '@/components/ui';

interface SplitRepoViewProps {
  repos: Repo[];
  loading?: boolean;
  selectedRepo: Repo | null;
  onRepoSelect: (repo: Repo | null) => void;
  onEditRepo?: (repo: Repo) => void;
  onDeleteRepo?: (repo: Repo) => void;
  onVaultRepo?: (repo: Repo) => void;
  onCreateRepo?: () => void;
  teamFilter?: string | string[];
}

export const SplitRepoView: React.FC<SplitRepoViewProps> = ({
  repos,
  loading,
  selectedRepo,
  onRepoSelect,
  onEditRepo,
  onDeleteRepo,
  onVaultRepo,
  onCreateRepo,
  teamFilter,
}) => {
  const { t } = useTranslation(['resources', 'common']);

  const [splitWidth, setSplitWidth] = useState(420);

  const handleRowClick = (repo: Repo) => {
    onRepoSelect(repo);
  };

  const handlePanelClose = () => {
    onRepoSelect(null);
  };

  const repoNameColumn = createTruncatedColumn<Repo>({
    title: t('resources:repos.repoName'),
    dataIndex: 'repoName',
    key: 'repoName',
    width: 300,
    sorter: createSorter<Repo>('repoName'),
  });

  const repoGuidColumn = createTruncatedColumn<Repo>({
    title: t('resources:repos.repoGuid'),
    dataIndex: 'repoGuid',
    key: 'repoGuid',
    width: 350,
    sorter: createSorter<Repo>('repoGuid'),
  });

  const columns: ColumnsType<Repo> = [
    {
      title: t('resources:repos.status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      align: 'center',
      render: () => (
        <Tooltip title={t('resources:repos.credentialExists')}>
          <IconWrapper $size="sm" $tone="primary">
            <KeyOutlined />
          </IconWrapper>
        </Tooltip>
      ),
    },
    {
      ...repoNameColumn,
      render: (name: string, record: Repo) => {
        const truncated = repoNameColumn.render?.(name, record, 0) as React.ReactNode;
        return (
          <Space>
            <IconWrapper $tone="success">
              <FolderOutlined />
            </IconWrapper>
            <RepoLink
              onClick={() => handleRowClick(record)}
              $isSelected={selectedRepo?.repoGuid === record.repoGuid}
              data-testid={`split-repo-view-repo-link-${record.repoName}`}
            >
              {truncated}
            </RepoLink>
          </Space>
        );
      },
    },
    {
      title: t('resources:repos.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      sorter: createSorter<Repo>('vaultVersion'),
      render: (version: number) => <Tag>{version}</Tag>,
    },
    {
      ...repoGuidColumn,
      render: (guid: string, record: Repo) => {
        const truncated = repoGuidColumn.render?.(guid, record, 0) as React.ReactNode;
        return <GuidText copyable={{ text: guid }}>{truncated}</GuidText>;
      },
    },
    createActionColumn<Repo>({
      title: t('common:table.actions'),
      width: 200,
      fixed: 'end',
      renderActions: (record) => {
        const menuItems: MenuProps['items'] = [];

        if (onEditRepo) {
          menuItems.push({
            key: 'edit',
            label: t('common:actions.edit'),
            icon: <EditOutlined />,
            onClick: (e: MenuClickEvent) => {
              e.domEvent.stopPropagation();
              onEditRepo(record);
            },
          });
        }

        if (onVaultRepo) {
          menuItems.push({
            key: 'vault',
            label: t('resources:repos.manageVault'),
            icon: <KeyOutlined />,
            onClick: (e: MenuClickEvent) => {
              e.domEvent.stopPropagation();
              onVaultRepo(record);
            },
          });
        }

        if (onDeleteRepo) {
          menuItems.push({
            key: 'delete',
            label: t('common:actions.delete'),
            icon: <DeleteOutlined />,
            danger: true,
            onClick: (e: MenuClickEvent) => {
              e.domEvent.stopPropagation();
              onDeleteRepo(record);
            },
          });
        }

        return (
          <Dropdown
            menu={{ items: menuItems }}
            trigger={['click']}
            data-testid={`split-repo-view-actions-dropdown-${record.repoName}`}
          >
            <ActionsButton
              type="primary"
              size="small"
              icon={<FunctionOutlined />}
              onClick={(e) => e.stopPropagation()}
              data-testid={`split-repo-view-actions-button-${record.repoName}`}
            >
              {t('common:actions.actions')}
            </ActionsButton>
          </Dropdown>
        );
      },
    }),
  ];

  return (
    <SplitViewContainer data-testid="split-repo-view-container">
      {/* Left Panel - Repo Table */}
      <LeftPanel data-testid="split-repo-view-left-panel">
        {/* Header */}
        <Header data-testid="split-repo-view-header">
          <TitleRow>
            <IconWrapper $tone="success" $size="lg">
              <FolderOutlined />
            </IconWrapper>
            <HeaderTitle data-testid="split-repo-view-title">
              {t('resources:repos.repos')}
            </HeaderTitle>
            {teamFilter && !Array.isArray(teamFilter) && (
              <TeamFilterTag
                icon={<AppstoreOutlined />}
                data-testid="split-repo-view-team-filter-tag"
              >
                {teamFilter}
              </TeamFilterTag>
            )}
          </TitleRow>
          {onCreateRepo && (
            <PrimaryButton
              icon={<CloudUploadOutlined />}
              onClick={onCreateRepo}
              data-testid="split-repo-view-create-button"
            >
              {t('resources:repos.create')}
            </PrimaryButton>
          )}
        </Header>

        {/* Table */}
        <TableSection>
          <RepoTable
            columns={columns}
            dataSource={repos}
            rowKey="repoGuid"
            size="small"
            pagination={false}
            loading={loading}
            scroll={{ x: 'max-content' }}
            data-testid="split-repo-view-table"
            rowClassName={(record) =>
              selectedRepo?.repoGuid === record.repoGuid ? 'is-selected' : ''
            }
            onRow={(record) => ({
              onClick: () => handleRowClick(record),
            })}
            locale={{
              emptyText: <EmptyState description={t('resources:repos.noRepos')} />,
            }}
          />
        </TableSection>
      </LeftPanel>

      {/* Right Panel - Detail Panel */}
      {selectedRepo && (
        <UnifiedDetailPanel
          type="repo"
          data={selectedRepo}
          visible={true}
          onClose={handlePanelClose}
          splitWidth={splitWidth}
          onSplitWidthChange={setSplitWidth}
        />
      )}
    </SplitViewContainer>
  );
};
