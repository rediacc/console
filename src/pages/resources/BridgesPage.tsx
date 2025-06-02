import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, Select } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined, CloudServerOutlined, SettingOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { useBridges, useCreateBridge, useDeleteBridge, useUpdateBridgeVault, Bridge } from '@/api/queries/bridges'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { createBridgeSchema, CreateBridgeForm } from '@/utils/validation'

const { Title } = Typography

const BridgesPage: React.FC = () => {
  const [selectedRegion, setSelectedRegion] = useState<string>('')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    bridge?: Bridge
  }>({ open: false })

  const { data: dropdownData } = useDropdownData()
  const { data: bridges, isLoading } = useBridges(selectedRegion)
  const createBridgeMutation = useCreateBridge()
  const deleteBridgeMutation = useDeleteBridge()
  const updateVaultMutation = useUpdateBridgeVault()

  const form = useForm<CreateBridgeForm>({
    resolver: zodResolver(createBridgeSchema) as any,
    defaultValues: {
      regionName: '',
      bridgeName: '',
      bridgeVault: '{}',
    },
  })

  const handleCreateBridge = async (data: CreateBridgeForm) => {
    try {
      await createBridgeMutation.mutateAsync(data)
      setIsCreateModalOpen(false)
      form.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteBridge = async (bridge: Bridge) => {
    try {
      await deleteBridgeMutation.mutateAsync({
        regionName: bridge.regionName,
        bridgeName: bridge.bridgeName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.bridge) return

    await updateVaultMutation.mutateAsync({
      regionName: vaultModalConfig.bridge.regionName,
      bridgeName: vaultModalConfig.bridge.bridgeName,
      bridgeVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const columns = [
    {
      title: 'Bridge Name',
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (text: string) => (
        <Space>
          <ApiOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Region',
      dataIndex: 'regionName',
      key: 'regionName',
      render: (text: string) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: 'Machines',
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <CloudServerOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Bridge) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, bridge: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Bridge"
            description={`Are you sure you want to delete bridge "${record.bridgeName}"? This will affect all machines using this bridge.`}
            onConfirm={() => handleDeleteBridge(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteBridgeMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const formFields = [
    {
      name: 'regionName',
      label: 'Region',
      placeholder: 'Select region',
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map(r => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: 'Bridge Name',
      placeholder: 'Enter bridge name',
      required: true,
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Bridges</Title>
        <Space>
          <Select
            placeholder="Select a region"
            style={{ width: 200 }}
            onChange={setSelectedRegion}
            value={selectedRegion}
            allowClear
            options={dropdownData?.regions?.map(r => ({ value: r.value, label: r.label })) || []}
          />
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => {
              form.setValue('regionName', selectedRegion)
              setIsCreateModalOpen(true)
            }}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
            disabled={!selectedRegion}
          >
            Create Bridge
          </Button>
        </Space>
      </div>
      
      <ResourceListView
        title={
          <Title level={4} style={{ margin: 0 }}>
            {selectedRegion ? `Bridges in ${selectedRegion}` : 'Select a region to view bridges'}
          </Title>
        }
        loading={isLoading}
        data={bridges}
        columns={columns}
        rowKey="bridgeName"
        searchPlaceholder="Search bridges..."
        emptyText={!selectedRegion ? "Please select a region to view bridges" : undefined}
      />

      <Modal
        title="Create Bridge"
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false)
          form.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={form}
          fields={formFields}
          onSubmit={handleCreateBridge}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createBridgeMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleUpdateVault}
        title={`Configure Vault - ${vaultModalConfig.bridge?.bridgeName}`}
        initialVault="{}"
        initialVersion={vaultModalConfig.bridge?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default BridgesPage