import React, { useState } from 'react'
import { Tabs, Empty, Alert, Tooltip } from 'antd'
import {
  PlusOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  ReloadOutlined,
  SettingOutlined,
  DesktopOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useCompanyInfo } from '@/api/queries/dashboard'
import { useTeamSelection, useQueueTraceModal } from '@/hooks'
import TeamSelector from '@/components/common/TeamSelector'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { ClusterTable } from './components/ClusterTable'
import { PoolTable } from './components/PoolTable'
import { DistributedStorageMachinesTab } from './components/DistributedStorageMachinesTab'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import { showMessage } from '@/utils/messages'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import {
  useDistributedStorageClusters,
  useDistributedStoragePools,
} from '@/api/queries/distributedStorage'
import {
  useCreateDistributedStorageCluster,
  useCreateDistributedStoragePool,
  useUpdateDistributedStorageClusterVault,
  useUpdateDistributedStoragePoolVault,
  useDeleteDistributedStorageCluster,
  useDeleteDistributedStoragePool,
} from '@/api/queries/distributedStorageMutations'
import { PageCard, PrimaryIconButton, SecondaryIconButton } from '@/styles/primitives'
import {
  PageWrapper,
  HeaderSection,
  HeaderRow,
  TitleGroup,
  HeaderTitle,
  TeamSelectorWrapper,
  ActionGroup,
  EmptyState,
} from './styles'

