import React, { useState, useRef, useCallback, useEffect } from 'react'
import { Empty, Modal, Tooltip } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { PlusOutlined, WifiOutlined, ReloadOutlined } from '@/utils/optimizedIcons'
import { RootState } from '@/store/store'
import UnifiedResourceModal, { ResourceType } from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import ConnectivityTestModal from '@/components/common/ConnectivityTestModal'
import { showMessage } from '@/utils/messages'
import { useTeams, Team } from '@/api/queries/teams'
import { SplitResourceView } from '@/components/resources/SplitResourceView'
import {
  useCreateMachine,
  useUpdateMachineName,
  useUpdateMachineBridge,
  useUpdateMachineVault,
  useDeleteMachine,
  useMachines
} from '@/api/queries/machines'
import { useRepositories, Repository } from '@/api/queries/repositories'
import { useStorage } from '@/api/queries/storage'
import { useQueueAction } from '@/hooks/useQueueAction'
import TeamSelector from '@/components/common/TeamSelector'
import { type Machine } from '@/types'
import { QueueFunction } from '@/api/queries/queue'
import { useTheme } from 'styled-components'
import {
  PageWrapper,
  PageCard,
  HeaderSection,
  HeaderRow,
  TeamControls,
  TeamSelectorWrapper,
  ButtonGroup,
  ActionButton,
  ContentSection
} from './styles'

interface UnifiedState {
  open: boolean
  resourceType: ResourceType
  mode: 'create' | 'edit' | 'vault'
  data?: Machine | null
  preselectedFunction?: string
  creationContext?: 'credentials-only' | 'normal'
}

const MachinesPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const [modal, contextHolder] = Modal.useModal()
  const location = useLocation()
  const navigate = useNavigate()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const theme = useTheme()

  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null)
  const [selectedRepositoryFromMachine, setSelectedRepositoryFromMachine] = useState<Repository | null>(null)
  const [selectedContainerFromMachine, setSelectedContainerFromMachine] = useState<any | null>(null)
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true)
  const [currentResource, setCurrentResource] = useState<Machine | null>(null)
  const [refreshKeys, setRefreshKeys] = useState<Record<string, number>>({})
  const [queueTraceModal, setQueueTraceModal] = useState<{ visible: boolean; taskId: string | null; machineName?: string | null }>({
    visible: false,
    taskId: null,
    machineName: null
  })
  const [connectivityTestModal, setConnectivityTestModal] = useState(false)

  const [unifiedModalState, setUnifiedModalState] = useState<UnifiedState>({
    open: false,
    resourceType: 'machine',
    mode: 'create'
  })

  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList: Team[] = teams || []

  const { data: machines = [], refetch: refetchMachines } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  )
  const { data: repositories = [] } = useRepositories(selectedTeams.length > 0 ? selectedTeams : undefined)
  const { data: storages = [] } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined)

  const createMachineMutation = useCreateMachine()
  const updateMachineNameMutation = useUpdateMachineName()
  const updateMachineBridgeMutation = useUpdateMachineBridge()
  const deleteMachineMutation = useDeleteMachine()
  const updateMachineVaultMutation = useUpdateMachineVault()
  const { executeAction, isExecuting } = useQueueAction()

  const hasInitializedTeam = useRef(false)

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
    const state = location.state as any
    if (state?.createRepository) {
      navigate('/credentials', { state, replace: true })
    }
  }, [location, navigate])

  const openUnifiedModal = useCallback(
    (mode: 'create' | 'edit' | 'vault', data?: Machine | null, preselectedFunction?: string) => {
      setUnifiedModalState({
        open: true,
        resourceType: 'machine',
        mode,
        data,
        preselectedFunction
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
      resourceType: 'machine',
      mode: 'create'
    })
    setCurrentResource(null)
  }, [])

  const handleMachineSelect = (machine: Machine | null) => {
    setSelectedMachine(machine)
    if (machine) {
      setSelectedRepositoryFromMachine(null)
      setSelectedContainerFromMachine(null)
      setIsPanelCollapsed(false)
    }
  }

  const handleTogglePanelCollapse = () => {
    setIsPanelCollapsed((prev) => !prev)
  }

  const handleDeleteMachine = useCallback(
    (machine: Machine) => {
      const machineName = machine.machineName
      modal.confirm({
        title: t('machines:confirmDelete') as string,
        content: t('machines:deleteWarning', { name: machineName, machineName }) as string,
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: async () => {
          try {
            await deleteMachineMutation.mutateAsync({
              teamName: machine.teamName,
              machineName
            } as any)
            refetchMachines()
            showMessage('success', t('machines:deleteSuccess'))
          } catch (error) {
            showMessage('error', t('machines:deleteError'))
          }
        }
      })
    },
    [deleteMachineMutation, modal, refetchMachines, t]
  )

  const handleUnifiedModalSubmit = useCallback(
    async (formData: any) => {
      try {
        if (unifiedModalState.mode === 'create') {
          const { autoSetup, ...machineData } = formData
          await createMachineMutation.mutateAsync(machineData)
          showMessage('success', t('machines:createSuccess'))

          if (autoSetup) {
            try {
              await new Promise((resolve) => setTimeout(resolve, 500))
              const result = await executeAction({
                teamName: formData.teamName,
                machineName: formData.machineName,
                bridgeName: formData.bridgeName,
                functionName: 'setup',
                params: {
                  datastore_size: '95%',
                  source: 'apt-repo',
                  rclone_source: 'install-script',
                  docker_source: 'docker-repo',
                  install_amd_driver: 'auto',
                  install_nvidia_driver: 'auto'
                },
                priority: 3,
                description: `Auto-setup for machine ${formData.machineName}`,
                addedVia: 'machine-creation-auto-setup',
                machineVault: formData.machineVault || '{}'
              })

              if (result.success) {
                if (result.taskId) {
                  showMessage('info', t('machines:setupQueued'))
                  setQueueTraceModal({ visible: true, taskId: result.taskId, machineName: formData.machineName })
                } else if (result.isQueued) {
                  showMessage('info', t('machines:setupQueuedForSubmission'))
                }
              }
            } catch (error) {
              showMessage('warning', t('machines:machineCreatedButSetupFailed'))
            }
          }

          closeUnifiedModal()
          refetchMachines()
        } else if (currentResource) {
          const currentName = currentResource.machineName
          const newName = formData.machineName

          if (newName && newName !== currentName) {
            await updateMachineNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentMachineName: currentName,
              newMachineName: newName
            } as any)
          }

          if (formData.bridgeName && formData.bridgeName !== currentResource.bridgeName) {
            await updateMachineBridgeMutation.mutateAsync({
              teamName: currentResource.teamName,
              machineName: newName || currentName,
              newBridgeName: formData.bridgeName
            })
          }

          const vaultData = formData.machineVault
          if (vaultData && vaultData !== currentResource.vaultContent) {
            await updateMachineVaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              machineName: newName || currentName,
              machineVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1
            } as any)
          }

          closeUnifiedModal()
          refetchMachines()
        }
      } catch (error) {
        // Errors surfaced via mutation toasts
      }
    },
    [
      closeUnifiedModal,
      createMachineMutation,
      currentResource,
      executeAction,
      refetchMachines,
      t,
      unifiedModalState.mode,
      updateMachineBridgeMutation,
      updateMachineNameMutation,
      updateMachineVaultMutation
    ]
  )

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return
      try {
        await updateMachineVaultMutation.mutateAsync({
          teamName: currentResource.teamName,
          machineName: currentResource.machineName,
          machineVault: vault,
          vaultVersion: version
        } as any)
        closeUnifiedModal()
        refetchMachines()
      } catch (error) {
        // Error handled by mutation toast
      }
    },
    [closeUnifiedModal, currentResource, refetchMachines, updateMachineVaultMutation]
  )

  const handleMachineFunctionSelected = useCallback(
    async (functionData: {
      function: QueueFunction
      params: Record<string, any>
      priority: number
      description: string
    }) => {
      if (!currentResource) return

      try {
        const machineName = currentResource.machineName
        const bridgeName = currentResource.bridgeName
        const teamData = teamsList.find((team) => team.teamName === currentResource.teamName)

        const queuePayload: any = {
          teamName: currentResource.teamName,
          machineName,
          bridgeName,
          functionName: functionData.function.name,
          params: functionData.params,
          priority: functionData.priority,
          description: functionData.description,
          addedVia: 'machine-table',
          teamVault: teamData?.vaultContent || '{}',
          machineVault: currentResource.vaultContent || '{}'
        }

        if (functionData.params.repo) {
          const repository = repositories.find((repo) => repo.repositoryGuid === functionData.params.repo)
          queuePayload.repositoryGuid = repository?.repositoryGuid || functionData.params.repo
          queuePayload.repositoryVault = repository?.vaultContent || '{}'
        } else {
          queuePayload.repositoryVault = '{}'
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
            showMessage('success', t('machines:queueItemCreated'))
            setQueueTraceModal({ visible: true, taskId: result.taskId, machineName })
          } else if (result.isQueued) {
            showMessage('info', t('resources:messages.highestPriorityQueued', { resourceType: 'machine' }))
          }
        } else {
          showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'))
        }
      } catch (error) {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'))
      }
    },
    [closeUnifiedModal, currentResource, executeAction, machines, repositories, storages, t, teamsList]
  )

  const handleResourceSelection = (resource: Machine | Repository | any | null) => {
    if (resource && 'machineName' in resource) {
      handleMachineSelect(resource as Machine)
    } else if (resource && 'repositoryName' in resource) {
      handleMachineSelect(null)
      setSelectedRepositoryFromMachine(resource as Repository)
      setSelectedContainerFromMachine(null)
      setIsPanelCollapsed(false)
    } else if (resource && 'id' in resource && 'state' in resource) {
      handleMachineSelect(null)
      setSelectedRepositoryFromMachine(null)
      setSelectedContainerFromMachine(resource)
      setIsPanelCollapsed(false)
    } else {
      handleMachineSelect(null)
      setSelectedRepositoryFromMachine(null)
      setSelectedContainerFromMachine(null)
    }
  }

  const handleRefreshMachines = () => {
    refetchMachines()
    setRefreshKeys((prev) => ({
      ...prev,
      _global: Date.now()
    }))
  }

  const isSubmitting =
    createMachineMutation.isPending ||
    updateMachineNameMutation.isPending ||
    updateMachineBridgeMutation.isPending ||
    isExecuting

  const isUpdatingVault = updateMachineVaultMutation.isPending

  return (
    <>
      <PageWrapper>
        <PageCard>
          <HeaderSection>
            <HeaderRow>
              <TeamControls>
                <TeamSelectorWrapper>
                  <TeamSelector
                    data-testid="machines-team-selector"
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
                  <Tooltip title={t('machines:createMachine')}>
                    <ActionButton
                      type="primary"
                      icon={<PlusOutlined />}
                      data-testid="machines-create-machine-button"
                      onClick={() => openUnifiedModal('create')}
                      aria-label={t('machines:createMachine')}
                    />
                  </Tooltip>
                  <Tooltip title={t('machines:connectivityTest')}>
                    <ActionButton
                      icon={<WifiOutlined />}
                      data-testid="machines-connectivity-test-button"
                      onClick={() => setConnectivityTestModal(true)}
                      disabled={machines.length === 0}
                      aria-label={t('machines:connectivityTest')}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:actions.refresh')}>
                    <ActionButton
                      icon={<ReloadOutlined />}
                      data-testid="machines-refresh-button"
                      onClick={handleRefreshMachines}
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
              <SplitResourceView
                type="machine"
                teamFilter={selectedTeams}
                showFilters
                showActions
                onCreateMachine={() => openUnifiedModal('create')}
                onEditMachine={(machine) => openUnifiedModal('edit', machine)}
                onVaultMachine={(machine) => openUnifiedModal('vault', machine)}
                onFunctionsMachine={(machine, functionName) => {
                  openUnifiedModal('create', machine, functionName)
                  setRefreshKeys((prev) => ({
                    ...prev,
                    [machine.machineName]: Date.now()
                  }))
                }}
                onDeleteMachine={handleDeleteMachine}
                enabled={selectedTeams.length > 0}
                refreshKeys={refreshKeys}
                onQueueItemCreated={(taskId, machineName) => {
                  setQueueTraceModal({ visible: true, taskId, machineName })
                }}
                selectedResource={selectedMachine || selectedRepositoryFromMachine || selectedContainerFromMachine}
                onResourceSelect={handleResourceSelection}
                isPanelCollapsed={isPanelCollapsed}
                onTogglePanelCollapse={handleTogglePanelCollapse}
              />
            )}
          </ContentSection>
        </PageCard>
      </PageWrapper>

      <UnifiedResourceModal
        data-testid="machines-machine-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="machine"
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data || currentResource || undefined}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        preselectedFunction={unifiedModalState.preselectedFunction}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={handleMachineFunctionSelected}
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['machine', 'backup']}
        hiddenParams={[]}
        defaultParams={{}}
      />

      <QueueItemTraceModal
        data-testid="machines-queue-trace-modal"
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null, machineName: null })
          if (queueTraceModal.machineName) {
            setRefreshKeys((prev) => ({
              ...prev,
              [queueTraceModal.machineName as string]: Date.now()
            }))
          }
          refetchMachines()
        }}
      />

      <ConnectivityTestModal
        data-testid="machines-connectivity-test-modal"
        open={connectivityTestModal}
        onClose={() => setConnectivityTestModal(false)}
        machines={machines}
        teamFilter={selectedTeams}
      />

      {contextHolder}
    </>
  )
}

export default MachinesPage
