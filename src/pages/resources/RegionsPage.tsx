import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, GlobalOutlined, ApiOutlined, SettingOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { useRegions, useCreateRegion, useDeleteRegion, useUpdateRegionVault, Region } from '@/api/queries/regions'
import { createRegionSchema, CreateRegionForm } from '@/utils/validation'

const { Title } = Typography

const RegionsPage: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    region?: Region
  }>({ open: false })

  const { data: regions, isLoading } = useRegions()
  const createRegionMutation = useCreateRegion()
  const deleteRegionMutation = useDeleteRegion()
  const updateVaultMutation = useUpdateRegionVault()

  const form = useForm<CreateRegionForm>({
    resolver: zodResolver(createRegionSchema) as any,
    defaultValues: {
      regionName: '',
      regionVault: '{}',
    },
  })

  const handleCreateRegion = async (data: CreateRegionForm) => {
    try {
      await createRegionMutation.mutateAsync(data)
      setIsCreateModalOpen(false)
      form.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteRegion = async (regionName: string) => {
    try {
      await deleteRegionMutation.mutateAsync(regionName)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.region) return

    await updateVaultMutation.mutateAsync({
      regionName: vaultModalConfig.region.regionName,
      regionVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const columns = [
    {
      title: 'Region Name',
      dataIndex: 'regionName',
      key: 'regionName',
      render: (text: string) => (
        <Space>
          <GlobalOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Bridges',
      dataIndex: 'bridgeCount',
      key: 'bridgeCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <ApiOutlined />
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
      render: (_: any, record: Region) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, region: record })}
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
            title="Delete Region"
            description={`Are you sure you want to delete region "${record.regionName}"? This will remove all bridges in the region.`}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRegionMutation.isPending}
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
      label: 'Region Name',
      placeholder: 'Enter region name',
      required: true,
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Regions & Infrastructure</Title>
      </div>
      
      <ResourceListView
        title={<Title level={4} style={{ margin: 0 }}>Regions</Title>}
        loading={isLoading}
        data={regions}
        columns={columns}
        rowKey="regionName"
        searchPlaceholder="Search regions..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            Create Region
          </Button>
        }
      />

      <Modal
        title="Create Region"
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
          onSubmit={handleCreateRegion}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createRegionMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleUpdateVault}
        title={`Configure Vault - ${vaultModalConfig.region?.regionName}`}
        initialVault="{}"
        initialVersion={vaultModalConfig.region?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default RegionsPage