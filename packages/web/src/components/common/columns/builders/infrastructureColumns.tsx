import { Button, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { featureFlags } from '@/config/featureFlags';
import { createSorter } from '@/platform';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  DesktopOutlined,
  EditOutlined,
  EnvironmentOutlined,
  HistoryOutlined,
  KeyOutlined,
  SyncOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type {
  GetOrganizationRegions_ResultSet1,
  GetRegionBridges_ResultSet1,
} from '@rediacc/shared/types';
import { RESPONSIVE_HIDE_XS } from '..';
import { createActionColumn } from '../factories/action';
import { createVersionColumn } from '../factories/advanced';
import type { ColumnsType } from 'antd/es/table';

const ACTIONS_COLUMN_WIDTH = 640;

interface BuildRegionColumnsParams {
  t: TypedTFunction;
  onEdit: (region: GetOrganizationRegions_ResultSet1) => void;
  onTrace: (region: GetOrganizationRegions_ResultSet1) => void;
  onDelete: (regionName: string) => void;
  isDeleting: boolean;
}

export const buildRegionColumns = ({
  t,
  onEdit,
  onTrace,
  onDelete,
  isDeleting,
}: BuildRegionColumnsParams): ColumnsType<GetOrganizationRegions_ResultSet1> => [
  {
    title: t('regions.regionName'),
    dataIndex: 'regionName',
    key: 'regionName',
    sorter: createSorter<GetOrganizationRegions_ResultSet1>('regionName'),
    render: (text: string) => (
      <Space>
        <EnvironmentOutlined />
        <strong>{text}</strong>
      </Space>
    ),
  },
  // Bridge count column - always visible for infrastructure overview
  {
    title: t('regions.bridges'),
    dataIndex: 'bridgeCount',
    key: 'bridgeCount',
    width: 120,
    responsive: RESPONSIVE_HIDE_XS,
    sorter: createSorter<GetOrganizationRegions_ResultSet1>('bridgeCount'),
    render: (count: number) => (
      <Space>
        <ApiOutlined />
        <Typography.Text>{count}</Typography.Text>
      </Space>
    ),
  },
  ...(featureFlags.isEnabled('vaultVersionColumns')
    ? [
        {
          ...createVersionColumn<GetOrganizationRegions_ResultSet1>({
            title: t('general.vaultVersion'),
            dataIndex: 'vaultVersion',
            key: 'vaultVersion',
            width: 120,
            sorter: createSorter<GetOrganizationRegions_ResultSet1>('vaultVersion'),
            formatVersion: (version: number) => t('common:general.versionFormat', { version }),
          }),
          responsive: RESPONSIVE_HIDE_XS,
        },
      ]
    : []),
  createActionColumn<GetOrganizationRegions_ResultSet1>({
    title: t('general.actions'),
    width: 300,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'edit',
            icon: <EditOutlined />,
            tooltip: 'resources:general.edit',
            onClick: () => onEdit(record),
            variant: 'primary',
            testId: `system-region-edit-button-${record.regionName}`,
          },
          {
            type: 'trace',
            icon: <HistoryOutlined />,
            tooltip: 'system:actions.trace',
            onClick: () => onTrace(record),
            variant: 'primary',
            testId: `system-region-trace-button-${record.regionName}`,
          },
          {
            type: 'custom',
            render: (rec) => (
              <Popconfirm
                title={t('regions.deleteRegion')}
                description={t('regions.confirmDelete', { regionName: rec.regionName ?? '' })}
                onConfirm={() => onDelete(rec.regionName ?? '')}
                okText={t('general.yes')}
                cancelText={t('general.no')}
                okButtonProps={{ danger: true }}
              >
                <Tooltip title={t('general.delete')}>
                  <Button
                    type="primary"
                    shape="circle"
                    danger
                    icon={<DeleteOutlined />}
                    loading={isDeleting}
                    data-testid={`system-region-delete-button-${rec.regionName}`}
                    aria-label={t('general.delete')}
                  />
                </Tooltip>
              </Popconfirm>
            ),
          },
        ]}
        record={record}
        idField="regionName"
        testIdPrefix="system-region"
        t={t}
      />
    ),
  }),
];

interface BuildBridgeColumnsParams {
  t: TypedTFunction;
  onEdit: (bridge: GetRegionBridges_ResultSet1) => void;
  onOpenToken: (bridge: GetRegionBridges_ResultSet1) => void;
  onResetAuth: (bridge: GetRegionBridges_ResultSet1) => void;
  onTrace: (bridge: GetRegionBridges_ResultSet1) => void;
  onDelete: (bridge: GetRegionBridges_ResultSet1) => void;
  isDeleting: boolean;
}

