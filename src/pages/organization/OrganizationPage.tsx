import React, { useState } from 'react'
import { Card, Tabs, Button, Space, Modal, Popconfirm, Tag, Typography, Form, Input, Table, Row, Col, Empty } from 'antd'
import { 
  TeamOutlined, 
  GlobalOutlined, 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  UserOutlined,
  ApiOutlined,
  SettingOutlined,
  CloudServerOutlined
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

// Bridge queries
import { 
  useBridges, 
  useCreateBridge, 
  useDeleteBridge, 
  useUpdateBridgeVault, 
  Bridge 
} from '@/api/queries/bridges'

import { useDropdownData } from '@/api/queries/useDropdownData'
import { createRegionSchema, CreateRegionForm, createBridgeSchema, CreateBridgeForm } from '@/utils/validation'

const { Title, Text } = Typography

const OrganizationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('teams')
  
  // Team state
  const [isCreateTeamModalOpen, setIsCreateTeamModalOpen] = useState(false)
  const [teamForm] = Form.useForm()
  
  // Region state
  const [isCreateRegionModalOpen, setIsCreateRegionModalOpen] = useState(false)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [regionVaultModalConfig, setRegionVaultModalConfig] = useState<{
    open: boolean
    region?: Region
  }>({ open: false })

  // Bridge state
  const [isCreateBridgeModalOpen, setIsCreateBridgeModalOpen] = useState(false)
  const [bridgeVaultModalConfig, setBridgeVaultModalConfig] = useState<{
    open: boolean
    bridge?: Bridge
  }>({ open: false })

  // Common hooks
  const { data: dropdownData } = useDropdownData()

  // Team hooks
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const createTeamMutation = useCreateTeam()
  const deleteTeamMutation = useDeleteTeam()

  // Region hooks
  const { data: regions = [], isLoading: regionsLoading } = useRegions()
  const createRegionMutation = useCreateRegion()
  const deleteRegionMutation = useDeleteRegion()
  const updateRegionVaultMutation = useUpdateRegionVault()

  // Bridge hooks
  const { data: bridges = [], isLoading: bridgesLoading } = useBridges(selectedRegion || undefined)
  const createBridgeMutation = useCreateBridge()
  const deleteBridgeMutation = useDeleteBridge()
  const updateBridgeVaultMutation = useUpdateBridgeVault()

  // Region form
  const regionForm = useForm<CreateRegionForm>({
    resolver: zodResolver(createRegionSchema) as any,
    defaultValues: {
      regionName: '',
      regionVault: '{}',
    },
  })

  // Bridge form
  const bridgeForm = useForm<CreateBridgeForm>({
    resolver: zodResolver(createBridgeSchema) as any,
    defaultValues: {
      regionName: '',
      bridgeName: '',
      bridgeVault: '{}',
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
      if (selectedRegion === regionName) {
        setSelectedRegion(null)
      }
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateRegionVault = async (vault: string, version: number) => {
    if (!regionVaultModalConfig.region) return

    await updateRegionVaultMutation.mutateAsync({
      regionName: regionVaultModalConfig.region.regionName,
      regionVault: vault,
      vaultVersion: version,
    })
    setRegionVaultModalConfig({ open: false })
  }

  // Bridge handlers
  const handleCreateBridge = async (data: CreateBridgeForm) => {
    try {
      await createBridgeMutation.mutateAsync(data)
      setIsCreateBridgeModalOpen(false)
      bridgeForm.reset()
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

  const handleUpdateBridgeVault = async (vault: string, version: number) => {
    if (!bridgeVaultModalConfig.bridge) return

    await updateBridgeVaultMutation.mutateAsync({
      regionName: bridgeVaultModalConfig.bridge.regionName,
      bridgeName: bridgeVaultModalConfig.bridge.bridgeName,
      bridgeVault: vault,
      vaultVersion: version,
    })
    setBridgeVaultModalConfig({ open: false })
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
      render: (text: string, record: Region) => (
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
            onClick={() => setRegionVaultModalConfig({ open: true, region: record })}
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

  // Bridge columns
  const bridgeColumns = [
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
            onClick={() => setBridgeVaultModalConfig({ open: true, bridge: record })}
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

  const regionFormFields = [
    {
      name: 'regionName',
      label: 'Region Name',
      placeholder: 'Enter region name',
      required: true,
    },
  ]

  const bridgeFormFields = [
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
          Regions & Infrastructure
        </span>
      ),
      children: (
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>Regions</span>
                  <span style={{ fontSize: 14, color: '#666' }}>Select a region to view its bridges</span>
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
              rowSelection={{
                type: 'radio',
                selectedRowKeys: selectedRegion ? [selectedRegion] : [],
                onChange: (selectedRowKeys: React.Key[]) => {
                  setSelectedRegion(selectedRowKeys[0] as string || null)
                },
              }}
              onRow={(record) => ({
                onClick: () => setSelectedRegion(record.regionName),
                style: { 
                  cursor: 'pointer',
                  backgroundColor: selectedRegion === record.regionName ? '#f0f5ff' : undefined
                },
              })}
            />
          </Col>
          
          <Col span={24}>
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedRegion ? `Bridges in ${selectedRegion}` : 'Bridges'}
                  </Title>
                  {!selectedRegion && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      Select a region above to view and manage its bridges
                    </Text>
                  )}
                </div>
                {selectedRegion && (
                  <Button 
                    type="primary" 
                    icon={<PlusOutlined />}
                    onClick={() => {
                      bridgeForm.setValue('regionName', selectedRegion)
                      setIsCreateBridgeModalOpen(true)
                    }}
                    style={{ background: '#556b2f', borderColor: '#556b2f' }}
                  >
                    Create Bridge
                  </Button>
                )}
              </div>
              
              {!selectedRegion ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="Select a region to view its bridges"
                  style={{ padding: '40px 0' }}
                />
              ) : (
                <Table
                  columns={bridgeColumns}
                  dataSource={bridges}
                  rowKey="bridgeName"
                  loading={bridgesLoading}
                  pagination={{
                    total: bridges?.length || 0,
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `Total ${total} bridges`,
                  }}
                  locale={{
                    emptyText: 'No bridges found in this region',
                  }}
                />
              )}
            </Card>
          </Col>
        </Row>
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
        open={regionVaultModalConfig.open}
        onCancel={() => setRegionVaultModalConfig({ open: false })}
        onSave={handleUpdateRegionVault}
        title={`Configure Vault - ${regionVaultModalConfig.region?.regionName}`}
        initialVault="{}"
        initialVersion={regionVaultModalConfig.region?.vaultVersion || 1}
        loading={updateRegionVaultMutation.isPending}
      />

      {/* Bridge Modals */}
      <Modal
        title="Create Bridge"
        open={isCreateBridgeModalOpen}
        onCancel={() => {
          setIsCreateBridgeModalOpen(false)
          bridgeForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={bridgeForm}
          fields={bridgeFormFields}
          onSubmit={handleCreateBridge}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateBridgeModalOpen(false)
            bridgeForm.reset()
          }}
          loading={createBridgeMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={bridgeVaultModalConfig.open}
        onCancel={() => setBridgeVaultModalConfig({ open: false })}
        onSave={handleUpdateBridgeVault}
        title={`Configure Vault - ${bridgeVaultModalConfig.bridge?.bridgeName}`}
        initialVault="{}"
        initialVersion={bridgeVaultModalConfig.bridge?.vaultVersion || 1}
        loading={updateBridgeVaultMutation.isPending}
      />
    </>
  )
}

export default OrganizationPage