import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Empty, Modal, Space, Tag, Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTheme } from 'styled-components'
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  HistoryOutlined,
  InboxOutlined
} from '@/utils/optimizedIcons'
import { RootState } from '@/store/store'
import UnifiedResourceModal, { ResourceType } from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import TeamSelector from '@/components/common/TeamSelector'
import { useTeams, Team } from '@/api/queries/teams'
import {
  useRepositories,
  useCreateRepository,
  useUpdateRepositoryName,
  useDeleteRepository,
  useUpdateRepositoryVault,
  Repository
} from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation'
import { useQueueAction } from '@/hooks/useQueueAction'
import { showMessage } from '@/utils/messages'
import { QueueFunction } from '@/api/queries/queue'
import {
  PageWrapper,
  PageCard,
  HeaderSection,
  HeaderRow,
  TeamControls,
  TeamSelectorWrapper,
  ButtonGroup,
  ActionButton,
  ContentSection,
  DataTable
} from './styles'
import { featureFlags } from '@/config/featureFlags'

interface CredentialsLocationState {
  createRepository?: boolean
  selectedTeam?: string
  selectedMachine?: string
  selectedTemplate?: string
}

const CredentialsPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const theme = useTheme()
  const [modal, contextHolder] = Modal.useModal()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const location = useLocation()
  const navigate = useNavigate()

  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [currentResource, setCurrentResource] = useState<Repository | null>(null)
  const [repositoryPageSize, setRepositoryPageSize] = useState(15)
  const [repositoryPage, setRepositoryPage] = useState(1)
  const [queueTraceModal, setQueueTraceModal] = useState<{ visible: boolean; taskId: string | null; machineName?: string | null }>({
    visible: false,
    taskId: null,
    machineName: null
  })
  const [auditTraceModal, setAuditTraceModal] = useState<{ open: boolean; entityType: string | null; entityIdentifier: string | null; entityName?: string }>({
    open: false,
    entityType: null,
    entityIdentifier: null
  })

  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    resourceType: ResourceType
    mode: 'create' | 'edit' | 'vault'
    data?: Repository | null
    creationContext?: 'credentials-only' | 'normal'
  }>({
    open: false,
    resourceType: 'repository',
    mode: 'create'
  })

  const hasInitializedTeam = useRef(false)

  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList: Team[] = teams || []

  const { data: dropdownData } = useDropdownData()

  const { data: repositories = [], isLoading: repositoriesLoading, refetch: refetchRepositories } = useRepositories(
    selectedTeams.length > 0 ? selectedTeams : undefined
  )

  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  )

  const { data: storages = [] } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined)

  const createRepositoryMutation = useCreateRepository()
  const updateRepositoryNameMutation = useUpdateRepositoryName()
  const deleteRepositoryMutation = useDeleteRepository()
  const updateRepositoryVaultMutation = useUpdateRepositoryVault()

  const { createRepository: createRepositoryWithQueue, isCreating } = useRepositoryCreation(machines)
  const { executeAction, isExecuting } = useQueueAction()

  const originalRepositories = useMemo(
    () =>
      repositories.filter((repo) => !repo.grandGuid || repo.grandGuid === repo.repositoryGuid),
    [repositories]
  )

  const openUnifiedModal = useCallback(
    (mode: 'create' | 'edit' | 'vault', data?: Repository | null, creationContext?: 'credentials-only' | 'normal') => {
      setUnifiedModalState({
        open: true,
        resourceType: 'repository',
        mode,
        data,
        creationContext
      })
      if (data) {
        setCurrentResource(data)
      }
    },
    []
  )

  const closeUnifiedModal = useCallback(() => {
    setUnifiedModalState({
      open: false,
      resourceType: 'repository',
      mode: 'create'
    })
    setCurrentResource(null)
  }, [])

  const handleDeleteRepository = useCallback(
    (repository: Repository) => {
      modal.confirm({
        title: t('repositories.deleteRepository'),
        content: t('repositories.confirmDelete', { repositoryName: repository.repositoryName }),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: async () => {
          try {
            await deleteRepositoryMutation.mutateAsync({
              teamName: repository.teamName,
              repositoryName: repository.repositoryName
            } as any)
            showMessage('success', t('repositories.deleteSuccess'))
            refetchRepositories()
          } catch (error) {
            showMessage('error', t('repositories.deleteError'))
          }
        }
      })
    },
    [deleteRepositoryMutation, modal, refetchRepositories, t]
  )

  const handleUnifiedModalSubmit = useCallback(
    async (data: any) => {
      try {
        if (unifiedModalState.mode === 'create') {
          const result = await createRepositoryWithQueue(data)

          if (result.success) {
            closeUnifiedModal()

            if (result.taskId) {
              setQueueTraceModal({
                visible: true,
                taskId: result.taskId,
                machineName: result.machineName
              })
            } else {
              refetchRepositories()
            }
          } else {
            showMessage('error', result.error || t('repositories.failedToCreateRepository'))
          }
        } else if (currentResource) {
          const currentName = currentResource.repositoryName
          const newName = data.repositoryName

          if (newName && newName !== currentName) {
            await updateRepositoryNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentRepositoryName: currentName,
              newRepositoryName: newName
            } as any)
          }

          const vaultData = data.repositoryVault
          if (vaultData && vaultData !== currentResource.vaultContent) {
            await updateRepositoryVaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              repositoryName: newName || currentName,
              repositoryVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1
            } as any)
          }

          closeUnifiedModal()
          refetchRepositories()
        }
      } catch (error) {
        showMessage('error', t('repositories.failedToCreateRepository'))
      }
    },
    [
      closeUnifiedModal,
      createRepositoryWithQueue,
      currentResource,
      refetchRepositories,
      t,
      unifiedModalState.mode,
      updateRepositoryNameMutation,
      updateRepositoryVaultMutation
    ]
  )

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return
      try {
        await updateRepositoryVaultMutation.mutateAsync({
          teamName: currentResource.teamName,
          repositoryName: currentResource.repositoryName,
          repositoryVault: vault,
          vaultVersion: version
        } as any)
        refetchRepositories()
        closeUnifiedModal()
      } catch (error) {
        // Error handled by mutation toast
      }
    },
    [closeUnifiedModal, currentResource, refetchRepositories, t, updateRepositoryVaultMutation]
  )

  const handleRepositoryFunctionSelected = useCallback(
    async (functionData: {
      function: QueueFunction
      params: Record<string, any>
      priority: number
      description: string
      selectedMachine?: string
    }) => {
      if (!currentResource) return
      try {
        if (!functionData.selectedMachine) {
          showMessage('error', t('resources:errors.machineNotFound'))
          return
        }

        const teamEntry = dropdownData?.machinesByTeam?.find((team) => team.teamName === currentResource.teamName)
        const machineEntry = teamEntry?.machines?.find((machine) => machine.value === functionData.selectedMachine)

        if (!machineEntry) {
          showMessage('error', t('resources:errors.machineNotFound'))
          return
        }

        const selectedMachine = machines.find(
          (machine) => machine.machineName === machineEntry.value && machine.teamName === currentResource.teamName
        )

        const queuePayload: any = {
          teamName: currentResource.teamName,
          machineName: machineEntry.value,
          bridgeName: machineEntry.bridgeName,
          functionName: functionData.function.name,
          params: functionData.params,
          priority: functionData.priority,
          description: functionData.description,
          addedVia: 'repository-table',
          teamVault: teamsList.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
          repositoryGuid: currentResource.repositoryGuid,
          repositoryVault: currentResource.vaultContent || '{}',
          repositoryLoopbackIp: currentResource.repoLoopbackIp,
          repositoryNetworkMode: currentResource.repoNetworkMode,
          repositoryTag: currentResource.repoTag,
          machineVault: selectedMachine?.vaultContent || '{}'
        }

        if (functionData.function.name === 'pull') {
          if (functionData.params.sourceType === 'machine' && functionData.params.from) {
            const sourceMachine = machines.find((machine) => machine.machineName === functionData.params.from)
            if (sourceMachine?.vaultContent) {
              queuePayload.sourceMachineVault = sourceMachine.vaultContent
            }
          }

          if (functionData.params.sourceType === 'storage' && functionData.params.from) {
            const sourceStorage = storages.find((storage) => storage.storageName === functionData.params.from)
            if (sourceStorage?.vaultContent) {
              queuePayload.sourceStorageVault = sourceStorage.vaultContent
            }
          }
        }

        const result = await executeAction(queuePayload)
        closeUnifiedModal()

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('repositories.queueItemCreated'))
            setQueueTraceModal({ visible: true, taskId: result.taskId, machineName: machineEntry.value })
          } else if (result.isQueued) {
            showMessage('info', t('resources:messages.highestPriorityQueued', { resourceType: 'repository' }))
          }
        } else {
          showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'))
        }
      } catch (error) {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'))
      }
    },
    [closeUnifiedModal, currentResource, dropdownData, executeAction, machines, storages, t, teamsList]
  )

  const isSubmitting =
    createRepositoryMutation.isPending ||
    updateRepositoryNameMutation.isPending ||
    isCreating ||
    isExecuting

  const isUpdatingVault = updateRepositoryVaultMutation.isPending

  useEffect(() => {
    if (!teamsLoading && !hasInitializedTeam.current && teamsList.length > 0) {
      hasInitializedTeam.current = true
      if (uiMode === 'simple') {
        const privateTeam = teamsList.find((team) => team.teamName === 'Private Team')
        setSelectedTeams([privateTeam?.teamName || teamsList[0].teamName])
      } else {
        setSelectedTeams([teamsList[0].teamName])
      }
    }
  }, [teamsLoading, teamsList, uiMode])

  useEffect(() => {
    const state = location.state as CredentialsLocationState | null
    if (state?.createRepository) {
      if (state.selectedTeam) {
        setSelectedTeams([state.selectedTeam])
      }

      setTimeout(() => {
        openUnifiedModal('create', {
          teamName: state.selectedTeam,
          machineName: state.selectedMachine,
          preselectedTemplate: state.selectedTemplate
        } as any, 'credentials-only')
      }, 100)

      navigate(location.pathname, { replace: true })
    }
  }, [location, navigate, openUnifiedModal])

  const repositoryColumns = useMemo(
    () => [
      {
        title: t('repositories.repositoryName'),
        dataIndex: 'repositoryName',
        key: 'repositoryName',
        ellipsis: true,
        render: (text: string) => (
          <Space>
            <InboxOutlined style={{ color: theme.colors.primary }} />
            <strong>{text}</strong>
          </Space>
        )
      },
      {
        title: t('general.team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: 150,
        ellipsis: true,
        render: (teamName: string) => <Tag color={theme.colors.secondary}>{teamName}</Tag>
      },
      ...(featureFlags.isEnabled('vaultVersionColumns')
        ? [
            {
              title: t('general.vaultVersion'),
              dataIndex: 'vaultVersion',
              key: 'vaultVersion',
              width: 120,
              align: 'center' as const,
              render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>
            }
          ]
        : []),
      {
        title: t('common:table.actions'),
        key: 'actions',
        width: 280,
        render: (_: any, record: Repository) => (
          <Space size="small">
            <Tooltip title={t('common:actions.edit')}>
              <ActionButton
                type="primary"
                size="small"
                icon={<EditOutlined />}
                data-testid={`resources-repository-edit-${record.repositoryName}`}
                onClick={() => openUnifiedModal('edit', record)}
                aria-label={t('common:actions.edit')}
              />
            </Tooltip>
            <Tooltip title={t('machines:trace')}>
              <ActionButton
                type="primary"
                size="small"
                icon={<HistoryOutlined />}
                data-testid={`resources-repository-trace-${record.repositoryName}`}
                onClick={() =>
                  setAuditTraceModal({
                    open: true,
                    entityType: 'Repo',
                    entityIdentifier: record.repositoryName,
                    entityName: record.repositoryName
                  })
                }
                aria-label={t('machines:trace')}
              />
            </Tooltip>
            <Tooltip title={t('common:actions.delete')}>
              <ActionButton
                type="primary"
                danger
                size="small"
                icon={<DeleteOutlined />}
                data-testid={`resources-repository-delete-${record.repositoryName}`}
                onClick={() => handleDeleteRepository(record)}
                aria-label={t('common:actions.delete')}
              />
            </Tooltip>
          </Space>
        )
      }
    ],
    [handleDeleteRepository, openUnifiedModal, setAuditTraceModal, t, theme.colors.primary, theme.colors.secondary]
  )

  return (
    <>
      <PageWrapper>
        <PageCard>
          <HeaderSection>
            <HeaderRow>
              <TeamControls>
                <TeamSelectorWrapper>
                  <TeamSelector
                    data-testid="resources-team-selector"
                    teams={teamsList}
                    selectedTeams={selectedTeams}
                    onChange={setSelectedTeams}
                    loading={teamsLoading}
                    placeholder={t('teams.selectTeamToView')}
                    style={{ width: '100%' }}
                  />
                </TeamSelectorWrapper>
              </TeamControls>
              {selectedTeams.length > 0 && (
                <ButtonGroup>
                  <Tooltip title={t('repositories.createRepository')}>
                    <ActionButton
                      type="primary"
                      icon={<PlusOutlined />}
                      data-testid="resources-create-repositorie-button"
                      onClick={() => openUnifiedModal('create', undefined, 'credentials-only')}
                      aria-label={t('repositories.createRepository')}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:actions.refresh')}>
                    <ActionButton
                      icon={<ReloadOutlined />}
                      data-testid="resources-refresh-button"
                      onClick={() => refetchRepositories()}
                      aria-label={t('common:actions.refresh')}
                    />
                  </Tooltip>
                </ButtonGroup>
              )}
            </HeaderRow>
          </HeaderSection>

          <ContentSection>
            {selectedTeams.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('teams.selectTeamPrompt')}
                style={{ padding: `${theme.spacing.LG}px 0` }}
              />
            ) : (
              <DataTable
                data-testid="resources-repository-table"
                columns={repositoryColumns}
                dataSource={originalRepositories}
                rowKey="repositoryName"
                scroll={{ x: 'max-content' }}
                loading={repositoriesLoading}
                $isLoading={repositoriesLoading}
                pagination={{
                  current: repositoryPage,
                  pageSize: repositoryPageSize,
                  total: originalRepositories.length,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total, range) =>
                    `${t('common:general.showingRecords', { start: range[0], end: range[1], total })}`,
                  onChange: (page, size) => {
                    setRepositoryPage(page)
                    if (size && size !== repositoryPageSize) {
                      setRepositoryPageSize(size)
                      setRepositoryPage(1)
                    }
                  },
                  position: ['bottomRight']
                }}
              />
            )}
          </ContentSection>
        </PageCard>
      </PageWrapper>

      <UnifiedResourceModal
        data-testid="resources-repository-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="repository"
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data || currentResource || undefined}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        creationContext={unifiedModalState.creationContext}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={unifiedModalState.mode === 'create' ? undefined : handleRepositoryFunctionSelected}
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['repository', 'backup', 'network']}
        hiddenParams={['repo', 'grand']}
        defaultParams={
          currentResource
            ? { repo: currentResource.repositoryGuid, grand: currentResource.grandGuid || '' }
            : {}
        }
      />

      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null, machineName: null })
          refetchRepositories()
        }}
      />

      <AuditTraceModal
        data-testid="resources-audit-trace-modal"
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />

      {contextHolder}
    </>
  )
}

export default CredentialsPage
