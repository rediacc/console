import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepositories } from '@/api/queries/repositories';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ActionGroup, CenteredState } from '@/components/common/styled';
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel';
import { RediaccTag, RediaccTooltip } from '@/components/ui';
import { RediaccButton, RediaccText } from '@/components/ui';
import { DETAIL_PANEL } from '@/constants/layout';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import ConnectivityTestModal from '@/pages/machines/components/ConnectivityTestModal';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { RepositoryContainerTable } from '@/pages/resources/components/RepositoryContainerTable';
import { Machine, PluginContainer } from '@/types';
import { DoubleLeftOutlined, InboxOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import {
  ActionsRow,
  BreadcrumbWrapper,
  DetailBackdrop,
  ErrorWrapper,
  FlexColumnCard,
  HeaderRow,
  HeaderSection,
  HeaderTitleText,
  ListPanel,
  PageWrapper,
  SplitLayout,
  TitleColumn,
  TitleRow,
} from './styles';

// Repository interface from vaultStatus (runtime data)
interface Repository {
  name: string;
  repositoryTag?: string;
  size: number;
  size_human: string;
  modified: number;
  modified_human: string;
  mounted: boolean;
  mount_path: string;
  image_path: string;
  accessible: boolean;
  has_rediaccfile: boolean;
  docker_available: boolean;
  docker_running: boolean;
  container_count: number;
  plugin_count: number;
  has_services: boolean;
  service_count: number;
  isUnmapped?: boolean;
  originalGuid?: string;
}

type RepoContainersLocationState = {
  machine?: Machine;
  repository?: Repository;
} | null;

const isRepositoryData = (value: unknown): value is Repository => {
  return typeof value === 'object' && value !== null && 'name' in value;
};

const RepoContainersPage: React.FC = () => {
  const { machineName, repositoryName } = useParams<{
    machineName: string;
    repositoryName: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation() as { state?: RepoContainersLocationState };
  const { t } = useTranslation(['resources', 'machines', 'common']);

  // Extract machine and repository from navigation state
  const machine = location.state?.machine;
  const repository = location.state?.repository;

  const [selectedContainer, setSelectedContainer] = useState<PluginContainer | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const queueTrace = useQueueTraceModal();
  const connectivityTest = useDialogState();

  // Fetch machine data if not provided via state
  const { data: machines, isLoading: machinesLoading, refetch: refetchMachines } = useMachines();
  const actualMachine = machine || machines?.find((m) => m.machineName === machineName);

  // Fetch repositories to get the repositoryGuid from friendly name
  const { data: teamRepositories = [], isLoading: repositoriesLoading } = useRepositories(
    actualMachine?.teamName ? [actualMachine.teamName] : undefined
  );

  // Reconstruct repository from vaultStatus if not provided via state
  const actualRepository = useMemo(() => {
    if (repository) return repository;

    if (!actualMachine?.vaultStatus || !repositoryName) return null;

    // First, find the repositoryGuid from the API data using the friendly name
    const repoCredential = teamRepositories.find((r) => r.repositoryName === repositoryName);
    const repoGuidToFind = repoCredential?.repositoryGuid;

    try {
      const vaultStatusData = JSON.parse(actualMachine.vaultStatus);
      if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
        let cleanedResult = vaultStatusData.result.trim();
        const newlineIndex = cleanedResult.indexOf('\njq:');
        if (newlineIndex > 0) {
          cleanedResult = cleanedResult.substring(0, newlineIndex);
        }
        const result = JSON.parse(cleanedResult);

        if (Array.isArray(result?.repositories)) {
          // Search by GUID if we have it, otherwise try by name as fallback
          return (
            result.repositories.find(
              (candidate: unknown): candidate is Repository =>
                isRepositoryData(candidate) &&
                (repoGuidToFind
                  ? candidate.name === repoGuidToFind
                  : candidate.name === repositoryName)
            ) || null
          );
        }
      }
    } catch (err) {
      console.error('Failed to parse repository from vaultStatus:', err);
    }

    return null;
  }, [repository, actualMachine?.vaultStatus, repositoryName, teamRepositories]);

  // Panel width management
  const panelWidth = usePanelWidth();
  const [splitWidth, setSplitWidth] = useState(panelWidth);
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true);

  // Update splitWidth when window resizes
  useEffect(() => {
    setSplitWidth(panelWidth);
  }, [panelWidth]);

  const actualPanelWidth = isPanelCollapsed ? DETAIL_PANEL.COLLAPSED_WIDTH : splitWidth;

  // Determine selected resource for detail panel
  const selectedResource = selectedContainer
    ? { type: 'container' as const, data: selectedContainer }
    : null;

  // Navigation handlers
  const handleBackToRepos = () => {
    navigate(`/machines/${machineName}/repositories`, {
      state: { machine: actualMachine },
    });
  };

  const handleBackToMachines = () => {
    navigate('/machines');
  };

  const handleContainerClick = (
    container: PluginContainer | { id: string; name: string; state: string; [key: string]: unknown }
  ) => {
    setSelectedContainer(container as PluginContainer);
    setIsPanelCollapsed(false);
  };

  const handleRefresh = async () => {
    setRefreshKey((prev) => prev + 1);
    // Refetch machines to get updated vaultStatus with container data
    await refetchMachines();
  };

  // Loading state
  if (machinesLoading || repositoriesLoading) {
    return (
      <PageWrapper>
        <FlexColumnCard fullHeight>
          <CenteredState>
            <LoadingWrapper loading centered minHeight={160}>
              <div />
            </LoadingWrapper>
            <RediaccText color="secondary">{t('common:general.loading')}</RediaccText>
          </CenteredState>
        </FlexColumnCard>
      </PageWrapper>
    );
  }

  // Error state - machine not found
  if (!actualMachine) {
    return (
      <PageWrapper>
        <FlexColumnCard fullHeight>
          <Alert
            message={t('machines:machineNotFound')}
            description={
              <ErrorWrapper>
                <p>{t('machines:machineNotFoundDescription', { machineName })}</p>
                <RediaccButton variant="primary" onClick={handleBackToMachines}>
                  {t('machines:backToMachines')}
                </RediaccButton>
              </ErrorWrapper>
            }
            type="error"
            showIcon
          />
        </FlexColumnCard>
      </PageWrapper>
    );
  }

  // Error state - repository not found
  if (!actualRepository) {
    return (
      <PageWrapper>
        <FlexColumnCard fullHeight>
          <Alert
            message={t('machines:repoNotFound')}
            description={
              <ErrorWrapper>
                <p>
                  {t('machines:repoNotFoundDescription', {
                    repositoryName: repositoryName,
                    machineName,
                  })}
                </p>
                <RediaccButton variant="primary" onClick={handleBackToRepos}>
                  {t('machines:backToRepos')}
                </RediaccButton>
              </ErrorWrapper>
            }
            type="error"
            showIcon
          />
        </FlexColumnCard>
      </PageWrapper>
    );
  }

  const actualRepositoryName = actualRepository.name;

  return (
    <PageWrapper>
      <FlexColumnCard fullHeight>
        <HeaderSection>
          <BreadcrumbWrapper
            items={[
              {
                title: <span>{t('machines:machines')}</span>,
                onClick: () => navigate('/machines'),
              },
              {
                title: <span>{actualMachine.machineName}</span>,
                onClick: () =>
                  navigate(`/machines/${machineName}/repositories`, {
                    state: { machine: actualMachine },
                  }),
              },
              {
                title: <span>{t('resources:repositories.repositories')}</span>,
                onClick: () =>
                  navigate(`/machines/${machineName}/repositories`, {
                    state: { machine: actualMachine },
                  }),
              },
              {
                title: actualRepositoryName,
              },
              {
                title: t('resources:containers.containers'),
              },
            ]}
            data-testid="repository-containers-breadcrumb"
          />

          <HeaderRow>
            <TitleColumn>
              <TitleRow>
                <RediaccTooltip title={t('machines:backToRepos')}>
                  <RediaccButton
                    iconOnly
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToRepos}
                    aria-label={t('machines:backToRepos')}
                    data-testid="repository-containers-back-button"
                  />
                </RediaccTooltip>
                <HeaderTitleText level={4}>
                  <Space>
                    <InboxOutlined />
                    <span>
                      {t('machines:repoContainers')}: {actualRepositoryName}
                    </span>
                  </Space>
                </HeaderTitleText>
              </TitleRow>
              <ActionGroup>
                <RediaccTag variant="neutral">
                  {t('machines:machine')}: {actualMachine.machineName}
                </RediaccTag>
                <RediaccTag variant="success">
                  {t('machines:team')}: {actualMachine.teamName}
                </RediaccTag>
                <RediaccTag variant="info">
                  {t('machines:bridge')}: {actualMachine.bridgeName}
                </RediaccTag>
                {actualMachine.regionName && (
                  <RediaccTag variant="info">
                    {t('machines:region')}: {actualMachine.regionName}
                  </RediaccTag>
                )}
              </ActionGroup>
            </TitleColumn>

            <ActionsRow>
              <RediaccTooltip title={t('machines:checkAndRefresh')}>
                <RediaccButton
                  iconOnly
                  icon={<ReloadOutlined />}
                  onClick={() => connectivityTest.open()}
                  disabled={!actualMachine}
                  data-testid="repository-containers-test-and-refresh-button"
                  aria-label={t('machines:checkAndRefresh')}
                />
              </RediaccTooltip>
            </ActionsRow>
          </HeaderRow>
        </HeaderSection>

        <SplitLayout>
          <ListPanel $showDetail={Boolean(selectedResource)} $detailWidth={actualPanelWidth}>
            <RepositoryContainerTable
              machine={actualMachine}
              repository={actualRepository}
              key={`${actualMachine.machineName}-${actualRepositoryName}-${refreshKey}`}
              refreshKey={refreshKey}
              onContainerClick={handleContainerClick}
              highlightedContainer={selectedContainer}
              onQueueItemCreated={(taskId, machineName) => {
                queueTrace.open(taskId, machineName);
              }}
            />
          </ListPanel>

          {/* Backdrop must come BEFORE panel for correct z-index layering */}
          {selectedResource && !isPanelCollapsed && (
            <DetailBackdrop
              $right={actualPanelWidth}
              $visible={true}
              onClick={() => {
                setSelectedContainer(null);
                setIsPanelCollapsed(true);
              }}
              data-testid="repository-containers-backdrop"
            />
          )}

          {selectedResource && (
            <UnifiedDetailPanel
              type={selectedResource.type}
              data={selectedResource.data}
              visible={true}
              onClose={() => {
                setSelectedContainer(null);
                setIsPanelCollapsed(true);
              }}
              splitWidth={splitWidth}
              onSplitWidthChange={setSplitWidth}
              isCollapsed={isPanelCollapsed}
              onToggleCollapse={() => setIsPanelCollapsed(!isPanelCollapsed)}
              collapsedWidth={DETAIL_PANEL.COLLAPSED_WIDTH}
            />
          )}
        </SplitLayout>
      </FlexColumnCard>

      {queueTrace.state.open && (
        <QueueItemTraceModal
          taskId={queueTrace.state.taskId}
          open={queueTrace.state.open}
          onCancel={() => {
            queueTrace.close();
            handleRefresh();
          }}
        />
      )}

      <ConnectivityTestModal
        data-testid="repository-containers-connectivity-test-modal"
        open={connectivityTest.isOpen}
        onClose={() => {
          connectivityTest.close();
          handleRefresh();
        }}
        machines={actualMachine ? [actualMachine] : []}
        teamFilter={actualMachine?.teamName ? [actualMachine.teamName] : undefined}
      />
    </PageWrapper>
  );
};

export default RepoContainersPage;
