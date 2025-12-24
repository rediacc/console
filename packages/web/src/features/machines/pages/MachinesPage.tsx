import React, { useCallback, useEffect, useState } from 'react';
import { Button, Card, Empty, Flex, Modal, Space, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  useCreateMachine,
  useDeleteMachine,
  useMachines,
  useUpdateMachineBridge,
  useUpdateMachineName,
  useUpdateMachineVault,
} from '@/api/queries/machines';
import { Repository, useRepositories } from '@/api/queries/repositories';
import { useStorage } from '@/api/queries/storage';
import { SplitResourceView, type ContainerData } from '@/components/common';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import TeamSelector from '@/components/common/TeamSelector';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import ConnectivityTestModal from '@/features/machines/components/ConnectivityTestModal';
import { useDialogState, useQueueTraceModal, useUnifiedModal } from '@/hooks';
import { useQueueAction } from '@/hooks/useQueueAction';
import { useTeamSelection } from '@/hooks/useTeamSelection';
import { type Machine } from '@/types';
import { confirmDelete } from '@/utils/confirmations';
import { showMessage } from '@/utils/messages';
import { PlusOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import { useMachineFunctionHandlers } from './hooks/useMachineFunctionHandlers';
import type { MachineFunctionData, MachineFormValues } from './types';

const MachinesPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common']);
  const [modal, contextHolder] = Modal.useModal();
  const location = useLocation();
  const navigate = useNavigate();

  // Use custom hooks for common patterns
  const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
  const {
    modalState: unifiedModalState,
    currentResource,
    openModal: openUnifiedModal,
    closeModal: closeUnifiedModal,
  } = useUnifiedModal<Machine & Record<string, unknown>>('machine');

  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [selectedRepositoryFromMachine, setSelectedRepositoryFromMachine] =
    useState<Repository | null>(null);
  const [selectedContainerFromMachine, setSelectedContainerFromMachine] =
    useState<ContainerData | null>(null);
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true);
  const [refreshKeys, setRefreshKeys] = useState<Record<string, number>>({});

  // Modal state management with new hooks
  const {
    state: queueTraceState,
    open: openQueueTrace,
    close: closeQueueTrace,
  } = useQueueTraceModal();
  const connectivityTest = useDialogState();

  const { data: machines = [], refetch: refetchMachines } = useMachines(
    selectedTeams.length > 0 ? selectedTeams : undefined,
    selectedTeams.length > 0
  );
  const { data: repositories = [] } = useRepositories(
    selectedTeams.length > 0 ? selectedTeams : undefined
  );
  const { data: storages = [] } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined);

  const createMachineMutation = useCreateMachine();
  const updateMachineNameMutation = useUpdateMachineName();
  const updateMachineBridgeMutation = useUpdateMachineBridge();
  const deleteMachineMutation = useDeleteMachine();
  const updateMachineVaultMutation = useUpdateMachineVault();
  const { executeAction, isExecuting } = useQueueAction();

  const { handleMachineFunctionSelected, handleDirectFunctionQueue } = useMachineFunctionHandlers({
    currentResource,
    teams,
    machines,
    repositories,
    storages,
    executeAction,
    closeUnifiedModal,
    openQueueTrace: (taskId, machineName) => openQueueTrace(taskId, machineName),
    setRefreshKeys,
    t,
  });

  useEffect(() => {
    const state = location.state;
    if (state?.createRepository) {
      navigate('/credentials', { state, replace: true });
    }
  }, [location, navigate]);

  const handleMachineSelect = (machine: Machine | null) => {
    setSelectedMachine(machine);
    if (machine) {
      setSelectedRepositoryFromMachine(null);
      setSelectedContainerFromMachine(null);
      setIsPanelCollapsed(false);
    }
  };

  const handleTogglePanelCollapse = () => {
    setIsPanelCollapsed((prev) => !prev);
  };

  const handleDeleteMachine = useCallback(
    (machine: Machine) => {
      confirmDelete({
        modal,
        t,
        resourceType: 'machine',
        resourceName: machine.machineName,
        translationNamespace: 'machines',
        onConfirm: () =>
          deleteMachineMutation.mutateAsync({
            teamName: machine.teamName,
            machineName: machine.machineName,
          }),
        onSuccess: () => refetchMachines(),
      });
    },
    [deleteMachineMutation, modal, refetchMachines, t]
  );

  const handleUnifiedModalSubmit = useCallback(
    async (formData: MachineFormValues) => {
      try {
        if (unifiedModalState.mode === 'create') {
          const { autoSetup, ...machineData } = formData;
          await createMachineMutation.mutateAsync(machineData);
          showMessage('success', t('machines:createSuccess'));

          if (autoSetup) {
            try {
              await new Promise((resolve) => setTimeout(resolve, 500));
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
                  install_nvidia_driver: 'auto',
                },
                priority: 3,
                addedVia: 'machine-creation-auto-setup',
                machineVault: formData.vaultContent || '{}',
              });

              if (result.success) {
                if (result.taskId) {
                  showMessage('info', t('machines:setupQueued'));
                  openQueueTrace(result.taskId, formData.machineName);
                } else if (result.isQueued) {
                  showMessage('info', t('machines:setupQueuedForSubmission'));
                }
              }
            } catch {
              showMessage('warning', t('machines:machineCreatedButSetupFailed'));
            }
          }

          closeUnifiedModal();
          refetchMachines();
        } else if (currentResource) {
          const currentName = currentResource.machineName;
          const newName = formData.machineName;

          if (newName && newName !== currentName) {
            await updateMachineNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentMachineName: currentName,
              newMachineName: newName,
            });
          }

          if (formData.bridgeName && formData.bridgeName !== currentResource.bridgeName) {
            await updateMachineBridgeMutation.mutateAsync({
              teamName: currentResource.teamName,
              machineName: newName || currentName,
              newBridgeName: formData.bridgeName,
            });
          }

          const vaultData = formData.vaultContent;
          if (vaultData && vaultData !== currentResource.vaultContent) {
            await updateMachineVaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              machineName: newName || currentName,
              vaultContent: vaultData,
              vaultVersion: currentResource.vaultVersion + 1,
            });
          }

          closeUnifiedModal();
          refetchMachines();
        }
      } catch {
        // Errors surfaced via mutation toasts
      }
    },
    [
      closeUnifiedModal,
      createMachineMutation,
      currentResource,
      executeAction,
      openQueueTrace,
      refetchMachines,
      t,
      unifiedModalState.mode,
      updateMachineBridgeMutation,
      updateMachineNameMutation,
      updateMachineVaultMutation,
    ]
  );

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
      if (!currentResource) return;
      try {
        await updateMachineVaultMutation.mutateAsync({
          teamName: currentResource.teamName,
          machineName: currentResource.machineName,
          vaultContent: vault,
          vaultVersion: version,
        });
        closeUnifiedModal();
        refetchMachines();
      } catch {
        // Error handled by mutation toast
      }
    },
    [closeUnifiedModal, currentResource, refetchMachines, updateMachineVaultMutation]
  );

  const handleResourceSelection = (resource: Machine | Repository | ContainerData | null) => {
    if (resource && 'machineName' in resource) {
      handleMachineSelect(resource);
    } else if (resource && 'repositoryName' in resource) {
      handleMachineSelect(null);
      setSelectedRepositoryFromMachine(resource);
      setSelectedContainerFromMachine(null);
      setIsPanelCollapsed(false);
    } else if (resource && 'id' in resource && 'state' in resource) {
      handleMachineSelect(null);
      setSelectedRepositoryFromMachine(null);
      setSelectedContainerFromMachine(resource);
      setIsPanelCollapsed(false);
    } else {
      handleMachineSelect(null);
      setSelectedRepositoryFromMachine(null);
      setSelectedContainerFromMachine(null);
    }
  };

  const handleRefreshMachines = () => {
    refetchMachines();
    setRefreshKeys((prev) => ({
      ...prev,
      _global: Date.now(),
    }));
  };

  const isSubmitting =
    createMachineMutation.isPending ||
    updateMachineNameMutation.isPending ||
    updateMachineBridgeMutation.isPending ||
    isExecuting;

  const isUpdatingVault = updateMachineVaultMutation.isPending;

  const modalExistingData = unifiedModalState.data ?? currentResource ?? undefined;

  // Note: This page uses SplitResourceView instead of ResourceListView
  // to support the side panel detail view. This is intentional.

  return (
    <>
      <Flex vertical>
        <Card>
          <Flex justify="space-between" align="center" wrap gap={12}>
            {/* eslint-disable-next-line no-restricted-syntax */}
            <Flex style={{ flex: 1, minWidth: 260 }}>
              <TeamSelector
                data-testid="machines-team-selector"
                teams={teams}
                selectedTeams={selectedTeams}
                onChange={setSelectedTeams}
                loading={teamsLoading}
                placeholder={t('teams.selectTeamToView')}
              />
            </Flex>
            {selectedTeams.length > 0 && (
              <Space size="small">
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
              </Space>
            )}
          </Flex>

          <Flex vertical>
            {selectedTeams.length === 0 ? (
              <>
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('teams.selectTeamPrompt')}
                />
              </>
            ) : (
              <SplitResourceView
                type="machine"
                teamFilter={selectedTeams}
                showFilters
                showActions
                onCreateMachine={() => openUnifiedModal('create')}
                onEditMachine={(machine) =>
                  openUnifiedModal('edit', machine as Machine & Record<string, unknown>)
                }
                onVaultMachine={(machine) =>
                  openUnifiedModal('vault', machine as Machine & Record<string, unknown>)
                }
                onFunctionsMachine={(machine, functionName) => {
                  // WARNING: Do not change this pattern!
                  // - Specific functions (functionName defined): Queue directly with defaults, NO modal
                  // - "Advanced" (functionName undefined): Open modal with function list
                  // This split behavior is intentional - users expect quick actions for specific
                  // functions and full configuration only when clicking "Advanced".
                  if (functionName) {
                    handleDirectFunctionQueue(machine, functionName);
                  } else {
                    openUnifiedModal('create', machine as Machine & Record<string, unknown>);
                  }
                }}
                onDeleteMachine={handleDeleteMachine}
                enabled={selectedTeams.length > 0}
                refreshKeys={refreshKeys}
                onQueueItemCreated={(taskId, machineName) => {
                  openQueueTrace(taskId, machineName);
                }}
                selectedResource={
                  selectedMachine || selectedRepositoryFromMachine || selectedContainerFromMachine
                }
                onResourceSelect={handleResourceSelection}
                isPanelCollapsed={isPanelCollapsed}
                onTogglePanelCollapse={handleTogglePanelCollapse}
              />
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
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        preselectedFunction={unifiedModalState.preselectedFunction}
        onSubmit={async (data) => {
          const machineData = data as MachineFormValues;
          await handleUnifiedModalSubmit(machineData);
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
          const machineName = queueTraceState.machineName;
          closeQueueTrace();
          if (machineName) {
            setRefreshKeys((prev) => ({
              ...prev,
              [machineName]: Date.now(),
            }));
          }
          refetchMachines();
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
        teamFilter={selectedTeams}
      />

      {contextHolder}
    </>
  );
};

export default MachinesPage;
