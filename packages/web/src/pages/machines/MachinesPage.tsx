import React, { useState, useCallback, useEffect } from 'react';
import { Empty, Modal, Tooltip } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PlusOutlined, WifiOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import ConnectivityTestModal from '@/pages/machines/components/ConnectivityTestModal';
import { showMessage } from '@/utils/messages';
import { SplitResourceView } from '@/pages/machines/components/SplitResourceView';
import type { ContainerData } from '@/pages/machines/components/SplitResourceView';
import {
 useCreateMachine,
 useUpdateMachineName,
 useUpdateMachineBridge,
 useUpdateMachineVault,
 useDeleteMachine,
 useMachines,
} from '@/api/queries/machines';
import { useRepos, Repo } from '@/api/queries/repos';
import { useStorage } from '@/api/queries/storage';
import { useQueueAction } from '@/hooks/useQueueAction';
import { useUnifiedModal, useTeamSelection, useQueueTraceModal, useDialogState } from '@/hooks';
import { confirmDelete } from '@/utils/confirmations';
import TeamSelector from '@/components/common/TeamSelector';
import { type Machine } from '@/types';
import { QueueFunction } from '@/api/queries/queue';
import type { QueueActionParams } from '@/services/queueActionService';
import { FUNCTION_DEFINITIONS } from '@/services/functionsService';
import { useTheme } from 'styled-components';
import {
 SectionStack,
 SectionHeading,
 PageWrapper,
 PageCard,
 SectionStack as HeaderSection,
 SectionHeaderRow as HeaderRow,
 ControlStack as TeamControls,
 InputSlot as TeamSelectorWrapper,
 ActionBar as ButtonGroup,
 ContentSection,
 RediaccButton as Button,
} from '@/components/ui';

interface MachineFormValues extends Record<string, unknown> {
 teamName: string;
 machineName: string;
 bridgeName: string;
 vaultContent?: string;
 autoSetup?: boolean;
}

interface MachineFunctionParams {
 repo?: string;
 sourceType?: string;
 from?: string;
 [key: string]: string | number | boolean | undefined;
}

interface MachineFunctionData {
 function: QueueFunction;
 params: MachineFunctionParams;
 priority: number;
 description: string;
}

