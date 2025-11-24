import { Space, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table/interface'
import { TFunction } from 'i18next'
import { createSorter, createCustomSorter } from '@/core'
import type { Machine } from '@/types'
import MachineAssignmentStatusCell from '../MachineAssignmentStatusCell'
import { LocalActionsMenu } from '../LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup'
import {
  EditOutlined,
  FunctionOutlined,
  WifiOutlined,
  CloudServerOutlined,
  HistoryOutlined,
  DeleteOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  DisconnectOutlined,
} from '@/utils/optimizedIcons'
import type { usePingFunction } from '@/services/pingService'
import { StatusIcon, MachineNameIcon, StyledTag, StyledBadge } from './styles'

type ExecutePingForMachineAndWait = ReturnType<typeof usePingFunction>['executePingForMachineAndWait']

export interface MachineFunctionAction {
  name?: string
  description?: string
  showInMenu?: boolean
}

interface MachineColumnsParams {
  t: TFunction
  isExpertMode: boolean
  uiMode: string
  showActions: boolean
  hasSplitView: boolean
  canAssignToCluster: boolean
  onEditMachine?: (machine: Machine) => void
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void
  handleDelete: (machine: Machine) => void
  handleRowClick: (machine: Machine) => void
  executePingForMachineAndWait: ExecutePingForMachineAndWait
  setAssignClusterModal: (state: {
    open: boolean
    machine: Machine | null
  }) => void
  setAuditTraceModal: (state: {
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }) => void
  machineFunctions: MachineFunctionAction[]
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
  executePingForMachineAndWait,
  setAssignClusterModal,
  setAuditTraceModal,
  machineFunctions,
}: MachineColumnsParams): ColumnsType<Machine> => {
  const baseColumns: ColumnsType<Machine> = []

  baseColumns.push(
    {
      title: t('machines:status'),
      dataIndex: 'vaultStatusTime',
      key: 'status',
      width: 100,
      align: 'center',
      sorter: createCustomSorter<Machine>((m) => {
        if (!m.vaultStatusTime) return Infinity
        const statusTime = new Date(m.vaultStatusTime + 'Z')
        const now = new Date()
        const diffMinutes = (now.getTime() - statusTime.getTime()) / 60000
        return diffMinutes <= 3 ? 0 : 1
      }),
      render: (_: unknown, record: Machine) => {
        if (!record.vaultStatusTime) {
          return (
            <Tooltip title={t('machines:statusUnknown')}>
              <StatusIcon $status="unknown">
                <DisconnectOutlined />
              </StatusIcon>
            </Tooltip>
          )
        }

        const statusTime = new Date(record.vaultStatusTime + 'Z')
        const now = new Date()
        const diffMinutes = (now.getTime() - statusTime.getTime()) / 60000
        const isOnline = diffMinutes <= 3

        return (
          <Tooltip title={isOnline ? t('machines:connected') : t('machines:connectionFailed')}>
            <StatusIcon $status={isOnline ? 'online' : 'offline'}>
              {isOnline ? <CheckCircleOutlined /> : <DisconnectOutlined />}
            </StatusIcon>
          </Tooltip>
        )
      },
    },
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      ellipsis: true,
      sorter: createSorter<Machine>('machineName'),
      render: (name: string) => (
        <Space>
          <MachineNameIcon />
          <strong>{name}</strong>
        </Space>
      ),
    },
  )

  if (!hasSplitView) {
    baseColumns.push({
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      ellipsis: true,
      sorter: createSorter<Machine>('teamName'),
      render: (teamName: string) => <StyledTag $variant="team">{teamName}</StyledTag>,
    })
  }

  if (!hasSplitView) {
    if (isExpertMode) {
      baseColumns.push(
        {
          title: t('machines:region'),
          dataIndex: 'regionName',
          key: 'regionName',
          width: 150,
          ellipsis: true,
          sorter: createSorter<Machine>('regionName'),
          render: (regionName: string) =>
            regionName ? <StyledTag $variant="region">{regionName}</StyledTag> : '-',
        },
        {
          title: t('machines:bridge'),
          dataIndex: 'bridgeName',
          key: 'bridgeName',
          width: 150,
          ellipsis: true,
          sorter: createSorter<Machine>('bridgeName'),
          render: (bridgeName: string) => <StyledTag $variant="bridge">{bridgeName}</StyledTag>,
        },
      )
    } else if (uiMode !== 'simple') {
      baseColumns.push({
        title: t('bridges.bridge'),
        dataIndex: 'bridgeName',
        key: 'bridgeName',
        width: 150,
        ellipsis: true,
        sorter: createSorter<Machine>('bridgeName'),
        render: (bridge: string) => <StyledTag $variant="bridge">{bridge}</StyledTag>,
      })
    }
  }

  if (!hasSplitView && canAssignToCluster) {
    baseColumns.push({
      title: t('machines:assignmentStatus.title'),
      key: 'assignmentStatus',
      width: 180,
      ellipsis: true,
      render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />,
    })
  }

  if (!hasSplitView) {
    baseColumns.push({
      title: t('machines:queueItems'),
      dataIndex: 'queueCount',
      key: 'queueCount',
      width: 100,
      align: 'center' as const,
      sorter: createSorter<Machine>('queueCount'),
      render: (count: number) => (
        <StyledBadge $isPositive={count > 0} count={count} showZero />
      ),
    })
  }

  if (showActions) {
    baseColumns.push({
      title: t('common:table.actions'),
      key: 'actions',
      width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH,
      render: (_: unknown, record: Machine) => (
        <ActionButtonGroup
          buttons={[
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
                      .filter((func) => func?.showInMenu !== false)
                      .map((func) => ({
                        key: `function-${func?.name || 'unknown'}`,
                        label: <span title={func?.description || ''}>{func?.name || 'Unknown'}</span>,
                        onClick: () => onFunctionsMachine?.(record, func?.name),
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
                    showMessage('info', t('machines:testingConnection'))
                    const result = await executePingForMachineAndWait(record, {
                      priority: 4,
                      description: 'Connectivity test',
                      addedVia: 'machine-table',
                      timeout: 15000,
                    })
                    if (result.success) {
                      showMessage('success', t('machines:connectionSuccessful'))
                    } else {
                      showMessage('error', result.error || t('machines:connectionFailed'))
                    }
                  },
                },
                ...(canAssignToCluster
                  ? [
                      {
                        key: 'assignCluster',
                        label: record.distributedStorageClusterName
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
                  entityIdentifier: record.machineName,
                  entityName: record.machineName,
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
              render: (r: Machine) => <LocalActionsMenu machine={r.machineName} teamName={r.teamName} />,
            },
          ]}
          record={record}
          idField="machineName"
          testIdPrefix="machine"
          t={t}
        />
      ),
    })
  }

  return baseColumns
}
