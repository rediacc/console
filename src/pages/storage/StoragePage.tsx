import React, { useCallback, useMemo } from 'react'
import { Empty, Modal, Space, Tag, Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import { useTheme } from 'styled-components'
import {
  PlusOutlined,
  ReloadOutlined,
  ImportOutlined,
  CloudOutlined,
} from '@/utils/optimizedIcons'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RcloneImportWizard from '@/components/resources/RcloneImportWizard'
import TeamSelector from '@/components/common/TeamSelector'
import { ActionButtonGroup, ActionButtonConfig } from '@/components/common/ActionButtonGroup'
import { FunctionOutlined, EditOutlined, DeleteOutlined, HistoryOutlined } from '@/utils/optimizedIcons'
import {
  useStorage,
  useCreateStorage,
  useUpdateStorageName,
  useDeleteStorage,
  useUpdateStorageVault,
  Storage,
} from '@/api/queries/storage'
import { useMachines } from '@/api/queries/machines'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { useQueueAction } from '@/hooks/useQueueAction'
import {
  useUnifiedModal,
  useTeamSelection,
  usePagination,
  useTraceModal,
  useQueueTraceModal,
  useDialogState,
  useAsyncAction,
} from '@/hooks'
import { confirmDelete } from '@/utils/confirmations'
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
  DataTable,
} from './styles'
import { featureFlags } from '@/config/featureFlags'