export const buildBridgeColumns = ({
  t,
  onEdit,
  onOpenToken,
  onResetAuth,
  onTrace,
  onDelete,
  isDeleting,
}: BuildBridgeColumnsParams): ColumnsType<GetRegionBridges_ResultSet1> => [
  {
    title: t('bridges.bridgeName'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    sorter: createSorter<GetRegionBridges_ResultSet1>('bridgeName'),
    render: (text: string, record: GetRegionBridges_ResultSet1) => (
      <Space>
        <ApiOutlined />
        <strong>{text}</strong>
        {record.hasAccess === true && (
          <Tag icon={<CheckCircleOutlined />}>{t('bridges.access')}</Tag>
        )}
      </Space>
    ),
  },
  {
    title: t('teams.machines'),
    dataIndex: 'machineCount',
    key: 'machineCount',
    width: 120,
    responsive: RESPONSIVE_HIDE_XS,
    sorter: createSorter<GetRegionBridges_ResultSet1>('machineCount'),
    render: (count: number) => (
      <Space>
        <DesktopOutlined />
        <Typography.Text>{count}</Typography.Text>
      </Space>
    ),
  },
  {
    title: t('bridges.type'),
    dataIndex: 'isGlobalBridge',
    key: 'isGlobalBridge',
    width: 120,
    responsive: RESPONSIVE_HIDE_XS,
    sorter: createSorter<GetRegionBridges_ResultSet1>('isGlobalBridge'),
    render: (isGlobal: boolean) =>
      isGlobal ? (
        <Tag icon={<CloudServerOutlined />}>{t('bridges.global')}</Tag>
      ) : (
        <Tag icon={<ApiOutlined />}>{t('bridges.regular')}</Tag>
      ),
  },
  {
    title: t('bridges.management'),
    dataIndex: 'managementMode',
    key: 'managementMode',
    width: 140,
    responsive: RESPONSIVE_HIDE_XS,
    sorter: createSorter<GetRegionBridges_ResultSet1>('managementMode'),
    render: (mode: string) => {
      if (!mode) return <Tag>{t('bridges.local')}</Tag>;
      const icon = mode === 'Cloud' ? <CloudServerOutlined /> : <DesktopOutlined />;
      return <Tag icon={icon}>{mode}</Tag>;
    },
  },
  ...(featureFlags.isEnabled('vaultVersionColumns')
    ? [
        {
          ...createVersionColumn<GetRegionBridges_ResultSet1>({
            title: t('general.vaultVersion'),
            dataIndex: 'vaultVersion',
            key: 'vaultVersion',
            width: 120,
            sorter: createSorter<GetRegionBridges_ResultSet1>('vaultVersion'),
            formatVersion: (version: number) => t('common:general.versionFormat', { version }),
          }),
          responsive: RESPONSIVE_HIDE_XS,
        },
      ]
    : []),
  createActionColumn<GetRegionBridges_ResultSet1>({
    title: t('general.actions'),
    width: ACTIONS_COLUMN_WIDTH,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'edit',
            icon: <EditOutlined />,
            tooltip: 'resources:general.edit',
            onClick: () => onEdit(record),
            variant: 'primary',
            testId: `system-bridge-edit-button-${record.bridgeName}`,
          },
          {
            type: 'token',
            icon: <KeyOutlined />,
            tooltip: 'system:actions.token',
            onClick: () => onOpenToken(record),
            variant: 'primary',
            testId: `system-bridge-token-button-${record.bridgeName}`,
          },
          {
            type: 'resetAuth',
            icon: <SyncOutlined />,
            tooltip: 'system:actions.resetAuth',
            onClick: () => onResetAuth(record),
            variant: 'primary',
            testId: `system-bridge-reset-auth-button-${record.bridgeName}`,
          },
          {
            type: 'trace',
            icon: <HistoryOutlined />,
            tooltip: 'system:actions.trace',
            onClick: () => onTrace(record),
            variant: 'primary',
            testId: `system-bridge-trace-button-${record.bridgeName}`,
          },
          {
            type: 'custom',
            render: (rec) => {
              const isProtected = rec.bridgeName === 'Global Bridges';
              return isProtected ? (
                <Tooltip title={t('bridges.cannotDeleteDefault')}>
                  <Button
                    type="primary"
                    shape="circle"
                    danger
                    disabled
                    icon={<DeleteOutlined />}
                    data-testid={`system-bridge-delete-button-${rec.bridgeName}`}
                    aria-label={t('general.delete')}
                  />
                </Tooltip>
              ) : (
                <Popconfirm
                  title={t('bridges.deleteBridge')}
                  description={t('bridges.confirmDelete', { bridgeName: rec.bridgeName })}
                  onConfirm={() => onDelete(rec)}
                  okText={t('general.yes')}
                  cancelText={t('general.no')}
                  okButtonProps={{ danger: true }}
                >
                  <Tooltip title={t('general.delete')}>
                    <Button
                      type="primary"
                      shape="circle"
                      danger
                      icon={<DeleteOutlined />}
                      loading={isDeleting}
                      data-testid={`system-bridge-delete-button-${rec.bridgeName}`}
                      aria-label={t('general.delete')}
                    />
                  </Tooltip>
                </Popconfirm>
              );
            },
          },
        ]}
        record={record}
        idField="bridgeName"
        testIdPrefix="system-bridge"
        t={t}
      />
    ),
  }),
];
