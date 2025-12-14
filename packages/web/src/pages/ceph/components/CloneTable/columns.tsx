import React from 'react';
import { CloudUploadOutlined, EllipsisOutlined } from '@ant-design/icons';
import { TFunction } from 'i18next';
import type { CephRbdClone } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn } from '@/components/common/columns';
import { RediaccTag, RediaccTooltip } from '@/components/ui';
import { CloneIcon, CloneName, NameCell } from './styles';
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
      <NameCell data-testid={`clone-list-item-${record.cloneName}`}>
        <CloneIcon />
        <CloneName>{text}</CloneName>
        {record.vaultContent && (
          <RediaccTooltip title={t('common.hasVault')}>
            <RediaccTag
              variant="neutral"
              compact
              data-testid={`clone-list-vault-tag-${record.cloneName}`}
            >
              {t('common.vault')}
            </RediaccTag>
          </RediaccTooltip>
        )}
      </NameCell>
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
