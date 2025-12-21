import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Breadcrumb, Button, Card, Flex, Space, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepositories } from '@/api/queries/repositories';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { MachineRepositoryTable } from '@/components/resources/MachineRepositoryTable';
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel';
import { DETAIL_PANEL } from '@/constants/layout';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation';
import ConnectivityTestModal from '@/pages/machines/components/ConnectivityTestModal';
import { RemoteFileBrowserModal } from '@/pages/resources/components/RemoteFileBrowserModal';
import { Machine, PluginContainer, Repository } from '@/types';
import {
  CloudDownloadOutlined,
  DesktopOutlined,
  DoubleLeftOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@/utils/optimizedIcons';

interface ContainerData {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  port_mappings?: Array<{
    host?: string;
    host_port?: string;
    container_port: string;
    protocol: string;
  }>;
  labels: string;
  mounts: string;
  networks: string;
  size: string;
  repository: string;
  cpu_percent: string;
  memory_usage: string;
  memory_percent: string;
  net_io: string;
  block_io: string;
  pids: string;
}

type MachineReposLocationState = {
  machine?: Machine;
} | null;

type RepositoryRowData = {
  name: string;
  repositoryTag?: string;
  originalGuid?: string;
};

const MachineReposPage: React.FC = () => {
  const { machineName } = useParams<{ machineName: string }>();
  const navigate = useNavigate();
  const location = useLocation() as { state?: MachineReposLocationState };
  const { t } = useTranslation(['resources', 'machines', 'common']);

  // State for machine data - can come from route state or API
  const routeState = location.state;
  const [machine, setMachine] = useState<Machine | null>(routeState?.machine ?? null);

  // Use shared panel width hook (33% of window, min 300px, max 700px)
  const panelWidth = usePanelWidth();

  // State for selected resource (Repository or container) and panel
  const [selectedResource, setSelectedResource] = useState<
    Repository | ContainerData | PluginContainer | null
  >(null);
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true);
  const [splitWidth, setSplitWidth] = useState(panelWidth);
  const [backdropVisible, setBackdropVisible] = useState(false);
  const [shouldRenderBackdrop, setShouldRenderBackdrop] = useState(false);

  // Refresh key for forcing MachineRepositoryTable updates
  const [refreshKey, setRefreshKey] = useState(0);

  // Auto-load state
  const [hasInitiallyLoaded, setHasInitiallyLoaded] = useState(false);

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

  // Fetch all machines to find our specific machine if not passed via state
  const {
    data: machines = [],
    isLoading: machinesLoading,
    error: machinesError,
    refetch: refetchMachines,
  } = useMachines(machine?.teamName ? [machine.teamName] : undefined, true);

  // Repository creation hook (handles credentials + queue item)
  const { createRepository } = useRepositoryCreation(machines);

  // Fetch repositories (needed for MachineRepositoryTable)
  const { data: repositories = [], refetch: refetchRepos } = useRepositories(
    machine?.teamName ? [machine.teamName] : undefined
  );

  // Find the machine from API if not already set OR update it when machines data changes
  useEffect(() => {
    if (machines.length > 0 && machineName) {
      const foundMachine = machines.find((m) => m.machineName === machineName);
      if (foundMachine) {
        // Update machine state with fresh data (including updated vaultStatus)
        setMachine(foundMachine);
      }
    }
  }, [machines, machineName]);

  const handleRefresh = useCallback(async () => {
    setRefreshKey((prev) => prev + 1);
    // Refetch both repositories AND machines to get updated vaultStatus
    await Promise.all([refetchRepos(), refetchMachines()]);
  }, [refetchRepos, refetchMachines]);

  // Auto-refresh data on mount (query existing data, no queue items)
  useEffect(() => {
    if (machine && !hasInitiallyLoaded) {
      setHasInitiallyLoaded(true);
      // Just refresh existing data from database
      handleRefresh();
    }
  }, [machine, hasInitiallyLoaded, handleRefresh]);

  const handleBackToMachines = () => {
    navigate('/machines');
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
        queueTrace.open(result.taskId, result.machineName || undefined);
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
      repositoryGuid: repoRow.originalGuid || repoRow.name,
      teamName: machine!.teamName,
      vaultVersion: 0,
      vaultContent: null,
      grandGuid: '',
      parentGuid: null,
      repositoryNetworkMode: '',
      repositoryNetworkId: 0,
      repositoryTag: repoRow.repositoryTag || '',
    };

    // Find the actual Repository from the API data - must match both name AND tag to distinguish forks
    const actualRepository = repositories.find(
      (r) => r.repositoryName === repoRow.name && r.repositoryTag === repoRow.repositoryTag
    );

    setSelectedResource(actualRepository || mappedRepo);
    setIsPanelCollapsed(false);
  };

  const handleContainerClick = (
    container:
      | PluginContainer
      | ContainerData
      | { id: string; name: string; state: string; [key: string]: unknown }
  ) => {
    setSelectedResource(container as PluginContainer | ContainerData);
    setIsPanelCollapsed(false);
  };

  const handlePanelClose = () => {
    setSelectedResource(null);
    // Panel closes completely, no need to set collapsed state
  };

  const handleTogglePanelCollapse = () => {
    setIsPanelCollapsed(!isPanelCollapsed);
  };

  // Update splitWidth when window resizes (to keep within bounds)
  useEffect(() => {
    setSplitWidth(panelWidth);
  }, [panelWidth]);

  // Manage backdrop fade in/out
  useEffect(() => {
    if (selectedResource) {
      // Mount backdrop and trigger fade-in
      setShouldRenderBackdrop(true);
      requestAnimationFrame(() => {
        setBackdropVisible(true);
      });
    } else {
      // Trigger fade-out
      setBackdropVisible(false);
      // Unmount backdrop after fade-out animation completes
      const timer = setTimeout(() => {
        setShouldRenderBackdrop(false);
      }, 250); // Match transition duration
      return () => clearTimeout(timer);
    }
  }, [selectedResource]);

  const actualPanelWidth = isPanelCollapsed ? DETAIL_PANEL.COLLAPSED_WIDTH : splitWidth;

  // Loading state
  if (machinesLoading && !machine) {
    return (
      <Flex vertical>
        <Card>
          <Flex vertical align="center" style={{ width: '100%' }}>
            <LoadingWrapper loading centered minHeight={160}>
              <Flex />
            </LoadingWrapper>
            <Typography.Text type="secondary">{t('common:general.loading')}</Typography.Text>
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
                <Flex vertical style={{ maxWidth: 520 }}>
                  <p>{t('machines:machineNotFoundDescription', { machineName })}</p>
                  <Button type="primary" onClick={handleBackToMachines}>
                    {t('machines:backToMachines')}
                  </Button>
                </Flex>
              }
              type="error"
              showIcon
            />
          </Flex>
        </Card>
      </Flex>
    );
  }

  return (
    <Flex vertical>
      <Card>
        <Flex vertical>
          <Flex vertical>
            <Breadcrumb
              items={[
                {
                  title: <Typography.Text>{t('machines:machines')}</Typography.Text>,
                  onClick: () => navigate('/machines'),
                },
                {
                  title: machine?.machineName || machineName,
                },
                {
                  title: t('resources:repositories.repositories'),
                },
              ]}
              data-testid="machine-repositories-breadcrumb"
            />

            <Flex align="center" justify="space-between" wrap>
              <Flex vertical style={{ flex: '1 1 auto', minWidth: 0 }}>
                <Flex align="center" gap={8} wrap>
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
                <Flex align="center" wrap>
                  <Tag color="success">
                    {t('machines:team')}: {machine?.teamName}
                  </Tag>
                  <Tag color="processing">
                    {t('machines:bridge')}: {machine?.bridgeName}
                  </Tag>
                  {machine?.regionName && (
                    <Tag color="default">
                      {t('machines:region')}: {machine.regionName}
                    </Tag>
                  )}
                </Flex>
              </Flex>

              <Flex align="center" wrap>
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
              </Flex>
            </Flex>
          </Flex>

          <Flex style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
            <Flex
              vertical
              style={{
                width: selectedResource ? `calc(100% - ${actualPanelWidth}px)` : '100%',
                height: '100%',
                overflow: 'auto',
                minWidth: 240,
              }}
            >
              {machine && (
                <MachineRepositoryTable
                  machine={machine}
                  key={`${machine.machineName}-${refreshKey}`}
                  refreshKey={refreshKey}
                  onActionComplete={handleRefresh}
                  onRepositoryClick={handleRepositoryClick}
                  onContainerClick={handleContainerClick}
                  onQueueItemCreated={(taskId, machineName) => {
                    queueTrace.open(taskId, machineName ?? undefined);
                  }}
                />
              )}
            </Flex>

            {shouldRenderBackdrop && (
              <Flex
                style={{
                  position: 'fixed',
                  top: 0,
                  left: 0,
                  right: actualPanelWidth,
                  bottom: 0,
                  backgroundColor: '#404040',
                  display: backdropVisible ? 'block' : 'none',
                  zIndex: 1000,
                  pointerEvents: backdropVisible ? 'auto' : 'none',
                }}
                onClick={handlePanelClose}
                data-testid="machine-repositories-backdrop"
              />
            )}

            {selectedResource && (
              <UnifiedDetailPanel
                type={'repositoryName' in selectedResource ? 'repository' : 'container'}
                data={selectedResource}
                visible={true}
                onClose={handlePanelClose}
                splitWidth={splitWidth}
                onSplitWidthChange={setSplitWidth}
                isCollapsed={isPanelCollapsed}
                onToggleCollapse={handleTogglePanelCollapse}
                collapsedWidth={DETAIL_PANEL.COLLAPSED_WIDTH}
              />
            )}
          </Flex>
        </Flex>
      </Card>

      <QueueItemTraceModal
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close();
          handleRefresh();
        }}
      />

      {fileBrowserModal.state.data && (
        <RemoteFileBrowserModal
          open={fileBrowserModal.isOpen}
          onCancel={fileBrowserModal.close}
          machineName={fileBrowserModal.state.data.machineName}
          teamName={fileBrowserModal.state.data.teamName}
          bridgeName={fileBrowserModal.state.data.bridgeName}
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
        mode={unifiedModal.state.data?.mode || 'create'}
        existingData={unifiedModal.state.data?.data}
        teamFilter={machine?.teamName ? [machine.teamName] : undefined}
        creationContext={unifiedModal.state.data?.creationContext}
        onSubmit={handleUnifiedModalSubmit}
      />

      <ConnectivityTestModal
        data-testid="machine-repositories-connectivity-test-modal"
        open={connectivityTest.isOpen}
        onTestsComplete={handleRefresh}
        onClose={() => {
          connectivityTest.close();
          handleRefresh();
        }}
        machines={machine ? [machine] : []}
        teamFilter={machine?.teamName ? [machine.teamName] : undefined}
      />
    </Flex>
  );
};

export default MachineReposPage;
