import React from 'react'
import { Table, Tag, Space, Badge } from 'antd'
import type { ColumnsType } from 'antd/es/table/interface'
import { CloudServerOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell'
import { MachineRepositoryList } from '@/components/resources/MachineRepositoryList'

interface FilterableMachineTableProps {
  machines: Machine[]
  loading?: boolean
  selectedRowKeys?: string[]
  onSelectionChange?: (keys: string[]) => void
  showSelection?: boolean
  expandedRowKeys?: string[]
  onExpandedRowsChange?: (keys: string[]) => void
  refreshKeys?: Record<string, number>
}

export const FilterableMachineTable: React.FC<FilterableMachineTableProps> = ({
  machines,
  loading = false,
  selectedRowKeys = [],
  onSelectionChange,
  showSelection = false,
  expandedRowKeys = [],
  onExpandedRowsChange,
  refreshKeys = {}
}) => {
  const { t } = useTranslation(['machines', 'distributedStorage'])
  
  const columns: ColumnsType<Machine> = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      ellipsis: true,
      sorter: (a: Machine, b: Machine) => a.machineName.localeCompare(b.machineName),
    },
    {
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      ellipsis: true,
      render: (teamName: string) => <Tag color="#8FBC8F">{teamName}</Tag>,
      sorter: (a: Machine, b: Machine) => a.teamName.localeCompare(b.teamName),
    },
    {
      title: t('machines:bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      width: 150,
      ellipsis: true,
      render: (bridgeName: string) => <Tag color="green">{bridgeName}</Tag>,
      sorter: (a: Machine, b: Machine) => a.bridgeName.localeCompare(b.bridgeName),
    },
    {
      title: t('distributedStorage:assignment.status'),
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
      align: 'center' as const,
      sorter: (a: Machine, b: Machine) => a.queueCount - b.queueCount,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: count > 0 ? '#52c41a' : '#d9d9d9' }} />
      ),
    },
  ]
  
  const rowSelection = showSelection ? {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      onSelectionChange?.(newSelectedRowKeys as string[])
    },
  } : undefined
  
  return (
    <Table
      columns={columns}
      dataSource={machines}
      rowKey="machineName"
      loading={loading}
      rowSelection={rowSelection}
      data-testid="ds-machines-table"
      expandable={{
        expandedRowKeys,
        onExpandedRowsChange: (keys) => onExpandedRowsChange?.(keys as string[]),
        expandedRowRender: (machine) => (
          <MachineRepositoryList
            machine={machine}
            refreshKey={refreshKeys[machine.machineName]}
          />
        ),
        rowExpandable: (machine) => machine.queueCount > 0,
      }}
      scroll={{ x: 800 }}
      pagination={{
        showSizeChanger: true,
        showTotal: (total, range) => 
          t('machines:showingMachines', { start: range[0], end: range[1], total }),
      }}
    />
  )
}