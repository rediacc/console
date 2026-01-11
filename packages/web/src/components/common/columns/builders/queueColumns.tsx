import { Space, Typography } from 'antd';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  PriorityWithTooltip,
  AgeRenderer,
  ErrorRetriesRenderer,
} from '@/features/queue/components/QueueTableRenderers';
import {
  ApiOutlined,
  CloseCircleOutlined,
  DesktopOutlined,
  GlobalOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';
import { renderQueueStatus } from '@/utils/queueRenderers';
import { DEFAULTS } from '@rediacc/shared/config';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { RESPONSIVE_HIDE_XS } from '..';
import { createActionColumn } from '../factories/action';
import { renderBoolean, renderTimestamp } from '../renderers';
import type { ColumnsType } from 'antd/es/table';

interface QueueColumnsConfig {
  handleViewTrace: (taskId: string) => void;
  handleCancelQueueItem: (taskId: string) => void;
  cancelLoading: boolean;
  t: TypedTFunction;
}

export const buildQueueColumns = ({
  handleViewTrace,
  handleCancelQueueItem,
  cancelLoading,
  t,
}: QueueColumnsConfig): ColumnsType<GetTeamQueueItems_ResultSet1> => [
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
    render: (healthStatus: string, record: GetTeamQueueItems_ResultSet1) =>
      renderQueueStatus(healthStatus, record),
  },
  {
    title: t('queue:columns.priority'),
    dataIndex: 'priorityLabel',
    key: 'priority',
    width: 140,
    responsive: RESPONSIVE_HIDE_XS,
    render: (priorityLabel: string | undefined, record: GetTeamQueueItems_ResultSet1) => (
      <PriorityWithTooltip priorityLabel={priorityLabel} record={record} />
    ),
    sorter: (a, b) =>
      (a.priority ?? DEFAULTS.PRIORITY.QUEUE_PRIORITY) -
      (b.priority ?? DEFAULTS.PRIORITY.QUEUE_PRIORITY),
  },
  {
    title: t('queue:columns.age'),
    dataIndex: 'ageInMinutes',
    key: 'ageInMinutes',
    width: 100,
    responsive: RESPONSIVE_HIDE_XS,
    render: (ageInMinutes: number, record: GetTeamQueueItems_ResultSet1) => (
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
    responsive: RESPONSIVE_HIDE_XS,
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
    responsive: RESPONSIVE_HIDE_XS,
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
    responsive: RESPONSIVE_HIDE_XS,
    render: (retryCount: number | undefined, record: GetTeamQueueItems_ResultSet1) => (
      <ErrorRetriesRenderer retryCount={retryCount} record={record} />
    ),
    sorter: (a, b) => (a.retryCount ?? 0) - (b.retryCount ?? 0),
  },
  {
    title: t('queue:columns.createdBy'),
    dataIndex: 'createdBy',
    key: 'createdBy',
    width: 150,
    responsive: RESPONSIVE_HIDE_XS,
    render: (createdBy: string | undefined) => createdBy ?? <Typography.Text>-</Typography.Text>,
  },
  {
    title: t('queue:columns.created'),
    dataIndex: 'createdTime',
    key: 'createdTime',
    width: 180,
    responsive: RESPONSIVE_HIDE_XS,
    render: (date: string) => renderTimestamp(date),
    sorter: (a, b) =>
      new Date(a.createdTime ?? 0).getTime() - new Date(b.createdTime ?? 0).getTime(),
  },
  createActionColumn<GetTeamQueueItems_ResultSet1>({
    title: t('common:actionsColumn'),
    width: 180,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'trace',
            icon: <HistoryOutlined />,
            tooltip: 'common:tooltips.trace',
            onClick: () => record.taskId && handleViewTrace(record.taskId),
            testId: `queue-trace-button-${record.taskId}`,
            ariaLabel: 'common:aria.trace',
          },
          {
            type: 'cancel',
            icon: <CloseCircleOutlined />,
            tooltip: 'common:tooltips.cancel',
            onClick: () => record.taskId && handleCancelQueueItem(record.taskId),
            danger: true,
            loading: cancelLoading,
            testId: `queue-cancel-button-${record.taskId}`,
            ariaLabel: 'common:aria.cancel',
            visible: (rec) =>
              Boolean(
                rec.canBeCancelled &&
                  rec.healthStatus !== 'CANCELLED' &&
                  rec.healthStatus !== 'CANCELLING'
              ),
          },
        ]}
        record={record}
        idField="taskId"
        testIdPrefix="queue"
        t={t}
      />
    ),
  }),
];
