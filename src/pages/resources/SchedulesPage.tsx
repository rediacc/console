import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, Switch, Tooltip } from 'antd'
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
import { createScheduleSchema, CreateScheduleForm } from '@/utils/validation'
import { format, formatDistanceToNow } from 'date-fns'

const { Title, Text } = Typography

const SchedulesPage: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [vaultModalConfig, setVaultModalConfig] = useState<{
    open: boolean
    schedule?: Schedule
  }>({ open: false })

  const { data: schedules, isLoading } = useSchedules()
  const createScheduleMutation = useCreateSchedule()
  const deleteScheduleMutation = useDeleteSchedule()
  const updateVaultMutation = useUpdateScheduleVault()
  const updateStatusMutation = useUpdateScheduleStatus()

  const form = useForm<CreateScheduleForm>({
    resolver: zodResolver(createScheduleSchema),
    defaultValues: {
      scheduleName: '',
      scheduleVault: '{}',
      description: '',
      cronExpression: '',
      isActive: true,
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

  const handleDeleteSchedule = async (scheduleName: string) => {
    try {
      await deleteScheduleMutation.mutateAsync(scheduleName)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultModalConfig.schedule) return

    await updateVaultMutation.mutateAsync({
      scheduleName: vaultModalConfig.schedule.scheduleName,
      scheduleVault: vault,
      vaultVersion: version,
    })
    setVaultModalConfig({ open: false })
  }

  const handleToggleStatus = async (schedule: Schedule) => {
    try {
      await updateStatusMutation.mutateAsync({
        scheduleName: schedule.scheduleName,
        isActive: !schedule.isActive,
      })
    } catch (error) {
      // Error handled by mutation
    }
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
      render: (isActive: boolean, record: Schedule) => (
        <Space>
          <Switch
            checked={isActive}
            onChange={() => handleToggleStatus(record)}
            loading={updateStatusMutation.isPending}
            checkedChildren={<PlayCircleOutlined />}
            unCheckedChildren={<PauseCircleOutlined />}
          />
          <Tag color={isActive ? 'success' : 'default'}>
            {isActive ? 'Active' : 'Inactive'}
          </Tag>
        </Space>
      ),
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
            onConfirm={() => handleDeleteSchedule(record.scheduleName)}
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
      name: 'scheduleName',
      label: 'Schedule Name',
      placeholder: 'Enter schedule name',
      required: true,
    },
    {
      name: 'description',
      label: 'Description',
      placeholder: 'Enter description (optional)',
    },
    {
      name: 'cronExpression',
      label: 'Cron Expression',
      placeholder: '0 0 * * * (e.g., daily at midnight)',
      required: true,
      help: 'Format: minute hour day month weekday',
    },
    {
      name: 'isActive',
      label: 'Active',
      type: 'switch' as const,
      valuePropName: 'checked',
    },
  ]

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Schedule Management</Title>
      </div>
      
      <ResourceListView
        title={<Title level={4} style={{ margin: 0 }}>Schedules</Title>}
        loading={isLoading}
        data={schedules}
        columns={columns}
        rowKey="scheduleName"
        searchPlaceholder="Search schedules..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            Create Schedule
          </Button>
        }
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