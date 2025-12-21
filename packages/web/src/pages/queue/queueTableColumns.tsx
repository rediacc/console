import { Button, Space, Tooltip, Typography } from 'antd';
import { renderBoolean, renderTimestamp } from '@/components/common/columns';
import {
  ApiOutlined,
  CloseCircleOutlined,
  DesktopOutlined,
  GlobalOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';
import { renderQueueStatus } from '@/utils/queueRenderers';
import type { GetTeamQueueItems_ResultSet1 as QueueItem } from '@rediacc/shared/types';
import {
  PriorityWithTooltip,
  AgeRenderer,
  ErrorRetriesRenderer,
} from './components/QueueTableRenderers';
import type { ColumnsType } from 'antd/es/table';

interface QueueColumnsConfig {
  handleViewTrace: (taskId: string) => void;
  handleCancelQueueItem: (taskId: string) => void;
  cancelLoading: boolean;
  t: (key: string) => string;
}

export const getQueueColumns = ({
  handleViewTrace,
  handleCancelQueueItem,
  cancelLoading,
  t,
}: QueueColumnsConfig): ColumnsType<QueueItem> => [
  {
    title: t('queue:columns.taskId'),
    dataIndex: 'taskId',
    key: 'taskId',
    width: 200,
    render: (id: string) => (
      <Typography.Text code copyable>
        {id}
      </Typography.Text>
    ),
  },
  {
    title: t('queue:columns.status'),
    dataIndex: 'healthStatus',
    key: 'healthStatus',
    width: 120,
    render: (healthStatus: string, record: QueueItem) => renderQueueStatus(healthStatus, record),
  },
  {
    title: t('queue:columns.priority'),
    dataIndex: 'priorityLabel',
    key: 'priority',
    width: 140,
    render: (priorityLabel: string | undefined, record: QueueItem) => (
      <PriorityWithTooltip priorityLabel={priorityLabel} record={record} />
    ),
    sorter: (a, b) => (a.priority ?? 3) - (b.priority ?? 3),
  },
  {
    title: t('queue:columns.age'),
    dataIndex: 'ageInMinutes',
    key: 'ageInMinutes',
    width: 100,
    render: (ageInMinutes: number, record: QueueItem) => (
      <AgeRenderer ageInMinutes={ageInMinutes} record={record} />
    ),
    sorter: (a, b) => (a.ageInMinutes ?? 0) - (b.ageInMinutes ?? 0),
  },
  {
    title: t('queue:columns.team'),
    dataIndex: 'teamName',
    key: 'teamName',
  },
  {
    title: t('queue:columns.machine'),
    dataIndex: 'machineName',
    key: 'machineName',
    render: (name: string) => (
      <Space>
        <DesktopOutlined />
        {name}
      </Space>
    ),
  },
  {
    title: t('queue:columns.region'),
    dataIndex: 'regionName',
    key: 'regionName',
    render: (name: string) => (
      <Space>
        <GlobalOutlined />
        {name}
      </Space>
    ),
  },
  {
    title: t('queue:columns.bridge'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    render: (name: string) => (
      <Space>
        <ApiOutlined />
        {name}
      </Space>
    ),
  },
  {
    title: t('queue:columns.response'),
    dataIndex: 'hasResponse',
    key: 'hasResponse',
    width: 80,
    render: (hasResponse: boolean) => renderBoolean(hasResponse),
  },
  {
    title: t('queue:columns.errorRetries'),
    dataIndex: 'retryCount',
    key: 'retryCount',
    width: 280,
    render: (retryCount: number | undefined, record: QueueItem) => (
      <ErrorRetriesRenderer retryCount={retryCount} record={record} />
    ),
    sorter: (a, b) => (a.retryCount ?? 0) - (b.retryCount ?? 0),
  },
  {
    title: t('queue:columns.createdBy'),
    dataIndex: 'createdBy',
    key: 'createdBy',
    width: 150,
    render: (createdBy: string | undefined) =>
      createdBy || <Typography.Text type="secondary">-</Typography.Text>,
  },
  {
    title: t('queue:columns.created'),
    dataIndex: 'createdTime',
    key: 'createdTime',
    width: 180,
    render: (date: string) => renderTimestamp(date),
    sorter: (a, b) =>
      new Date(a.createdTime ?? 0).getTime() - new Date(b.createdTime ?? 0).getTime(),
  },
  {
    title: t('common:actionsColumn'),
    key: 'actions',
    width: 180,
    render: (_: unknown, record: QueueItem) => (
      <Space size="small">
        <Tooltip title={t('common:tooltips.trace')}>
          <Button
            type="text"
            icon={<HistoryOutlined />}
            onClick={() => record.taskId && handleViewTrace(record.taskId)}
            data-testid={`queue-trace-button-${record.taskId}`}
            aria-label={t('common:aria.trace')}
          />
        </Tooltip>
        {record.canBeCancelled &&
          record.healthStatus !== 'CANCELLED' &&
          record.healthStatus !== 'CANCELLING' && (
            <Tooltip title={t('common:tooltips.cancel')}>
              <Button
                danger
                type="text"
                icon={<CloseCircleOutlined />}
                onClick={() => record.taskId && handleCancelQueueItem(record.taskId)}
                loading={cancelLoading}
                data-testid={`queue-cancel-button-${record.taskId}`}
                aria-label={t('common:aria.cancel')}
              />
            </Tooltip>
          )}
      </Space>
    ),
  },
];
