import React, { useEffect, useState } from 'react'
import { Table, Spin, Alert, Tag, Space, Typography, Button } from 'antd'
import { InboxOutlined, CheckCircleOutlined, CloseCircleOutlined, FunctionOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useCreateQueueItem, type QueueFunction } from '@/api/queries/queue'
import { useQueueItemTrace } from '@/api/queries/queue'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories } from '@/api/queries/repositories'
import type { ColumnsType } from 'antd/es/table'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'
import { useDropdownData } from '@/api/queries/useDropdownData'

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
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [functionModalOpen, setFunctionModalOpen] = useState(false)
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null })
  
  const createQueueItemMutation = useCreateQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading } = useRepositories(machine.teamName)
  const { data: dropdownData } = useDropdownData()
  
  // Use queue trace to monitor the task
  const { data: traceData } = useQueueItemTrace(taskId, !!taskId)

  useEffect(() => {
    // Only fetch when repositories are loaded
    if (!repositoriesLoading && machine) {
      fetchRepositories()
    }
  }, [machine, repositoriesLoading])

  useEffect(() => {
    // Check if task is completed
    if (traceData?.queueDetails?.status === 'COMPLETED' && traceData?.responseVaultContent?.vaultContent) {
      try {
        // Parse the response vault content
        const vaultContent = JSON.parse(traceData.responseVaultContent.vaultContent)
        
        // The result is nested in the response
        if (vaultContent.result) {
          const result = JSON.parse(vaultContent.result)
          
          // Parse the command output which contains the repositories
          if (result.command_output) {
            const commandOutput = JSON.parse(result.command_output)
            
            
            if (commandOutput.repositories && Array.isArray(commandOutput.repositories)) {
              setRepositories(commandOutput.repositories)
            } else {
              setRepositories([])
            }
          } else {
            setRepositories([])
          }
        } else {
          setError('Invalid response format')
        }
        setLoading(false)
      } catch (err) {
        console.error('Error parsing repository data:', err)
        setError('Failed to parse repository data')
        setLoading(false)
      }
    } else if (traceData?.queueDetails?.status === 'FAILED' || traceData?.queueDetails?.permanentlyFailed) {
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
            console.warn('[MachineRepositoryList] Failed to parse repository vault:', {
              repositoryName: repo.repositoryName,
              repositoryGuid: repo.repositoryGuid,
              error: e
            })
          }
        }
      })
      
      console.log('[MachineRepositoryList] Built repository credentials:', {
        repositories: teamRepositories.map(r => ({ 
          name: r.repositoryName, 
          guid: r.repositoryGuid 
        })),
        credentialKeys: Object.keys(allRepositoryCredentials)
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
      
      const response = await createQueueItemMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 1
      })
      
      if (response?.taskId) {
        setTaskId(response.taskId)
      } else {
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
      
      console.log('[MachineRepositoryList] Selected repository for function:', {
        selectedRepositoryName: selectedRepository.name,
        foundRepositoryData: repositoryData,
        repositoryGuid: repositoryData?.repositoryGuid
      })
      
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
      
      const response = await createQueueItemMutation.mutateAsync({
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
      }
    } catch (error) {
      // Error is handled by the mutation
      showMessage('error', t('common:errors.failedToCreateQueueItem'))
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
      width: 200,
      render: (_: any, record: Repository) => (
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
            {t('machines:run')}
          </Button>
        ) : null
      ),
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <Spin tip={t('resources:repositories.fetchingRepositories')} />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '20px' }}>
        <Alert
          message={t('common:errors.error')}
          description={error}
          type="error"
          showIcon
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
        loading={createQueueItemMutation.isPending}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repo', 'grand']}
        defaultParams={{ 
          repo: (() => {
            const repo = teamRepositories.find(r => r.repositoryName === selectedRepository?.name);
            console.log('[MachineRepositoryList] Setting default params:', {
              selectedRepositoryName: selectedRepository?.name,
              foundRepo: repo,
              repositoryGuid: repo?.repositoryGuid,
              allRepositories: teamRepositories.map(r => ({ 
                name: r.repositoryName, 
                guid: r.repositoryGuid 
              }))
            });
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