import React, { useState } from 'react';
import { Empty, Alert, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCephClusters, useCephPools } from '@/api/queries/ceph';
import type { CephCluster, CephPool } from '@/api/queries/ceph';
import {
  useCreateCephCluster,
  useCreateCephPool,
  useUpdateCephClusterVault,
  useUpdateCephPoolVault,
  useDeleteCephCluster,
  useDeleteCephPool,
} from '@/api/queries/cephMutations';
import { useCompanyInfo } from '@/api/queries/dashboard';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { RediaccButton } from '@/components/ui';
import { useTeamSelection, useQueueTraceModal } from '@/hooks';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import {
  PageCard,
  PageContainer,
  SectionStack,
  SectionHeaderRow,
  EmptyStateWrapper,
} from '@/styles/primitives';
import { showMessage } from '@/utils/messages';
import { PlusOutlined, ReloadOutlined, SettingOutlined } from '@/utils/optimizedIcons';
import type {
  ClusterFormValues as BaseClusterFormValues,
  PoolFormValues as BasePoolFormValues,
} from '@rediacc/shared/types';
import { CephMachinesTab } from './components/CephMachinesTab';
import { ClusterTable } from './components/ClusterTable';
import { PoolTable } from './components/PoolTable';
import { TitleGroup, HeaderTitle, TeamSelectorWrapper, ActionGroup } from './styles';

type CephView = 'clusters' | 'pools' | 'machines';

interface CephPageProps {
  view?: CephView;
}

type ModalData =
  | (Partial<CephCluster> & Record<string, unknown>)
  | (Partial<CephPool> & Record<string, unknown>);

// Extend shared types with vault version for edit operations and required vaultContent
type ClusterFormValues = BaseClusterFormValues & { vaultVersion?: number; vaultContent: string };
type PoolFormValues = BasePoolFormValues & { vaultVersion?: number; vaultContent: string };

type ModalFormValues = ClusterFormValues | PoolFormValues;

const isPoolFormValues = (values: ModalFormValues): values is PoolFormValues => {
  return 'poolName' in values;
};

const isPoolEntity = (data: CephCluster | CephPool): data is CephPool => {
  return 'poolName' in data;
};

