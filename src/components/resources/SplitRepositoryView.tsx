import React, { useState } from 'react'
import { Repository } from '@/api/queries/repositories'
import { Table, Button, Tag, Space, Empty, Typography, Dropdown, Tooltip } from 'antd'
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
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
import { UnifiedDetailPanel } from './UnifiedDetailPanel'
import { useTheme } from '@/context/ThemeContext'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

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
  const { theme } = useTheme()
  const tableStyles = useTableStyles()
  const componentStyles = useComponentStyles()
  
  const [splitWidth, setSplitWidth] = useState(420)

  const handleRowClick = (repository: Repository) => {
    onRepositorySelect(repository)
  }

  const handlePanelClose = () => {
    onRepositorySelect(null)
  }

  const columns: ColumnsType<Repository> = [
    {
      title: t('resources:repositories.status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      align: 'center',
      render: (_: any, _record: Repository) => {
        // Note: SplitRepositoryView shows global repositories, not machine-specific data
        // So we don't have mounted/docker_running status here - this is a credential view
        // We can show a simple indicator that credentials exist
        return (
          <Tooltip title={t('resources:repositories.credentialExists')}>
            <span style={{ fontSize: 18, color: '#1890ff' }}>
              <KeyOutlined />
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: t('resources:repositories.repositoryName'),
      dataIndex: 'repositoryName',
      key: 'repositoryName',
      width: 300,
      ellipsis: true,
      render: (name: string, record: Repository) => (
        <Space>
          <FolderOutlined style={{ color: '#8FBC8F' }} />
          <Button
            type="link"
            onClick={() => handleRowClick(record)}
            style={{
              ...componentStyles.controlSurface,
              padding: 0,
              height: 'auto',
              fontWeight: selectedRepository?.repositoryGuid === record.repositoryGuid ? 'bold' : 'normal'
            }}
            data-testid={`split-repo-view-repository-link-${record.repositoryName}`}
          >
            {name}
          </Button>
        </Space>
      ),
    },
    {
      title: t('resources:repositories.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{version}</Tag>,
    },
    {
      title: t('resources:repositories.repositoryGuid'),
      dataIndex: 'repositoryGuid',
      key: 'repositoryGuid',
      width: 350,
      ellipsis: true,
      render: (guid: string) => (
        <Text copyable style={{ fontSize: 12, fontFamily: 'monospace' }}>
          {guid}
        </Text>
      ),
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_: any, record: Repository) => {
        const menuItems = []

        if (onEditRepository) {
          menuItems.push({
            key: 'edit',
            label: t('common:actions.edit'),
            icon: <EditOutlined />,
            onClick: (e: any) => {
              e.domEvent.stopPropagation()
              onEditRepository(record)
            }
          })
        }

        if (onVaultRepository) {
          menuItems.push({
            key: 'vault',
            label: t('resources:repositories.manageVault'),
            icon: <KeyOutlined />,
            onClick: (e: any) => {
              e.domEvent.stopPropagation()
              onVaultRepository(record)
            }
          })
        }

        if (onDeleteRepository) {
          menuItems.push({
            key: 'delete',
            label: t('common:actions.delete'),
            icon: <DeleteOutlined />,
            danger: true,
            onClick: (e: any) => {
              e.domEvent.stopPropagation()
              onDeleteRepository(record)
            }
          })
        }

        return (
          <Dropdown
            menu={{ items: menuItems }}
            trigger={['click']}
            data-testid={`split-repo-view-actions-dropdown-${record.repositoryName}`}
          >
            <Button
              type="primary"
              size="small"
              icon={<FunctionOutlined />}
              onClick={(e) => e.stopPropagation()}
              style={componentStyles.controlSurface}
              data-testid={`split-repo-view-actions-button-${record.repositoryName}`}
            >
              {t('common:actions.actions')}
            </Button>
          </Dropdown>
        )
      },
    },
  ]

  return (
    <div 
      style={{
        display: 'flex',
        height: '100%',
        width: '100%',
        position: 'relative',
        overflow: 'hidden',
      }}
      data-testid="split-repo-view-container"
    >
      {/* Left Panel - Repository Table */}
      <div 
        style={{
          flex: 1,
          height: '100%',
          overflow: 'auto',
          minWidth: 0,
          backgroundColor: theme === 'dark' ? '#141414' : '#fff',
        }}
        data-testid="split-repo-view-left-panel"
      >
        {/* Header */}
        <div 
          style={{ 
            padding: '16px 24px', 
            borderBottom: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
          data-testid="split-repo-view-header"
        >
          <Space>
            <FolderOutlined style={{ fontSize: 20, color: '#8FBC8F' }} />
            <Typography.Title level={4} style={{ margin: 0 }} data-testid="split-repo-view-title">
              {t('resources:repositories.repositories')}
            </Typography.Title>
            {teamFilter && !Array.isArray(teamFilter) && (
              <Tag color="#8FBC8F" icon={<AppstoreOutlined />} data-testid="split-repo-view-team-filter-tag">
                {teamFilter}
              </Tag>
            )}
          </Space>
          {onCreateRepository && (
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              onClick={onCreateRepository}
              style={componentStyles.controlSurface}
              data-testid="split-repo-view-create-button"
            >
              {t('resources:repositories.create')}
            </Button>
          )}
        </div>

        {/* Table */}
        <div style={{ padding: '0 24px' }}>
          <Table
            columns={columns}
            dataSource={repositories}
            rowKey="repositoryGuid"
            size="small"
            pagination={false}
            loading={loading}
            scroll={{ x: 'max-content' }}
            style={tableStyles.tableContainer}
            data-testid="split-repo-view-table"
            onRow={(record) => ({
              onClick: () => handleRowClick(record),
              style: {
                cursor: 'pointer',
                backgroundColor: selectedRepository?.repositoryGuid === record.repositoryGuid 
                  ? (theme === 'dark' ? 'rgba(24, 144, 255, 0.1)' : 'rgba(24, 144, 255, 0.05)')
                  : undefined
              }
            })}
            locale={{
              emptyText: (
                <Empty 
                  description={t('resources:repositories.noRepositories')}
                  style={{ margin: '40px 0' }}
                />
              )
            }}
          />
        </div>
      </div>

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
    </div>
  )
}