const StoragePage: React.FC = () => {
  const { t } = useTranslation(['resources', 'common'])
  const theme = useTheme()
  const [modal, contextHolder] = Modal.useModal()

  // Custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection()
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
    setCurrentResource,
  } = useUnifiedModal<Storage>('storage')
  const {
    page: storagePage,
    pageSize: storagePageSize,
    setPage: setStoragePage,
    setPageSize: setStoragePageSize,
  } = usePagination({ defaultPageSize: 15 })

  // Modal state management with new hooks
  const rcloneImportWizard = useDialogState()
  const queueTrace = useQueueTraceModal()
  const auditTrace = useTraceModal()

  // Async action handler
  const { execute } = useAsyncAction()

  // Data fetching
  const {
    data: storages = [],
    isLoading: storagesLoading,
    refetch: refetchStorage,
  } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined)

  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  )

  const { data: dropdownData } = useDropdownData()
  const { executeAction, isExecuting } = useQueueAction()

  // Mutations
  const createStorageMutation = useCreateStorage()
  const updateStorageNameMutation = useUpdateStorageName()
  const deleteStorageMutation = useDeleteStorage()
  const updateStorageVaultMutation = useUpdateStorageVault()

  const handleDeleteStorage = useCallback(
    (storage: Storage) => {
      confirmDelete({
        modal,
        t,
        resourceType: 'storage',
        resourceName: storage.storageName,
        translationNamespace: 'storage',
        onConfirm: () =>
          deleteStorageMutation.mutateAsync({
            teamName: storage.teamName,
            storageName: storage.storageName,
          } as any),
        onSuccess: () => refetchStorage(),
      })
    },
    [deleteStorageMutation, modal, refetchStorage, t]
  )

  const handleUnifiedModalSubmit = useCallback(
    async (data: any) => {
      await execute(
        async () => {
          if (unifiedModalState.mode === 'create') {
            await createStorageMutation.mutateAsync(data)
          } else if (currentResource) {
            const currentName = currentResource.storageName
            const newName = data.storageName

            if (newName && newName !== currentName) {
              await updateStorageNameMutation.mutateAsync({
                teamName: currentResource.teamName,
                currentStorageName: currentName,
                newStorageName: newName,
              } as any)
            }

            const vaultData = data.storageVault
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateStorageVaultMutation.mutateAsync({
                teamName: currentResource.teamName,
                storageName: newName || currentName,
                storageVault: vaultData,
                vaultVersion: currentResource.vaultVersion + 1,
              } as any)
            }
          }
          closeUnifiedModal()
          refetchStorage()
        },
        { skipSuccessMessage: true }
      )
    },
    [
      closeUnifiedModal,
      createStorageMutation,
      currentResource,
      execute,
      refetchStorage,
      unifiedModalState.mode,
      updateStorageNameMutation,
      updateStorageVaultMutation,
    ]
  )

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return
      await execute(
        async () => {
          await updateStorageVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            storageName: currentResource.storageName,
            storageVault: vault,
            vaultVersion: version,
          } as any)
          refetchStorage()
          closeUnifiedModal()
        },
        { skipSuccessMessage: true }
      )
    },
    [closeUnifiedModal, currentResource, execute, refetchStorage, updateStorageVaultMutation]
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

      if (!functionData.selectedMachine) {
        showMessage('error', t('resources:errors.machineNotFound'))
        return
      }

      const teamEntry = dropdownData?.machinesByTeam?.find(
        (team) => team.teamName === currentResource.teamName
      )
      const machineEntry = teamEntry?.machines?.find(
        (machine) => machine.value === functionData.selectedMachine
      )

      if (!machineEntry) {
        showMessage('error', t('resources:errors.machineNotFound'))
        return
      }

      const selectedMachine = machines.find(
        (machine) =>
          machine.machineName === machineEntry.value && machine.teamName === currentResource.teamName
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
        teamVault:
          teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent || '{}',
        storageName: currentResource.storageName,
        storageVault: currentResource.vaultContent || '{}',
        machineVault: selectedMachine?.vaultContent || '{}',
      }

      // Handle pull function source vaults
      if (functionData.function.name === 'pull') {
        if (functionData.params.sourceType === 'machine' && functionData.params.from) {
          const sourceMachine = machines.find(
            (machine) => machine.machineName === functionData.params.from
          )
          if (sourceMachine?.vaultContent) {
            queuePayload.sourceMachineVault = sourceMachine.vaultContent
          }
        }

        if (functionData.params.sourceType === 'storage' && functionData.params.from) {
          const sourceStorage = storages.find(
            (storage) => storage.storageName === functionData.params.from
          )
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
          queueTrace.open(result.taskId, machineEntry.value)
        } else if (result.isQueued) {
          showMessage('info', t('resources:messages.highestPriorityQueued', { resourceType: 'storage' }))
        }
      } else {
        showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'))
      }
    },
    [closeUnifiedModal, currentResource, dropdownData, executeAction, machines, queueTrace, storages, t, teams]
  )

  const isSubmitting =
    createStorageMutation.isPending || updateStorageNameMutation.isPending || isExecuting

  const isUpdatingVault = updateStorageVaultMutation.isPending

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
        ),
      },
      {
        title: t('general.team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: 150,
        ellipsis: true,
        render: (teamName: string) => <Tag color={theme.colors.secondary}>{teamName}</Tag>,
      },
      ...(featureFlags.isEnabled('vaultVersionColumns')
        ? [
            {
              title: t('general.vaultVersion'),
              dataIndex: 'vaultVersion',
              key: 'vaultVersion',
              width: 120,
              align: 'center' as const,
              render: (version: number) => (
                <Tag>{t('common:general.versionFormat', { version })}</Tag>
              ),
            },
          ]
        : []),
      {
        title: t('common:table.actions'),
        key: 'actions',
        width: 200,
        render: (_: unknown, record: Storage) => {
          const buttons: ActionButtonConfig<Storage>[] = [
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'common:actions.edit',
              onClick: (r: Storage) => openUnifiedModal('edit', r),
              variant: 'primary',
            },
            {
              type: 'run',
              icon: <FunctionOutlined />,
              tooltip: 'common:actions.runFunction',
              onClick: (r: Storage) => {
                setCurrentResource(r)
                openUnifiedModal('create', r)
              },
              variant: 'primary',
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'machines:trace',
              onClick: (r: Storage) =>
                auditTrace.open({
                  entityType: 'Storage',
                  entityIdentifier: r.storageName,
                  entityName: r.storageName,
                }),
              variant: 'default',
            },
            {
              type: 'delete',
              icon: <DeleteOutlined />,
              tooltip: 'common:actions.delete',
              onClick: handleDeleteStorage,
              variant: 'primary',
              danger: true,
            },
          ]

          return (
            <ActionButtonGroup<Storage>
              buttons={buttons}
              record={record}
              idField="storageName"
              testIdPrefix="resources-storage"
              t={t}
            />
          )
        },
      },
    ],
    [auditTrace, handleDeleteStorage, openUnifiedModal, setCurrentResource, t, theme.colors.primary, theme.colors.secondary]
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
                  <Tooltip title={t('storage.createStorage')}>
                    <ActionButton
                      type="primary"
                      icon={<PlusOutlined />}
                      data-testid="resources-create-storage-button"
                      onClick={() => openUnifiedModal('create')}
                      aria-label={t('storage.createStorage')}
                    />
                  </Tooltip>
                  <Tooltip title={t('resources:storage.import.button')}>
                    <ActionButton
                      icon={<ImportOutlined />}
                      data-testid="resources-import-button"
                      onClick={() => rcloneImportWizard.open()}
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
                  position: ['bottomRight'],
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
        existingData={(unifiedModalState.data || currentResource) as any}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={
          unifiedModalState.mode === 'create' ? undefined : handleStorageFunctionSelected
        }
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['backup']}
        hiddenParams={['storage']}
        defaultParams={currentResource ? { storage: currentResource.storageName } : {}}
      />

      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close()
          refetchStorage()
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

      <RcloneImportWizard
        data-testid="resources-rclone-import-wizard"
        open={rcloneImportWizard.isOpen}
        onClose={rcloneImportWizard.close}
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
