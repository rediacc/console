import React, { useState, useEffect } from 'react'
import { Button, Form, Input, Select, Table } from 'antd'
import { PlusOutlined, DownloadOutlined, SettingOutlined } from '@ant-design/icons'
import { useTelemetry, useInteractionTracking, useComponentTelemetry } from '../TelemetryProvider'
import { useTelemetryTracking } from '@/hooks/useTelemetryTracking'
import { ModalSize } from '@/types/modal'
import {
  PageContainer,
  PageHeader,
  ActionRow,
  TelemetryModal,
  ModalActions,
  UsageCard,
  UsageList,
  UsageListItem,
} from './styles'

/**
 * Example component demonstrating comprehensive telemetry tracking
 * This serves as a reference for implementing telemetry in other components
 */
const TelemetryExample: React.FC = () => {
  // Component lifecycle tracking
  useComponentTelemetry('TelemetryExample')

  // Basic telemetry hooks
  const { trackEvent, measureAndTrack } = useTelemetry()
  const interactions = useInteractionTracking()

  // Advanced telemetry tracking
  const {
    trackResourceCreation,
    trackDataExport,
    trackFormInteraction,
    trackErrorWithContext,
    trackFeatureAccess,
    trackClick
  } = useTelemetryTracking()

  // Component state
  const [data, setData] = useState<Array<{ id: number; name: string; status: string }>>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  // Track feature access when component mounts
  useEffect(() => {
    trackFeatureAccess('telemetry_example_page')
  }, [trackFeatureAccess])

  // Example: Tracking data loading with performance measurement
  const loadData = async () => {
    setLoading(true)
    try {
      const result = await measureAndTrack('data.load.example_table', async () => {
        // Simulate API call
        await new Promise(resolve => setTimeout(resolve, 1000))
        return [
          { id: 1, name: 'Example Item 1', status: 'Active' },
          { id: 2, name: 'Example Item 2', status: 'Inactive' },
        ]
      })

      setData(result)

      // Track successful data load
      trackEvent('data.loaded', {
        'data.type': 'example_items',
        'data.count': result.length,
        'data.source': 'example_api'
      })
    } catch (error) {
      // Track error with context
      trackErrorWithContext(error as Error, {
        component: 'TelemetryExample',
        action: 'load_data',
        resourceType: 'example_items'
      })
    } finally {
      setLoading(false)
    }
  }

  // Example: Tracking modal interactions
  const handleCreateNew = () => {
    setModalVisible(true)
    interactions.trackModalOpen('create_example_item')
    trackClick('create_new_button', { source: 'table_header' })
  }

  const handleModalCancel = () => {
    setModalVisible(false)
    interactions.trackModalClose('create_example_item')
  }

  // Example: Tracking form submission with validation
  const handleFormSubmit = async (values: any) => {
    try {
      // Track form interaction
      trackFormInteraction('create_example_item', 'submit')

      // Simulate form submission with performance tracking
      await measureAndTrack('form.submit.create_example_item', async () => {
        await new Promise(resolve => setTimeout(resolve, 500))
      })

      // Track successful resource creation
      trackResourceCreation('example_item', values.name)

      // Close modal and reset form
      setModalVisible(false)
      form.resetFields()

      // Reload data
      loadData()

    } catch (error) {
      // Track form error
      interactions.trackFormError('create_example_item', {
        error: (error as Error).message
      })
    }
  }

  // Example: Tracking data export
  const handleExport = () => {
    trackClick('export_button', {
      export_type: 'csv',
      record_count: data.length
    })

    trackDataExport('example_items', data.length, 'csv')

    // Simulate export
    console.log('Exporting data...', data)
  }

  // Example: Tracking settings access
  const handleSettings = () => {
    trackClick('settings_button')
    trackEvent('settings.access', {
      'settings.type': 'example_settings',
      'settings.source': 'table_header'
    })
  }

  // Example: Tracking table operations
  const handleTableChange = (_pagination: any, _filters: any, sorter: any) => {
    trackEvent('table.interaction', {
      'table.name': 'example_table',
      'table.action': 'sort',
      'table.column': sorter.field || 'unknown',
      'table.order': sorter.order || 'none'
    })
  }

  // Table columns with click tracking
  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: any) => (
        <Button
          type="link"
          onClick={() => {
            trackClick('item_name_link', {
              item_id: record.id,
              item_name: record.name
            })
            // Navigate to item details
            console.log('Navigate to item:', record.id)
          }}
        >
          {text}
        </Button>
      )
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Select
          value={status}
          style={{ width: 120 }}
          onChange={(newStatus) => {
            trackEvent('status.change', {
              'status.old': status,
              'status.new': newStatus,
              'status.resource': 'example_item'
            })
            // Update status
            console.log('Status changed:', newStatus)
          }}
        >
          <Select.Option value="Active">Active</Select.Option>
          <Select.Option value="Inactive">Inactive</Select.Option>
        </Select>
      )
    },
  ]

  return (
    <PageContainer>
      <PageHeader>
        <h1>Telemetry Implementation Example</h1>
        <p>This component demonstrates how to implement comprehensive telemetry tracking.</p>
      </PageHeader>

      {/* Header with action buttons */}
      <ActionRow>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreateNew}
        >
          Create New
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={handleExport}
          disabled={data.length === 0}
        >
          Export
        </Button>
        <Button
          icon={<SettingOutlined />}
          onClick={handleSettings}
        >
          Settings
        </Button>
        <Button onClick={loadData} loading={loading}>
          Load Data
        </Button>
      </ActionRow>

      {/* Data table with telemetry tracking */}
      <Table
        columns={columns}
        dataSource={data}
        loading={loading}
        rowKey="id"
        onChange={handleTableChange}
        pagination={{
          onChange: (page, pageSize) => {
            trackEvent('table.pagination', {
              'table.name': 'example_table',
              'pagination.page': page,
              'pagination.size': pageSize
            })
          }
        }}
      />

      {/* Modal with form tracking */}
      <TelemetryModal
        title="Create New Item"
        open={modalVisible}
        onCancel={handleModalCancel}
        footer={null}
        className={ModalSize.Medium}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleFormSubmit}
          onFieldsChange={(changedFields) => {
            // Track form field interactions
            changedFields.forEach(field => {
              if (field.name && field.value !== undefined) {
                trackFormInteraction('create_example_item', 'field_change', field.name[0])
              }
            })
          }}
        >
          <Form.Item
            label="Name"
            name="name"
            rules={[{ required: true, message: 'Please enter a name' }]}
          >
            <Input
              placeholder="Enter item name"
              onFocus={() => trackFormInteraction('create_example_item', 'field_focus', 'name')}
            />
          </Form.Item>

          <Form.Item
            label="Status"
            name="status"
            initialValue="Active"
          >
            <Select
              onFocus={() => trackFormInteraction('create_example_item', 'field_focus', 'status')}
            >
              <Select.Option value="Active">Active</Select.Option>
              <Select.Option value="Inactive">Inactive</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <ModalActions>
              <Button onClick={handleModalCancel}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit">
                Create
              </Button>
            </ModalActions>
          </Form.Item>
        </Form>
      </TelemetryModal>

      {/* Usage information */}
      <UsageCard>
        <h3>Telemetry Events Tracked in This Component:</h3>
        <UsageList>
          <UsageListItem><strong>Component lifecycle:</strong> Mount/unmount events</UsageListItem>
          <UsageListItem><strong>Feature access:</strong> Page/component access tracking</UsageListItem>
          <UsageListItem><strong>User interactions:</strong> Button clicks, form interactions</UsageListItem>
          <UsageListItem><strong>Data operations:</strong> Loading, exporting, status changes</UsageListItem>
          <UsageListItem><strong>Modal interactions:</strong> Open/close tracking</UsageListItem>
          <UsageListItem><strong>Form events:</strong> Submit, field changes, validation errors</UsageListItem>
          <UsageListItem><strong>Table operations:</strong> Sorting, pagination, row interactions</UsageListItem>
          <UsageListItem><strong>Performance:</strong> API call timing, form submission timing</UsageListItem>
          <UsageListItem><strong>Error tracking:</strong> API failures, form validation errors</UsageListItem>
        </UsageList>
        <p><strong>Note:</strong> Open browser DevTools Network tab to see OTLP telemetry requests being sent to obs.rediacc.com</p>
      </UsageCard>
    </PageContainer>
  )
}

export default TelemetryExample
