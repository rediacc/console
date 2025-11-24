import { Space, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { TFunction } from 'i18next'
import { AuditLog } from '@/api/queries/audit'
import { createDateSorter } from '@/core'
import { FilterHintIcon, ColumnFilterIcon, DescriptionText } from './styles'

interface ColumnBuilderParams {
  t: TFunction<'system' | 'common'>
  auditLogs?: AuditLog[]
  getActionIcon: (action: string) => React.ReactNode
  getActionColor: (action: string) => string
}

export const buildAuditColumns = ({
  t,
  auditLogs,
  getActionIcon,
  getActionColor,
}: ColumnBuilderParams): ColumnsType<AuditLog> => [
  {
    title: t('system:audit.columns.timestamp'),
    dataIndex: 'timestamp',
    key: 'timestamp',
    width: 180,
    render: (timestamp: string) => dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss'),
    sorter: createDateSorter<AuditLog>('timestamp'),
    defaultSortOrder: 'descend',
  },
  {
    title: (
      <Space>
        {t('system:audit.columns.action')}
        <FilterHintIcon />
      </Space>
    ),
    dataIndex: 'action',
    key: 'action',
    width: 200,
    render: (action: string) => (
      <Space>
        {getActionIcon(action)}
        <Tag color={getActionColor(action)}>{action.replace(/_/g, ' ')}</Tag>
      </Space>
    ),
    filters:
      [...new Set(auditLogs?.map((log) => log.action) || [])].map((action) => ({
        text: action.replace(/_/g, ' '),
        value: action,
      })) || [],
    onFilter: (value, record) => record.action === value,
    filterIcon: (filtered: boolean) => <ColumnFilterIcon $active={filtered} />,
  },
  {
    title: (
      <Space>
        {t('system:audit.columns.entityType')}
        <FilterHintIcon />
      </Space>
    ),
    dataIndex: 'entity',
    key: 'entity',
    width: 160,
    render: (entity: string) => <Tag>{entity}</Tag>,
    filters:
      [...new Set(auditLogs?.map((log) => log.entity) || [])].map((entity) => ({
        text: entity,
        value: entity,
      })) || [],
    onFilter: (value, record) => record.entity === value,
    filterIcon: (filtered: boolean) => <ColumnFilterIcon $active={filtered} />,
  },
  {
    title: (
      <Space>
        {t('system:audit.columns.entityName')}
        <FilterHintIcon />
      </Space>
    ),
    dataIndex: 'entityName',
    key: 'entityName',
    width: 220,
    filters:
      [...new Set(auditLogs?.map((log) => log.entityName) || [])].map((name) => ({
        text: name,
        value: name,
      })) || [],
    onFilter: (value, record) => record.entityName === value,
    filterIcon: (filtered: boolean) => <ColumnFilterIcon $active={filtered} />,
    render: (entityName: string) => (
      <Tooltip title={entityName} placement="topLeft">
        <span>{entityName}</span>
      </Tooltip>
    ),
  },
  {
    title: (
      <Space>
        {t('system:audit.columns.user')}
        <FilterHintIcon />
      </Space>
    ),
    dataIndex: 'actionByUser',
    key: 'actionByUser',
    width: 200,
    filters:
      [...new Set(auditLogs?.map((log) => log.actionByUser) || [])].map((user) => ({
        text: user,
        value: user,
      })) || [],
    onFilter: (value, record) => record.actionByUser === value,
    filterIcon: (filtered: boolean) => <ColumnFilterIcon $active={filtered} />,
  },
  {
    title: t('system:audit.columns.details'),
    dataIndex: 'details',
    key: 'details',
    ellipsis: true,
    render: (details: string) => (
      <Tooltip title={details} placement="topLeft">
        <DescriptionText>{details}</DescriptionText>
      </Tooltip>
    ),
  },
]
