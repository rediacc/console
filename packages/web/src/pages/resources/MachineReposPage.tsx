import React, { useState, useEffect } from 'react';
import { Button as AntButton, Space, Tag, Alert, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepos } from '@/api/queries/repos';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ActionGroup } from '@/components/common/styled';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { MachineRepoTable } from '@/components/resources/MachineRepoTable';
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel';
import { RediaccButton } from '@/components/ui';
import { RediaccText } from '@/components/ui';
import { DETAIL_PANEL } from '@/constants/layout';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { useRepoCreation } from '@/hooks/useRepoCreation';
import { RemoteFileBrowserModal } from '@/pages/resources/components/RemoteFileBrowserModal';
import { Machine, Repo, PluginContainer } from '@/types';
import {
  DoubleLeftOutlined,
  ReloadOutlined,
  DesktopOutlined,
  PlusOutlined,
  CloudDownloadOutlined,
} from '@/utils/optimizedIcons';
import {
  PageWrapper,
  FullHeightCard,
  BreadcrumbWrapper,
  HeaderSection,
  HeaderRow,
  TitleColumn,
  TitleRow,
  ActionsRow,
  HeaderTitleText,
  SplitLayout,
  ListPanel,
  DetailBackdrop,
  CenteredState,
  ErrorWrapper,
} from './styles';

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
  repo: string;
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

type RepoRowData = {
  name: string;
  repoTag?: string;
  originalGuid?: string;
};

