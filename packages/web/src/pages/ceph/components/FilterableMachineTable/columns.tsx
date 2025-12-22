import { Badge, Tag } from 'antd';
import { createTruncatedColumn } from '@/components/common/columns';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import { createSorter } from '@/platform';
import type { Machine } from '@/types';
import type { ColumnsType } from 'antd/es/table/interface';
import type { TFunction } from 'i18next';

export const buildMachineTableColumns = (
  t: TFunction<'machines' | 'ceph'>
): ColumnsType<Machine> => [
  createTruncatedColumn<Machine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<Machine>('machineName'),
  }),
  createTruncatedColumn<Machine>({
    title: t('machines:team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    sorter: createSorter<Machine>('teamName'),
    renderWrapper: (content) => (content ? <Tag bordered={false}>{content}</Tag> : null),
  }),
  createTruncatedColumn<Machine>({
    title: t('machines:bridge'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    width: 150,
    sorter: createSorter<Machine>('bridgeName'),
    renderWrapper: (content) => (content ? <Tag bordered={false}>{content}</Tag> : null),
  }),
  {
    title: t('ceph:assignment.status'),
    key: 'assignmentStatus',
    width: 200,
    ellipsis: true,
    render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />,
  },
  {
    title: t('machines:queueItems'),
    dataIndex: 'queueCount',
    key: 'queueCount',
    width: 100,
    align: 'center',
    sorter: createSorter<Machine>('queueCount'),
    render: (count: number = 0) => <Badge count={count} showZero />,
  },
];
