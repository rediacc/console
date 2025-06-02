import React, { useState } from 'react'
import { Card, Tabs, Modal, Form, Input, Button, Space, Popconfirm } from 'antd'
import { TeamOutlined, GlobalOutlined, PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined } from '@ant-design/icons'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { 
  useTeams, 
  useCreateTeam, 
  useUpdateTeamName, 
  useUpdateTeamVault, 
  useDeleteTeam,
  Team 
} from '@/api/queries/teams'
import { 
  useRegions, 
  useCreateRegion, 
  useUpdateRegionName, 
  useUpdateRegionVault, 
  useDeleteRegion,
  Region 
} from '@/api/queries/regions'
import { 
  createTeamSchema, 
  createRegionSchema,
  CreateTeamForm,
  CreateRegionForm 
} from '@/utils/validation'

const OrganizationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('teams')
  const [isTeamModalOpen, setIsTeamModalOpen] = useState(false)
  const [isRegionModalOpen, setIsRegionModalOpen] = useState(false)
  const [editingTeam, setEditingTeam] = useState<Team | null>(null)
  const [editingRegion, setEditingRegion] = useState<Region | null>(null)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    item?: Team | Region
    type?: 'team' | 'region'
  }>({ open: false })

  // Teams hooks
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const createTeamMutation = useCreateTeam()
  const updateTeamNameMutation = useUpdateTeamName()
  const updateTeamVaultMutation = useUpdateTeamVault()
  const deleteTeamMutation = useDeleteTeam()

  // Regions hooks
  const { data: regions = [], isLoading: regionsLoading } = useRegions()
  const createRegionMutation = useCreateRegion()
  const updateRegionNameMutation = useUpdateRegionName()
  const updateRegionVaultMutation = useUpdateRegionVault()
  const deleteRegionMutation = useDeleteRegion()

  // Team form
  const teamForm = useForm<CreateTeamForm>({
    resolver: zodResolver(createTeamSchema),
    defaultValues: {
      teamName: '',
      teamVault: '{}',
    },
  })

  // Region form
  const regionForm = useForm<CreateRegionForm>({
    resolver: zodResolver(createRegionSchema),
    defaultValues: {
      regionName: '',
      regionVault: '{}',
    },
  })

  const handleCreateTeam = async (data: CreateTeamForm) => {
    try {
      if (editingTeam) {
        await updateTeamNameMutation.mutateAsync({
          currentTeamName: editingTeam.teamName,
          newTeamName: data.teamName,
        })
      } else {
        await createTeamMutation.mutateAsync(data)
      }
      setIsTeamModalOpen(false)
      setEditingTeam(null)
      teamForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleCreateRegion = async (data: CreateRegionForm) => {
    try {
      if (editingRegion) {
        await updateRegionNameMutation.mutateAsync({
          currentRegionName: editingRegion.regionName,
          newRegionName: data.regionName,
        })
      } else {
        await createRegionMutation.mutateAsync(data)
      }
      setIsRegionModalOpen(false)
      setEditingRegion(null)
      regionForm.reset()
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

  const handleDeleteRegion = async (regionName: string) => {
    try {
      await deleteRegionMutation.mutateAsync(regionName)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleVaultSave = async (vaultConfig: string) => {
    if (!vaultModalConfig.item) return

    try {
      let parsedConfig = {}
      try {
        parsedConfig = JSON.parse(vaultConfig)
      } catch {
        parsedConfig = {}
      }

      if (vaultModalConfig.type === 'team') {
        const team = vaultModalConfig.item as Team
        await updateTeamVaultMutation.mutateAsync({
          teamName: team.teamName,
          teamVault: vaultConfig,
          vaultVersion: team.vaultVersion,
        })
      } else {
        const region = vaultModalConfig.item as Region
        await updateRegionVaultMutation.mutateAsync({
          regionName: region.regionName,
          regionVault: vaultConfig,
          vaultVersion: region.vaultVersion,
        })
      }
      setVaultModalConfig({ open: false })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const teamColumns = [
    {
      title: 'Team Name',
      dataIndex: 'teamName',
      key: 'teamName',
    },
    {
      title: 'Members',
      dataIndex: 'memberCount',
      key: 'memberCount',
      width: 100,
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
            type="text"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingTeam(record)
              teamForm.setValue('teamName', record.teamName)
              setIsTeamModalOpen(true)
            }}
          />
          <Button
            type="text"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, item: record, type: 'team' })}
          />
          <Popconfirm
            title="Delete Team"
            description={`Are you sure you want to delete "${record.teamName}"?`}
            onConfirm={() => handleDeleteTeam(record.teamName)}
            okText="Yes"
            cancelText="No"
          >
            <Button type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const regionColumns = [
    {
      title: 'Region Name',
      dataIndex: 'regionName',
      key: 'regionName',
    },
    {
      title: 'Bridges',
      dataIndex: 'bridgeCount',
      key: 'bridgeCount',
      width: 100,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_: any, record: Region) => (
        <Space>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingRegion(record)
              regionForm.setValue('regionName', record.regionName)
              setIsRegionModalOpen(true)
            }}
          />
          <Button
            type="text"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, item: record, type: 'region' })}
          />
          <Popconfirm
            title="Delete Region"
            description={`Are you sure you want to delete "${record.regionName}"?`}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText="Yes"
            cancelText="No"
          >
            <Button type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
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
              <span style={{ fontSize: 14, color: '#666' }}>Manage teams and their members</span>
            </Space>
          }
          data={teams}
          columns={teamColumns}
          loading={teamsLoading}
          actions={
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingTeam(null)
                teamForm.reset()
                setIsTeamModalOpen(true)
              }}
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
              <span style={{ fontSize: 14, color: '#666' }}>Manage geographic regions and data centers</span>
            </Space>
          }
          data={regions}
          columns={regionColumns}
          loading={regionsLoading}
          actions={
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingRegion(null)
                regionForm.reset()
                setIsRegionModalOpen(true)
              }}
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

      {/* Team Modal */}
      <Modal
        title={editingTeam ? 'Edit Team' : 'Create Team'}
        open={isTeamModalOpen}
        onCancel={() => {
          setIsTeamModalOpen(false)
          setEditingTeam(null)
          teamForm.reset()
        }}
        footer={null}
      >
        <Form layout="vertical" onFinish={teamForm.handleSubmit(handleCreateTeam)}>
          <Controller
            name="teamName"
            control={teamForm.control}
            render={({ field, fieldState }) => (
              <Form.Item
                label="Team Name"
                validateStatus={fieldState.error ? 'error' : ''}
                help={fieldState.error?.message}
              >
                <Input {...field} placeholder="Enter team name" />
              </Form.Item>
            )}
          />
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={createTeamMutation.isPending || updateTeamNameMutation.isPending}>
                {editingTeam ? 'Update' : 'Create'}
              </Button>
              <Button onClick={() => {
                setIsTeamModalOpen(false)
                setEditingTeam(null)
                teamForm.reset()
              }}>
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Region Modal */}
      <Modal
        title={editingRegion ? 'Edit Region' : 'Create Region'}
        open={isRegionModalOpen}
        onCancel={() => {
          setIsRegionModalOpen(false)
          setEditingRegion(null)
          regionForm.reset()
        }}
        footer={null}
      >
        <Form layout="vertical" onFinish={regionForm.handleSubmit(handleCreateRegion)}>
          <Controller
            name="regionName"
            control={regionForm.control}
            render={({ field, fieldState }) => (
              <Form.Item
                label="Region Name"
                validateStatus={fieldState.error ? 'error' : ''}
                help={fieldState.error?.message}
              >
                <Input {...field} placeholder="Enter region name" />
              </Form.Item>
            )}
          />
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={createRegionMutation.isPending || updateRegionNameMutation.isPending}>
                {editingRegion ? 'Update' : 'Create'}
              </Button>
              <Button onClick={() => {
                setIsRegionModalOpen(false)
                setEditingRegion(null)
                regionForm.reset()
              }}>
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Vault Config Modal */}
      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleVaultSave}
        initialValue={(vaultModalConfig.item as any)?.teamVault || (vaultModalConfig.item as any)?.regionVault || '{}'}
        title={`${(vaultModalConfig.item as any)?.teamName || (vaultModalConfig.item as any)?.regionName} - Vault Configuration`}
      />
    </>
  )
}

export default OrganizationPage