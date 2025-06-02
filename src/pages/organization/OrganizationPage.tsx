import React, { useState } from 'react'
import { Card, Tabs, Button, Space, Modal, Popconfirm, Tag, Typography, Form, Input } from 'antd'
import { 
  TeamOutlined, 
  GlobalOutlined, 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  UserOutlined,
  ApiOutlined,
  SettingOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'

// Team queries
import { useTeams, useCreateTeam, useDeleteTeam, Team } from '@/api/queries/teams'

// Region queries
import { 
  useRegions, 
  useCreateRegion, 
  useDeleteRegion, 
  useUpdateRegionVault, 
  Region 
} from '@/api/queries/regions'

import { createRegionSchema, CreateRegionForm } from '@/utils/validation'

const { Title } = Typography

const OrganizationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('teams')
  
  // Team state
  const [isCreateTeamModalOpen, setIsCreateTeamModalOpen] = useState(false)
  const [teamForm] = Form.useForm()
  
  // Region state
  const [isCreateRegionModalOpen, setIsCreateRegionModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    region?: Region
  }>({ open: false })

  // Team hooks
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const createTeamMutation = useCreateTeam()
  const deleteTeamMutation = useDeleteTeam()

  // Region hooks
  const { data: regions = [], isLoading: regionsLoading } = useRegions()
  const createRegionMutation = useCreateRegion()
  const deleteRegionMutation = useDeleteRegion()
  const updateVaultMutation = useUpdateRegionVault()

  // Region form
  const regionForm = useForm<CreateRegionForm>({
    resolver: zodResolver(createRegionSchema) as any,
    defaultValues: {
      regionName: '',
      regionVault: '{}',
    },
  })

  // Team handlers
  const handleCreateTeam = async (values: { teamName: string }) => {
    try {
      await createTeamMutation.mutateAsync(values)
      setIsCreateTeamModalOpen(false)
      teamForm.resetFields()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteTeam = async (teamName: string) => {
    try {
      await deleteTeamMutation.mutateAsync(teamName)
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Region handlers
  const handleCreateRegion = async (data: CreateRegionForm) => {
    try {
      await createRegionMutation.mutateAsync(data)
      setIsCreateRegionModalOpen(false)
      regionForm.reset()
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

  // Team columns
  const teamColumns = [
    {
      title: 'Team Name',
      dataIndex: 'teamName',
      key: 'teamName',
      render: (text: string) => (
        <Space>
          <TeamOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Members',
      dataIndex: 'memberCount',
      key: 'memberCount',
      width: 100,
      render: (count: number) => (
        <Space>
          <UserOutlined />
          {count}
        </Space>
      ),
    },
    {
      title: 'Machines',
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 100,
    },
    {
      title: 'Repositories',
      dataIndex: 'repoCount',
      key: 'repoCount',
      width: 120,
    },
    {
      title: 'Storage',
      dataIndex: 'storageCount',
      key: 'storageCount',
      width: 100,
    },
    {
      title: 'Schedules',
      dataIndex: 'scheduleCount',
      key: 'scheduleCount',
      width: 100,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_: any, record: Team) => (
        <Space>
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
            title="Delete Team"
            description={`Are you sure you want to delete team "${record.teamName}"? This will remove all resources in the team.`}
            onConfirm={() => handleDeleteTeam(record.teamName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteTeamMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Region columns
  const regionColumns = [
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

  const regionFormFields = [
    {
      name: 'regionName',
      label: 'Region Name',
      placeholder: 'Enter region name',
      required: true,
    },
  ]

  const tabItems = [
    {
      key: 'teams',
      label: (
        <span>
          <TeamOutlined />
          Teams
        </span>
      ),
      children: (
        <ResourceListView
          title={
            <Space>
              <span style={{ fontSize: 16, fontWeight: 500 }}>Teams</span>
              <span style={{ fontSize: 14, color: '#666' }}>Manage teams and their resources</span>
            </Space>
          }
          loading={teamsLoading}
          data={teams}
          columns={teamColumns}
          rowKey="teamName"
          searchPlaceholder="Search teams..."
          actions={
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={() => setIsCreateTeamModalOpen(true)}
              style={{ background: '#556b2f', borderColor: '#556b2f' }}
            >
              Create Team
            </Button>
          }
        />
      ),
    },
    {
      key: 'regions',
      label: (
        <span>
          <GlobalOutlined />
          Regions
        </span>
      ),
      children: (
        <ResourceListView
          title={
            <Space>
              <span style={{ fontSize: 16, fontWeight: 500 }}>Regions</span>
              <span style={{ fontSize: 14, color: '#666' }}>Manage regions and infrastructure</span>
            </Space>
          }
          loading={regionsLoading}
          data={regions}
          columns={regionColumns}
          rowKey="regionName"
          searchPlaceholder="Search regions..."
          actions={
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={() => setIsCreateRegionModalOpen(true)}
              style={{ background: '#556b2f', borderColor: '#556b2f' }}
            >
              Create Region
            </Button>
          }
        />
      ),
    },
  ]

  return (
    <>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
        />
      </Card>

      {/* Team Modals */}
      <Modal
        title="Create Team"
        open={isCreateTeamModalOpen}
        onCancel={() => {
          setIsCreateTeamModalOpen(false)
          teamForm.resetFields()
        }}
        footer={null}
      >
        <Form
          form={teamForm}
          layout="vertical"
          onFinish={handleCreateTeam}
        >
          <Form.Item
            name="teamName"
            label="Team Name"
            rules={[
              { required: true, message: 'Please enter team name' },
              { pattern: /^[a-zA-Z0-9-_]+$/, message: 'Team name can only contain letters, numbers, hyphens, and underscores' },
            ]}
          >
            <Input placeholder="Enter team name" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => {
                setIsCreateTeamModalOpen(false)
                teamForm.resetFields()
              }}>
                Cancel
              </Button>
              <Button 
                type="primary" 
                htmlType="submit"
                loading={createTeamMutation.isPending}
                style={{ background: '#556b2f', borderColor: '#556b2f' }}
              >
                Create
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Region Modals */}
      <Modal
        title="Create Region"
        open={isCreateRegionModalOpen}
        onCancel={() => {
          setIsCreateRegionModalOpen(false)
          regionForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={regionForm}
          fields={regionFormFields}
          onSubmit={handleCreateRegion}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateRegionModalOpen(false)
            regionForm.reset()
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
    </>
  )
}

export default OrganizationPage