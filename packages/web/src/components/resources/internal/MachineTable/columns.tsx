import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Badge, Space, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  createStatusColumn,
  createTruncatedColumn,
  RESPONSIVE_HIDE_XS,
} from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { LocalActionsMenu } from '@/components/resources/internal/LocalActionsMenu';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import { createCustomSorter, createSorter } from '@/platform';
import type { usePingFunction } from '@/services/pingService';
import type { Machine } from '@/types';
import { showMessage } from '@/utils/messages';
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  DesktopOutlined,
  DisconnectOutlined,
  EditOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  FunctionOutlined,
  HistoryOutlined,
  WifiOutlined,
} from '@/utils/optimizedIcons';

type ExecutePingForMachineAndWait = ReturnType<
  typeof usePingFunction
>['executePingForMachineAndWait'];

export interface MachineFunctionAction {
  name?: string;
  description?: string;
  showInMenu?: boolean;
}

interface MachineColumnsParams {
  t: TypedTFunction;
  isExpertMode: boolean;
  uiMode: string;
  showActions: boolean;
  hasSplitView: boolean;
  canAssignToCluster: boolean;
  onEditMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void;
  handleDelete: (machine: Machine) => void;
  handleRowClick: (machine: Machine) => void;
  onViewRepositories: (machine: Machine) => void;
  executePingForMachineAndWait: ExecutePingForMachineAndWait;
  setAssignClusterModal: (state: { open: boolean; machine: Machine | null }) => void;
  setAuditTraceModal: (state: {
    open: boolean;
    entityType: string | null;
    entityIdentifier: string | null;
    entityName?: string;
  }) => void;
  machineFunctions: MachineFunctionAction[];
}

