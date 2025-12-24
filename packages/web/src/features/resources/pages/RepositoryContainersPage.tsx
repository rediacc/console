import React, { useCallback, useMemo } from 'react';
import { Alert, Button, Card, Drawer, Flex, Space, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepositories } from '@/api/queries/repositories';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';
import { ContainerDetailPanel } from '@/components/resources/internal/ContainerDetailPanel';
import ConnectivityTestModal from '@/features/machines/components/ConnectivityTestModal';
import { RepositoryContainerTable } from '@/features/resources/components/RepositoryContainerTable';
import { ResourcePageLayout } from '@/features/resources/shared/ResourcePageLayout';
import { ContainerData, RepositoryContainerData } from '@/features/resources/shared/types';
import { useResourcePageState } from '@/features/resources/shared/useResourcePageState';
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { Machine, PluginContainer } from '@/types';
import { DoubleLeftOutlined, InboxOutlined, ReloadOutlined } from '@/utils/optimizedIcons';

type RepoContainersLocationState = {
  machine?: Machine;
  repository?: RepositoryContainerData;
} | null;

const isRepositoryData = (value: unknown): value is RepositoryContainerData => {
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
            result.repositories.find((candidate: unknown): candidate is RepositoryContainerData => {
              if (!isRepositoryData(candidate)) {
                return false;
              }
              return repoGuidToFind
                ? candidate.name === repoGuidToFind
                : candidate.name === repositoryName;
            }) ?? null
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

  const refreshData = useCallback(async () => {
    await refetchMachines();
  }, [refetchMachines]);

  const {
    selectedResource: selectedContainer,
    setSelectedResource: setSelectedContainer,
    refreshKey,
    handleRefresh,
    handlePanelClose,
  } = useResourcePageState<PluginContainer>(refreshData, !!actualMachine);

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

  // Loading state
  if (machinesLoading || repositoriesLoading) {
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
  if (!actualMachine) {
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
              message={t('machines:repositoryNotFound')}
              description={
                <Flex vertical>
                  <p>
                    {t('machines:repositoryNotFoundDescription', {
                      repositoryName: repositoryName,
                      machineName,
                    })}
                  </p>
                  <Button type="primary" onClick={handleBackToRepos}>
                    {t('machines:backToRepositories')}
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

  const breadcrumbItems = [
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
      title: <Typography.Text>{t('resources:repositories.repositories')}</Typography.Text>,
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
  ];

  const header = (
    <Flex align="center" gap={8} wrap>
      <Tooltip title={t('machines:backToRepositories')}>
        <Button
          type="text"
          icon={<DoubleLeftOutlined />}
          onClick={handleBackToRepos}
          aria-label={t('machines:backToRepositories')}
          data-testid="repository-containers-back-button"
        />
      </Tooltip>
      <Typography.Title level={4}>
        <Space>
          <InboxOutlined />
          <Typography.Text>
            {t('machines:repositoryContainers')}: {actualRepositoryName}
          </Typography.Text>
        </Space>
      </Typography.Title>
    </Flex>
  );

  const tags = (
    <Flex align="center" wrap>
      <Tag>
        {t('machines:machine')}: {actualMachine.machineName}
      </Tag>
      <Tag>
        {t('machines:team')}: {actualMachine.teamName}
      </Tag>
      <Tag>
        {t('machines:bridge')}: {actualMachine.bridgeName}
      </Tag>
      {actualMachine.regionName && (
        <Tag>
          {t('machines:region')}: {actualMachine.regionName}
        </Tag>
      )}
    </Flex>
  );

  const actions = (
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
  );

  const content = (
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
  );

  const drawer = (
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
  );

  return (
    <>
      <ResourcePageLayout
        breadcrumbItems={breadcrumbItems}
        breadcrumbTestId="repository-containers-breadcrumb"
        header={header}
        tags={tags}
        actions={actions}
        content={content}
        drawer={drawer}
      />

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
    </>
  );
};

export default RepoContainersPage;
