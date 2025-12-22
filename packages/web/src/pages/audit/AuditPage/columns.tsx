import { Space, Tag, Typography } from 'antd';
import { TFunction } from 'i18next';
import { GetAuditLogs_ResultSet1 } from '@/api/queries/audit';
import {
  createDateColumn,
  createStatusColumn,
  createTruncatedColumn,
  type StatusConfig,
} from '@/components/common/columns';
import { createDateSorter } from '@/platform';
import { FilterOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';

interface ColumnBuilderParams {
  t: TFunction<'system' | 'common'>;
  auditLogs?: GetAuditLogs_ResultSet1[];
  getActionIcon: (action: string) => React.ReactNode;
  getActionColor: (action: string) => string;
}

export const buildAuditColumns = ({
  t,
  auditLogs,
  getActionIcon,
  getActionColor,
}: ColumnBuilderParams): ColumnsType<GetAuditLogs_ResultSet1> => {
  const actionStatusMap = (auditLogs || []).reduce<Record<string, StatusConfig>>((acc, log) => {
    if (!acc[log.action]) {
      acc[log.action] = {
        color: getActionColor(log.action),
        icon: getActionIcon(log.action),
        label: log.action.replace(/_/g, ' '),
      };
    }
    return acc;
  }, {});

  const timestampColumn = createDateColumn<GetAuditLogs_ResultSet1>({
    title: t('system:audit.columns.timestamp'),
    dataIndex: 'timestamp',
    key: 'timestamp',
    width: 180,
    sorter: createDateSorter<GetAuditLogs_ResultSet1>('timestamp'),
    defaultSortOrder: 'descend',
  });

  const actionColumn = createStatusColumn<GetAuditLogs_ResultSet1>({
    title: (
      <Space>
        {t('system:audit.columns.action')}
        <FilterOutlined />
      </Space>
    ),
    dataIndex: 'action',
    key: 'action',
    width: 200,
    statusMap: actionStatusMap,
    defaultConfig: { color: 'default' },
    sorter: (a, b) => a.action.localeCompare(b.action),
  });
  actionColumn.filters =
    [...new Set(auditLogs?.map((log) => log.action) || [])].map((action) => ({
      text: action.replace(/_/g, ' '),
      value: action,
    })) || [];
  actionColumn.onFilter = (value, record) => record.action === value;
  actionColumn.filterIcon = (_filtered: boolean) => <FilterOutlined />;

  const entityNameColumn = createTruncatedColumn<GetAuditLogs_ResultSet1>({
    title: (
      <Space>
        {t('system:audit.columns.entityName')}
        <FilterOutlined />
      </Space>
    ),
    dataIndex: 'entityName',
    key: 'entityName',
    width: 220,
    maxLength: 24,
  });
  entityNameColumn.filters =
    [
      ...new Set(
        auditLogs?.map((log) => log.entityName).filter((name): name is string => name != null) || []
      ),
    ].map((name) => ({
      text: name,
      value: name,
    })) || [];
  entityNameColumn.onFilter = (value, record) => record.entityName === value;
  entityNameColumn.filterIcon = (_filtered: boolean) => <FilterOutlined />;

  const userColumnFilters =
    [
      ...new Set(
        auditLogs?.map((log) => log.actionByUser).filter((user): user is string => user != null) ||
          []
      ),
    ].map((user) => ({
      text: user,
      value: user,
    })) || [];

  const detailsColumn = createTruncatedColumn<GetAuditLogs_ResultSet1>({
    title: t('system:audit.columns.details'),
    dataIndex: 'details',
    key: 'details',
    maxLength: 48,
    renderText: (value) => value || '',
    renderWrapper: (content) => <Typography.Text>{content}</Typography.Text>,
  });

  return [
    timestampColumn,
    actionColumn,
    {
      title: (
        <Space>
          {t('system:audit.columns.entityType')}
          <FilterOutlined />
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
      filterIcon: (_filtered: boolean) => <FilterOutlined />,
    },
    entityNameColumn,
    {
      title: (
        <Space>
          {t('system:audit.columns.user')}
          <FilterOutlined />
        </Space>
      ),
      dataIndex: 'actionByUser',
      key: 'actionByUser',
      width: 200,
      filters: userColumnFilters,
      onFilter: (value, record) => record.actionByUser === value,
      filterIcon: (_filtered: boolean) => <FilterOutlined />,
    },
    detailsColumn,
  ];
};
