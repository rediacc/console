import React, { useState } from 'react'
import { Repository } from '@/api/queries/repositories'
import { Space, Dropdown, Tooltip, Tag } from 'antd'
import type { MenuProps } from 'antd'
import type { MenuInfo } from 'rc-menu/lib/interface'
import { 
  FolderOutlined, 
  CloudUploadOutlined, 
  EditOutlined, 
  DeleteOutlined,
  KeyOutlined,
  AppstoreOutlined,
  FunctionOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { UnifiedDetailPanel } from '../../UnifiedDetailPanel'
import type { ColumnsType } from 'antd/es/table'
import { createSorter } from '@/core'
import { createActionColumn, createTruncatedColumn } from '@/components/common/columns'
import {
  ActionsButton,
  EmptyState,
  GuidText,
  Header,
  HeaderTitle,
  IconWrapper,
  LeftPanel,
  PrimaryButton,
  RepositoryLink,
  RepositoryTable,
  SplitViewContainer,
  TableSection,
  TeamFilterTag,
  TitleRow,
} from './styles'

interface SplitRepositoryViewProps {
  repositories: Repository[]
  loading?: boolean
  selectedRepository: Repository | null
  onRepositorySelect: (repository: Repository | null) => void
  onEditRepository?: (repository: Repository) => void
  onDeleteRepository?: (repository: Repository) => void
  onVaultRepository?: (repository: Repository) => void
  onCreateRepository?: () => void
  teamFilter?: string | string[]
}

export const SplitRepositoryView: React.FC<SplitRepositoryViewProps> = ({
  repositories,
  loading,
  selectedRepository,
  onRepositorySelect,
  onEditRepository,
  onDeleteRepository,
  onVaultRepository,
  onCreateRepository,
  teamFilter
}) => {
  const { t } = useTranslation(['resources', 'common'])
  
  const [splitWidth, setSplitWidth] = useState(420)

  const handleRowClick = (repository: Repository) => {
    onRepositorySelect(repository)
  }

  const handlePanelClose = () => {
    onRepositorySelect(null)
  }

  const repositoryNameColumn = createTruncatedColumn<Repository>({
    title: t('resources:repositories.repositoryName'),
    dataIndex: 'repositoryName',
    key: 'repositoryName',
    width: 300,
    sorter: createSorter<Repository>('repositoryName'),
  })

  const repositoryGuidColumn = createTruncatedColumn<Repository>({
    title: t('resources:repositories.repositoryGuid'),
    dataIndex: 'repositoryGuid',
    key: 'repositoryGuid',
    width: 350,
    sorter: createSorter<Repository>('repositoryGuid'),
  })

  const columns: ColumnsType<Repository> = [
    {
      title: t('resources:repositories.status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      align: 'center',
      render: () => (
        <Tooltip title={t('resources:repositories.credentialExists')}>
          <IconWrapper>
            <KeyOutlined />
          </IconWrapper>
        </Tooltip>
      ),
    },
    {
      ...repositoryNameColumn,
      render: (name: string, record: Repository) => {
        const truncated = repositoryNameColumn.render?.(name, record, 0) as React.ReactNode
        return (
          <Space>
            <IconWrapper $variant="success">
              <FolderOutlined />
            </IconWrapper>
            <RepositoryLink
              onClick={() => handleRowClick(record)}
              $isSelected={selectedRepository?.repositoryGuid === record.repositoryGuid}
              data-testid={`split-repo-view-repository-link-${record.repositoryName}`}
            >
              {truncated}
            </RepositoryLink>
          </Space>
        )
      },
    },
    {
      title: t('resources:repositories.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      sorter: createSorter<Repository>('vaultVersion'),
      render: (version: number) => <Tag>{version}</Tag>,
    },
    {
      ...repositoryGuidColumn,
      render: (guid: string, record: Repository) => {
        const truncated = repositoryGuidColumn.render?.(guid, record, 0) as React.ReactNode
        return (
          <GuidText copyable={{ text: guid }}>
            {truncated}
          </GuidText>
        )
      },
    },
    createActionColumn<Repository>({
      title: t('common:table.actions'),
      width: 200,
      fixed: 'right',
      renderActions: (record) => {
        const menuItems: MenuProps['items'] = []

        if (onEditRepository) {
          menuItems.push({
            key: 'edit',
            label: t('common:actions.edit'),
            icon: <EditOutlined />,
            onClick: (e: MenuInfo) => {
              e.domEvent.stopPropagation()
              onEditRepository(record)
            },
          })
        }

        if (onVaultRepository) {
          menuItems.push({
            key: 'vault',
            label: t('resources:repositories.manageVault'),
            icon: <KeyOutlined />,
            onClick: (e: MenuInfo) => {
              e.domEvent.stopPropagation()
              onVaultRepository(record)
            },
          })
        }

        if (onDeleteRepository) {
          menuItems.push({
            key: 'delete',
            label: t('common:actions.delete'),
            icon: <DeleteOutlined />,
            danger: true,
            onClick: (e: MenuInfo) => {
              e.domEvent.stopPropagation()
              onDeleteRepository(record)
            },
          })
        }

        return (
          <Dropdown
            menu={{ items: menuItems }}
            trigger={['click']}
            data-testid={`split-repo-view-actions-dropdown-${record.repositoryName}`}
          >
            <ActionsButton
              type="primary"
              size="small"
              icon={<FunctionOutlined />}
              onClick={(e) => e.stopPropagation()}
              data-testid={`split-repo-view-actions-button-${record.repositoryName}`}
            >
              {t('common:actions.actions')}
            </ActionsButton>
          </Dropdown>
        )
      },
    }),
  ]

  return (
    <SplitViewContainer data-testid="split-repo-view-container">
      {/* Left Panel - Repository Table */}
      <LeftPanel data-testid="split-repo-view-left-panel">
        {/* Header */}
        <Header data-testid="split-repo-view-header">
          <TitleRow>
            <IconWrapper $variant="success" $size="lg">
              <FolderOutlined />
            </IconWrapper>
            <HeaderTitle data-testid="split-repo-view-title">
              {t('resources:repositories.repositories')}
            </HeaderTitle>
            {teamFilter && !Array.isArray(teamFilter) && (
              <TeamFilterTag icon={<AppstoreOutlined />} data-testid="split-repo-view-team-filter-tag">
                {teamFilter}
              </TeamFilterTag>
            )}
          </TitleRow>
          {onCreateRepository && (
            <PrimaryButton
              icon={<CloudUploadOutlined />}
              onClick={onCreateRepository}
              data-testid="split-repo-view-create-button"
            >
              {t('resources:repositories.create')}
            </PrimaryButton>
          )}
        </Header>

        {/* Table */}
        <TableSection>
          <RepositoryTable
            columns={columns}
            dataSource={repositories}
            rowKey="repositoryGuid"
            size="small"
            pagination={false}
            loading={loading}
            scroll={{ x: 'max-content' }}
            data-testid="split-repo-view-table"
            rowClassName={(record) =>
              selectedRepository?.repositoryGuid === record.repositoryGuid ? 'is-selected' : ''}
            onRow={(record) => ({
              onClick: () => handleRowClick(record),
            })}
            locale={{
              emptyText: (
                <EmptyState description={t('resources:repositories.noRepositories')} />
              )
            }}
          />
        </TableSection>
      </LeftPanel>

      {/* Right Panel - Detail Panel */}
      {selectedRepository && (
        <UnifiedDetailPanel
          type="repository"
          data={selectedRepository}
          visible={true}
          onClose={handlePanelClose}
          splitWidth={splitWidth}
          onSplitWidthChange={setSplitWidth}
        />
      )}
    </SplitViewContainer>
  )
}
