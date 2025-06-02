import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, Select } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, CloudServerOutlined, ApiOutlined, SettingOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { useMachines, useCreateMachine, useDeleteMachine, useUpdateMachineVault, Machine } from '@/api/queries/machines'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { createMachineSchema, CreateMachineForm } from '@/utils/validation'

const { Title } = Typography

const MachinesPage: React.FC = () => {
  const [selectedTeam, setSelectedTeam] = useState<string>('')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    machine?: Machine
  }>({ open: false })

  const { data: dropdownData } = useDropdownData()
  const { data: machines, isLoading } = useMachines(selectedTeam)
  const createMachineMutation = useCreateMachine()
  const deleteMachineMutation = useDeleteMachine()
  const updateVaultMutation = useUpdateMachineVault()

  const form = useForm<CreateMachineForm>({
    resolver: zodResolver(createMachineSchema) as any,
    defaultValues: {
      teamName: '',
      bridgeName: '',
      machineName: '',
      machineVault: '{}',
    },
  })

  const handleCreateMachine = async (data: CreateMachineForm) => {
    try {
      await createMachineMutation.mutateAsync(data)
      setIsCreateModalOpen(false)
      form.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteMachine = async (machine: Machine) => {
    try {
      await deleteMachineMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.machine) return

    await updateVaultMutation.mutateAsync({
      teamName: vaultModalConfig.machine.teamName,
      machineName: vaultModalConfig.machine.machineName,
      machineVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const columns = [
    {
      title: 'Machine Name',
      dataIndex: 'machineName',
      key: 'machineName',
      render: (text: string) => (
        <Space>
          <CloudServerOutlined style={{ color: '#556b2f' }} />
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
      title: 'Bridge',
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (text: string) => (
        <Space>
          <ApiOutlined />
          <span>{text}</span>
        </Space>
      ),
    },
    {
      title: 'Queue Items',
      dataIndex: 'queueCount',
      key: 'queueCount',
      width: 120,
      render: (count: number) => <Tag color={count > 0 ? 'processing' : 'default'}>{count}</Tag>,
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
      render: (_: any, record: Machine) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, machine: record })}
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
            title="Delete Machine"
            description={`Are you sure you want to delete machine "${record.machineName}"? This will remove all queue items for this machine.`}
            onConfirm={() => handleDeleteMachine(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteMachineMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Get bridges for all regions
  const allBridges = dropdownData?.bridgesByRegion?.flatMap(r => 
    r.bridges.map(b => ({ 
      value: b.value, 
      label: `${b.label} (${r.regionName})`,
      group: r.regionName 
    }))
  ) || []

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
      name: 'bridgeName',
      label: 'Bridge',
      placeholder: 'Select bridge',
      required: true,
      type: 'select' as const,
      options: allBridges,
    },
    {
      name: 'machineName',
      label: 'Machine Name',
      placeholder: 'Enter machine name',
      required: true,
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Machines</Title>
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
            Create Machine
          </Button>
        </Space>
      </div>
      
      <ResourceListView
        title={
          <Title level={4} style={{ margin: 0 }}>
            {selectedTeam ? `Machines in ${selectedTeam}` : 'Select a team to view machines'}
          </Title>
        }
        loading={isLoading}
        data={machines || []}
        columns={columns}
        rowKey="machineName"
        searchPlaceholder="Search machines..."
        emptyText={!selectedTeam ? "Please select a team to view machines" : undefined}
      />

      <Modal
        title="Create Machine"
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
          onSubmit={handleCreateMachine}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createMachineMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleUpdateVault}
        title={`Configure Vault - ${vaultModalConfig.machine?.machineName}`}
        initialVault="{}"
        initialVersion={vaultModalConfig.machine?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default MachinesPage