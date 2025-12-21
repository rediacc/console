import React from 'react';
import { CloudUploadOutlined, CopyOutlined, EllipsisOutlined } from '@ant-design/icons';
import { Flex, Tag, Tooltip, Typography } from 'antd';
import { TFunction } from 'i18next';
import type { CephRbdClone } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn } from '@/components/common/columns';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

interface ColumnBuilderParams {
  t: TFunction<'ceph' | 'common'>;
  renderMachineCount: (clone: CephRbdClone) => React.ReactNode;
  handleRunFunction: (functionName: string, clone?: CephRbdClone) => void;
  getCloneMenuItems: (clone: CephRbdClone) => MenuProps['items'];
}

export const buildCloneColumns = ({
  t,
  renderMachineCount,
  handleRunFunction,
  getCloneMenuItems,
}: ColumnBuilderParams): ColumnsType<CephRbdClone> => [
  {
    title: t('clones.name'),
    dataIndex: 'cloneName',
    key: 'cloneName',
    render: (text: string, record: CephRbdClone) => (
      <Flex align="center" gap={8} data-testid={`clone-list-item-${record.cloneName}`}>
        <CopyOutlined style={{ fontSize: 16 }} />
        <Typography.Text style={{ fontWeight: 400 }}>{text}</Typography.Text>
        {record.vaultContent && (
          <Tooltip title={t('common.hasVault')}>
            <Tag data-testid={`clone-list-vault-tag-${record.cloneName}`} bordered={false}>
              {t('common.vault')}
            </Tag>
          </Tooltip>
        )}
      </Flex>
    ),
  },
  {
    title: t('machines:machines'),
    key: 'machines',
    width: 100,
    align: 'center' as const,
    render: (_: unknown, record: CephRbdClone) => renderMachineCount(record),
  },
  createActionColumn<CephRbdClone>({
    width: 180,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'remote',
            icon: <CloudUploadOutlined />,
            tooltip: 'ceph:common.remote',
            label: 'ceph:common.remote',
            onClick: () => handleRunFunction('ceph_rbd_info', record),
            testIdSuffix: 'remote',
          },
          {
            type: 'actions',
            icon: <EllipsisOutlined />,
            tooltip: 'ceph:common.moreActions',
            dropdownItems: getCloneMenuItems(record),
            variant: 'default',
            testIdSuffix: 'actions',
          },
        ]}
        record={record}
        idField="cloneName"
        testIdPrefix="clone-list"
        t={t}
      />
    ),
  }),
];
