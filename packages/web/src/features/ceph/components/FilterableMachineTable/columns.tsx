import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Badge, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import { createTruncatedColumn, RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import { createSorter } from '@/platform';
import type { Machine } from '@/types';

export const buildMachineTableColumns = (t: TypedTFunction): ColumnsType<Machine> => [
  createTruncatedColumn<Machine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<Machine>('machineName'),
  }),
  {
    ...createTruncatedColumn<Machine>({
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      sorter: createSorter<Machine>('teamName'),
      renderWrapper: (content) => (content ? <Tag bordered={false}>{content}</Tag> : null),
    }),
    responsive: RESPONSIVE_HIDE_XS,
  },
  {
    ...createTruncatedColumn<Machine>({
      title: t('machines:bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      width: 150,
      sorter: createSorter<Machine>('bridgeName'),
      renderWrapper: (content) => (content ? <Tag bordered={false}>{content}</Tag> : null),
    }),
    responsive: RESPONSIVE_HIDE_XS,
  },
  {
    title: t('ceph:assignment.status'),
    key: 'assignmentStatus',
    width: 200,
    ellipsis: true,
    responsive: RESPONSIVE_HIDE_XS,
    render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />,
  },
  {
    title: t('machines:queueItems'),
    dataIndex: 'queueCount',
    key: 'queueCount',
    width: 100,
    align: 'center',
    responsive: RESPONSIVE_HIDE_XS,
    sorter: createSorter<Machine>('queueCount'),
    render: (count = 0) => <Badge count={count} showZero />,
  },
];