const CephPage: React.FC<CephPageProps> = ({ view = 'clusters' }) => {
  const { t } = useTranslation(['ceph', 'common']);

  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
  const queueTrace = useQueueTraceModal();
  const { data: companyData } = useCompanyInfo();
  const [modalState, setModalState] = useState<{
    open: boolean;
    type: 'cluster' | 'pool';
    mode: 'create' | 'edit' | 'vault';
    data?: ModalData;
  }>({ open: false, type: 'cluster', mode: 'create' });

  const planCode = companyData?.activeSubscription?.planCode;
  const hasCephAccess = planCode === 'ENTERPRISE' || planCode === 'BUSINESS';
  const hasSelectedTeam = selectedTeams.length > 0;
  const teamFilter = hasSelectedTeam ? selectedTeams : undefined;
  const primaryTeam = hasSelectedTeam ? selectedTeams[0] : undefined;

  const isClustersView = view === 'clusters';
  const isPoolsView = view === 'pools';
  const isMachinesView = view === 'machines';

  const {
    data: clusters = [],
    isLoading: clustersLoading,
    refetch: refetchClusters,
  } = useCephClusters(teamFilter, hasCephAccess && !!companyData);

  const shouldLoadPools = hasCephAccess && !!companyData && hasSelectedTeam && isPoolsView;

  const {
    data: pools = [],
    isLoading: poolsLoading,
    refetch: refetchPools,
  } = useCephPools(teamFilter, shouldLoadPools);

  const createClusterMutation = useCreateCephCluster();
  const createPoolMutation = useCreateCephPool();
  const updateClusterVaultMutation = useUpdateCephClusterVault();
  const updatePoolVaultMutation = useUpdateCephPoolVault();
  const deleteClusterMutation = useDeleteCephCluster();
  const deletePoolMutation = useDeleteCephPool();

  useManagedQueueItem();
  useQueueVaultBuilder();

  if (!companyData) {
    return (
      <PageContainer>
        <PageCard>
          <Alert message="Loading company data..." type="info" showIcon />
        </PageCard>
      </PageContainer>
    );
  }

  const openModal = (
    type: 'cluster' | 'pool',
    mode: 'create' | 'edit' | 'vault',
    data?: ModalData
  ) => {
    setModalState({
      open: true,
      type,
      mode,
      data,
    });
  };

  const closeModal = () => {
    setModalState({
      open: false,
      type: 'cluster',
      mode: 'create',
      data: undefined,
    });
  };

  const handleModalSubmit = async (data: ModalFormValues) => {
    try {
      const { type, mode } = modalState;

      if (mode === 'create') {
        if (type === 'cluster' && !isPoolFormValues(data)) {
          await createClusterMutation.mutateAsync({
            clusterName: data.clusterName,
            vaultContent: data.vaultContent,
          });
        } else if (type === 'pool' && isPoolFormValues(data)) {
          await createPoolMutation.mutateAsync({
            teamName: data.teamName,
            clusterName: data.clusterName,
            poolName: data.poolName,
            vaultContent: data.vaultContent,
          });
        }
      } else if (mode === 'edit' || mode === 'vault') {
        if (type === 'cluster' && !isPoolFormValues(data)) {
          await updateClusterVaultMutation.mutateAsync({
            clusterName: data.clusterName,
            vaultContent: data.vaultContent,
            vaultVersion: data.vaultVersion ?? 0,
          });
        } else if (type === 'pool' && isPoolFormValues(data)) {
          await updatePoolVaultMutation.mutateAsync({
            poolName: data.poolName,
            teamName: data.teamName,
            vaultContent: data.vaultContent,
            vaultVersion: data.vaultVersion ?? 0,
          });
        }
      }

      closeModal();
    } catch {
      // Error handled by mutation
    }
  };

  const handleDelete = async (type: 'cluster' | 'pool', data: CephCluster | CephPool) => {
    try {
      if (type === 'cluster' && !isPoolEntity(data)) {
        await deleteClusterMutation.mutateAsync({
          clusterName: data.clusterName,
        });
      } else if (type === 'pool' && isPoolEntity(data)) {
        await deletePoolMutation.mutateAsync({
          poolName: data.poolName,
          teamName: data.teamName,
        });
      }
    } catch {
      // Error handled by mutation
    }
  };

  const handleFunctionSubmit = async (_functionData: unknown) => {
    showMessage('info', 'Function execution coming soon');
    closeModal();
  };

  if (!hasCephAccess) {
    return (
      <PageContainer>
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
                Has Access: {String(hasCephAccess)}
                <br />
                Company Data: {JSON.stringify(companyData, null, 2)}
              </>
            }
            type="warning"
            showIcon
            icon={<SettingOutlined />}
          />
        </PageCard>
      </PageContainer>
    );
  }

  const renderContent = () => {
    if (!hasSelectedTeam) {
      return (
        <EmptyStateWrapper>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectTeamPrompt')} />
        </EmptyStateWrapper>
      );
    }

    if (isClustersView) {
      return (
        <ClusterTable
          clusters={clusters}
          loading={clustersLoading}
          onCreateCluster={() => openModal('cluster', 'create')}
          onEditCluster={(cluster) => openModal('cluster', 'edit', cluster as ModalData)}
          onDeleteCluster={(cluster) => handleDelete('cluster', cluster)}
          onRunFunction={(cluster) =>
            openModal('cluster', 'create', { ...cluster, isFunction: true } as ModalData)
          }
        />
      );
    }

    if (isPoolsView) {
      return (
        <PoolTable
          pools={pools}
          clusters={clusters}
          loading={poolsLoading}
          onCreatePool={() => openModal('pool', 'create')}
          onEditPool={(pool) => openModal('pool', 'edit', pool as ModalData)}
          onDeletePool={(pool) => handleDelete('pool', pool)}
          onRunFunction={(pool) =>
            openModal('pool', 'create', { ...pool, isFunction: true } as ModalData)
          }
        />
      );
    }

    return <CephMachinesTab teamFilter={teamFilter} />;
  };

  const renderActions = () => {
    if (!hasSelectedTeam || isMachinesView) {
      return null;
    }

    const createLabel = isClustersView ? t('clusters.create') : t('pools.create');
    const createTestId = isClustersView ? 'ds-create-cluster-button' : 'ds-create-pool-button';

    return (
      <ActionGroup>
        <Tooltip title={createLabel}>
          <RediaccButton
            iconOnly
            icon={<PlusOutlined />}
            onClick={() => {
              if (isClustersView) {
                openModal('cluster', 'create');
              } else if (isPoolsView) {
                openModal('pool', 'create');
              }
            }}
            data-testid={createTestId}
            aria-label={createLabel}
          />
        </Tooltip>
        <Tooltip title={t('common:actions.refresh')}>
          <RediaccButton
            iconOnly
            icon={<ReloadOutlined />}
            onClick={() => {
              if (isClustersView) {
                refetchClusters();
              } else if (isPoolsView) {
                refetchPools();
              }
            }}
            data-testid="ds-refresh-button"
            aria-label={t('common:actions.refresh')}
          />
        </Tooltip>
      </ActionGroup>
    );
  };

  return (
    <PageContainer>
      <PageCard>
        <SectionStack>
          <SectionHeaderRow>
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
            {renderActions()}
          </SectionHeaderRow>
        </SectionStack>

        {renderContent()}
      </PageCard>

      {!isMachinesView && (
        <>
          <UnifiedResourceModal
            open={modalState.open}
            onCancel={closeModal}
            resourceType={modalState.type}
            mode={modalState.mode}
            data-testid="ds-resource-modal"
            existingData={{
              ...modalState.data,
              teamName: primaryTeam,
              clusters: clusters,
              pools: pools,
              vaultContent: (modalState.data?.vaultContent ||
                modalState.data?.[`${modalState.type}Vault`] ||
                undefined) as string | undefined,
            }}
            teamFilter={primaryTeam}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onSubmit={handleModalSubmit as any}
            onFunctionSubmit={handleFunctionSubmit}
            onUpdateVault={async (vault: string, version: number) => {
              const data = modalState.data || {};
              if (modalState.type === 'cluster') {
                await updateClusterVaultMutation.mutateAsync({
                  clusterName: data.clusterName as string,
                  vaultContent: vault,
                  vaultVersion: version,
                });
              } else if (modalState.type === 'pool' && primaryTeam) {
                await updatePoolVaultMutation.mutateAsync({
                  teamName: primaryTeam,
                  poolName: data.poolName as string,
                  vaultContent: vault,
                  vaultVersion: version,
                });
              }
            }}
            isSubmitting={createClusterMutation.isPending || createPoolMutation.isPending}
            isUpdatingVault={
              updateClusterVaultMutation.isPending || updatePoolVaultMutation.isPending
            }
            functionCategories={modalState.data?.isFunction ? [modalState.type] : []}
            hiddenParams={
              modalState.data?.isFunction
                ? modalState.type === 'cluster'
                  ? ['cluster_name']
                  : ['cluster_name', 'pool_name']
                : []
            }
            defaultParams={
              modalState.data?.isFunction
                ? modalState.type === 'cluster'
                  ? { cluster_name: modalState.data.clusterName as string }
                  : {
                      cluster_name: modalState.data.clusterName as string,
                      pool_name: modalState.data.poolName as string,
                    }
                : undefined
            }
            preselectedFunction={modalState.data?.preselectedFunction as string | undefined}
          />

          <QueueItemTraceModal
            taskId={queueTrace.state.taskId}
            open={queueTrace.state.open}
            data-testid="ds-queue-trace-modal"
            onCancel={() => {
              queueTrace.close();
              if (isClustersView) {
                refetchClusters();
              } else if (isPoolsView) {
                refetchPools();
              }
            }}
          />
        </>
      )}
    </PageContainer>
  );
};

export default CephPage;
