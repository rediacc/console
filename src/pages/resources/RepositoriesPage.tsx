import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, Select } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, DatabaseOutlined, SettingOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { useRepositories, useCreateRepository, useDeleteRepository, useUpdateRepositoryVault, Repository } from '@/api/queries/repositories'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { createRepositorySchema, CreateRepositoryForm } from '@/utils/validation'

const { Title } = Typography

const RepositoriesPage: React.FC = () => {
  const [selectedTeam, setSelectedTeam] = useState<string>('')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    repository?: Repository
  }>({ open: false })

  const { data: dropdownData } = useDropdownData()
  const { data: repositories, isLoading } = useRepositories(selectedTeam)
  const createRepositoryMutation = useCreateRepository()
  const deleteRepositoryMutation = useDeleteRepository()
  const updateVaultMutation = useUpdateRepositoryVault()

  const form = useForm<CreateRepositoryForm>({
    resolver: zodResolver(createRepositorySchema) as any,
    defaultValues: {
      teamName: '',
      repoName: '',
      repoVault: '{}',
    },
  })

  const handleCreateRepository = async (data: CreateRepositoryForm) => {
    try {
      await createRepositoryMutation.mutateAsync(data)
      setIsCreateModalOpen(false)
      form.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteRepository = async (repository: Repository) => {
    try {
      await deleteRepositoryMutation.mutateAsync({
        teamName: repository.teamName,
        repoName: repository.repoName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.repository) return

    await updateVaultMutation.mutateAsync({
      teamName: vaultModalConfig.repository.teamName,
      repoName: vaultModalConfig.repository.repoName,
      repoVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'active':
        return 'success'
      case 'inactive':
        return 'default'
      case 'error':
        return 'error'
      default:
        return 'default'
    }
  }

  const columns = [
    {
      title: 'Repository Name',
      dataIndex: 'repoName',
      key: 'repoName',
      render: (text: string) => (
        <Space>
          <DatabaseOutlined style={{ color: '#556b2f' }} />
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
      title: 'Size',
      dataIndex: 'repoSize',
      key: 'repoSize',
      width: 100,
      render: (size: string) => size || 'N/A',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>
          {status || 'Active'}
        </Tag>
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
      render: (_: any, record: Repository) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, repository: record })}
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
            title="Delete Repository"
            description={`Are you sure you want to delete repository "${record.repoName}"? This action cannot be undone.`}
            onConfirm={() => handleDeleteRepository(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRepositoryMutation.isPending}
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
      name: 'repoName',
      label: 'Repository Name',
      placeholder: 'Enter repository name',
      required: true,
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Repositories</Title>
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
            Create Repository
          </Button>
        </Space>
      </div>
      
      <ResourceListView
        title={
          <Title level={4} style={{ margin: 0 }}>
            {selectedTeam ? `Repositories in ${selectedTeam}` : 'Select a team to view repositories'}
          </Title>
        }
        loading={isLoading}
        data={repositories}
        columns={columns}
        rowKey="repoName"
        searchPlaceholder="Search repositories..."
        emptyText={!selectedTeam ? "Please select a team to view repositories" : undefined}
      />

      <Modal
        title="Create Repository"
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
          onSubmit={handleCreateRepository}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createRepositoryMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleUpdateVault}
        title={`Configure Vault - ${vaultModalConfig.repository?.repoName}`}
        initialVault="{}"
        initialVersion={vaultModalConfig.repository?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default RepositoriesPage