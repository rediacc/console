import React, { useState, useCallback } from 'react'
import { Card, Table, Button, Space, Tag, Empty, Spin, Input, Row, Col, Statistic, message, Modal, Typography, Alert } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { 
  CloudServerOutlined, 
  DesktopOutlined, 
  PlusOutlined, 
  DeleteOutlined,
  ReloadOutlined,
  SearchOutlined,
  TeamOutlined,
  CopyOutlined,
  ExportOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { 
  useGetCloneMachines,
  useGetAvailableMachinesForClone,
  useUpdateCloneMachineAssignments,
  useUpdateCloneMachineRemovals,
  type DistributedStorageRbdClone,
  type DistributedStorageRbdSnapshot,
  type DistributedStorageRbdImage,
  type DistributedStoragePool,
  type CloneMachine
} from '@/api/queries/distributedStorage'
import { AvailableMachinesSelector } from '@/components/resources/AvailableMachinesSelector'
import { MachineExclusivityWarning } from '@/components/distributedStorage/MachineExclusivityWarning'
import { showMessage } from '@/utils/messages'

const { Search } = Input
const { Text, Title } = Typography

interface CloneMachineManagerProps {
  clone: DistributedStorageRbdClone
  snapshot: DistributedStorageRbdSnapshot
  image: DistributedStorageRbdImage
  pool: DistributedStoragePool
  teamName: string
}

export const CloneMachineManager: React.FC<CloneMachineManagerProps> = ({
  clone,
  snapshot,
  image,
  pool,
  teamName
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines', 'common'])
  const [searchText, setSearchText] = useState('')
  const [selectedMachines, setSelectedMachines] = useState<string[]>([])
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [selectedNewMachines, setSelectedNewMachines] = useState<string[]>([])
  const [isAdding, setIsAdding] = useState(false)
  const [isRemoving, setIsRemoving] = useState(false)
  
  // Fetch assigned machines
  const { 
    data: assignedMachines = [], 
    isLoading: loadingMachines, 
    refetch: refetchMachines 
  } = useGetCloneMachines(
    clone.cloneName,
    snapshot.snapshotName,
    image.imageName,
    pool.poolName,
    teamName,
    true
  )
  
  // Fetch available machines
  const { 
    data: availableMachines = [], 
    isLoading: loadingAvailable 
  } = useGetAvailableMachinesForClone(teamName, addModalOpen)
  
  // Mutations
  const assignMutation = useUpdateCloneMachineAssignments()
  const removeMutation = useUpdateCloneMachineRemovals()
  
  // Filter machines based on search
  const filteredMachines = assignedMachines.filter(machine =>
    machine.machineName.toLowerCase().includes(searchText.toLowerCase()) ||
    machine.bridgeName.toLowerCase().includes(searchText.toLowerCase())
  )
  
  const handleAddMachines = () => {
    setAddModalOpen(true)
    setSelectedNewMachines([])
  }
  
  const handleAssignMachines = async () => {
    if (selectedNewMachines.length === 0) {
      message.warning(t('machines:validation.noMachinesSelected'))
      return
    }
    
    setIsAdding(true)
    try {
      await assignMutation.mutateAsync({
        teamName,
        poolName: pool.poolName,
        imageName: image.imageName,
        snapshotName: snapshot.snapshotName,
        cloneName: clone.cloneName,
        machineNames: selectedNewMachines.join(',')
      })
      
      showMessage('success', t('distributedStorage:clones.machinesAssignedSuccess'))
      setAddModalOpen(false)
      refetchMachines()
    } catch (error) {
      // Error handled by mutation
    } finally {
      setIsAdding(false)
    }
  }
  
  const handleRemoveMachines = async () => {
    if (selectedMachines.length === 0) {
      message.warning(t('machines:validation.noMachinesSelected'))
      return
    }
    
    Modal.confirm({
      title: t('machines:removeFromClone'),
      content: t('machines:removeFromClusterWarning', { count: selectedMachines.length }),
      okText: t('common:actions.remove'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: async () => {
        setIsRemoving(true)
        try {
          await removeMutation.mutateAsync({
            teamName,
            poolName: pool.poolName,
            imageName: image.imageName,
            snapshotName: snapshot.snapshotName,
            cloneName: clone.cloneName,
            machineNames: selectedMachines.join(',')
          })
          
          showMessage('success', t('distributedStorage:clones.machinesRemovedSuccess'))
          setSelectedMachines([])
          refetchMachines()
        } catch (error) {
          // Error handled by mutation
        } finally {
          setIsRemoving(false)
        }
      }
    })
  }
  
  const handleExport = () => {
    const csvContent = [
      ['Machine Name', 'Bridge Name', 'Assignment ID'],
      ...assignedMachines.map(m => [m.machineName, m.bridgeName, m.assignmentId])
    ].map(row => row.join(',')).join('\n')
    
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `clone-${clone.cloneName}-machines.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    
    message.success(t('common:actions.exportSuccess'))
  }
  
  const columns: ColumnsType<CloneMachine> = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string) => (
        <Space>
          <DesktopOutlined />
          <Text strong>{name}</Text>
        </Space>
      ),
      sorter: (a, b) => a.machineName.localeCompare(b.machineName),
    },
    {
      title: t('machines:bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (bridge: string) => <Tag color="green">{bridge}</Tag>,
      sorter: (a, b) => a.bridgeName.localeCompare(b.bridgeName),
    },
    {
      title: t('machines:assignmentStatus.title'),
      key: 'status',
      render: () => (
        <Tag color="orange" icon={<CopyOutlined />}>
          {t('machines:assignmentStatus.clone')}
        </Tag>
      ),
    },
  ]
  
  const rowSelection = {
    selectedRowKeys: selectedMachines,
    onChange: (selectedRowKeys: React.Key[]) => {
      setSelectedMachines(selectedRowKeys as string[])
    },
  }
  
  return (
    <Card>
      {/* Header */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={16}>
          <Space direction="vertical" size="small">
            <Title level={4} style={{ margin: 0 }}>
              <Space>
                <CopyOutlined />
                {t('distributedStorage:clones.clone')}: {clone.cloneName}
              </Space>
            </Title>
            <Text type="secondary">
              {t('distributedStorage:pools.pool')}: {pool.poolName} | 
              {t('distributedStorage:images.image')}: {image.imageName} | 
              {t('distributedStorage:snapshots.snapshot')}: {snapshot.snapshotName}
            </Text>
          </Space>
        </Col>
        <Col span={8}>
          <Row gutter={16}>
            <Col span={12}>
              <Statistic
                title={t('machines:totalMachines')}
                value={assignedMachines.length}
                prefix={<TeamOutlined />}
              />
            </Col>
            <Col span={12}>
              <Statistic
                title={t('machines:bulkActions.selected')}
                value={selectedMachines.length}
                valueStyle={{ color: selectedMachines.length > 0 ? '#1890ff' : undefined }}
              />
            </Col>
          </Row>
        </Col>
      </Row>
      
      {/* Toolbar */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col flex="auto">
          <Space wrap>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddMachines}
            >
              {t('machines:assignToClone')}
            </Button>
            {selectedMachines.length > 0 && (
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={handleRemoveMachines}
                loading={isRemoving}
              >
                {t('machines:removeFromClone')} ({selectedMachines.length})
              </Button>
            )}
            <Button
              icon={<ReloadOutlined />}
              onClick={() => refetchMachines()}
            >
              {t('common:actions.refresh')}
            </Button>
            <Button
              icon={<ExportOutlined />}
              onClick={handleExport}
              disabled={assignedMachines.length === 0}
            >
              {t('common:actions.export')}
            </Button>
          </Space>
        </Col>
        <Col>
          <Search
            placeholder={t('machines:searchPlaceholder')}
            allowClear
            enterButton={<SearchOutlined />}
            size="middle"
            onSearch={setSearchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 300 }}
          />
        </Col>
      </Row>
      
      {/* Info Alert */}
      <MachineExclusivityWarning
        type="clone"
        style={{ marginBottom: 16 }}
      />
      
      {/* Table */}
      {loadingMachines ? (
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" />
        </div>
      ) : assignedMachines.length === 0 ? (
        <Empty
          description={t('distributedStorage:clones.noMachinesAssigned')}
          style={{ marginTop: 48 }}
        >
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAddMachines}>
            {t('distributedStorage:clones.assignMachines')}
          </Button>
        </Empty>
      ) : (
        <Table
          rowSelection={rowSelection}
          columns={columns}
          dataSource={filteredMachines}
          rowKey="machineName"
          loading={loadingMachines}
          pagination={{
            showSizeChanger: true,
            showTotal: (total, range) => t('common:table.showingRecords', { 
              start: range[0], 
              end: range[1], 
              total 
            }),
          }}
        />
      )}
      
      {/* Add Machines Modal */}
      <Modal
        title={
          <Space>
            <TeamOutlined />
            {t('distributedStorage:clones.assignMachines')}
          </Space>
        }
        open={addModalOpen}
        onCancel={() => setAddModalOpen(false)}
        onOk={handleAssignMachines}
        okText={t('machines:assignToClone')}
        cancelText={t('common:actions.cancel')}
        confirmLoading={isAdding}
        okButtonProps={{ disabled: selectedNewMachines.length === 0 }}
        width={700}
      >
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            message={t('distributedStorage:clones.assignMachinesInfo')}
            type="info"
            showIcon
          />
          
          {loadingAvailable ? (
            <div style={{ textAlign: 'center', padding: '50px 0' }}>
              <Spin />
            </div>
          ) : availableMachines.length === 0 ? (
            <Empty description={t('machines:noAvailableMachinesForClone')} />
          ) : (
            <AvailableMachinesSelector
              availableMachines={availableMachines}
              selectedMachines={selectedNewMachines}
              onSelectionChange={setSelectedNewMachines}
              teamName={teamName}
            />
          )}
          
          {selectedNewMachines.length > 0 && (
            <Tag color="blue">
              {t('machines:bulkOperations.selectedCount', { count: selectedNewMachines.length })}
            </Tag>
          )}
        </Space>
      </Modal>
    </Card>
  )
}