const DistributedStoragePage: React.FC = () => {
  const { t } = useTranslation(['distributedStorage', 'common'])

  // Use custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection()

  const [activeTab, setActiveTab] = useState('clusters')
  const [modalState, setModalState] = useState<{
    open: boolean
    type: 'cluster' | 'pool'
    mode: 'create' | 'edit' | 'vault'
    data?: Record<string, any>
  }>({ open: false, type: 'cluster', mode: 'create' })

  // Queue trace modal with hook
  const queueTrace = useQueueTraceModal()
  
  // Company info for subscription check
  const { data: companyData } = useCompanyInfo()
  
  // Debug logging
  console.log('DistributedStorage Debug:', {
    companyData,
    activeSubscription: companyData?.activeSubscription,
    planCode: companyData?.activeSubscription?.PlanCode,
    fullCompanyData: JSON.stringify(companyData, null, 2)
  })

  const planCode = companyData?.activeSubscription?.PlanCode
  const hasDistributedStorageAccess = planCode === 'ENTERPRISE' || planCode === 'BUSINESS'

  console.log('hasDistributedStorageAccess:', hasDistributedStorageAccess, 'planCode:', planCode)

  // Distributed storage queries - must be called unconditionally
  const { data: clusters = [], isLoading: clustersLoading, refetch: refetchClusters } = useDistributedStorageClusters(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    hasDistributedStorageAccess && !!companyData
  )

  const { data: pools = [], isLoading: poolsLoading, refetch: refetchPools } = useDistributedStoragePools(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    hasDistributedStorageAccess && activeTab === 'pools' && !!companyData
  )

  // Mutations - must be called unconditionally
  const createClusterMutation = useCreateDistributedStorageCluster()
  const createPoolMutation = useCreateDistributedStoragePool()
  const updateClusterVaultMutation = useUpdateDistributedStorageClusterVault()
  const updatePoolVaultMutation = useUpdateDistributedStoragePoolVault()
  const deleteClusterMutation = useDeleteDistributedStorageCluster()
  const deletePoolMutation = useDeleteDistributedStoragePool()

  // Queue management - must be called unconditionally (hooks must be called unconditionally)
  useManagedQueueItem()
  useQueueVaultBuilder()

  // Show debug info in UI temporarily
  if (!companyData) {
    return (
      <PageWrapper>
        <PageCard>
          <Alert message="Loading company data..." type="info" showIcon />
        </PageCard>
      </PageWrapper>
    )
  }
  
  // Handle modal operations
  const openModal = (type: 'cluster' | 'pool', mode: 'create' | 'edit' | 'vault', data?: Record<string, any>) => {
    setModalState({
      open: true,
      type,
      mode,
      data
    })
  }
  
  const closeModal = () => {
    setModalState({
      open: false,
      type: 'cluster',
      mode: 'create',
      data: undefined
    })
  }
  
  // Handle modal submit
  const handleModalSubmit = async (data: Record<string, any>) => {
    try {
      const { type, mode } = modalState
      
      if (mode === 'create') {
        if (type === 'cluster') {
          await createClusterMutation.mutateAsync({
            clusterName: data.clusterName,
            clusterVault: data.clusterVault
          })
        } else if (type === 'pool') {
          await createPoolMutation.mutateAsync({
            teamName: data.teamName,
            clusterName: data.clusterName,
            poolName: data.poolName,
            poolVault: data.poolVault
          })
        }
      } else if (mode === 'edit' || mode === 'vault') {
        if (type === 'cluster') {
          await updateClusterVaultMutation.mutateAsync({
            clusterName: data.clusterName,
            clusterVault: data.clusterVault,
            vaultVersion: data.vaultVersion
          })
        } else if (type === 'pool') {
          await updatePoolVaultMutation.mutateAsync({
            poolName: data.poolName,
            teamName: data.teamName,
            poolVault: data.poolVault,
            vaultVersion: data.vaultVersion
          })
        }
      }
      
      closeModal()
    } catch {
      // Error handled by mutation
    }
  }
  
  // Handle delete operations
  const handleDelete = async (type: 'cluster' | 'pool', data: Record<string, any>) => {
    try {
      if (type === 'cluster') {
        await deleteClusterMutation.mutateAsync({
          clusterName: data.clusterName
        })
      } else if (type === 'pool') {
        await deletePoolMutation.mutateAsync({
          poolName: data.poolName,
          teamName: data.teamName
        })
      }
    } catch {
      // Error handled by mutation
    }
  }
  
  // Handle function execution
  const handleFunctionSubmit = async (_functionData: Record<string, any>) => {
    // This will be implemented when we have the function definitions
    showMessage('info', 'Function execution coming soon')
    closeModal()
  }
  
  // Tab items
  const tabItems = [
    {
      key: 'clusters',
      label: (
        <span data-testid="ds-tab-clusters">
          <CloudServerOutlined />
          {t('tabs.clusters')}
        </span>
      ),
      children: (
        <ClusterTable
          clusters={clusters}
          loading={clustersLoading}
          onCreateCluster={() => openModal('cluster', 'create')}
          onEditCluster={(cluster) => openModal('cluster', 'edit', cluster)}
          onDeleteCluster={(cluster) => handleDelete('cluster', cluster)}
          onRunFunction={(cluster) => openModal('cluster', 'create', { ...cluster, isFunction: true })}
        />
      )
    },
    {
      key: 'pools',
      label: (
        <span data-testid="ds-tab-pools">
          <DatabaseOutlined />
          {t('tabs.pools')}
        </span>
      ),
      children: (
        <PoolTable
          pools={pools}
          clusters={clusters}
          loading={poolsLoading}
          onCreatePool={() => openModal('pool', 'create')}
          onEditPool={(pool) => openModal('pool', 'edit', pool)}
          onDeletePool={(pool) => handleDelete('pool', pool)}
          onRunFunction={(pool) => openModal('pool', 'create', { ...pool, isFunction: true })}
        />
      )
    },
    {
      key: 'machines',
      label: (
        <span data-testid="ds-tab-machines">
          <DesktopOutlined />
          {t('tabs.machines')}
        </span>
      ),
      children: (
        <DistributedStorageMachinesTab
          teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        />
      )
    }
  ]
  
  // Render access denied message if no access
  if (!hasDistributedStorageAccess) {
    return (
      <PageWrapper>
        <PageCard>
          <Alert
            message={t('accessDenied.title')}
            description={
              <>
                {t('accessDenied.description')}
                <br />
                <br />
                <strong>Debug Info:</strong>
                <br />
                Current Plan: {planCode || 'No plan detected'}
                <br />
                Has Access: {String(hasDistributedStorageAccess)}
                <br />
                Company Data: {JSON.stringify(companyData, null, 2)}
              </>
            }
            type="warning"
            showIcon
            icon={<SettingOutlined />}
          />
        </PageCard>
      </PageWrapper>
    )
  }
  
  return (
    <PageWrapper>
      <PageCard>
        <HeaderSection>
          <HeaderRow>
            <TitleGroup>
              <HeaderTitle level={4}>{t('title')}</HeaderTitle>
              <TeamSelectorWrapper>
                <TeamSelector
                  teams={teams}
                  selectedTeams={selectedTeams}
                  onChange={setSelectedTeams}
                  loading={teamsLoading}
                  placeholder={t('selectTeamToView')}
                  data-testid="ds-team-selector"
                />
              </TeamSelectorWrapper>
            </TitleGroup>
            {selectedTeams.length > 0 && (
              <ActionGroup>
                {activeTab !== 'machines' && (
                  <Tooltip title={activeTab === 'clusters' ? t('clusters.create') : t('pools.create')}>
                    <PrimaryIconButton
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        if (activeTab === 'clusters') {
                          openModal('cluster', 'create')
                        } else if (activeTab === 'pools') {
                          openModal('pool', 'create')
                        }
                      }}
                      data-testid={activeTab === 'clusters' ? 'ds-create-cluster-button' : 'ds-create-pool-button'}
                      aria-label={activeTab === 'clusters' ? t('clusters.create') : t('pools.create')}
                    />
                  </Tooltip>
                )}
                <Tooltip title={t('common:actions.refresh')}>
                  <SecondaryIconButton
                    icon={<ReloadOutlined />}
                    onClick={() => {
                      if (activeTab === 'clusters') {
                        refetchClusters()
                      } else if (activeTab === 'pools') {
                        refetchPools()
                      }
                    }}
                    data-testid="ds-refresh-button"
                    aria-label={t('common:actions.refresh')}
                  />
                </Tooltip>
              </ActionGroup>
            )}
          </HeaderRow>
        </HeaderSection>

        {selectedTeams.length === 0 ? (
          <EmptyState>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectTeamPrompt')} />
          </EmptyState>
        ) : (
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            data-testid="ds-tabs"
          />
        )}
      </PageCard>
      
      {/* Unified Resource Modal */}
      <UnifiedResourceModal
        open={modalState.open}
        onCancel={closeModal}
        resourceType={modalState.type}
        mode={modalState.mode}
        data-testid="ds-resource-modal"
        existingData={{
          ...modalState.data,
          teamName: selectedTeams[0],
          clusters: clusters,
          pools: pools,
          vaultContent: modalState.data?.vaultContent || modalState.data?.[`${modalState.type}Vault`]
        }}
        teamFilter={selectedTeams[0]}
        onSubmit={handleModalSubmit}
        onFunctionSubmit={handleFunctionSubmit}
        onUpdateVault={async (vault: string, version: number) => {
          const data = modalState.data || {}
          if (modalState.type === 'cluster') {
            await updateClusterVaultMutation.mutateAsync({
              clusterName: data.clusterName,
              clusterVault: vault,
              vaultVersion: version
            })
          } else if (modalState.type === 'pool') {
            await updatePoolVaultMutation.mutateAsync({
              teamName: selectedTeams[0],
              poolName: data.poolName,
              poolVault: vault,
              vaultVersion: version
            })
          }
        }}
        isSubmitting={
          createClusterMutation.isPending ||
          createPoolMutation.isPending
        }
        isUpdatingVault={
          updateClusterVaultMutation.isPending ||
          updatePoolVaultMutation.isPending
        }
        functionCategories={modalState.data?.isFunction ? [modalState.type] : []}
        hiddenParams={modalState.data?.isFunction ? 
          (modalState.type === 'cluster' ? ['cluster_name'] : ['cluster_name', 'pool_name']) : []
        }
        defaultParams={modalState.data?.isFunction ? 
          (modalState.type === 'cluster' ? 
            { cluster_name: modalState.data.clusterName } : 
            { cluster_name: modalState.data.clusterName, pool_name: modalState.data.poolName }
          ) : {}
        }
        preselectedFunction={modalState.data?.preselectedFunction}
      />
      
      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTrace.state.taskId}
        visible={queueTrace.state.visible}
        data-testid="ds-queue-trace-modal"
        onClose={() => {
          queueTrace.close()
          // Refresh data when modal closes
          if (activeTab === 'clusters') {
            refetchClusters()
          } else if (activeTab === 'pools') {
            refetchPools()
          }
        }}
      />
    </PageWrapper>
  )
}

export default DistributedStoragePage
