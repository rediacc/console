import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Drawer,
  Flex,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepositories } from '@/api/queries/repositories';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ContainerDetailPanel } from '@/components/resources/internal/ContainerDetailPanel';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import ConnectivityTestModal from '@/pages/machines/components/ConnectivityTestModal';
import { ContainerData } from '@/pages/machines/components/SplitResourceView';
import { RepositoryContainerTable } from '@/pages/resources/components/RepositoryContainerTable';
import { Machine, PluginContainer } from '@/types';
import { DoubleLeftOutlined, InboxOutlined, ReloadOutlined } from '@/utils/optimizedIcons';

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
  const [hasInitiallyLoaded, setHasInitiallyLoaded] = useState(false);
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
            ) ?? null
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

  const handleRefresh = useCallback(async () => {
    setRefreshKey((prev) => prev + 1);
    // Refetch machines to get updated vaultStatus with container data
    await refetchMachines();
  }, [refetchMachines]);

  // Auto-refresh data on mount (query existing data, no queue items)
  useEffect(() => {
    if (actualMachine && !hasInitiallyLoaded) {
      setHasInitiallyLoaded(true);
      // Just refresh existing data from database
      handleRefresh();
    }
  }, [actualMachine, hasInitiallyLoaded, handleRefresh]);

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
  };

  const handlePanelClose = () => {
    setSelectedContainer(null);
  };

  // Loading state
  if (machinesLoading || repositoriesLoading) {
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
  if (!actualMachine) {
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

  // Error state - repository not found
  if (!actualRepository) {
    return (
      <Flex vertical>
        <Card>
          <Flex vertical>
            <Alert
              message={t('machines:repoNotFound')}
              description={
                <Flex vertical style={{ maxWidth: 520 }}>
                  <p>
                    {t('machines:repoNotFoundDescription', {
                      repositoryName: repositoryName,
                      machineName,
                    })}
                  </p>
                  <Button type="primary" onClick={handleBackToRepos}>
                    {t('machines:backToRepos')}
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

  const actualRepositoryName = actualRepository.name;

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
                  title: <Typography.Text>{actualMachine.machineName}</Typography.Text>,
                  onClick: () =>
                    navigate(`/machines/${machineName}/repositories`, {
                      state: { machine: actualMachine },
                    }),
                },
                {
                  title: (
                    <Typography.Text>{t('resources:repositories.repositories')}</Typography.Text>
                  ),
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

            <Flex align="center" justify="space-between" wrap>
              <Flex vertical style={{ flex: '1 1 auto', minWidth: 0 }}>
                <Flex align="center" gap={8} wrap>
                  <Tooltip title={t('machines:backToRepos')}>
                    <Button
                      type="text"
                      icon={<DoubleLeftOutlined />}
                      onClick={handleBackToRepos}
                      aria-label={t('machines:backToRepos')}
                      data-testid="repository-containers-back-button"
                    />
                  </Tooltip>
                  <Typography.Title level={4}>
                    <Space>
                      <InboxOutlined />
                      <Typography.Text>
                        {t('machines:repoContainers')}: {actualRepositoryName}
                      </Typography.Text>
                    </Space>
                  </Typography.Title>
                </Flex>
                <Flex align="center" wrap>
                  <Tag color="default">
                    {t('machines:machine')}: {actualMachine.machineName}
                  </Tag>
                  <Tag color="success">
                    {t('machines:team')}: {actualMachine.teamName}
                  </Tag>
                  <Tag color="processing">
                    {t('machines:bridge')}: {actualMachine.bridgeName}
                  </Tag>
                  {actualMachine.regionName && (
                    <Tag color="processing">
                      {t('machines:region')}: {actualMachine.regionName}
                    </Tag>
                  )}
                </Flex>
              </Flex>

              <Flex align="center" wrap>
                <Tooltip title={t('machines:checkAndRefresh')}>
                  <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    onClick={() => connectivityTest.open()}
                    disabled={!actualMachine}
                    data-testid="repository-containers-test-and-refresh-button"
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
                width: '100%',
                height: '100%',
                overflow: 'auto',
                minWidth: 240,
              }}
            >
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
            </Flex>

            <Drawer
              open={!!selectedContainer}
              onClose={handlePanelClose}
              width={panelWidth}
              placement="right"
              mask={true}
              data-testid="repository-containers-drawer"
            >
              {selectedContainer && (
                <ContainerDetailPanel
                  container={selectedContainer as unknown as ContainerData}
                  visible={true}
                  onClose={handlePanelClose}
                  splitView
                />
              )}
            </Drawer>
          </Flex>
        </Flex>
      </Card>

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
        onTestsComplete={handleRefresh}
        onClose={() => {
          connectivityTest.close();
          handleRefresh();
        }}
        machines={actualMachine ? [actualMachine] : []}
        teamFilter={actualMachine?.teamName ? [actualMachine.teamName] : undefined}
      />
    </Flex>
  );
};

export default RepoContainersPage;
