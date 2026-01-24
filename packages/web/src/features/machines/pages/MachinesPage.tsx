import React, { useCallback, useEffect, useState } from 'react';
import { Button, Card, Drawer, Empty, Flex, Grid, Modal, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  useGetTeamMachines,
  useGetTeamRepositories,
  useGetTeamStorages,
  useMachineMutations,
} from '@/api/api-hooks.generated';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { ContainerDetailPanel } from '@/components/resources/internal/ContainerDetailPanel';
import { MachineTable } from '@/components/resources/internal/MachineTable';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { RepositoryDetailPanel } from '@/components/resources/internal/RepositoryDetailPanel';
import ConnectivityTestModal from '@/features/machines/components/ConnectivityTestModal';
import type { ContainerData } from '@/features/resources/shared/types';
import { useDialogState, useQueueTraceModal, useUnifiedModal } from '@/hooks';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { useQueueAction } from '@/hooks/useQueueAction';
import { useTeamSelection } from '@/hooks/useTeamSelection';
import { type Machine } from '@/types';
import { confirmDelete } from '@/utils/confirmations';
import { showMessage } from '@/utils/messages';
import { PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { useMachineFunctionHandlers } from './hooks/useMachineFunctionHandlers';
import type { MachineFormValues, MachineFunctionData } from './types';

const MachinesPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common']);
  const [modal, contextHolder] = Modal.useModal();
  const location = useLocation();
  const navigate = useNavigate();

  // Use custom hooks for common patterns
  const {
    teams,
    selectedTeam,
    setSelectedTeam,
    isLoading: teamsLoading,
  } = useTeamSelection({
    pageId: 'machines',
  });
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
  } = useUnifiedModal<Machine & Record<string, unknown>>('machine');

  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [selectedRepositoryFromMachine, setSelectedRepositoryFromMachine] =
    useState<GetTeamRepositories_ResultSet1 | null>(null);
  const [selectedContainerFromMachine, setSelectedContainerFromMachine] =
    useState<ContainerData | null>(null);

  const panelWidth = usePanelWidth();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;

  // Modal state management with new hooks
  const {
    state: queueTraceState,
    open: openQueueTrace,
    close: closeQueueTrace,
  } = useQueueTraceModal();
  const connectivityTest = useDialogState();

  const { data: machines = [], refetch: refetchMachines } = useGetTeamMachines(
    selectedTeam ?? undefined
  );
  const { data: repositories = [] } = useGetTeamRepositories(selectedTeam ?? undefined);
  const { data: storages = [] } = useGetTeamStorages(selectedTeam ?? undefined);

  const mutations = useMachineMutations();
  const { executeDynamic, isExecuting } = useQueueAction();

  const { handleMachineFunctionSelected, handleDirectFunctionQueue } = useMachineFunctionHandlers({
    currentResource,
    teams: teams.map((t) => ({
      teamName: t.teamName ?? '',
      vaultContent: t.vaultContent ?? undefined,
    })),
    machines,
    repositories: repositories.map((r) => ({
      repositoryGuid: r.repositoryGuid ?? '',
      vaultContent: r.vaultContent ?? undefined,
    })),
    storages: storages.map((s) => ({
      storageName: s.storageName ?? '',
      vaultContent: s.vaultContent ?? undefined,
    })),
    executeDynamic,
    closeUnifiedModal,
    openQueueTrace: (taskId, machineName) => openQueueTrace(taskId, machineName),
    t,
  });

  useEffect(() => {
    const state = location.state;
    if (state?.createRepository) {
      void navigate('/credentials', { state, replace: true });
    }
  }, [location, navigate]);

  const handleMachineSelect = (machine: Machine | null) => {
    setSelectedMachine(machine);
    if (machine) {
      setSelectedRepositoryFromMachine(null);
      setSelectedContainerFromMachine(null);
    }
  };

  const handleDeleteMachine = useCallback(
    (machine: Machine) => {
      confirmDelete({
        modal,
        t,
        resourceType: 'machine',
        resourceName: machine.machineName ?? '',
        translationNamespace: 'machines',
        onConfirm: () =>
          mutations.deleteMachine.mutateAsync({
            teamName: machine.teamName ?? '',
            machineName: machine.machineName ?? '',
          }),
        onSuccess: () => refetchMachines(),
      });
    },
    [mutations.deleteMachine, modal, refetchMachines, t]
  );

  const executeAutoSetup = useCallback(
    async (formData: MachineFormValues) => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const result = await executeDynamic('setup', {
        params: {
          datastore_size: '95%',
          from: 'apt-repo',
          rclone_source: 'install-script',
          docker_source: 'docker-repo',
          install_amd_driver: 'auto',
          install_nvidia_driver: 'auto',
        },
        teamName: formData.teamName,
        machineName: formData.machineName,
        bridgeName: formData.bridgeName,
        priority: 3,
        addedVia: 'machine-creation-auto-setup',
        machineVault: formData.vaultContent ?? '{}',
      });

      if (!result.success) return;

      if (result.taskId) {
        showMessage('info', t('machines:setupQueued'));
        openQueueTrace(result.taskId, formData.machineName);
      } else if (result.isQueued) {
        showMessage('info', t('machines:setupQueuedForSubmission'));
      }
    },
    [executeDynamic, openQueueTrace, t]
  );

  const handleCreateMachine = useCallback(
    async (formData: MachineFormValues) => {
      const { autoSetup, ...machineData } = formData;
      await mutations.createMachine.mutateAsync({
        ...machineData,
        vaultContent: machineData.vaultContent ?? '{}',
      });
      showMessage('success', t('machines:createSuccess'));

      if (autoSetup) {
        try {
          await executeAutoSetup(formData);
        } catch {
          showMessage('warning', t('machines:machineCreatedButSetupFailed'));
        }
      }

      closeUnifiedModal();
      void refetchMachines();
    },
    [closeUnifiedModal, executeAutoSetup, mutations, refetchMachines, t]
  );

  const handleEditMachine = useCallback(
    async (formData: MachineFormValues) => {
      if (!currentResource) return;

      const currentName = currentResource.machineName;
      const newName = formData.machineName;

      if (newName && newName !== currentName) {
        await mutations.updateMachineName.mutateAsync({
          teamName: currentResource.teamName,
          currentMachineName: currentName,
          newMachineName: newName,
        });
      }

      if (formData.bridgeName && formData.bridgeName !== currentResource.bridgeName) {
        await mutations.updateMachineAssignedBridge.mutateAsync({
          teamName: currentResource.teamName,
          machineName: newName || currentName,
          newBridgeName: formData.bridgeName,
        });
      }

      const vaultData = formData.vaultContent;
      if (vaultData && vaultData !== currentResource.vaultContent) {
        await mutations.updateMachineVault.mutateAsync({
          teamName: currentResource.teamName,
          machineName: newName || currentName,
          vaultContent: vaultData,
          vaultVersion: (currentResource.vaultVersion ?? 0) + 1,
        });
      }

      closeUnifiedModal();
      void refetchMachines();
    },
    [closeUnifiedModal, currentResource, mutations, refetchMachines]
  );

  const handleUnifiedModalSubmit = useCallback(
    async (formData: MachineFormValues) => {
      try {
        if (unifiedModalState.mode === 'create') {
          await handleCreateMachine(formData);
        } else if (currentResource) {
          await handleEditMachine(formData);
        }
      } catch {
        // Errors surfaced via mutation toasts
      }
    },
    [currentResource, handleCreateMachine, handleEditMachine, unifiedModalState.mode]
  );

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return;
      try {
        await mutations.updateMachineVault.mutateAsync({
          teamName: currentResource.teamName,
          machineName: currentResource.machineName,
          vaultContent: vault,
          vaultVersion: version,
        });
        closeUnifiedModal();
        void refetchMachines();
      } catch {
        // Error handled by mutation toast
      }
    },
    [closeUnifiedModal, currentResource, refetchMachines, mutations.updateMachineVault]
  );

  const handleResourceSelection = (
    resource: Machine | GetTeamRepositories_ResultSet1 | ContainerData | null
  ) => {
    if (resource && 'machineName' in resource) {
      handleMachineSelect(resource);
    } else if (resource && 'repositoryName' in resource) {
      handleMachineSelect(null);
      setSelectedRepositoryFromMachine(resource);
      setSelectedContainerFromMachine(null);
    } else if (resource && 'id' in resource && 'state' in resource) {
      handleMachineSelect(null);
      setSelectedRepositoryFromMachine(null);
      setSelectedContainerFromMachine(resource);
    } else {
      handleMachineSelect(null);
      setSelectedRepositoryFromMachine(null);
      setSelectedContainerFromMachine(null);
    }
  };

  const handlePanelClose = () => {
    handleResourceSelection(null);
  };

  const selectedResource =
    selectedMachine ?? selectedRepositoryFromMachine ?? selectedContainerFromMachine;

  const renderPanelContent = () => {
    if (!selectedResource) return null;

    if ('machineName' in selectedResource) {
      return (
        <MachineVaultStatusPanel
          machine={selectedResource}
          visible
          onClose={handlePanelClose}
          splitView
        />
      );
    }
    if ('repositoryName' in selectedResource) {
      return (
        <RepositoryDetailPanel
          repository={selectedResource}
          visible
          onClose={handlePanelClose}
          splitView
        />
      );
    }
    return (
      <ContainerDetailPanel
        container={selectedResource}
        visible
        onClose={handlePanelClose}
        splitView
      />
    );
  };

  const handleRefreshMachines = () => {
    void refetchMachines();
  };

  const isSubmitting = [
    mutations.createMachine.isPending,
    mutations.updateMachineName.isPending,
    mutations.updateMachineAssignedBridge.isPending,
    isExecuting,
  ].some(Boolean);

  const isUpdatingVault = mutations.updateMachineVault.isPending;

  const modalExistingData = unifiedModalState.data ?? currentResource ?? undefined;

  const renderContent = () => {
    if (!selectedTeam) {
      return (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('teams.selectTeamPrompt')} />
      );
    }

    return (
      <Flex className="h-full w-full relative overflow-hidden">
        <Flex className="w-full h-full overflow-auto">
          <MachineTable
            teamFilter={[selectedTeam]}
            showActions
            onEditMachine={(machine) =>
              openUnifiedModal('edit', machine as Machine & Record<string, unknown>)
            }
            onFunctionsMachine={(machine, functionName) => {
              // WARNING: Do not change this pattern!
              // - Specific functions (functionName defined): Queue directly with defaults, NO modal
              // - "Advanced" (functionName undefined): Open modal with function list
              // This split behavior is intentional - users expect quick actions for specific
              // functions and full configuration only when clicking "Advanced".
              if (functionName) {
                void handleDirectFunctionQueue(machine, functionName);
              } else {
                openUnifiedModal('create', machine as Machine & Record<string, unknown>);
              }
            }}
            onDeleteMachine={handleDeleteMachine}
            onQueueItemCreated={(taskId, machineName) => openQueueTrace(taskId, machineName)}
            onRowClick={(machine) => handleResourceSelection(machine)}
            selectedMachine={selectedMachine}
          />
        </Flex>

        {isMobile ? (
          <Modal
            data-testid="machines-detail-modal"
            open={!!selectedResource}
            onCancel={handlePanelClose}
            footer={null}
            width="100%"
            centered
          >
            {renderPanelContent()}
          </Modal>
        ) : (
          <Drawer
            data-testid="machines-detail-drawer"
            open={!!selectedResource}
            onClose={handlePanelClose}
            width={panelWidth}
            placement="right"
            mask
          >
            {renderPanelContent()}
          </Drawer>
        )}
      </Flex>
    );
  };

  return (
    <>
      <Flex vertical>
        <Card classNames={{ body: 'flex flex-col gap-3' }}>
          <Flex justify="space-between" align="center" wrap className="w-full !gap-3">
            {}
            <Flex className="flex-1 min-w-[260px]">
              <TeamSelector
                data-testid="machines-team-selector"
                teams={teams}
                selectedTeam={selectedTeam}
                onChange={setSelectedTeam}
                loading={teamsLoading}
                placeholder={t('teams.selectTeamToView')}
              />
            </Flex>
            {selectedTeam && (
              <Flex align="center">
                <Tooltip title={t('machines:createMachine')}>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    data-testid="machines-create-machine-button"
                    onClick={() => openUnifiedModal('create')}
                    aria-label={t('machines:createMachine')}
                  />
                </Tooltip>
                <Tooltip title={t('machines:checkAndRefresh')}>
                  <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    data-testid="machines-test-and-refresh-button"
                    onClick={() => connectivityTest.open()}
                    disabled={machines.length === 0}
                    aria-label={t('machines:checkAndRefresh')}
                  />
                </Tooltip>
              </Flex>
            )}
          </Flex>

          <Flex vertical>
            {teamsLoading ? (
              <LoadingWrapper loading centered minHeight={200}>
                <Flex />
              </LoadingWrapper>
            ) : (
              renderContent()
            )}
          </Flex>
        </Card>
      </Flex>

      <UnifiedResourceModal
        data-testid="machines-machine-modal"
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="machine"
        mode={unifiedModalState.mode}
        existingData={modalExistingData}
        teamFilter={selectedTeam ? [selectedTeam] : undefined}
        preselectedFunction={unifiedModalState.preselectedFunction}
        onSubmit={async (data) => {
          await handleUnifiedModalSubmit(data as unknown as MachineFormValues);
        }}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={(functionData) => {
          const machineFunctionData = functionData as MachineFunctionData;
          return handleMachineFunctionSelected(machineFunctionData);
        }}
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={['machine', 'backup']}
        hiddenParams={[]}
        defaultParams={{}}
      />

      <QueueItemTraceModal
        data-testid="machines-queue-trace-modal"
        taskId={queueTraceState.taskId}
        open={queueTraceState.open}
        onCancel={() => {
          closeQueueTrace();
          void refetchMachines();
        }}
      />

      <ConnectivityTestModal
        data-testid="machines-connectivity-test-modal"
        open={connectivityTest.isOpen}
        onClose={() => {
          connectivityTest.close();
          handleRefreshMachines();
        }}
        machines={machines}
        teamFilter={selectedTeam ? [selectedTeam] : []}
      />

      {contextHolder}
    </>
  );
};

export default MachinesPage;