export const buildMachineTableColumns = ({
  t,
  isExpertMode,
  uiMode,
  showActions,
  hasSplitView,
  canAssignToCluster,
  onEditMachine,
  onFunctionsMachine,
  handleDelete,
  handleRowClick,
  onViewRepositories,
  executePingForMachineAndWait,
  setAssignClusterModal,
  setAuditTraceModal,
  machineFunctions,
}: MachineColumnsParams): ColumnsType<Machine> => {
  const baseColumns: ColumnsType<Machine> = [];
  const machineNameColumn = createTruncatedColumn<Machine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    maxLength: 50, // Increased from default 12 to show more of the machine name
    sorter: createSorter<Machine>('machineName'),
    renderWrapper: (content) => (
      <Space>
        <DesktopOutlined />
        <strong>{content}</strong>
      </Space>
    ),
  });

  baseColumns.push(
    createStatusColumn<Machine>({
      title: t('machines:status'),
      dataIndex: 'vaultStatusTime',
      key: 'status',
      statusMap: {
        online: { icon: <CheckCircleOutlined />, label: t('machines:connected') },
        offline: {
          icon: <DisconnectOutlined />,
          label: t('machines:connectionFailed'),
        },
        unknown: {
          icon: <DisconnectOutlined />,
          label: t('machines:statusUnknown'),
        },
      },
      sorter: createCustomSorter<Machine>((m) => {
        if (!m.vaultStatusTime) return Infinity;
        const statusTime = new Date(`${m.vaultStatusTime}Z`);
        const diffMinutes = (new Date().getTime() - statusTime.getTime()) / 60000;
        return diffMinutes <= 3 ? 0 : 1;
      }),
      renderValue: (_value: unknown, record: Machine) => {
        if (!record.vaultStatusTime) return 'unknown';
        const statusTime = new Date(`${record.vaultStatusTime}Z`);
        const diffMinutes = (new Date().getTime() - statusTime.getTime()) / 60000;
        return diffMinutes <= 3 ? 'online' : 'offline';
      },
    }),
    machineNameColumn
  );

  if (!hasSplitView) {
    baseColumns.push({
      ...createTruncatedColumn<Machine>({
        title: t('machines:team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: 150,
        sorter: createSorter<Machine>('teamName'),
        renderWrapper: (content) => <Tag bordered={false}>{content}</Tag>,
      }),
      responsive: RESPONSIVE_HIDE_XS,
    });
  }

  if (!hasSplitView) {
    if (isExpertMode) {
      baseColumns.push(
        {
          ...createTruncatedColumn<Machine>({
            title: t('machines:region'),
            dataIndex: 'regionName',
            key: 'regionName',
            width: 150,
            sorter: createSorter<Machine>('regionName'),
            renderText: (regionName?: string | null) => regionName ?? '-',
            renderWrapper: (content, fullText) =>
              fullText === '-' ? (
                <Typography.Text>-</Typography.Text>
              ) : (
                <Tag bordered={false}>{content}</Tag>
              ),
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
            renderWrapper: (content) => <Tag bordered={false}>{content}</Tag>,
          }),
          responsive: RESPONSIVE_HIDE_XS,
        }
      );
    } else if (uiMode !== 'simple') {
      baseColumns.push({
        ...createTruncatedColumn<Machine>({
          title: t('bridges.bridge'),
          dataIndex: 'bridgeName',
          key: 'bridgeName',
          width: 150,
          sorter: createSorter<Machine>('bridgeName'),
          renderWrapper: (content) => <Tag bordered={false}>{content}</Tag>,
        }),
        responsive: RESPONSIVE_HIDE_XS,
      });
    }
  }

  if (!hasSplitView && canAssignToCluster) {
    baseColumns.push({
      title: t('machines:assignmentStatus.title'),
      key: 'assignmentStatus',
      width: 180,
      ellipsis: true,
      responsive: RESPONSIVE_HIDE_XS,
      render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />,
    });
  }

  if (!hasSplitView) {
    baseColumns.push({
      title: t('machines:queueItems'),
      dataIndex: 'queueCount',
      key: 'queueCount',
      width: 100,
      align: 'center' as const,
      responsive: RESPONSIVE_HIDE_XS,
      sorter: createSorter<Machine>('queueCount'),
      render: (count: number) => <Badge count={count} showZero />,
    });
  }

  if (showActions) {
    baseColumns.push(
      createActionColumn<Machine>({
        title: t('common:table.actions'),
        renderActions: (record) => (
          <ActionButtonGroup
            buttons={[
              {
                type: 'viewRepositories',
                icon: <FolderOpenOutlined />,
                tooltip: 'machines:viewRepositories',
                onClick: () => onViewRepositories(record),
                variant: 'default',
                testIdSuffix: 'view-repositories',
              },
              {
                type: 'view',
                icon: <EyeOutlined />,
                tooltip: 'common:viewDetails',
                onClick: () => handleRowClick(record),
                variant: 'default',
                testIdSuffix: 'view-details',
              },
              {
                type: 'edit',
                icon: <EditOutlined />,
                tooltip: 'common:actions.edit',
                onClick: () => onEditMachine?.(record),
              },
              {
                type: 'remote',
                icon: <FunctionOutlined />,
                tooltip: 'machines:remote',
                dropdownItems: [
                  {
                    key: 'functions',
                    label: t('machines:runAction'),
                    icon: <FunctionOutlined />,
                    children: [
                      ...machineFunctions
                        .filter((func) => func.showInMenu !== false)
                        .map((func) => ({
                          key: `function-${func.name}`,
                          label: (
                            <Typography.Text title={func.description}>{func.name}</Typography.Text>
                          ),
                          onClick: () => onFunctionsMachine?.(record, func.name),
                        })),
                      { type: 'divider' as const },
                      {
                        key: 'advanced',
                        label: t('machines:advanced'),
                        icon: <FunctionOutlined />,
                        onClick: () => onFunctionsMachine?.(record),
                      },
                    ],
                  },
                  {
                    key: 'test',
                    label: t('machines:connectivityTest'),
                    icon: <WifiOutlined />,
                    onClick: async () => {
                      showMessage('info', t('machines:testingConnection'));
                      const result = await executePingForMachineAndWait(record, {
                        priority: 4,
                        description: 'Connectivity test',
                        addedVia: 'machine-table',
                        timeout: 15000,
                      });
                      if (result.success) {
                        showMessage('success', t('machines:connectionSuccessful'));
                      } else {
                        showMessage('error', result.error ?? t('machines:connectionFailed'));
                      }
                    },
                  },
                  ...(canAssignToCluster
                    ? [
                        {
                          key: 'assignCluster',
                          label: record.cephClusterName
                            ? t('machines:changeClusterAssignment')
                            : t('machines:assignToCluster'),
                          icon: <CloudServerOutlined />,
                          onClick: () => setAssignClusterModal({ open: true, machine: record }),
                        },
                      ]
                    : []),
                ],
              },
              {
                type: 'trace',
                icon: <HistoryOutlined />,
                tooltip: 'machines:trace',
                onClick: () =>
                  setAuditTraceModal({
                    open: true,
                    entityType: 'Machine',
                    entityIdentifier: record.machineName ?? '',
                    entityName: record.machineName ?? undefined,
                  }),
              },
              {
                type: 'delete',
                icon: <DeleteOutlined />,
                tooltip: 'common:actions.delete',
                onClick: () => handleDelete(record),
                danger: true,
              },
              {
                type: 'custom',
                render: (r: Machine) => (
                  <LocalActionsMenu
                    machine={r.machineName ?? ''}
                    teamName={r.teamName ?? undefined}
                  />
                ),
              },
            ]}
            record={record}
            idField="machineName"
            testIdPrefix="machine"
            t={t}
          />
        ),
      })
    );
  }

  return baseColumns;
};
