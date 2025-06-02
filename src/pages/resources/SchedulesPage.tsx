import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, Switch, Tooltip, Select } from 'antd'
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  ClockCircleOutlined, 
  SettingOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  CalendarOutlined,
  FieldTimeOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { 
  useSchedules, 
  useCreateSchedule, 
  useDeleteSchedule, 
  useUpdateScheduleVault,
  useUpdateScheduleStatus,
  Schedule 
} from '@/api/queries/schedules'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { createScheduleSchema, CreateScheduleForm } from '@/utils/validation'
import { format, formatDistanceToNow } from 'date-fns'

const { Title, Text } = Typography

const SchedulesPage: React.FC = () => {
  const [selectedTeam, setSelectedTeam] = useState<string>('')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    schedule?: Schedule
  }>({ open: false })

  const { data: dropdownData } = useDropdownData()
  const { data: schedules, isLoading } = useSchedules(selectedTeam)
  const createScheduleMutation = useCreateSchedule()
  const deleteScheduleMutation = useDeleteSchedule()
  const updateVaultMutation = useUpdateScheduleVault()

  const form = useForm<CreateScheduleForm>({
    resolver: zodResolver(createScheduleSchema) as any,
    defaultValues: {
      teamName: '',
      scheduleName: '',
      scheduleVault: '{}',
    },
  })

  const handleCreateSchedule = async (data: CreateScheduleForm) => {
    try {
      await createScheduleMutation.mutateAsync(data)
      setIsCreateModalOpen(false)
      form.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteSchedule = async (schedule: Schedule) => {
    try {
      await deleteScheduleMutation.mutateAsync({
        teamName: schedule.teamName,
        scheduleName: schedule.scheduleName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.schedule) return

    await updateVaultMutation.mutateAsync({
      teamName: vaultModalConfig.schedule.teamName,
      scheduleName: vaultModalConfig.schedule.scheduleName,
      scheduleVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const formatCronExpression = (cron: string) => {
    // Simple cron expression formatter
    const parts = cron.split(' ')
    if (parts.length !== 5) return cron
    
    const [minute, hour, dayOfMonth, month, dayOfWeek] = parts
    const descriptions = []
    
    if (minute === '*') descriptions.push('every minute')
    else if (minute === '0') descriptions.push('at minute 0')
    else descriptions.push(`at minute ${minute}`)
    
    if (hour !== '*') descriptions.push(`hour ${hour}`)
    
    return descriptions.join(', ')
  }

  const columns = [
    {
      title: 'Schedule Name',
      dataIndex: 'scheduleName',
      key: 'scheduleName',
      render: (text: string, record: Schedule) => (
        <Space>
          <ClockCircleOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
          {record.description && (
            <Tooltip title={record.description}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                ({record.description})
              </Text>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'isActive',
      key: 'isActive',
      width: 100,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'success' : 'default'}>
          {isActive ? 'Active' : 'Inactive'}
        </Tag>
      ),
    },
    {
      title: 'Team',
      dataIndex: 'teamName',
      key: 'teamName',
      render: (text: string) => <Tag color="green">{text}</Tag>,
    },
    {
      title: 'Cron Expression',
      dataIndex: 'cronExpression',
      key: 'cronExpression',
      width: 200,
      render: (cron: string) => (
        <Tooltip title={formatCronExpression(cron)}>
          <Tag icon={<FieldTimeOutlined />}>
            <Text code style={{ fontSize: 11 }}>{cron}</Text>
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: 'Next Run',
      dataIndex: 'nextRunTime',
      key: 'nextRunTime',
      width: 180,
      render: (time: string, record: Schedule) => {
        if (!time || !record.isActive) return <Text type="secondary">-</Text>
        const date = new Date(time)
        return (
          <Tooltip title={format(date, 'PPpp')}>
            <Space size="small">
              <CalendarOutlined />
              <Text>{formatDistanceToNow(date, { addSuffix: true })}</Text>
            </Space>
          </Tooltip>
        )
      },
    },
    {
      title: 'Last Run',
      dataIndex: 'lastRunTime',
      key: 'lastRunTime',
      width: 180,
      render: (time: string) => {
        if (!time) return <Text type="secondary">Never</Text>
        const date = new Date(time)
        return (
          <Tooltip title={format(date, 'PPpp')}>
            <Text type="secondary">
              {formatDistanceToNow(date, { addSuffix: true })}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: 'Queue',
      dataIndex: 'queueCount',
      key: 'queueCount',
      width: 80,
      render: (count: number) => (
        <Tag color={count > 0 ? 'blue' : 'default'}>{count}</Tag>
      ),
    },
    {
      title: 'Vault',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 80,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Schedule) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setVaultModalConfig({ open: true, schedule: record })}
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
            title="Delete Schedule"
            description={`Are you sure you want to delete schedule "${record.scheduleName}"?`}
            onConfirm={() => handleDeleteSchedule(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteScheduleMutation.isPending}
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
      name: 'scheduleName',
      label: 'Schedule Name',
      placeholder: 'Enter schedule name',
      required: true,
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Schedules</Title>
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
            Create Schedule
          </Button>
        </Space>
      </div>
      
      <ResourceListView
        title={
          <Title level={4} style={{ margin: 0 }}>
            {selectedTeam ? `Schedules in ${selectedTeam}` : 'Select a team to view schedules'}
          </Title>
        }
        loading={isLoading}
        data={schedules}
        columns={columns}
        rowKey="scheduleName"
        searchPlaceholder="Search schedules..."
        emptyText={!selectedTeam ? "Please select a team to view schedules" : undefined}
      />

      <Modal
        title="Create Schedule"
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false)
          form.reset()
        }}
        footer={null}
        width={600}
      >
        <ResourceForm
          form={form}
          fields={formFields}
          onSubmit={handleCreateSchedule}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createScheduleMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={vaultModalConfig.open}
        onCancel={() => setVaultModalConfig({ open: false })}
        onSave={handleUpdateVault}
        title={`Configure Vault - ${vaultModalConfig.schedule?.scheduleName}`}
        initialVault={vaultModalConfig.schedule?.scheduleVault || '{}'}
        initialVersion={vaultModalConfig.schedule?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default SchedulesPage