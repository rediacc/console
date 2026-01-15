import React from 'react';
import { CloudUploadOutlined, CopyOutlined, EllipsisOutlined } from '@ant-design/icons';
import { Flex, Tag, Tooltip, Typography } from 'antd';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetCephRbdClones_ResultSet1 } from '@rediacc/shared/types';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

interface ColumnBuilderParams {
  t: TypedTFunction;
  renderMachineCount: (clone: GetCephRbdClones_ResultSet1) => React.ReactNode;
  handleRunFunction: (functionName: string, clone?: GetCephRbdClones_ResultSet1) => void;
  getCloneMenuItems: (clone: GetCephRbdClones_ResultSet1) => MenuProps['items'];
}

export const buildCloneColumns = ({
  t,
  renderMachineCount,
  handleRunFunction,
  getCloneMenuItems,
}: ColumnBuilderParams): ColumnsType<GetCephRbdClones_ResultSet1> => {
  return [
    {
      title: t('clones.name'),
      dataIndex: 'cloneName',
      key: 'cloneName',
      render: (text: string, record: GetCephRbdClones_ResultSet1) => (
        <Flex align="center" data-testid={`clone-list-item-${record.cloneName}`}>
          <CopyOutlined />
          <Typography.Text>{text}</Typography.Text>
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
      responsive: RESPONSIVE_HIDE_XS,
      render: (_: unknown, record: GetCephRbdClones_ResultSet1) => renderMachineCount(record),
    },
    createActionColumn<GetCephRbdClones_ResultSet1>({
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
};
