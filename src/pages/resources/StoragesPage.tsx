import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, Select, Progress } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, CloudOutlined, SettingOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { useStorage, useCreateStorage, useDeleteStorage, useUpdateStorageVault, Storage } from '@/api/queries/storage'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { createStorageSchema, CreateStorageForm } from '@/utils/validation'

const { Title } = Typography

const StoragesPage: React.FC = () => {
  const [selectedTeam, setSelectedTeam] = useState<string>('')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    storage?: Storage
  }>({ open: false })

  const { data: dropdownData } = useDropdownData()
  const { data: storageList, isLoading } = useStorage(selectedTeam)
  const createStorageMutation = useCreateStorage()
  const deleteStorageMutation = useDeleteStorage()
  const updateVaultMutation = useUpdateStorageVault()

  const form = useForm<CreateStorageForm>({
    resolver: zodResolver(createStorageSchema) as any,
    defaultValues: {
      teamName: '',
      storageName: '',
      storageVault: '{}',
    },
  })

  const handleCreateStorage = async (data: CreateStorageForm) => {
    try {
      await createStorageMutation.mutateAsync(data)
      setIsCreateModalOpen(false)
      form.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteStorage = async (storage: Storage) => {
    try {
      await deleteStorageMutation.mutateAsync({
        teamName: storage.teamName,
        storageName: storage.storageName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.storage) return

    await updateVaultMutation.mutateAsync({
      teamName: vaultModalConfig.storage.teamName,
      storageName: vaultModalConfig.storage.storageName,
      storageVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const getUsagePercent = (used: string, capacity: string) => {
    try {
      const usedNum = parseFloat(used) || 0
      const capacityNum = parseFloat(capacity) || 100
      return Math.round((usedNum / capacityNum) * 100)
    } catch {
      return 0
    }
  }

  const getUsageColor = (percent: number) => {
    if (percent >= 90) return '#ff4d4f'
    if (percent >= 70) return '#faad14'
    return '#52c41a'
  }

  const columns = [
    {
      title: 'Storage Name',
      dataIndex: 'storageName',
      key: 'storageName',
      render: (text: string) => (
        <Space>
          <CloudOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Team',
      dataIndex: 'teamName',
      key: 'teamName',
      render: (text: string) => <Tag color="green">{text}</Tag>,
    },
    {
      title: 'Type',
      dataIndex: 'storageType',
      key: 'storageType',
      width: 100,
      render: (type: string) => <Tag>{type || 'Standard'}</Tag>,
    },
    {
      title: 'Usage',
      key: 'usage',
      width: 200,
      render: (_: any, record: Storage) => {
        const percent = getUsagePercent(record.used, record.capacity)
        return (
          <div style={{ width: '100%' }}>
            <Progress 
              percent={percent} 
              size="small"
              strokeColor={getUsageColor(percent)}
              format={() => `${record.used || '0'} / ${record.capacity || 'N/A'}`}
            />
          </div>
        )
      },
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
      render: (_: any, record: Storage) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, storage: record })}
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
            title="Delete Storage"
            description={`Are you sure you want to delete storage "${record.storageName}"? This action cannot be undone.`}
            onConfirm={() => handleDeleteStorage(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteStorageMutation.isPending}
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
      name: 'teamName',
      label: 'Team',
      placeholder: 'Select team',
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'storageName',
      label: 'Storage Name',
      placeholder: 'Enter storage name',
      required: true,
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Storage</Title>
        <Space>
          <Select
            placeholder="Select a team"
            style={{ width: 200 }}
            onChange={setSelectedTeam}
            value={selectedTeam}
            allowClear
            options={dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || []}
          />
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => {
              form.setValue('teamName', selectedTeam)
              setIsCreateModalOpen(true)
            }}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
            disabled={!selectedTeam}
          >
            Create Storage
          </Button>
        </Space>
      </div>
      
      <ResourceListView
        title={
          <Title level={4} style={{ margin: 0 }}>
            {selectedTeam ? `Storage in ${selectedTeam}` : 'Select a team to view storage'}
          </Title>
        }
        loading={isLoading}
        data={storageList}
        columns={columns}
        rowKey="storageName"
        searchPlaceholder="Search storage..."
        emptyText={!selectedTeam ? "Please select a team to view storage" : undefined}
      />

      <Modal
        title="Create Storage"
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
          onSubmit={handleCreateStorage}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createStorageMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleUpdateVault}
        title={`Configure Vault - ${vaultModalConfig.storage?.storageName}`}
        initialVault="{}"
        initialVersion={vaultModalConfig.storage?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default StoragesPage