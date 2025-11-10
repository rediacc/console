import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Empty, Modal, Space, Tag, Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { useTheme } from 'styled-components'
import {
  PlusOutlined,
  ReloadOutlined,
  ImportOutlined,
  EditOutlined,
  DeleteOutlined,
  HistoryOutlined,
  FunctionOutlined,
  CloudOutlined
} from '@/utils/optimizedIcons'
import { RootState } from '@/store/store'
import UnifiedResourceModal, { ResourceType } from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RcloneImportWizard from '@/components/resources/RcloneImportWizard'
import TeamSelector from '@/components/common/TeamSelector'
import { useTeams, Team } from '@/api/queries/teams'
import {
  useStorage,
  useCreateStorage,
  useUpdateStorageName,
  useDeleteStorage,
  useUpdateStorageVault,
  Storage
} from '@/api/queries/storage'
import { useMachines } from '@/api/queries/machines'
import { useDropdownData } from '@/api/queries/useDropdownData'
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

const StoragePage: React.FC = () => {
  const { t } = useTranslation(['resources', 'common'])
  const theme = useTheme()
  const [modal, contextHolder] = Modal.useModal()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)

  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [currentResource, setCurrentResource] = useState<Storage | null>(null)
  const [storagePageSize, setStoragePageSize] = useState(15)
  const [storagePage, setStoragePage] = useState(1)
  const [rcloneImportWizardOpen, setRcloneImportWizardOpen] = useState(false)

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
    data?: Storage | null
  }>({
    open: false,
    resourceType: 'storage',
    mode: 'create'
  })

  const hasInitializedTeam = useRef(false)

  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList: Team[] = teams || []

  const { data: storages = [], isLoading: storagesLoading, refetch: refetchStorage } = useStorage(
    selectedTeams.length > 0 ? selectedTeams : undefined
  )

  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  )

  const { data: dropdownData } = useDropdownData()
  const { executeAction, isExecuting } = useQueueAction()

  const createStorageMutation = useCreateStorage()
  const updateStorageNameMutation = useUpdateStorageName()
  const deleteStorageMutation = useDeleteStorage()
  const updateStorageVaultMutation = useUpdateStorageVault()

  const openUnifiedModal = useCallback(
    (mode: 'create' | 'edit' | 'vault', data?: Storage | null) => {
      setUnifiedModalState({
        open: true,
        resourceType: 'storage',
        mode,
        data
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
      resourceType: 'storage',
      mode: 'create'
    })
    setCurrentResource(null)
  }, [])

  const handleDeleteStorage = useCallback(
    (storage: Storage) => {
      modal.confirm({
        title: t('storage.deleteStorage'),
        content: t('storage.confirmDelete', { storageName: storage.storageName }),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: async () => {
          try {
            await deleteStorageMutation.mutateAsync({
              teamName: storage.teamName,
              storageName: storage.storageName
            } as any)
            showMessage('success', t('storage.deleteSuccess'))
            refetchStorage()
          } catch (error) {
            showMessage('error', t('storage.deleteError'))
          }
        }
      })
    },
    [deleteStorageMutation, modal, refetchStorage, t]
  )

  const handleUnifiedModalSubmit = useCallback(
    async (data: any) => {
      try {
        if (unifiedModalState.mode === 'create') {
          await createStorageMutation.mutateAsync(data)
          closeUnifiedModal()
          refetchStorage()
        } else if (currentResource) {
          const currentName = currentResource.storageName
          const newName = data.storageName

          if (newName && newName !== currentName) {
            await updateStorageNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentStorageName: currentName,
              newStorageName: newName
            } as any)
          }

          const vaultData = data.storageVault
          if (vaultData && vaultData !== currentResource.vaultContent) {
            await updateStorageVaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              storageName: newName || currentName,
              storageVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1
            } as any)
          }

          closeUnifiedModal()
          refetchStorage()
        }
      } catch (error) {
        // Error handled by mutation toast
      }
    },
    [
      closeUnifiedModal,
      createStorageMutation,
      currentResource,
      refetchStorage,
      t,
      unifiedModalState.mode,
      updateStorageNameMutation,
      updateStorageVaultMutation
    ]
  )

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return
      try {
        await updateStorageVaultMutation.mutateAsync({
          teamName: currentResource.teamName,
          storageName: currentResource.storageName,
          storageVault: vault,
          vaultVersion: version
        } as any)
        refetchStorage()
        closeUnifiedModal()
      } catch (error) {
        // Error handled via mutation toast
      }
    },
    [closeUnifiedModal, currentResource, refetchStorage, updateStorageVaultMutation]
  )

  const handleStorageFunctionSelected = useCallback(
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
          addedVia: 'storage-table',
          teamVault: teamsList.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
          storageName: currentResource.storageName,
          storageVault: currentResource.vaultContent || '{}',
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
            showMessage('success', t('storage.queueItemCreated'))
            setQueueTraceModal({ visible: true, taskId: result.taskId, machineName: machineEntry.value })
          } else if (result.isQueued) {
            showMessage('info', t('resources:messages.highestPriorityQueued', { resourceType: 'storage' }))
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
    createStorageMutation.isPending ||
    updateStorageNameMutation.isPending ||
    isExecuting

  const isUpdatingVault = updateStorageVaultMutation.isPending

  useEffect(() => {
    if (!teamsLoading && !hasInitializedTeam.current && teamsList.length > 0) {
      hasInitializedTeam.current = true
      if (uiMode === 'simple') {
        const privateTeam = teamsList.find((team) => team.teamName === 'Private Team')
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSelectedTeams([privateTeam?.teamName || teamsList[0].teamName])
      } else {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSelectedTeams([teamsList[0].teamName])
      }
    }
  }, [teamsLoading, teamsList, uiMode])

  const storageColumns = useMemo(
    () => [
      {
        title: t('storage.storageName'),
        dataIndex: 'storageName',
        key: 'storageName',
        ellipsis: true,
        render: (text: string) => (
          <Space>
            <CloudOutlined style={{ color: theme.colors.primary }} />
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
        width: 360,
        render: (_: any, record: Storage) => (
          <Space size="small">
            <Tooltip title={t('common:actions.edit')}>
              <ActionButton
                type="primary"
                size="small"
                icon={<EditOutlined />}
                data-testid={`resources-storage-edit-${record.storageName}`}
                onClick={() => openUnifiedModal('edit', record)}
                aria-label={t('common:actions.edit')}
              />
            </Tooltip>
            <Tooltip title={t('common:actions.runFunction')}>
              <ActionButton
                type="primary"
                size="small"
                icon={<FunctionOutlined />}
                data-testid={`resources-storage-run-${record.storageName}`}
                onClick={() => {
                  setCurrentResource(record)
                  setUnifiedModalState({
                    open: true,
                    resourceType: 'storage',
                    mode: 'create',
                    data: record
                  })
                }}
                aria-label={t('common:actions.run')}
              />
            </Tooltip>
            <Tooltip title={t('machines:trace')}>
              <ActionButton
                type="primary"
                size="small"
                icon={<HistoryOutlined />}
                data-testid={`resources-storage-trace-${record.storageName}`}
                onClick={() =>
                  setAuditTraceModal({
                    open: true,
                    entityType: 'Storage',
                    entityIdentifier: record.storageName,
                    entityName: record.storageName
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
                data-testid={`resources-storage-delete-${record.storageName}`}
                onClick={() => handleDeleteStorage(record)}
                aria-label={t('common:actions.delete')}
              />
            </Tooltip>
          </Space>
        )
      }
    ],
    [handleDeleteStorage, openUnifiedModal, t, theme.colors.primary, theme.colors.secondary]
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
                  <Tooltip title={t('storage.createStorage')}>
                    <ActionButton
                      type="primary"
                      icon={<PlusOutlined />}
                      data-testid="resources-create-storag-button"
                      onClick={() => openUnifiedModal('create')}
                      aria-label={t('storage.createStorage')}
                    />
                  </Tooltip>
                  <Tooltip title={t('resources:storage.import.button')}>
                    <ActionButton
                      icon={<ImportOutlined />}
                      data-testid="resources-import-button"
                      onClick={() => setRcloneImportWizardOpen(true)}
                      aria-label={t('resources:storage.import.button')}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:actions.refresh')}>
                    <ActionButton
                      icon={<ReloadOutlined />}
                      data-testid="resources-refresh-button"
                      onClick={() => refetchStorage()}
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
                data-testid="resources-storage-table"
                columns={storageColumns}
                dataSource={storages}
                rowKey="storageName"
                scroll={{ x: 'max-content' }}
                loading={storagesLoading}
                $isLoading={storagesLoading}
                pagination={{
                  current: storagePage,
                  pageSize: storagePageSize,
                  total: storages.length,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  showTotal: (total: number, range: [number, number]) =>
                    `${t('common:general.showingRecords', { start: range[0], end: range[1], total })}`,
                  onChange: (page: number, size: number) => {
                    setStoragePage(page)
                    if (size && size !== storagePageSize) {
                      setStoragePageSize(size)
                      setStoragePage(1)
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
        data-testid="resources-storage-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="storage"
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data || currentResource || undefined}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={unifiedModalState.mode === 'create' ? undefined : handleStorageFunctionSelected}
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['backup']}
        hiddenParams={['storage']}
        defaultParams={currentResource ? { storage: currentResource.storageName } : {}}
      />

      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null, machineName: null })
          refetchStorage()
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

      <RcloneImportWizard
        data-testid="resources-rclone-import-wizard"
        open={rcloneImportWizardOpen}
        onClose={() => setRcloneImportWizardOpen(false)}
        teamName={selectedTeams[0] || ''}
        onImportComplete={() => {
          refetchStorage()
          showMessage('success', t('resources:storage.import.successMessage'))
        }}
      />

      {contextHolder}
    </>
  )
}

export default StoragePage
