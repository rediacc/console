import { Button, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd';
import type { Bridge } from '@/api/queries/bridges';
import type { Region } from '@/api/queries/regions';
import { createVersionColumn } from '@/components/common/columns';
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
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

const ACTIONS_COLUMN_WIDTH = 640;

interface BuildRegionColumnsParams {
  t: TFunction<'resources'>;
  tCommon: TFunction<'common'>;
  tSystem: TFunction<'system'>;
  onEdit: (region: Region) => void;
  onTrace: (region: Region) => void;
  onDelete: (regionName: string) => void;
  isDeleting: boolean;
}

export const buildRegionColumns = ({
  t,
  tCommon,
  tSystem,
  onEdit,
  onTrace,
  onDelete,
  isDeleting,
}: BuildRegionColumnsParams): ColumnsType<Region> => [
  {
    title: t('regions.regionName'),
    dataIndex: 'regionName',
    key: 'regionName',
    sorter: createSorter<Region>('regionName'),
    render: (text: string) => (
      <Space>
        <EnvironmentOutlined />
        <strong>{text}</strong>
      </Space>
    ),
  },
  ...(!featureFlags.isEnabled('disableBridge')
    ? [
        {
          title: t('regions.bridges'),
          dataIndex: 'bridgeCount',
          key: 'bridgeCount',
          width: 120,
          sorter: createSorter<Region>('bridgeCount'),
          render: (count: number) => (
            <Space>
              <ApiOutlined />
              <Typography.Text>{count}</Typography.Text>
            </Space>
          ),
        } as ColumnsType<Region>[number],
      ]
    : []),
  ...(featureFlags.isEnabled('vaultVersionColumns')
    ? [
        createVersionColumn<Region>({
          title: t('general.vaultVersion'),
          dataIndex: 'vaultVersion',
          key: 'vaultVersion',
          width: 120,
          sorter: createSorter<Region>('vaultVersion'),
          formatVersion: (version: number) => tCommon('general.versionFormat', { version }),
        }),
      ]
    : []),
  {
    title: t('general.actions'),
    key: 'actions',
    width: 300,
    render: (_: unknown, record: Region) => (
      <Space>
        <Tooltip title={t('general.edit')}>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(record)}
            data-testid={`system-region-edit-button-${record.regionName}`}
            aria-label={t('general.edit')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.trace')}>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => onTrace(record)}
            data-testid={`system-region-trace-button-${record.regionName}`}
            aria-label={tSystem('actions.trace')}
          />
        </Tooltip>
        <Popconfirm
          title={t('regions.deleteRegion')}
          description={t('regions.confirmDelete', { regionName: record.regionName })}
          onConfirm={() => onDelete(record.regionName)}
          okText={t('general.yes')}
          cancelText={t('general.no')}
          okButtonProps={{ danger: true }}
        >
          <Tooltip title={t('general.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={isDeleting}
              data-testid={`system-region-delete-button-${record.regionName}`}
              aria-label={t('general.delete')}
            />
          </Tooltip>
        </Popconfirm>
      </Space>
    ),
  },
];

interface BuildBridgeColumnsParams {
  t: TFunction<'resources'>;
  tCommon: TFunction<'common'>;
  tSystem: TFunction<'system'>;
  onEdit: (bridge: Bridge) => void;
  onOpenToken: (bridge: Bridge) => void;
  onResetAuth: (bridge: Bridge) => void;
  onTrace: (bridge: Bridge) => void;
  onDelete: (bridge: Bridge) => void;
  isDeleting: boolean;
}

export const buildBridgeColumns = ({
  t,
  tCommon,
  tSystem,
  onEdit,
  onOpenToken,
  onResetAuth,
  onTrace,
  onDelete,
  isDeleting,
}: BuildBridgeColumnsParams): ColumnsType<Bridge> => [
  {
    title: t('bridges.bridgeName'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    sorter: createSorter<Bridge>('bridgeName'),
    render: (text: string, record: Bridge) => (
      <Space>
        <ApiOutlined />
        <strong>{text}</strong>
        {Number(record.hasAccess || 0) === 1 && (
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
    sorter: createSorter<Bridge>('machineCount'),
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
    sorter: createSorter<Bridge>('isGlobalBridge'),
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
    sorter: createSorter<Bridge>('managementMode'),
    render: (mode: string) => {
      if (!mode) return <Tag>{t('bridges.local')}</Tag>;
      const icon = mode === 'Cloud' ? <CloudServerOutlined /> : <DesktopOutlined />;
      return <Tag icon={icon}>{mode}</Tag>;
    },
  },
  ...(featureFlags.isEnabled('vaultVersionColumns')
    ? [
        createVersionColumn<Bridge>({
          title: t('general.vaultVersion'),
          dataIndex: 'vaultVersion',
          key: 'vaultVersion',
          width: 120,
          sorter: createSorter<Bridge>('vaultVersion'),
          formatVersion: (version: number) => tCommon('general.versionFormat', { version }),
        }),
      ]
    : []),
  {
    title: t('general.actions'),
    key: 'actions',
    width: ACTIONS_COLUMN_WIDTH,
    render: (_: unknown, record: Bridge) => (
      <Space>
        <Tooltip title={t('general.edit')}>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(record)}
            data-testid={`system-bridge-edit-button-${record.bridgeName}`}
            aria-label={t('general.edit')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.token')}>
          <Button
            type="primary"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => onOpenToken(record)}
            data-testid={`system-bridge-token-button-${record.bridgeName}`}
            aria-label={tSystem('actions.token')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.resetAuth')}>
          <Button
            type="primary"
            size="small"
            icon={<SyncOutlined />}
            onClick={() => onResetAuth(record)}
            data-testid={`system-bridge-reset-auth-button-${record.bridgeName}`}
            aria-label={tSystem('actions.resetAuth')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.trace')}>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => onTrace(record)}
            data-testid={`system-bridge-trace-button-${record.bridgeName}`}
            aria-label={tSystem('actions.trace')}
          />
        </Tooltip>
        <Popconfirm
          title={t('bridges.deleteBridge')}
          description={t('bridges.confirmDelete', { bridgeName: record.bridgeName })}
          onConfirm={() => onDelete(record)}
          okText={t('general.yes')}
          cancelText={t('general.no')}
          okButtonProps={{ danger: true }}
        >
          <Tooltip title={t('general.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={isDeleting}
              data-testid={`system-bridge-delete-button-${record.bridgeName}`}
              aria-label={t('general.delete')}
            />
          </Tooltip>
        </Popconfirm>
      </Space>
    ),
  },
];
