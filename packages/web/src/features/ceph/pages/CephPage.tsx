import React, { useState } from 'react';
import { Alert, Button, Card, Empty, Flex, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useGetCephClusters, useGetCephPools } from '@/api/api-hooks.generated';
import {
  useCreateCephCluster,
  useCreateCephPool,
  useDeleteCephCluster,
  useDeleteCephPool,
  useUpdateCephClusterVault,
  useUpdateCephPoolVault,
} from '@/api/api-hooks.generated';
import { useGetUserOrganization } from '@/api/api-hooks.generated';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { useQueueTraceModal } from '@/hooks';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { useTeamSelection } from '@/hooks/useTeamSelection';
import { showMessage } from '@/utils/messages';
import { PlusOutlined, ReloadOutlined, SettingOutlined } from '@/utils/optimizedIcons';
import type {
  CreateCephClusterParams,
  CreateCephPoolParams,
  GetCephClusters_ResultSet1 as CephCluster,
  GetCephPools_ResultSet1 as CephPool,
} from '@rediacc/shared/types';
import { CephMachinesTab } from '../components/CephMachinesTab';
import { ClusterTable } from '../components/ClusterTable';
import { PoolTable } from '../components/PoolTable';

type CephView = 'clusters' | 'pools' | 'machines';

interface CephPageProps {
  view?: CephView;
}

type ModalData =
  | (Partial<CephCluster> & Record<string, unknown>)
  | (Partial<CephPool> & Record<string, unknown>);

