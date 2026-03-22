import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamStorages_ResultSet1 } from '@rediacc/shared/types';
import { Space, Tag } from 'antd';
import React, { useMemo } from 'react';
import { ActionButtonConfig, ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { COLUMN_RESPONSIVE, COLUMN_WIDTHS } from '@/components/common/ResourceListView';
import { featureFlags } from '@/config/featureFlags';
import {
  CloudOutlined,
  DeleteOutlined,
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';

interface BuildStorageColumnsParams {
  t: TypedTFunction;
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

const StorageLocationIcon = (props: React.ComponentProps<typeof CloudOutlined>) => (
  <CloudOutlined {...props} />
);

export const useBuildStorageColumns = ({
  t,
  openUnifiedModal,
  setCurrentResource,
  handleDeleteStorage,
  openAuditTrace,
}: BuildStorageColumnsParams) => {
  return useMemo(
    () => [
      {
        title: t('storage.storageName'),
        dataIndex: 'storageName',
        key: 'storageName',
        width: COLUMN_WIDTHS.NAME,
        ellipsis: true,
        render: (text: string) => (
          <Space>
            <StorageLocationIcon />
            <strong>{text}</strong>
          </Space>
        ),
      },
      {
        title: t('general.team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: COLUMN_WIDTHS.TAG,
        ellipsis: true,
        render: (teamName: string) => <Tag>{teamName}</Tag>,
      },
      ...(featureFlags.isEnabled('vaultVersionColumns')
        ? [
            {
              title: t('general.vaultVersion'),
              dataIndex: 'vaultVersion',
              key: 'vaultVersion',
              width: COLUMN_WIDTHS.VERSION,
              align: 'center' as const,
              responsive: ['lg', 'xl', 'xxl'] as typeof COLUMN_RESPONSIVE.DESKTOP_ONLY,
              render: (version: number) => (
                <Tag>{t('common:general.versionFormat', { version })}</Tag>
              ),
            },
          ]
        : []),
      createActionColumn<GetTeamStorages_ResultSet1>({
        width: COLUMN_WIDTHS.ACTIONS_WIDE,
        renderActions: (record) => {
          const buttons: ActionButtonConfig<GetTeamStorages_ResultSet1>[] = [
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'common:actions.edit',
              onClick: (r: GetTeamStorages_ResultSet1) =>
                openUnifiedModal('edit', r as GetTeamStorages_ResultSet1 & Record<string, unknown>),
              variant: 'primary',
            },
            {
              type: 'run',
              icon: <FunctionOutlined />,
              tooltip: 'common:actions.runFunction',
              onClick: (r: GetTeamStorages_ResultSet1) => {
                setCurrentResource(r as GetTeamStorages_ResultSet1 & Record<string, unknown>);
                openUnifiedModal(
                  'create',
                  r as GetTeamStorages_ResultSet1 & Record<string, unknown>
                );
              },
              variant: 'primary',
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'machines:trace',
              onClick: (r: GetTeamStorages_ResultSet1) =>
                openAuditTrace({
                  entityType: 'Storage',
                  entityIdentifier: r.storageName ?? '',
                  entityName: r.storageName ?? '',
                }),
              variant: 'default',
            },
            {
              type: 'delete',
              icon: <DeleteOutlined />,
              tooltip: 'common:actions.delete',
              onClick: handleDeleteStorage,
              variant: 'primary',
              danger: true,
            },
          ];

          return (
            <ActionButtonGroup<GetTeamStorages_ResultSet1>
              buttons={buttons}
              record={record}
              idField="storageName"
              testIdPrefix="resources-storage"
              t={t}
            />
          );
        },
      }),
    ],
    [t, openUnifiedModal, setCurrentResource, handleDeleteStorage, openAuditTrace]
  );
};
