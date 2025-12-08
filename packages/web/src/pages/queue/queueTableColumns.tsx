import { Space, Tooltip } from 'antd';
import { renderBoolean, renderTimestamp } from '@/components/common/columns';
import { RediaccButton, RediaccText } from '@/components/ui';
import { formatAge } from '@/platform';
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
}

export const getQueueColumns = ({
  handleViewTrace,
  handleCancelQueueItem,
  cancelLoading,
}: QueueColumnsConfig): ColumnsType<QueueItem> => [
  {
    title: 'Task ID',
    dataIndex: 'taskId',
    key: 'taskId',
    width: 200,
    render: (id: string) => (
      <RediaccText code copyable>
        {id}
      </RediaccText>
    ),
  },
  {
    title: 'Status',
    dataIndex: 'healthStatus',
    key: 'healthStatus',
    width: 120,
    render: (healthStatus: string, record: QueueItem) => renderQueueStatus(healthStatus, record),
  },
  {
    title: 'Priority',
    dataIndex: 'priorityLabel',
    key: 'priority',
    width: 140,
    render: (priorityLabel: string | undefined, record: QueueItem) => (
      <PriorityWithTooltip priorityLabel={priorityLabel} record={record} />
    ),
    sorter: (a, b) => (a.priority ?? 3) - (b.priority ?? 3),
  },
  {
    title: 'Age',
    dataIndex: 'ageInMinutes',
    key: 'ageInMinutes',
    width: 100,
    render: (minutes: number) => formatAge(minutes),
    sorter: (a, b) => (a.ageInMinutes ?? 0) - (b.ageInMinutes ?? 0),
  },
  {
    title: 'Team',
    dataIndex: 'teamName',
    key: 'teamName',
  },
  {
    title: 'Machine',
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
    title: 'Region',
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
    title: 'Bridge',
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
    title: 'Response',
    dataIndex: 'hasResponse',
    key: 'hasResponse',
    width: 80,
    render: (hasResponse: boolean) => renderBoolean(hasResponse),
  },
  {
    title: 'Error / Retries',
    dataIndex: 'retryCount',
    key: 'retryCount',
    width: 280,
    render: (retryCount: number | undefined, record: QueueItem) => (
      <ErrorRetriesRenderer retryCount={retryCount} record={record} />
    ),
    sorter: (a, b) => (a.retryCount ?? 0) - (b.retryCount ?? 0),
  },
  {
    title: 'Created By',
    dataIndex: 'createdBy',
    key: 'createdBy',
    width: 150,
    render: (createdBy: string | undefined) =>
      createdBy || <RediaccText color="secondary">-</RediaccText>,
  },
  {
    title: 'Age',
    dataIndex: 'ageInMinutes',
    key: 'age',
    width: 100,
    render: (ageInMinutes: number, record: QueueItem) => (
      <AgeRenderer ageInMinutes={ageInMinutes} record={record} />
    ),
    sorter: (a, b) => (a.ageInMinutes ?? 0) - (b.ageInMinutes ?? 0),
  },
  {
    title: 'Created',
    dataIndex: 'createdTime',
    key: 'createdTime',
    width: 180,
    render: (date: string) => renderTimestamp(date),
    sorter: (a, b) =>
      new Date(a.createdTime ?? 0).getTime() - new Date(b.createdTime ?? 0).getTime(),
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 180,
    render: (_: unknown, record: QueueItem) => (
      <Space size="small">
        <Tooltip title="Trace">
          <RediaccButton
            size="sm"
            iconOnly
            icon={<HistoryOutlined />}
            onClick={() => record.taskId && handleViewTrace(record.taskId)}
            data-testid={`queue-trace-button-${record.taskId}`}
            aria-label="Trace"
          />
        </Tooltip>
        {record.canBeCancelled &&
          record.healthStatus !== 'CANCELLED' &&
          record.healthStatus !== 'CANCELLING' && (
            <Tooltip title="Cancel">
              <RediaccButton
                size="sm"
                danger
                iconOnly
                icon={<CloseCircleOutlined />}
                onClick={() => record.taskId && handleCancelQueueItem(record.taskId)}
                loading={cancelLoading}
                data-testid={`queue-cancel-button-${record.taskId}`}
                aria-label="Cancel"
              />
            </Tooltip>
          )}
      </Space>
    ),
  },
];
