import React, { useCallback, useEffect, useMemo } from 'react'
import { Alert, Empty, Modal, Space, Tag, Tooltip, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTheme } from 'styled-components'
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  HistoryOutlined,
  InboxOutlined,
  WarningOutlined
} from '@/utils/optimizedIcons'

const { Text } = Typography
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import TeamSelector from '@/components/common/TeamSelector'
import { ActionButtonGroup, ActionButtonConfig } from '@/components/common/ActionButtonGroup'
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
import {
  useUnifiedModal,
  useTeamSelection,
  usePagination,
  useTraceModal,
  useQueueTraceModal,
  useAsyncAction,
} from '@/hooks'
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
import { getAffectedResources as coreGetAffectedResources } from '@/core'

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
  const location = useLocation()
  const navigate = useNavigate()

  // Use custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection()
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal
  } = useUnifiedModal<Repository>('repository')
  const { page: repositoryPage, pageSize: repositoryPageSize, setPage: setRepositoryPage, setPageSize: setRepositoryPageSize } = usePagination({ defaultPageSize: 15 })

  // Modal state management with new hooks
  const queueTrace = useQueueTraceModal()
  const auditTrace = useTraceModal()

  // Async action handler
  const { execute } = useAsyncAction()

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

  // Helper function to find affected resources when deleting a repository
  // Uses core repository relationship service
  const getAffectedResources = useCallback((repository: Repository) => {
    return coreGetAffectedResources(repository, repositories, machines)
  }, [repositories, machines])


  const handleDeleteRepository = useCallback(
    (repository: Repository) => {
      const { isCredential, forks, affectedMachines } = getAffectedResources(repository)

      // For credential deletion with machine deployments - BLOCK
      if (isCredential && affectedMachines.length > 0) {
        modal.error({
          title: t('repositories.cannotDeleteCredential'),
          content: (
            <div>
              <Text>
                {forks.length > 0
                  ? t('repositories.credentialHasDeploymentsWithForks', {
                      count: affectedMachines.length,
                      forkCount: forks.length
                    })
                  : t('repositories.credentialHasDeployments', {
                      count: affectedMachines.length
                    })
                }
              </Text>

              {forks.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Text strong>{t('repositories.affectedForks')}</Text>
                  <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 20 }}>
                    {forks.map(fork => (
                      <li key={fork.repositoryGuid}>
                        {fork.repositoryName}{fork.repoTag ? `:${fork.repoTag}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{ marginTop: 16 }}>
                <Text strong>{t('repositories.affectedMachines')}</Text>
                <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 20 }}>
                  {affectedMachines.map(machine => (
                    <li key={machine.machineName}>
                      <Text strong>{machine.machineName}</Text>
                      <Text type="secondary"> ({machine.repoNames.join(', ')})</Text>
                    </li>
                  ))}
                </ul>
              </div>

              <Alert
                type="warning"
                message={t('repositories.removeDeploymentsFirst')}
                showIcon
                icon={<WarningOutlined />}
                style={{ marginTop: 16 }}
              />
            </div>
          ),
          okText: t('common:actions.close')
        })
        return
      }

      // For fork deletion with machine deployments - WARNING but allow
      if (!isCredential && affectedMachines.length > 0) {
        modal.confirm({
          title: t('repositories.deleteRepository'),
          content: (
            <div>
              <Text>
                {t('repositories.confirmDelete', { repositoryName: repository.repositoryName })}
              </Text>

              <Alert
                type="warning"
                message={t('repositories.machinesWillLoseAccess')}
                description={
                  <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 20 }}>
                    {affectedMachines.map(machine => (
                      <li key={machine.machineName}>
                        <Text strong>{machine.machineName}</Text>
                      </li>
                    ))}
                  </ul>
                }
                showIcon
                icon={<WarningOutlined />}
                style={{ marginTop: 16 }}
              />
            </div>
          ),
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
        return
      }

      // For credential deletion without deployments or fork deletion without deployments - simple confirm
      modal.confirm({
        title: isCredential ? t('repositories.deleteCredential') : t('repositories.deleteRepository'),
        content: isCredential
          ? t('repositories.confirmDeleteCredential', { repositoryName: repository.repositoryName })
          : t('repositories.confirmDelete', { repositoryName: repository.repositoryName }),
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
    [deleteRepositoryMutation, getAffectedResources, modal, refetchRepositories, t]
  )

  const handleUnifiedModalSubmit = useCallback(
    async (data: any) => {
      await execute(
        async () => {
          if (unifiedModalState.mode === 'create') {
            const result = await createRepositoryWithQueue(data)

            if (result.success) {
              closeUnifiedModal()

              if (result.taskId) {
                queueTrace.open(result.taskId, result.machineName)
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
        },
        { skipSuccessMessage: true }
      )
    },
    [
      closeUnifiedModal,
      createRepositoryWithQueue,
      currentResource,
      execute,
      queueTrace,
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
      await execute(
        async () => {
          await updateRepositoryVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            repositoryName: currentResource.repositoryName,
            repositoryVault: vault,
            vaultVersion: version
          } as any)
          refetchRepositories()
          closeUnifiedModal()
        },
        { skipSuccessMessage: true }
      )
    },
    [closeUnifiedModal, currentResource, execute, refetchRepositories, updateRepositoryVaultMutation]
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
          teamVault: teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
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
            queueTrace.open(result.taskId, machineEntry.value)
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
    [closeUnifiedModal, currentResource, dropdownData, executeAction, machines, queueTrace, storages, t, teams]
  )

  const isSubmitting =
    createRepositoryMutation.isPending ||
    updateRepositoryNameMutation.isPending ||
    isCreating ||
    isExecuting

  const isUpdatingVault = updateRepositoryVaultMutation.isPending

  useEffect(() => {
    const state = location.state as CredentialsLocationState | null
    if (state?.createRepository) {
      if (state.selectedTeam) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
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
        width: 200,
        render: (_: unknown, record: Repository) => {
          const buttons: ActionButtonConfig<Repository>[] = [
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'common:actions.edit',
              onClick: (r: Repository) => openUnifiedModal('edit', r),
              variant: 'primary',
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'machines:trace',
              onClick: (r: Repository) =>
                auditTrace.open({
                  entityType: 'Repo',
                  entityIdentifier: r.repositoryName,
                  entityName: r.repositoryName,
                }),
              variant: 'default',
            },
            {
              type: 'delete',
              icon: <DeleteOutlined />,
              tooltip: 'common:actions.delete',
              onClick: handleDeleteRepository,
              variant: 'primary',
              danger: true,
            },
          ]

          return (
            <ActionButtonGroup<Repository>
              buttons={buttons}
              record={record}
              idField="repositoryName"
              testIdPrefix="resources-repository"
              t={t}
            />
          )
        },
      }
    ],
    [auditTrace, handleDeleteRepository, openUnifiedModal, t, theme.colors.primary, theme.colors.secondary]
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
                    teams={teams}
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
                  showTotal: (total: number, range: [number, number]) =>
                    `${t('common:general.showingRecords', { start: range[0], end: range[1], total })}`,
                  onChange: (page: number, size: number) => {
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
        existingData={(unifiedModalState.data || currentResource) as any}
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
        taskId={queueTrace.state.taskId}
        visible={queueTrace.state.visible}
        onClose={() => {
          queueTrace.close()
          refetchRepositories()
        }}
      />

      <AuditTraceModal
        data-testid="resources-audit-trace-modal"
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />

      {contextHolder}
    </>
  )
}

export default CredentialsPage
