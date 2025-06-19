import React, { useEffect, useState } from 'react'
import { Table, Spin, Alert, Tag, Space, Typography, Button } from 'antd'
import { InboxOutlined, CheckCircleOutlined, CloseCircleOutlined, FunctionOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { type QueueFunction, useCreateQueueItem } from '@/api/queries/queue'
import { useQueueItemTrace } from '@/api/queries/queue'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories } from '@/api/queries/repositories'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import queueManagerService from '@/services/queueManagerService'
import type { ColumnsType } from 'antd/es/table'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'

const { Text } = Typography

interface Repository {
  name: string
  repo_exists: boolean
  size: number
  size_human: string
  modified: number
  modified_human: string
  mounted: boolean
  mount_path: string
  image_path: string
}

interface MachineRepositoryListProps {
  machine: Machine
}

export const MachineRepositoryList: React.FC<MachineRepositoryListProps> = ({ machine }) => {
  const { t } = useTranslation(['resources', 'common', 'machines'])
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [queueId, setQueueId] = useState<string | null>(null)
  const [isQueued, setIsQueued] = useState(false)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [functionModalOpen, setFunctionModalOpen] = useState(false)
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null })
  
  // Use direct queue item creation for list operations (not managed)
  const createQueueItemMutation = useCreateQueueItem()
  // Keep managed queue for function execution
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading } = useRepositories(machine.teamName)
  
  // Use queue trace to monitor the task
  const { data: traceData } = useQueueItemTrace(taskId, !!taskId)

  useEffect(() => {
    // Only fetch when repositories are loaded
    if (!repositoriesLoading && machine) {
      fetchRepositories()
    }
  }, [machine, repositoriesLoading])

  // Monitor queued item for task ID
  useEffect(() => {
    if (!queueId) return

    const unsubscribe = managedQueueMutation.subscribeToQueueItem?.(queueId, (item) => {
      if (item?.taskId) {
        // Got the task ID!
        setTaskId(item.taskId)
        setQueueId(null) // Clear queue ID
        setIsQueued(false)
        showMessage('info', t('resources:repositories.taskSubmitted'))
        
        // Start monitoring the task with bridge info for priority 1 tasks
        queueMonitoringService.addTask(
          item.taskId,
          machine.teamName,
          machine.machineName,
          'PENDING', // Initial status when task is created
          undefined, // retryCount
          undefined, // lastFailureReason
          machine.bridgeName, // bridgeName for priority 1 tracking
          1 // priority 1 for repository list tasks
        )
      } else if (item?.status === 'failed') {
        setError(t('resources:repositories.failedToSubmit'))
        setLoading(false)
        setQueueId(null)
        setIsQueued(false)
      } else if (item?.status === 'cancelled') {
        setError(t('resources:repositories.taskCancelled'))
        setLoading(false)
        setQueueId(null)
        setIsQueued(false)
      }
    })

    return () => {
      unsubscribe?.()
    }
  }, [queueId, managedQueueMutation, t])

  useEffect(() => {
    // Log task status for debugging
    if (traceData?.queueDetails?.status) {
      console.log('Task status:', traceData.queueDetails.status)
    }
    
    // Check if task is completed
    if (traceData?.queueDetails?.status === 'COMPLETED') {
      // Ensure the queue manager is updated
      if (taskId) {
        console.log('Task completed, updating queue manager')
        queueManagerService.updateTaskStatus(taskId, 'completed')
      }
      
      // Check if we have response vault content
      if (!traceData?.responseVaultContent?.vaultContent) {
        console.error('Task completed but no response vault content received')
        console.error('Full trace data:', traceData)
        setError('Task completed but no response data received. Check console for details.')
        setLoading(false)
        return
      }
      
      try {
        // Parse the response vault content
        const vaultContent = JSON.parse(traceData.responseVaultContent.vaultContent)
        console.log('Parsed vault content:', vaultContent)
        
        // The result is nested in the response
        if (vaultContent.result) {
          const result = JSON.parse(vaultContent.result)
          console.log('Parsed result:', result)
          
          // Parse the command output which contains the repositories
          if (result.command_output) {
            const commandOutput = JSON.parse(result.command_output)
            console.log('Command output:', commandOutput)
            
            if (commandOutput.repositories && Array.isArray(commandOutput.repositories)) {
              // Map repository GUIDs back to names if needed
              const mappedRepositories = commandOutput.repositories.map((repo: Repository) => {
                // Check if the name looks like a GUID
                const isGuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(repo.name);
                
                if (isGuid) {
                  // Find the matching repository by GUID
                  const matchingRepo = teamRepositories.find(r => r.repositoryGuid === repo.name);
                  if (matchingRepo) {
                    return {
                      ...repo,
                      name: matchingRepo.repositoryName
                    };
                  }
                }
                
                // If not a GUID or no match found, check if it's a repository name that needs GUID lookup
                const repoByName = teamRepositories.find(r => r.repositoryName === repo.name);
                if (!repoByName) {
                  // This might be a case where name is "A1" but it's actually a repository name
                }
                
                return repo;
              });
              
              setRepositories(mappedRepositories)
            } else {
              setRepositories([])
            }
          } else {
            console.error('No command_output in result')
            setRepositories([])
            setError('No repository data in response')
          }
        } else {
          console.error('No result in vault content')
          setError('Invalid response format - missing result')
        }
        setLoading(false)
      } catch (err) {
        console.error('Error parsing response:', err)
        setError('Failed to parse repository data: ' + (err as Error).message)
        setLoading(false)
      }
    } else if (traceData?.queueDetails?.status === 'FAILED' || traceData?.queueDetails?.permanentlyFailed) {
      // Ensure the queue manager is updated
      if (taskId) {
        console.log('Task failed, updating queue manager')
        queueManagerService.updateTaskStatus(taskId, 'failed')
      }
      
      setError(traceData.queueDetails.lastFailureReason || 'Failed to fetch repositories')
      setLoading(false)
    }
  }, [traceData])

  const fetchRepositories = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Collect all repository credentials from team repositories
      const allRepositoryCredentials: Record<string, string> = {}
      teamRepositories.forEach(repo => {
        if (repo.vaultContent) {
          try {
            const vaultData = JSON.parse(repo.vaultContent)
            if (vaultData.credential) {
              // Use repositoryGuid as the key instead of repositoryName
              allRepositoryCredentials[repo.repositoryGuid] = vaultData.credential
            }
          } catch (e) {
            // Silently skip repositories with invalid vault data
            // Silently skip repositories with invalid vault data
          }
        }
      })
      
      
      // Build queue vault for the list function
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'list',
        params: {},
        priority: 1, // Highest priority for UI tasks
        description: `List repositories on ${machine.machineName}`,
        addedVia: 'machine-repository-list',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        allRepositoryCredentials
      })
      
      // Use managed queue for priority 1 tasks so they appear in Queue Manager
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 1
      })
      
      console.log('Queue item response:', response)
      
      if (response?.taskId) {
        console.log('Task ID received:', response.taskId)
        setTaskId(response.taskId)
        // Start monitoring the task
        showMessage('info', 'Repository list request submitted. Monitoring task...')
        
        // Start monitoring the task with bridge info for priority 1 tasks
        queueMonitoringService.addTask(
          response.taskId,
          machine.teamName,
          machine.machineName,
          'PENDING', // Initial status when task is created
          undefined, // retryCount
          undefined, // lastFailureReason
          machine.bridgeName, // bridgeName for priority 1 tracking
          1 // priority 1 for repository list tasks
        )
      } else if (response?.isQueued && response?.queueId) {
        // Item was queued for highest priority management
        showMessage('info', t('resources:repositories.requestQueued'))
        setQueueId(response.queueId)
        setIsQueued(true)
        // Keep loading state while we wait for task ID
      } else {
        console.error('No taskId in response:', response)
        setError('Failed to create queue item')
        setLoading(false)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch repositories')
      setLoading(false)
    }
  }

  const handleRunFunction = (repository: Repository) => {
    setSelectedRepository(repository)
    setFunctionModalOpen(true)
  }

  const handleFunctionSubmit = async (functionData: {
    function: QueueFunction
    params: Record<string, any>
    priority: number
    description: string
  }) => {
    if (!selectedRepository) return

    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === selectedRepository.name)
      
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: selectedRepository.name }))
        setFunctionModalOpen(false)
        setSelectedRepository(null)
        return
      }
      
      // Build queue vault
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: functionData.params,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'machine-repository-list',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: repositoryData.vaultContent
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: functionData.priority
      })
      
      setFunctionModalOpen(false)
      setSelectedRepository(null)
      
      if (response?.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'))
        setQueueTraceModal({ visible: true, taskId: response.taskId })
      } else if (response?.isQueued) {
        // Item was queued for highest priority management
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error) {
      // Error is handled by the mutation
      showMessage('error', t('resources:repositories.failedToCreateQueueItem'))
    }
  }

  const columns: ColumnsType<Repository> = [
    {
      title: t('resources:repositories.repositoryName'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => (
        <Space>
          <InboxOutlined style={{ color: '#556b2f' }} />
          <strong>{name}</strong>
        </Space>
      ),
    },
    {
      title: t('resources:repositories.size'),
      dataIndex: 'size_human',
      key: 'size_human',
      width: 100,
      render: (size: string) => <Text>{size}</Text>,
    },
    {
      title: t('resources:repositories.status'),
      key: 'status',
      width: 250,
      render: (_: any, record: Repository) => (
        <Space direction="vertical" size={0}>
          <Space>
            {record.repo_exists ? (
              <Tag icon={<CheckCircleOutlined />} color="success">
                {t('resources:repositories.exists')}
              </Tag>
            ) : (
              <Tag icon={<CloseCircleOutlined />} color="error">
                {t('resources:repositories.notFound')}
              </Tag>
            )}
            {record.mounted && (
              <Tag color="blue">{t('resources:repositories.mounted')}</Tag>
            )}
          </Space>
          {record.mounted && record.mount_path && (
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('resources:repositories.mountPath')}: {record.mount_path}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: t('resources:repositories.lastModified'),
      dataIndex: 'modified_human',
      key: 'modified_human',
      width: 200,
      render: (modified: string) => <Text type="secondary">{modified}</Text>,
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 100,
      render: (_: any, record: Repository) => (
        record.repo_exists ? (
          <Button
            type="primary"
            size="small"
            icon={<FunctionOutlined />}
            onClick={() => handleRunFunction(record)}
          >
            {t('machines:remote')}
          </Button>
        ) : null
      ),
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <Spin tip={
          isQueued 
            ? t('resources:repositories.waitingInQueue')
            : t('resources:repositories.fetchingRepositories')
        } />
        {isQueued && queueId && (
          <div style={{ marginTop: 20 }}>
            <Text type="secondary">{t('resources:repositories.queuePosition')}: {managedQueueMutation.getQueuePosition?.(queueId) || '...'}</Text>
            <br />
            <Text type="secondary">{t('resources:repositories.checkQueueManager')}</Text>
          </div>
        )}
        {taskId && (
          <div style={{ marginTop: 20 }}>
            <Text type="secondary">Task ID: {taskId}</Text>
            <br />
            <Text type="secondary">
              {t('common:status.label')}: {traceData?.queueDetails?.status || t('common:status.initializing')}
              {traceData?.queueDetails?.status === 'PENDING' && ` (${t('common:status.waitingForExecution')})`}
              {traceData?.queueDetails?.status === 'ASSIGNED' && ` (${t('common:status.processing')})`}
              {traceData?.queueDetails?.status === 'PROCESSING' && ` (${t('common:status.running')})`}
            </Text>
          </div>
        )}
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '20px' }}>
        <Alert
          message={t('common:messages.error')}
          description={error}
          type="error"
          showIcon
          action={
            <Button size="small" onClick={fetchRepositories}>
              {t('common:actions.retry')}
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div style={{ padding: '0 20px 20px 20px' }}>
      <Table
        columns={columns}
        dataSource={repositories}
        rowKey="name"
        size="small"
        pagination={false}
        locale={{
          emptyText: t('resources:repositories.noRepositories')
        }}
      />
      
      {/* Function Selection Modal */}
      <FunctionSelectionModal
        open={functionModalOpen}
        onCancel={() => {
          setFunctionModalOpen(false)
          setSelectedRepository(null)
        }}
        onSubmit={handleFunctionSubmit}
        title={t('machines:runFunction')}
        subtitle={
          selectedRepository && (
            <Space>
              <Text>{t('resources:repositories.repository')}:</Text>
              <Tag color="#8FBC8F">{selectedRepository.name}</Tag>
              <Text>•</Text>
              <Text>{t('machines:machine')}:</Text>
              <Tag color="#556b2f">{machine.machineName}</Tag>
            </Space>
          )
        }
        allowedCategories={['repository', 'backup', 'network']}
        loading={managedQueueMutation.isPending}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repo', 'grand']}
        defaultParams={{ 
          repo: (() => {
            const repo = teamRepositories.find(r => r.repositoryName === selectedRepository?.name);
            return repo?.repositoryGuid || '';
          })(),
          grand: teamRepositories.find(r => r.repositoryName === selectedRepository?.name)?.grandGuid || ''
        }}
      />
      
      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => setQueueTraceModal({ visible: false, taskId: null })}
      />
    </div>
  )
}