import React, { useState, useEffect } from 'react'
import { Modal, Table, Button, Space, Typography, Progress, Tag, Alert } from 'antd'
import { SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, WifiOutlined, ClockCircleOutlined } from '@/utils/optimizedIcons'
import type { ColumnsType } from 'antd/es/table/interface'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/context/ThemeContext'
import { showMessage } from '@/utils/messages'
import type { Machine } from '@/types'
import { usePingFunction } from '@/services/pingService'
import './ConnectivityTestModal.css'

const { Text, Title } = Typography

interface ConnectivityTestModalProps {
  open: boolean
  onClose: () => void
  machines: Machine[]
  teamFilter?: string | string[]
}

interface TestResult {
  machineName: string
  teamName: string
  bridgeName: string
  status: 'pending' | 'testing' | 'success' | 'failed'
  message?: string
  taskId?: string
  duration?: number
  timestamp?: string
}

const ConnectivityTestModal: React.FC<ConnectivityTestModalProps> = ({
  open,
  onClose,
  machines,
  teamFilter
}) => {
  const { t } = useTranslation(['machines', 'common'])
  const { theme } = useTheme()
  const [testResults, setTestResults] = useState<TestResult[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentMachineIndex, setCurrentMachineIndex] = useState(-1)
  
  const { executePingForMachine, waitForQueueItemCompletion } = usePingFunction()

  // Initialize test results when modal opens
  useEffect(() => {
    if (open && machines.length > 0) {
      const initialResults: TestResult[] = machines.map(machine => ({
        machineName: machine.machineName,
        teamName: machine.teamName,
        bridgeName: machine.bridgeName,
        status: 'pending'
      }))
      setTestResults(initialResults)
      setProgress(0)
      setCurrentMachineIndex(-1)
    }
  }, [open, machines])

  // Helper to format completion message
  const formatCompletionMessage = (result: any) => {
    if (result.success) {
      return t('machines:connectionSuccessful')
    }
    if (result.status === 'TIMEOUT') {
      return t('machines:testTimeout')
    }
    return result.message || t('machines:connectionFailed')
  }

  // Run connectivity test for a single machine
  const testMachineConnectivity = async (machine: Machine, index: number): Promise<void> => {
    const startTime = Date.now()
    
    // Update status to testing
    setTestResults(prev => prev.map((result, i) => 
      i === index ? { ...result, status: 'testing', timestamp: new Date().toISOString() } : result
    ))

    try {
      // Execute ping function using the shared service
      // The ping service will automatically fetch the team vault data
      const result = await executePingForMachine(machine, {
        priority: 4, // Normal priority for connectivity tests
        description: 'Connectivity test',
        addedVia: 'connectivity-test'
      })

      if (result.success && result.taskId) {
        // Update with taskId
        setTestResults(prev => prev.map((r, i) => 
          i === index ? { ...r, taskId: result.taskId } : r
        ))

        // Wait for completion
        const completionResult = await waitForQueueItemCompletion(result.taskId)
        const duration = Date.now() - startTime

        // Update final status
        setTestResults(prev => prev.map((r, i) => 
          i === index ? { 
            ...r, 
            status: completionResult.success ? 'success' : 'failed',
            message: formatCompletionMessage(completionResult),
            duration
          } : r
        ))
      } else {
        throw new Error(result.error || 'Failed to create test task')
      }
    } catch (error: any) {
      const duration = Date.now() - startTime
      setTestResults(prev => prev.map((result, i) => 
        i === index ? { 
          ...result, 
          status: 'failed', 
          message: error.message || 'Failed to create test task',
          duration
        } : result
      ))
    }
  }

  // Run all tests sequentially
  const runAllTests = async () => {
    setIsRunning(true)
    
    for (let i = 0; i < machines.length; i++) {
      setCurrentMachineIndex(i)
      setProgress(Math.round((i / machines.length) * 100))
      await testMachineConnectivity(machines[i], i)
    }
    
    setProgress(100)
    setIsRunning(false)
    setCurrentMachineIndex(-1)
    
    // Show summary
    const successCount = testResults.filter(r => r.status === 'success').length
    const failedCount = testResults.filter(r => r.status === 'failed').length
    
    if (failedCount === 0) {
      showMessage('success', t('machines:allMachinesConnected', { count: successCount }))
    } else {
      showMessage('warning', t('machines:machinesConnectedWithFailures', { successCount, failedCount }))
    }
  }

  // Table columns
  const columns: ColumnsType<TestResult> = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string, record: TestResult) => (
        <Space data-testid={`connectivity-machine-${name}`}>
          {record.status === 'testing' && <SyncOutlined spin style={{ color: '#1890ff' }} data-testid={`connectivity-status-icon-testing-${name}`} />}
          {record.status === 'success' && <CheckCircleOutlined style={{ color: '#52c41a' }} data-testid={`connectivity-status-icon-success-${name}`} />}
          {record.status === 'failed' && <CloseCircleOutlined style={{ color: '#ff4d4f' }} data-testid={`connectivity-status-icon-failed-${name}`} />}
          {record.status === 'pending' && <ClockCircleOutlined style={{ color: '#8c8c8c' }} data-testid={`connectivity-status-icon-pending-${name}`} />}
          <Text strong>{name}</Text>
        </Space>
      )
    },
    {
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      render: (name: string) => <Tag color="#8FBC8F">{name}</Tag>
    },
    {
      title: t('machines:bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (name: string) => <Tag color="green">{name}</Tag>
    },
    {
      title: t('machines:status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: TestResult['status'], record: TestResult) => {
        const config = {
          pending: { color: 'default', text: t('machines:pending') },
          testing: { color: 'processing', text: t('machines:testing') },
          success: { color: 'success', text: t('machines:connected') },
          failed: { color: 'error', text: t('machines:failed') }
        }
        return <Tag color={config[status].color} data-testid={`connectivity-status-tag-${record.machineName}-${status}`}>{config[status].text}</Tag>
      }
    },
    {
      title: t('machines:responseTime'),
      dataIndex: 'duration',
      key: 'duration',
      width: 120,
      render: (duration?: number) => {
        if (!duration) return '-'
        if (duration < 1000) return `${duration}ms`
        return `${(duration / 1000).toFixed(1)}s`
      }
    },
    {
      title: t('machines:message'),
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (message?: string, record: TestResult) => {
        if (!message) return '-'
        return (
          <Text type={record.status === 'failed' ? 'danger' : undefined}>
            {message}
          </Text>
        )
      }
    }
  ]

  return (
    <Modal
      data-testid="connectivity-modal"
      title={
        <Space>
          <WifiOutlined />
          <span>{t('machines:connectivityTest')}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={1000}
      footer={[
        <Button 
          key="run" 
          type="primary" 
          icon={<SyncOutlined />}
          onClick={runAllTests}
          disabled={isRunning || machines.length === 0}
          loading={isRunning}
          data-testid="connectivity-run-test-button"
        >
          {isRunning ? t('machines:testing') : t('machines:runTest')}
        </Button>,
        <Button key="close" onClick={onClose} data-testid="connectivity-close-button">
          Close
        </Button>
      ]}
    >
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Progress Bar */}
        {isRunning && (
          <div style={{ marginBottom: 16 }} data-testid="connectivity-progress-container">
            <Progress 
              percent={progress} 
              status="active"
              strokeColor={{
                '0%': '#108ee9',
                '100%': '#87d068'
              }}
              data-testid="connectivity-progress-bar"
            />
            {currentMachineIndex >= 0 && currentMachineIndex < machines.length && (
              <Text type="secondary" style={{ fontSize: '12px' }} data-testid="connectivity-progress-text">
                {t('machines:testingMachine', { machineName: machines[currentMachineIndex].machineName })}
              </Text>
            )}
          </div>
        )}

        {/* Info Alert */}
        <Alert
          message={t('machines:connectivityTestDescription')}
          type="info"
          showIcon
          icon={<WifiOutlined />}
          data-testid="connectivity-info-alert"
        />

        {/* Results Table */}
        <Table
          columns={columns}
          dataSource={testResults}
          rowKey="machineName"
          pagination={false}
          scroll={{ y: 400 }}
          loading={machines.length === 0}
          rowClassName={(record) => {
            if (record.status === 'testing') return 'connectivity-test-active-row'
            if (record.status === 'success') return 'connectivity-test-success-row'
            if (record.status === 'failed') return 'connectivity-test-failed-row'
            return ''
          }}
          data-testid="connectivity-results-table"
        />

        {/* Summary Statistics */}
        {!isRunning && testResults.some(r => r.status !== 'pending') && (
          <div style={{ 
            padding: '16px', 
            background: theme === 'dark' ? '#1f1f1f' : '#f0f2f5',
            borderRadius: '8px'
          }}
          data-testid="connectivity-summary-statistics">
            <Space size="large">
              <div data-testid="connectivity-total-machines">
                <Text type="secondary">{t('machines:totalMachines')}:</Text>{' '}
                <Text strong>{machines.length}</Text>
              </div>
              <div data-testid="connectivity-connected-count">
                <Text type="secondary">{t('machines:connected')}:</Text>{' '}
                <Text strong style={{ color: '#52c41a' }}>
                  {testResults.filter(r => r.status === 'success').length}
                </Text>
              </div>
              <div data-testid="connectivity-failed-count">
                <Text type="secondary">{t('machines:failed')}:</Text>{' '}
                <Text strong style={{ color: '#ff4d4f' }}>
                  {testResults.filter(r => r.status === 'failed').length}
                </Text>
              </div>
              <div data-testid="connectivity-average-response">
                <Text type="secondary">{t('machines:averageResponse')}:</Text>{' '}
                <Text strong>
                  {(() => {
                    const successfulTests = testResults.filter(r => r.status === 'success' && r.duration)
                    if (successfulTests.length === 0) return '-'
                    const avgDuration = successfulTests.reduce((sum, r) => sum + (r.duration || 0), 0) / successfulTests.length
                    return avgDuration < 1000 ? `${Math.round(avgDuration)}ms` : `${(avgDuration / 1000).toFixed(1)}s`
                  })()}
                </Text>
              </div>
            </Space>
          </div>
        )}
      </Space>
    </Modal>
  )
}

export default ConnectivityTestModal