const MachinesPage: React.FC = () => {
 const { t } = useTranslation(['resources', 'machines', 'common']);
 const [modal, contextHolder] = Modal.useModal();
 const location = useLocation();
 const navigate = useNavigate();
 const theme = useTheme();

 // Use custom hooks for common patterns
 const { teams, selectedTeams, setSelectedTeams, isLoading: teamsLoading } = useTeamSelection();
 const {
 modalState: unifiedModalState,
 currentResource,
 openModal: openUnifiedModal,
 closeModal: closeUnifiedModal,
 } = useUnifiedModal<Machine & Record<string, unknown>>('machine');

 const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
 const [selectedRepoFromMachine, setSelectedRepoFromMachine] = useState<Repo | null>(null);
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
 const { data: repos = [] } = useRepos(selectedTeams.length > 0 ? selectedTeams : undefined);
 const { data: storages = [] } = useStorage(selectedTeams.length > 0 ? selectedTeams : undefined);

 const createMachineMutation = useCreateMachine();
 const updateMachineNameMutation = useUpdateMachineName();
 const updateMachineBridgeMutation = useUpdateMachineBridge();
 const deleteMachineMutation = useDeleteMachine();
 const updateMachineVaultMutation = useUpdateMachineVault();
 const { executeAction, isExecuting } = useQueueAction();

 useEffect(() => {
 const state = location.state;
 if (state?.createRepo) {
 navigate('/credentials', { state, replace: true });
 }
 }, [location, navigate]);

 const handleMachineSelect = (machine: Machine | null) => {
 setSelectedMachine(machine);
 if (machine) {
 setSelectedRepoFromMachine(null);
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

 const handleMachineFunctionSelected = useCallback(
 async (functionData: MachineFunctionData) => {
 if (!currentResource) return;

 try {
 const machineName = currentResource.machineName;
 const bridgeName = currentResource.bridgeName;
 const teamData = teams.find((team) => team.teamName === currentResource.teamName);
 const repoParam =
 typeof functionData.params.repo === 'string' ? functionData.params.repo : undefined;

 const queuePayload: QueueActionParams = {
 teamName: currentResource.teamName,
 machineName,
 bridgeName,
 functionName: functionData.function.name,
 params: functionData.params,
 priority: functionData.priority,
 addedVia: 'machine-table',
 teamVault: teamData?.vaultContent || '{}',
 machineVault: currentResource.vaultContent || '{}',
 vaultContent: '{}',
 };

 if (repoParam) {
 const repo = repos.find((item) => item.repoGuid === repoParam);
 queuePayload.repoGuid = repo?.repoGuid || repoParam;
 queuePayload.vaultContent = repo?.vaultContent || '{}';
 }

 if (functionData.function.name === 'pull') {
 const sourceType =
 typeof functionData.params.sourceType === 'string'
 ? functionData.params.sourceType
 : undefined;
 const sourceIdentifier =
 typeof functionData.params.from === 'string' ? functionData.params.from : undefined;

 if (sourceType === 'machine' && sourceIdentifier) {
 const sourceMachine = machines.find(
 (machine) => machine.machineName === sourceIdentifier
 );
 if (sourceMachine?.vaultContent) {
 queuePayload.sourceMachineVault = sourceMachine.vaultContent;
 }
 }

 if (sourceType === 'storage' && sourceIdentifier) {
 const sourceStorage = storages.find(
 (storage) => storage.storageName === sourceIdentifier
 );
 if (sourceStorage?.vaultContent) {
 queuePayload.sourceStorageVault = sourceStorage.vaultContent;
 }
 }
 }

 const result = await executeAction(queuePayload);
 closeUnifiedModal();

 if (result.success) {
 if (result.taskId) {
 showMessage('success', t('machines:queueItemCreated'));
 openQueueTrace(result.taskId, machineName);
 } else if (result.isQueued) {
 showMessage(
 'info',
 t('resources:messages.highestPriorityQueued', { resourceType: 'machine' })
 );
 }
 } else {
 showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'));
 }
 } catch {
 showMessage('error', t('resources:errors.failedToCreateQueueItem'));
 }
 },
 [
 closeUnifiedModal,
 currentResource,
 executeAction,
 machines,
 openQueueTrace,
 repos,
 storages,
 t,
 teams,
 ]
 );

 const handleResourceSelection = (resource: Machine | Repo | ContainerData | null) => {
 if (resource && 'machineName' in resource) {
 handleMachineSelect(resource);
 } else if (resource && 'repoName' in resource) {
 handleMachineSelect(null);
 setSelectedRepoFromMachine(resource);
 setSelectedContainerFromMachine(null);
 setIsPanelCollapsed(false);
 } else if (resource && 'id' in resource && 'state' in resource) {
 handleMachineSelect(null);
 setSelectedRepoFromMachine(null);
 setSelectedContainerFromMachine(resource);
 setIsPanelCollapsed(false);
 } else {
 handleMachineSelect(null);
 setSelectedRepoFromMachine(null);
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

 // Direct queue handler for specific functions (bypasses modal)
 const handleDirectFunctionQueue = useCallback(
 async (machine: Machine, functionName: string) => {
 const funcDef = FUNCTION_DEFINITIONS[functionName];
 if (!funcDef) {
 showMessage('error', t('resources:errors.functionNotFound'));
 return;
 }

 // Build default params from function definition
 const defaultParams: Record<string, string> = {};
 if (funcDef.params) {
 Object.entries(funcDef.params).forEach(([paramName, paramInfo]) => {
 if (paramInfo.default) {
 defaultParams[paramName] = paramInfo.default;
 }
 });
 }

 const teamData = teams.find((team) => team.teamName === machine.teamName);

 const queuePayload: QueueActionParams = {
 teamName: machine.teamName,
 machineName: machine.machineName,
 bridgeName: machine.bridgeName,
 functionName,
 params: defaultParams,
 priority: 4, // Normal priority
 addedVia: 'machine-table-quick',
 teamVault: teamData?.vaultContent || '{}',
 machineVault: machine.vaultContent || '{}',
 vaultContent: '{}',
 };

 try {
 const result = await executeAction(queuePayload);

 if (result.success) {
 if (result.taskId) {
 showMessage('success', t('machines:queueItemCreated'));
 openQueueTrace(result.taskId, machine.machineName);
 } else if (result.isQueued) {
 showMessage(
 'info',
 t('resources:messages.highestPriorityQueued', { resourceType: 'machine' })
 );
 }
 } else {
 showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'));
 }

 setRefreshKeys((prev) => ({
 ...prev,
 [machine.machineName]: Date.now(),
 }));
 } catch {
 showMessage('error', t('resources:errors.failedToCreateQueueItem'));
 }
 },
 [executeAction, openQueueTrace, t, teams]
 );

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
 <PageWrapper>
 <SectionStack>
 <SectionHeading level={3}>
 {t('machines:heading', { defaultValue: 'Machines' })}
 </SectionHeading>
 <PageCard>
 <HeaderSection>
 <HeaderRow>
 <TeamControls>
 <TeamSelectorWrapper>
 <TeamSelector
 data-testid="machines-team-selector"
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
 <Tooltip title={t('machines:createMachine')}>
 <Button
 
 iconOnly
 icon={<PlusOutlined />}
 data-testid="machines-create-machine-button"
 onClick={() => openUnifiedModal('create')}
 aria-label={t('machines:createMachine')}
 />
 </Tooltip>
 <Tooltip title={t('machines:connectivityTest')}>
 <Button
 iconOnly
 icon={<WifiOutlined />}
 data-testid="machines-connectivity-test-button"
 onClick={() => connectivityTest.open()}
 disabled={machines.length === 0}
 aria-label={t('machines:connectivityTest')}
 />
 </Tooltip>
 <Tooltip title={t('common:actions.refresh')}>
 <Button
 iconOnly
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
 selectedMachine || selectedRepoFromMachine || selectedContainerFromMachine
 }
 onResourceSelect={handleResourceSelection}
 isPanelCollapsed={isPanelCollapsed}
 onTogglePanelCollapse={handleTogglePanelCollapse}
 />
 )}
 </ContentSection>
 </PageCard>
 </SectionStack>
 </PageWrapper>

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
 onClose={connectivityTest.close}
 machines={machines}
 teamFilter={selectedTeams}
 />

 {contextHolder}
 </>
 );
};

export default MachinesPage;
