import React, { useMemo } from 'react';
import { Space, Tag, Typography, type MenuProps } from 'antd';
import type { GetTeamStorages_ResultSet1 } from '@/api/queries/storage';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import { CloudOutlined, FunctionOutlined } from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface UseStorageMobileRenderParams {
  t: TFunction;
  openUnifiedModal: (
    mode: 'create' | 'edit',
    data?: GetTeamStorages_ResultSet1 & Record<string, unknown>
  ) => void;
  setCurrentResource: (resource: GetTeamStorages_ResultSet1 & Record<string, unknown>) => void;
  handleDeleteStorage: (storage: GetTeamStorages_ResultSet1) => void;
  openAuditTrace: (params: {
    entityType: string;
    entityIdentifier: string;
    entityName: string;
  }) => void;
}

export const useStorageMobileRender = ({
  t,
  openUnifiedModal,
  setCurrentResource,
  handleDeleteStorage,
  openAuditTrace,
}: UseStorageMobileRenderParams) => {
  return useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetTeamStorages_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(t, () =>
          openUnifiedModal('edit', record as GetTeamStorages_ResultSet1 & Record<string, unknown>)
        ),
        {
          key: 'run',
          label: t('common:actions.runFunction'),
          icon: <FunctionOutlined />,
          onClick: () => {
            setCurrentResource(record as GetTeamStorages_ResultSet1 & Record<string, unknown>);
            openUnifiedModal(
              'create',
              record as GetTeamStorages_ResultSet1 & Record<string, unknown>
            );
          },
        },
        buildTraceMenuItem(t, () =>
          openAuditTrace({
            entityType: 'Storage',
            entityIdentifier: record.storageName,
            entityName: record.storageName,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(t, () => handleDeleteStorage(record)),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <CloudOutlined />
            <Typography.Text strong className="truncate">
              {record.storageName}
            </Typography.Text>
          </Space>
          <Tag>{record.teamName}</Tag>
        </MobileCard>
      );
    },
    [t, openUnifiedModal, setCurrentResource, openAuditTrace, handleDeleteStorage]
  );
};
