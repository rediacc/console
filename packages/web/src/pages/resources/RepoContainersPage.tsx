import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Button as AntButton, Space, Tag, Alert, Tooltip } from 'antd';
import { DoubleLeftOutlined, ReloadOutlined, InboxOutlined } from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { DETAIL_PANEL } from '@/constants/layout';
import { useMachines } from '@/api/queries/machines';
import { useRepos } from '@/api/queries/repos';
import { RepoContainerTable } from '@/pages/resources/components/RepoContainerTable';
import { Machine, PluginContainer } from '@/types';
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { useQueueTraceModal } from '@/hooks/useDialogState';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccButton as Button, RediaccText as Text } from '@/components/ui';
import { ActionGroup } from '@/components/common/styled';
import {
  PageWrapper,
  FullHeightCard,
  BreadcrumbWrapper,
  HeaderSection,
  HeaderRow,
  TitleColumn,
  TitleRow,
  ActionsRow,
  SplitLayout,
  ListPanel,
  DetailBackdrop,
  CenteredState,
  ErrorWrapper,
  HeaderTitleText,
} from './styles';

// Repo interface from vaultStatus (runtime data)
interface Repo {
  name: string;
  repoTag?: string;
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
  repo?: Repo;
} | null;

const isRepoData = (value: unknown): value is Repo => {
  return typeof value === 'object' && value !== null && 'name' in value;
};

const RepoContainersPage: React.FC = () => {
  const { machineName, repoName } = useParams<{ machineName: string; repoName: string }>();
  const navigate = useNavigate();
  const location = useLocation() as { state?: RepoContainersLocationState };
  const { t } = useTranslation(['resources', 'machines', 'common']);

  // Extract machine and repo from navigation state
  const machine = location.state?.machine;
  const repo = location.state?.repo;

  const [selectedContainer, setSelectedContainer] = useState<PluginContainer | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const queueTrace = useQueueTraceModal();

  // Fetch machine data if not provided via state
  const { data: machines, isLoading: machinesLoading, refetch: refetchMachines } = useMachines();
  const actualMachine = machine || machines?.find((m) => m.machineName === machineName);

  // Fetch repos to get the repoGuid from friendly name
  const { data: teamRepos = [], isLoading: reposLoading } = useRepos(
    actualMachine?.teamName ? [actualMachine.teamName] : undefined
  );

  // Reconstruct repo from vaultStatus if not provided via state
  const actualRepo = useMemo(() => {
    if (repo) return repo;

    if (!actualMachine?.vaultStatus || !repoName) return null;

    // First, find the repoGuid from the API data using the friendly name
    const repoCredential = teamRepos.find((r) => r.repoName === repoName);
    const repoGuidToFind = repoCredential?.repoGuid;

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
              (candidate: unknown): candidate is Repo =>
                isRepoData(candidate) &&
                (repoGuidToFind ? candidate.name === repoGuidToFind : candidate.name === repoName)
            ) || null
          );
        }
      }
    } catch (err) {
      console.error('Failed to parse repo from vaultStatus:', err);
    }

    return null;
  }, [repo, actualMachine?.vaultStatus, repoName, teamRepos]);

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
    navigate(`/machines/${machineName}/repos`, {
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
  if (machinesLoading || reposLoading) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <CenteredState>
            <LoadingWrapper loading centered minHeight={160}>
              <div />
            </LoadingWrapper>
            <Text color="secondary">{t('common:general.loading')}</Text>
          </CenteredState>
        </FullHeightCard>
      </PageWrapper>
    );
  }

  // Error state - machine not found
  if (!actualMachine) {
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

  // Error state - repo not found
  if (!actualRepo) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <Alert
            message={t('machines:repoNotFound')}
            description={
              <ErrorWrapper>
                <p>{t('machines:repoNotFoundDescription', { repoName: repoName, machineName })}</p>
                <AntButton type="primary" onClick={handleBackToRepos}>
                  {t('machines:backToRepos')}
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

  const actualRepoName = actualRepo.name;

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
                title: <span>{actualMachine.machineName}</span>,
                onClick: () =>
                  navigate(`/machines/${machineName}/repos`, { state: { machine: actualMachine } }),
              },
              {
                title: <span>{t('resources:repos.repos')}</span>,
                onClick: () =>
                  navigate(`/machines/${machineName}/repos`, { state: { machine: actualMachine } }),
              },
              {
                title: actualRepoName,
              },
              {
                title: t('resources:containers.containers'),
              },
            ]}
            data-testid="repo-containers-breadcrumb"
          />

          <HeaderRow>
            <TitleColumn>
              <TitleRow>
                <Tooltip title={t('machines:backToRepos')}>
                  <Button
                    iconOnly
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToRepos}
                    aria-label={t('machines:backToRepos')}
                    data-testid="repo-containers-back-button"
                  />
                </Tooltip>
                <HeaderTitleText level={4}>
                  <Space>
                    <InboxOutlined />
                    <span>
                      {t('machines:repoContainers')}: {actualRepoName}
                    </span>
                  </Space>
                </HeaderTitleText>
              </TitleRow>
              <ActionGroup>
                <Tag color="default">
                  {t('machines:machine')}: {actualMachine.machineName}
                </Tag>
                <Tag color="success">
                  {t('machines:team')}: {actualMachine.teamName}
                </Tag>
                <Tag color="blue">
                  {t('machines:bridge')}: {actualMachine.bridgeName}
                </Tag>
                {actualMachine.regionName && (
                  <Tag color="cyan">
                    {t('machines:region')}: {actualMachine.regionName}
                  </Tag>
                )}
              </ActionGroup>
            </TitleColumn>

            <ActionsRow>
              <Tooltip title={t('common:actions.refresh')}>
                <Button
                  iconOnly
                  icon={<ReloadOutlined />}
                  onClick={handleRefresh}
                  data-testid="repo-containers-refresh-button"
                />
              </Tooltip>
            </ActionsRow>
          </HeaderRow>
        </HeaderSection>

        <SplitLayout>
          <ListPanel $showDetail={Boolean(selectedResource)} $detailWidth={actualPanelWidth}>
            <RepoContainerTable
              machine={actualMachine}
              repo={actualRepo}
              key={`${actualMachine.machineName}-${actualRepoName}-${refreshKey}`}
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
              data-testid="repo-containers-backdrop"
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
      </FullHeightCard>

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
    </PageWrapper>
  );
};

export default RepoContainersPage;
