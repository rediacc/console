import React, { useState, useRef } from 'react'
import { Card, Tabs, Button, Empty, Row, Col, Alert, Typography, Tooltip } from 'antd'
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
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { useTeams } from '@/api/queries/teams'
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
  useCreateDistributedStorageCluster,
  useCreateDistributedStoragePool,
  useUpdateDistributedStorageClusterVault,
  useUpdateDistributedStoragePoolVault,
  useDeleteDistributedStorageCluster,
  useDeleteDistributedStoragePool
} from '@/api/queries/distributedStorage'

const { Title } = Typography

const DistributedStoragePage: React.FC = () => {
  const { t } = useTranslation(['distributedStorage', 'common'])
  const styles = useComponentStyles()
  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState('clusters')
  const [modalState, setModalState] = useState<{
    open: boolean
    type: 'cluster' | 'pool'
    mode: 'create' | 'edit' | 'vault'
    data?: Record<string, any>
  }>({ open: false, type: 'cluster', mode: 'create' })
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null })

  // Team state
  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList = teams || []
  
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
  const hasDistributedStorageAccess = planCode === 'ELITE' || planCode === 'PREMIUM'

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

  // Set default selected team on startup
  const hasInitializedTeam = useRef(false)
  React.useEffect(() => {
    if (!teamsLoading && !hasInitializedTeam.current && teamsList && teamsList.length > 0) {
      hasInitializedTeam.current = true
      setSelectedTeams([teamsList[0].teamName])
    }
  }, [teamsList, teamsLoading])

  // Show debug info in UI temporarily
  if (!companyData) {
    return (
      <Row gutter={24}>
        <Col span={24}>
          <Card style={styles.card}>
            <Alert
              message="Loading company data..."
              type="info"
              showIcon
            />
          </Card>
        </Col>
      </Row>
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
      <Row gutter={24}>
        <Col span={24}>
          <Card style={styles.card}>
            <Alert
              message={t('accessDenied.title')}
              description={
                <>
                  {t('accessDenied.description')}
                  <br /><br />
                  <strong>Debug Info:</strong>
                  <br />
                  Current Plan: {planName || 'No plan detected'}
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
          </Card>
        </Col>
      </Row>
    )
  }
  
  return (
    <>
      <Row gutter={24}>
        <Col span={24}>
          <Card style={styles.card}>
            <div style={{ marginBottom: 16 }}>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 16
              }}>
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 16,
                  flex: '1 1 auto',
                  minWidth: 0
                }}>
                  <Title level={4} style={{ ...styles.heading4, margin: 0, flexShrink: 0 }}>
                    {t('title')}
                  </Title>
                  <TeamSelector
                    teams={teamsList}
                    selectedTeams={selectedTeams}
                    onChange={setSelectedTeams}
                    loading={teamsLoading}
                    placeholder={t('selectTeamToView')}
                    style={{ 
                      minWidth: 250, 
                      maxWidth: 400,
                      width: '100%'
                    }}
                    data-testid="ds-team-selector"
                  />
                </div>
                
                {selectedTeams.length > 0 && (
                  <div style={{ 
                    display: 'flex',
                    gap: 8,
                    flexShrink: 0
                  }}>
                    {activeTab !== 'machines' && (
                      <Tooltip title={activeTab === 'clusters' ? t('clusters.create') : t('pools.create')}>
                        <Button 
                          type="primary" 
                          icon={<PlusOutlined />}
                          style={{
                            ...styles.buttonPrimary,
                            ...styles.touchTarget,
                            background: '#556b2f',
                            borderColor: '#556b2f'
                          }}
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
                      <Button 
                        icon={<ReloadOutlined />}
                        style={styles.touchTarget}
                        onClick={() => {
                          if (activeTab === 'clusters') {
                            refetchClusters()
                          } else if (activeTab === 'pools') {
                            refetchPools()
                          }
                          // Machines tab handles its own refresh
                        }}
                        data-testid="ds-refresh-button"
                        aria-label={t('common:actions.refresh')}
                      />
                    </Tooltip>
                  </div>
                )}
              </div>
            </div>
            
            {selectedTeams.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('selectTeamPrompt')}
                style={{ padding: '40px 0' }}
              />
            ) : (
              <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={tabItems}
                data-testid="ds-tabs"
              />
            )}
          </Card>
        </Col>
      </Row>
      
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
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        data-testid="ds-queue-trace-modal"
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null })
          // Refresh data when modal closes
          if (activeTab === 'clusters') {
            refetchClusters()
          } else if (activeTab === 'pools') {
            refetchPools()
          }
        }}
      />
    </>
  )
}

export default DistributedStoragePage