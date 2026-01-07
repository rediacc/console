import React, { useCallback, useMemo } from 'react';
import {
  Alert,
  Button,
  Card,
  Drawer,
  Flex,
  Grid,
  Modal,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useGetTeamMachines } from '@/api/api-hooks.generated';
import { useGetTeamRepositories } from '@/api/api-hooks.generated';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { RemoteFileBrowserModal } from '@/components/common/RemoteFileBrowserModal';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { ContainerDetailPanel } from '@/components/resources/internal/ContainerDetailPanel';
import { RepositoryDetailPanel } from '@/components/resources/internal/RepositoryDetailPanel';
import { MachineRepositoryTable } from '@/components/resources/MachineRepositoryTable';
import ConnectivityTestModal from '@/features/machines/components/ConnectivityTestModal';
import { ResourcePageLayout } from '@/features/resources/shared/ResourcePageLayout';
import { ContainerData, RepositoryRowData } from '@/features/resources/shared/types';
import { useResourcePageState } from '@/features/resources/shared/useResourcePageState';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation';
import { Machine, PluginContainer, Repository } from '@/types';
import {
  CloudDownloadOutlined,
  DesktopOutlined,
  DoubleLeftOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@/utils/optimizedIcons';

type MachineReposLocationState = {
  machine?: Machine;
} | null;

const MachineReposPage: React.FC = () => {
  const { machineName } = useParams<{ machineName: string }>();
  const navigate = useNavigate();
  const location = useLocation() as { state?: MachineReposLocationState };
  const { t } = useTranslation(['resources', 'machines', 'common']);

  // State for machine data - can come from route state or API
  const routeState = location.state;

  // Use shared panel width hook (33% of window, min 300px, max 700px)
  const panelWidth = usePanelWidth();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;

  // Queue trace modal state
  const queueTrace = useQueueTraceModal();

  // Remote file browser modal state
  const fileBrowserModal = useDialogState<Machine>();

  // Unified resource modal state
  const unifiedModal = useDialogState<{
    mode: 'create' | 'edit' | 'vault';
    data?: Record<string, unknown>;
    creationContext?: 'credentials-only' | 'normal';
  }>();

  // Connectivity test modal state
  const connectivityTest = useDialogState();

  // Get team name from route state for initial queries
  const initialTeamName = routeState?.machine?.teamName;

  // Fetch all machines to find our specific machine if not passed via state
  const {
    data: machines = [],
    isLoading: machinesLoading,
    error: machinesError,
    refetch: refetchMachines,
  } = useGetTeamMachines(initialTeamName ?? undefined);

  // Derive machine from route state or API data (no setState needed)
  const machine = useMemo(() => {
    // First try to find fresh data from API
    if (machines.length > 0 && machineName) {
      const foundMachine = machines.find((m) => m.machineName === machineName);
      if (foundMachine) return foundMachine;
    }
    // Fall back to route state
    return routeState?.machine ?? null;
  }, [machines, machineName, routeState?.machine]);

  // Repository creation hook (handles credentials + queue item)
  const { createRepository } = useRepositoryCreation(machines);

  // Fetch repositories (needed for MachineRepositoryTable)
  const { data: repositories = [], refetch: refetchRepos } = useGetTeamRepositories(
    machine?.teamName ?? undefined
  );

  const refreshData = useCallback(async () => {
    await Promise.all([refetchRepos(), refetchMachines()]);
  }, [refetchRepos, refetchMachines]);

  const { selectedResource, setSelectedResource, refreshKey, handleRefresh, handlePanelClose } =
    useResourcePageState<Repository | ContainerData | PluginContainer>(refreshData, !!machine);

  const handleBackToMachines = () => {
    void navigate('/machines');
  };

  const handleCreateRepo = () => {
    if (!machine) return;

    // Open the Repository creation modal with prefilled machine
    unifiedModal.open({
      mode: 'create',
      data: {
        machineName: machine.machineName,
        teamName: machine.teamName,
        prefilledMachine: true,
      },
      creationContext: 'normal',
    });
  };

  const handlePull = () => {
    if (!machine) return;

    fileBrowserModal.open(machine);
  };

  const handleUnifiedModalSubmit = async (data: Record<string, unknown>) => {
    const result = await createRepository(
      data as unknown as Parameters<typeof createRepository>[0]
    );

    if (result.success) {
      unifiedModal.close();

      // If we have a taskId, open the queue trace modal
      if (result.taskId) {
        queueTrace.open(result.taskId, result.machineName ?? undefined);
      } else {
        // No queue item (credentials-only mode), just refresh
        await handleRefresh();
      }
    }
  };

  const handleRepositoryClick = (repoRow: RepositoryRowData) => {
    // Map Repository data to Repository type
    const mappedRepo: Repository = {
      repositoryName: repoRow.name,
      repositoryGuid: repoRow.originalGuid ?? repoRow.name,
      teamName: machine!.teamName ?? '',
      vaultVersion: 0,
      vaultContent: null,
      grandGuid: '',
      parentGuid: null,
      repositoryNetworkMode: '',
      repositoryNetworkId: 0,
      repositoryTag: repoRow.repositoryTag ?? '',
    };

    // Find the actual Repository from the API data - must match both name AND tag to distinguish forks
    const actualRepository = repositories.find(
      (r) => r.repositoryName === repoRow.name && r.repositoryTag === repoRow.repositoryTag
    );

    setSelectedResource(actualRepository ?? mappedRepo);
  };

  const handleContainerClick = (
    container:
      | PluginContainer
      | ContainerData
      | { id: string; name: string; state: string; [key: string]: unknown }
  ) => {
    setSelectedResource(container);
  };

  // Loading state
  if (machinesLoading && !machine) {
    return (
      <Flex vertical>
        <Card>
          <Flex vertical align="center" className="w-full">
            <LoadingWrapper loading centered minHeight={160}>
              <Flex />
            </LoadingWrapper>
            <Typography.Text>{t('common:general.loading')}</Typography.Text>
          </Flex>
        </Card>
      </Flex>
    );
  }

  // Error state - machine not found
  if (machinesError || (!machinesLoading && !machine)) {
    return (
      <Flex vertical>
        <Card>
          <Flex vertical>
            <Alert
              message={t('machines:machineNotFound')}
              description={
                <Flex vertical>
                  <p>{t('machines:machineNotFoundDescription', { machineName })}</p>
                  <Button type="primary" onClick={handleBackToMachines}>
                    {t('machines:backToMachines')}
                  </Button>
                </Flex>
              }
              type="error"
            />
          </Flex>
        </Card>
      </Flex>
    );
  }

  const breadcrumbItems = [
    {
      title: <Typography.Text>{t('machines:machines')}</Typography.Text>,
      onClick: () => navigate('/machines'),
    },
    {
      title: machine?.machineName ?? machineName,
    },
    {
      title: t('resources:repositories.repositories'),
    },
  ];

  const header = (
    <Flex align="center" wrap>
      <Tooltip title={t('machines:backToMachines')}>
        <Button
          type="text"
          icon={<DoubleLeftOutlined />}
          onClick={handleBackToMachines}
          aria-label={t('machines:backToMachines')}
          data-testid="machine-repositories-back-button"
        />
      </Tooltip>
      <Typography.Title level={4}>
        <Space>
          <DesktopOutlined />
          <Typography.Text>
            {t('machines:machine')}: {machine?.machineName}
          </Typography.Text>
        </Space>
      </Typography.Title>
    </Flex>
  );

  const tags = (
    <Flex align="center" wrap>
      <Tag>
        {t('machines:team')}: {machine?.teamName}
      </Tag>
      <Tag>
        {t('machines:bridge')}: {machine?.bridgeName}
      </Tag>
      {machine?.regionName && (
        <Tag>
          {t('machines:region')}: {machine.regionName}
        </Tag>
      )}
    </Flex>
  );

  const actions = (
    <>
      <Tooltip title={t('machines:createRepository')}>
        <Button
          type="text"
          icon={<PlusOutlined />}
          onClick={handleCreateRepo}
          data-testid="machine-repositories-create-repo-button"
        />
      </Tooltip>
      <Tooltip title={t('functions:functions.pull.name')}>
        <Button
          type="text"
          icon={<CloudDownloadOutlined />}
          onClick={handlePull}
          data-testid="machine-repositories-pull-button"
        />
      </Tooltip>
      <Tooltip title={t('machines:checkAndRefresh')}>
        <Button
          type="text"
          icon={<ReloadOutlined />}
          onClick={() => connectivityTest.open()}
          disabled={!machine}
          data-testid="machine-repositories-test-and-refresh-button"
          aria-label={t('machines:checkAndRefresh')}
        />
      </Tooltip>
    </>
  );

  const content = machine ? (
    <MachineRepositoryTable
      machine={machine}
      key={`${machine.machineName}-${refreshKey}`}
      refreshKey={refreshKey}
      onActionComplete={handleRefresh}
      onRepositoryClick={handleRepositoryClick}
      onContainerClick={handleContainerClick}
      onQueueItemCreated={(taskId, machineName) => {
        queueTrace.open(taskId, machineName);
      }}
    />
  ) : null;

  const panelContent =
    selectedResource &&
    ('repositoryName' in selectedResource ? (
      <RepositoryDetailPanel
        repository={selectedResource}
        visible
        onClose={handlePanelClose}
        splitView
      />
    ) : (
      <ContainerDetailPanel
        container={selectedResource as unknown as ContainerData}
        visible
        onClose={handlePanelClose}
        splitView
      />
    ));

  const drawer = isMobile ? (
    <Modal
      open={!!selectedResource}
      onCancel={handlePanelClose}
      footer={null}
      width="100%"
      styles={{ body: { padding: 0 } }}
      data-testid="machine-repositories-modal"
      centered
    >
      {panelContent}
    </Modal>
  ) : (
    <Drawer
      open={!!selectedResource}
      onClose={handlePanelClose}
      width={panelWidth}
      placement="right"
      mask
      data-testid="machine-repositories-drawer"
    >
      {panelContent}
    </Drawer>
  );

  return (
    <>
      <ResourcePageLayout
        breadcrumbItems={breadcrumbItems}
        breadcrumbTestId="machine-repositories-breadcrumb"
        header={header}
        tags={tags}
        actions={actions}
        content={content}
        drawer={drawer}
      />

      <QueueItemTraceModal
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close();
          void handleRefresh();
        }}
      />

      {fileBrowserModal.state.data && (
        <RemoteFileBrowserModal
          open={fileBrowserModal.isOpen}
          onCancel={fileBrowserModal.close}
          machineName={fileBrowserModal.state.data.machineName ?? ''}
          teamName={fileBrowserModal.state.data.teamName ?? ''}
          bridgeName={fileBrowserModal.state.data.bridgeName ?? ''}
          onQueueItemCreated={(taskId: string) => {
            queueTrace.open(taskId, fileBrowserModal.state.data?.machineName ?? undefined);
            fileBrowserModal.close();
          }}
        />
      )}

      <UnifiedResourceModal
        open={unifiedModal.isOpen}
        onCancel={() => unifiedModal.close()}
        resourceType="repository"
        mode={unifiedModal.state.data?.mode ?? 'create'}
        existingData={unifiedModal.state.data?.data}
        teamFilter={machine?.teamName ? [machine.teamName] : undefined}
        creationContext={unifiedModal.state.data?.creationContext}
        onSubmit={handleUnifiedModalSubmit}
      />

      <ConnectivityTestModal
        data-testid="machine-repositories-connectivity-test-modal"
        open={connectivityTest.isOpen}
        onTestsComplete={() => void handleRefresh()}
        onClose={() => {
          connectivityTest.close();
          void handleRefresh();
        }}
        machines={machine ? [machine] : []}
        teamFilter={machine?.teamName ? [machine.teamName] : undefined}
      />
    </>
  );
};

export default MachineReposPage;