// Form values with required vaultContent for form validation
// Note: vaultContent and vaultVersion are already optional in generated types
interface ClusterFormValues extends CreateCephClusterParams {
  vaultContent: string; // Required for form
}
interface PoolFormValues extends CreateCephPoolParams {
  vaultContent: string; // Required for form
}

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
  const { data: organizationData } = useGetUserOrganization();
  const [modalState, setModalState] = useState<{
    open: boolean;
    type: 'cluster' | 'pool';
    mode: 'create' | 'edit' | 'vault';
    data?: ModalData;
  }>({ open: false, type: 'cluster', mode: 'create' });

  // TODO: Replace hardcoded value with actual subscription from API when available
  const planCode = 'ENTERPRISE' as string;
  const hasCephAccess = ['ENTERPRISE', 'BUSINESS'].includes(planCode);
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
  } = useGetCephClusters();

  const {
    data: pools = [],
    isLoading: poolsLoading,
    refetch: refetchPools,
  } = useGetCephPools(teamFilter?.[0]);

  const createClusterMutation = useCreateCephCluster();
  const createPoolMutation = useCreateCephPool();
  const updateClusterVaultMutation = useUpdateCephClusterVault();
  const updatePoolVaultMutation = useUpdateCephPoolVault();
  const deleteClusterMutation = useDeleteCephCluster();
  const deletePoolMutation = useDeleteCephPool();

  useManagedQueueItem();
  useQueueVaultBuilder();

  if (!organizationData) {
    return (
      <Flex>
        <Card>
          <Alert message={t('common:general.loading')} type="info" />
        </Card>
      </Flex>
    );
  }

  const isSubmitting = [createClusterMutation.isPending, createPoolMutation.isPending].some(
    Boolean
  );
  const isUpdatingVault = [
    updateClusterVaultMutation.isPending,
    updatePoolVaultMutation.isPending,
  ].some(Boolean);

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

  const handleModalSubmit = async (data: Record<string, unknown>) => {
    try {
      const { type, mode } = modalState;
      const formValues = data as unknown as ModalFormValues;

      if (mode === 'create') {
        if (type === 'cluster' && !isPoolFormValues(formValues)) {
          await createClusterMutation.mutateAsync({
            clusterName: formValues.clusterName,
            vaultContent: formValues.vaultContent,
          });
        } else if (type === 'pool' && isPoolFormValues(formValues)) {
          await createPoolMutation.mutateAsync({
            teamName: formValues.teamName,
            clusterName: formValues.clusterName,
            poolName: formValues.poolName,
            vaultContent: formValues.vaultContent,
          });
        }
      } else if (type === 'cluster' && !isPoolFormValues(formValues)) {
        await updateClusterVaultMutation.mutateAsync({
          clusterName: formValues.clusterName,
          vaultContent: formValues.vaultContent,
          vaultVersion: formValues.vaultVersion ?? 0,
        });
      } else if (isPoolFormValues(formValues)) {
        await updatePoolVaultMutation.mutateAsync({
          poolName: formValues.poolName,
          teamName: formValues.teamName,
          vaultContent: formValues.vaultContent,
          vaultVersion: formValues.vaultVersion ?? 0,
        });
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
    await Promise.resolve();
    showMessage('info', 'Function execution coming soon');
    closeModal();
  };

  if (!hasCephAccess) {
    return (
      <Flex>
        <Card>
          <Alert
            message={t('accessDenied.title')}
            description={
              <>
                {t('accessDenied.description')}
                <br />
                <br />
                <strong>{t('accessDenied.debugInfo')}:</strong>
                <br />
                {t('accessDenied.currentPlan')}: {planCode}
                <br />
                {t('accessDenied.hasAccess')}: {String(hasCephAccess)}
                <br />
                {t('accessDenied.organizationData')}: {JSON.stringify(organizationData, null, 2)}
              </>
            }
            type="warning"
            icon={<SettingOutlined />}
          />
        </Card>
      </Flex>
    );
  }

  const renderContent = () => {
    if (!hasSelectedTeam) {
      return (
        <Flex align="center" justify="center">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectTeamPrompt')} />
        </Flex>
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
      <Flex align="center" wrap>
        <Tooltip title={createLabel}>
          <Button
            type="primary"
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
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={() => {
              if (isClustersView) {
                void refetchClusters();
              } else if (isPoolsView) {
                void refetchPools();
              }
            }}
            data-testid="ds-refresh-button"
            aria-label={t('common:actions.refresh')}
          />
        </Tooltip>
      </Flex>
    );
  };

  return (
    <Flex vertical>
      <Card>
        <Flex vertical>
          <Flex align="center" justify="space-between" wrap>
            <Flex align="center" className="flex-1 min-w-0">
              <Flex
                className="flex-1"
                // eslint-disable-next-line no-restricted-syntax
                style={{ minWidth: 320, maxWidth: 520 }}
              >
                <TeamSelector
                  teams={teams}
                  selectedTeams={selectedTeams}
                  onChange={setSelectedTeams}
                  loading={teamsLoading}
                  placeholder={t('selectTeamToView')}
                  data-testid="ds-team-selector"
                />
              </Flex>
            </Flex>
            {renderActions()}
          </Flex>
        </Flex>

        {renderContent()}
      </Card>

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
              clusters: clusters.map((c) => ({ ...c, clusterName: c.clusterName ?? '' })),
              pools: pools.map((p) => ({
                ...p,
                poolName: p.poolName ?? '',
                clusterName: p.clusterName ?? '',
              })),
              vaultContent: (modalState.data?.vaultContent ??
                modalState.data?.[`${modalState.type}Vault`] ??
                undefined) as string | undefined,
            }}
            teamFilter={primaryTeam}
            onSubmit={handleModalSubmit}
            onFunctionSubmit={handleFunctionSubmit}
            onUpdateVault={async (vault: string, version: number) => {
              const data = modalState.data ?? {};
              if (modalState.type === 'cluster') {
                await updateClusterVaultMutation.mutateAsync({
                  clusterName: data.clusterName as string,
                  vaultContent: vault,
                  vaultVersion: version,
                });
              } else if (primaryTeam) {
                await updatePoolVaultMutation.mutateAsync({
                  teamName: primaryTeam,
                  poolName: data.poolName as string,
                  vaultContent: vault,
                  vaultVersion: version,
                });
              }
            }}
            isSubmitting={isSubmitting}
            isUpdatingVault={isUpdatingVault}
            functionCategories={modalState.data?.isFunction ? [modalState.type] : []}
            hiddenParams={(() => {
              if (!modalState.data?.isFunction) return [];
              if (modalState.type === 'cluster') return ['cluster_name'];
              return ['cluster_name', 'pool_name'];
            })()}
            defaultParams={(() => {
              if (!modalState.data?.isFunction) return undefined;
              if (modalState.type === 'cluster') {
                return { cluster_name: modalState.data.clusterName as string };
              }
              return {
                cluster_name: modalState.data.clusterName as string,
                pool_name: modalState.data.poolName as string,
              };
            })()}
            preselectedFunction={modalState.data?.preselectedFunction as string | undefined}
          />

          <QueueItemTraceModal
            taskId={queueTrace.state.taskId}
            open={queueTrace.state.open}
            data-testid="ds-queue-trace-modal"
            onCancel={() => {
              queueTrace.close();
              if (isClustersView) {
                void refetchClusters();
              } else if (isPoolsView) {
                void refetchPools();
              }
            }}
          />
        </>
      )}
    </Flex>
  );
};

export default CephPage;