const MachineReposPage: React.FC = () => {
  const { machineName } = useParams<{ machineName: string }>();
  const navigate = useNavigate();
  const location = useLocation() as { state?: MachineReposLocationState };
  const { t } = useTranslation(['resources', 'machines', 'common']);

  // State for machine data - can come from route state or API
  const routeState = location.state;
  const [machine, setMachine] = useState<Machine | null>(routeState?.machine || null);

  // Use shared panel width hook (33% of window, min 300px, max 700px)
  const panelWidth = usePanelWidth();

  // State for selected resource (Repo or container) and panel
  const [selectedResource, setSelectedResource] = useState<
    Repo | ContainerData | PluginContainer | null
  >(null);
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true);
  const [splitWidth, setSplitWidth] = useState(panelWidth);
  const [backdropVisible, setBackdropVisible] = useState(false);
  const [shouldRenderBackdrop, setShouldRenderBackdrop] = useState(false);

  // Refresh key for forcing MachineRepoTable updates
  const [refreshKey, setRefreshKey] = useState(0);

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

  // Fetch all machines to find our specific machine if not passed via state
  const {
    data: machines = [],
    isLoading: machinesLoading,
    error: machinesError,
    refetch: refetchMachines,
  } = useMachines(machine?.teamName ? [machine.teamName] : undefined, true);

  // Repo creation hook (handles credentials + queue item)
  const { createRepo } = useRepoCreation(machines);

  // Fetch repos (needed for MachineRepoTable)
  const { data: repos = [], refetch: refetchRepos } = useRepos(
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

  const handleBackToMachines = () => {
    navigate('/machines');
  };

  const handleRefresh = async () => {
    setRefreshKey((prev) => prev + 1);
    // Refetch both repos AND machines to get updated vaultStatus
    await Promise.all([refetchRepos(), refetchMachines()]);
  };

  const handleCreateRepo = () => {
    if (!machine) return;

    // Open the Repo creation modal with prefilled machine
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

  const handleUnifiedModalSubmit = async (data: Parameters<typeof createRepo>[0]) => {
    const result = await createRepo(data);

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

  const handleRepoClick = (repoRow: RepoRowData) => {
    // Map Repo data to Repo type
    const mappedRepo: Repo = {
      repoName: repoRow.name,
      repoGuid: repoRow.originalGuid || repoRow.name,
      teamName: machine!.teamName,
      vaultVersion: 0,
      vaultContent: undefined,
      grandGuid: undefined,
      repoTag: repoRow.repoTag,
    };

    // Find the actual Repo from the API data - must match both name AND tag to distinguish forks
    const actualRepo = repos.find(
      (r) => r.repoName === repoRow.name && r.repoTag === repoRow.repoTag
    );

    setSelectedResource(actualRepo || mappedRepo);
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
      <PageWrapper>
        <FullHeightCard>
          <CenteredState>
            <LoadingWrapper loading centered minHeight={160}>
              <div />
            </LoadingWrapper>
            <RediaccText color="secondary">{t('common:general.loading')}</RediaccText>
          </CenteredState>
        </FullHeightCard>
      </PageWrapper>
    );
  }

  // Error state - machine not found
  if (machinesError || (!machinesLoading && !machine)) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <Alert
            message={t('machines:machineNotFound')}
            description={
              <ErrorWrapper>
                <p>{t('machines:machineNotFoundDescription', { machineName })}</p>
                <AntButton type="primary" onClick={handleBackToMachines}>
                  {t('machines:backToMachines')}
                </AntButton>
              </ErrorWrapper>
            }
            type="error"
            showIcon
          />
        </FullHeightCard>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <FullHeightCard>
        <HeaderSection>
          <BreadcrumbWrapper
            items={[
              {
                title: <span>{t('machines:machines')}</span>,
                onClick: () => navigate('/machines'),
              },
              {
                title: machine?.machineName || machineName,
              },
              {
                title: t('resources:repos.repos'),
              },
            ]}
            data-testid="machine-repos-breadcrumb"
          />

          <HeaderRow>
            <TitleColumn>
              <TitleRow>
                <Tooltip title={t('machines:backToMachines')}>
                  <RediaccButton
                    iconOnly
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToMachines}
                    aria-label={t('machines:backToMachines')}
                    data-testid="machine-repos-back-button"
                  />
                </Tooltip>
                <HeaderTitleText level={4}>
                  <Space>
                    <DesktopOutlined />
                    <span>
                      {t('machines:machine')}: {machine?.machineName}
                    </span>
                  </Space>
                </HeaderTitleText>
              </TitleRow>
              <ActionGroup>
                <Tag color="success">
                  {t('machines:team')}: {machine?.teamName}
                </Tag>
                <Tag color="blue">
                  {t('machines:bridge')}: {machine?.bridgeName}
                </Tag>
                {machine?.regionName && (
                  <Tag color="default">
                    {t('machines:region')}: {machine.regionName}
                  </Tag>
                )}
              </ActionGroup>
            </TitleColumn>

            <ActionsRow>
              <Tooltip title={t('machines:createRepo')}>
                <RediaccButton
                  iconOnly
                  icon={<PlusOutlined />}
                  onClick={handleCreateRepo}
                  data-testid="machine-repos-create-repo-button"
                />
              </Tooltip>
              <Tooltip title={t('functions:functions.pull.name')}>
                <RediaccButton
                  iconOnly
                  icon={<CloudDownloadOutlined />}
                  onClick={handlePull}
                  data-testid="machine-repos-pull-button"
                />
              </Tooltip>
              <Tooltip title={t('common:actions.refresh')}>
                <RediaccButton
                  iconOnly
                  icon={<ReloadOutlined />}
                  onClick={handleRefresh}
                  data-testid="machine-repos-refresh-button"
                />
              </Tooltip>
            </ActionsRow>
          </HeaderRow>
        </HeaderSection>

        <SplitLayout>
          <ListPanel $showDetail={Boolean(selectedResource)} $detailWidth={actualPanelWidth}>
            {machine && (
              <MachineRepoTable
                machine={machine}
                key={`${machine.machineName}-${refreshKey}`}
                refreshKey={refreshKey}
                onActionComplete={handleRefresh}
                onRepoClick={handleRepoClick}
                onContainerClick={handleContainerClick}
                onQueueItemCreated={(taskId, machineName) => {
                  queueTrace.open(taskId, machineName || undefined);
                }}
              />
            )}
          </ListPanel>

          {shouldRenderBackdrop && (
            <DetailBackdrop
              $right={actualPanelWidth}
              $visible={backdropVisible}
              onClick={handlePanelClose}
              data-testid="machine-repos-backdrop"
            />
          )}

          {selectedResource && (
            <UnifiedDetailPanel
              type={'repoName' in selectedResource ? 'repo' : 'container'}
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
        </SplitLayout>
      </FullHeightCard>

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
            queueTrace.open(taskId, fileBrowserModal.state.data?.machineName || undefined);
            fileBrowserModal.close();
          }}
        />
      )}

      <UnifiedResourceModal
        open={unifiedModal.isOpen}
        onCancel={() => unifiedModal.close()}
        resourceType="repo"
        mode={unifiedModal.state.data?.mode || 'create'}
        existingData={unifiedModal.state.data?.data}
        teamFilter={machine?.teamName ? [machine.teamName] : undefined}
        creationContext={unifiedModal.state.data?.creationContext}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onSubmit={handleUnifiedModalSubmit as any}
      />
    </PageWrapper>
  );
};

export default MachineReposPage;
