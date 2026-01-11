import React, { useEffect, useMemo, useState } from 'react';
import {
  CloseOutlined,
  CloudDownloadOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Alert, Button, Empty, Flex, Input, Select, Space, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useGetTeamMachines } from '@/api/api-hooks.generated';
import { useGetTeamRepositories } from '@/api/api-hooks.generated';
import { useGetTeamStorages } from '@/api/api-hooks.generated';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import { SizedModal } from '@/components/common/SizedModal';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { waitForQueueItemCompletion } from '@/services/helloService';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { BrowserBreadcrumb } from './BrowserBreadcrumb';
import { BrowserFileTable } from './BrowserFileTable';
import { FileListParserFactory } from './parsers';
import { buildListQueueVault, buildPullQueueVault } from './vaultBuilder';
import type {
  AdditionalVaultData,
  RemoteFile,
  RemoteFileBrowserModalProps,
  SourceOption,
} from './types';

interface ExecuteListParams {
  selectedSource: string;
  currentPath: string;
  teamName: string;
  machineName: string;
  bridgeName: string;
  additionalVaultData: AdditionalVaultData;
  mapGuidToRepository: (guid: string) => {
    displayName: string;
    repositoryName?: string;
    repositoryTag?: string;
    isUnmapped: boolean;
  };
}

const parseListResponse = (
  responseData: { result?: string } | undefined,
  currentPath: string,
  mapGuidToRepository: ExecuteListParams['mapGuidToRepository']
): RemoteFile[] => {
  const commandResult = responseData?.result;

  if (!commandResult && !responseData) {
    console.warn('Remote file browser received no response data');
    return [];
  }

  let dataToProcess = '';

  if (typeof commandResult === 'string') {
    try {
      const parsed = JSON.parse(commandResult);
      dataToProcess = parsed.command_output ?? '';
    } catch {
      dataToProcess = commandResult;
    }
  }

  if (typeof dataToProcess === 'string' && dataToProcess) {
    const parser = new FileListParserFactory(currentPath, mapGuidToRepository);
    return parser.parse(dataToProcess);
  }

  return [];
};

export const RemoteFileBrowserModal: React.FC<RemoteFileBrowserModalProps> = ({
  open,
  onCancel,
  machineName,
  teamName,
  bridgeName,
  onPullSelected,
  onClose: _onClose,
  onQueueItemCreated,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines']);
  const { data: _dropdownData } = useDropdownData();
  const { data: storageData, isLoading: isLoadingStorage } = useGetTeamStorages(teamName);
  const { data: machinesData, isLoading: isLoadingMachines } = useGetTeamMachines(teamName);
  const { data: teamsData } = useGetOrganizationTeams();
  const { data: teamRepositories = [] } = useGetTeamRepositories(teamName);
  const { buildQueueVault } = useQueueVaultBuilder();
  const { mutateAsync: createQueueItem } = useManagedQueueItem();

  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState<RemoteFile[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [searchText, setSearchText] = useState('');

  const storageSources = useMemo((): SourceOption[] => {
    const sources: SourceOption[] = [];

    machinesData?.forEach((machine) => {
      sources.push({
        value: machine.machineName ?? '',
        label: `${machine.machineName ?? ''} (Machine)`,
        type: 'machine',
      });
    });

    storageData?.forEach((storage) => {
      sources.push({
        value: storage.storageName ?? '',
        label: `${storage.storageName ?? ''} (Cloud Storage)`,
        type: 'storage',
      });
    });

    return sources;
  }, [machinesData, storageData]);

  useEffect(() => {
    if (!selectedSource && machineName) {
      setSelectedSource(machineName);
    }
  }, [machineName, selectedSource]);

  const mapGuidToRepository = (guid: string) => {
    const repositoryInfo = teamRepositories.find((r) => r.repositoryGuid === guid);
    if (!repositoryInfo) {
      return {
        displayName: guid,
        isUnmapped: true,
      };
    }
    const tag = repositoryInfo.repositoryTag ?? 'latest';
    return {
      displayName: `${repositoryInfo.repositoryName ?? ''}:${tag}`,
      repositoryName: repositoryInfo.repositoryName ?? undefined,
      repositoryTag: tag,
      isUnmapped: false,
    };
  };

  const executeList = async (params: ExecuteListParams): Promise<RemoteFile[]> => {
    const {
      selectedSource,
      currentPath,
      teamName,
      machineName,
      bridgeName,
      additionalVaultData,
      mapGuidToRepository,
    } = params;

    const vault = await buildQueueVault({
      teamName,
      machineName,
      bridgeName,
      functionName: 'repository_list',
      params: {
        from: selectedSource,
        path: currentPath || '',
        format: 'json',
      },
      priority: 4,
      addedVia: 'file-browser',
      ...additionalVaultData,
    });

    const result = await createQueueItem({
      teamName,
      machineName,
      bridgeName,
      queueVault: vault,
      priority: 4,
    });

    const taskId = result.taskId ?? result.queueId;
    if (!taskId) {
      throw new Error('Failed to create queue item - no taskId returned');
    }

    if (result.isQueued) {
      throw new Error('QUEUED');
    }

    const completionResult = await waitForQueueItemCompletion(taskId, 30000);
    if (!completionResult.success) {
      throw new Error(completionResult.message || 'List operation failed');
    }

    return parseListResponse(completionResult.responseData, currentPath, mapGuidToRepository);
  };

  const loadFiles = async () => {
    if (!selectedSource) {
      return;
    }
    setLoading(true);
    try {
      const additionalVaultData = buildListQueueVault({
        selectedSource,
        machineName,
        storageSources,
        machinesData: machinesData?.filter(
          (m): m is typeof m & { machineName: string } => !!m.machineName
        ),
        storageData: storageData?.filter(
          (s): s is typeof s & { storageName: string } => !!s.storageName
        ),
        teamsData: teamsData?.filter((t): t is typeof t & { teamName: string } => !!t.teamName),
        teamName,
      });

      const fileList = await executeList({
        selectedSource,
        currentPath,
        teamName,
        machineName,
        bridgeName,
        additionalVaultData,
        mapGuidToRepository,
      });

      setFiles(fileList);
    } catch (error: unknown) {
      if (error instanceof Error && error.message === 'QUEUED') {
        showMessage('info', 'File listing has been queued. Please try again in a moment.');
        setFiles([]);
      } else {
        console.error('Error loading files:', error);
        const errorMessage =
          error instanceof Error ? error.message : t('resources:remoteFiles.loadError');
        showMessage('error', errorMessage);
        setFiles([]);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleNavigate = (path: string) => {
    setCurrentPath(path);
    setSelectedFile('');
    setFiles([]);
  };

  const handlePull = async () => {
    if (!selectedFile) {
      showMessage('warning', t('resources:remoteFiles.selectFile'));
      return;
    }

    const selectedFileObject = files.find((f) => f.name === selectedFile);
    if (!selectedFileObject) return;

    if (onPullSelected) {
      onPullSelected([selectedFileObject], selectedSource);
      onCancel();
      return;
    }

    await executePullOperation(selectedFileObject);
  };

  const executePullOperation = async (file: RemoteFile) => {
    const additionalVaultData = buildPullQueueVault({
      selectedSource,
      machineName,
      teamName,
      storageSources,
      machinesData: machinesData?.filter(
        (m): m is typeof m & { machineName: string } => !!m.machineName
      ),
      storageData: storageData?.filter(
        (s): s is typeof s & { storageName: string } => !!s.storageName
      ),
      teamsData: teamsData?.filter((t): t is typeof t & { teamName: string } => !!t.teamName),
    });

    const sourceDetails = storageSources.find((s) => s.value === selectedSource);
    const isStorageSource = sourceDetails?.type === 'storage';

    const vault = await buildQueueVault({
      teamName,
      machineName,
      bridgeName,
      functionName: 'backup_pull',
      params: {
        from: selectedSource,
        repository: file.originalGuid ?? file.name,
        grand: file.originalGuid ?? file.name,
        path: currentPath || '',
        sourceType: isStorageSource ? 'storage' : 'machine',
      },
      priority: 3,
      addedVia: 'file-browser',
      ...additionalVaultData,
    });

    const response = await createQueueItem({
      teamName,
      machineName,
      bridgeName,
      queueVault: vault,
      priority: 3,
    });

    if (response.taskId && onQueueItemCreated) {
      onQueueItemCreated(response.taskId, machineName);
    } else if (response.isQueued) {
      showMessage('info', t('resources:messages.pullOperationQueued'));
    }

    showMessage('success', t('resources:remoteFiles.pullStarted'));
    onCancel();
  };

  return (
    <SizedModal
      data-testid="file-browser-modal"
      title={
        <Space>
          <CloudDownloadOutlined />
          {t('resources:remoteFiles.title')}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      size={ModalSize.Large}
      footer={[
        <Tooltip key="cancel" title={t('common:actions.cancel')}>
          <Button
            icon={<CloseOutlined />}
            onClick={onCancel}
            data-testid="file-browser-cancel-button"
            aria-label={t('common:actions.cancel')}
          />
        </Tooltip>,
        <Tooltip key="refresh" title={t('common:actions.refresh')}>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadFiles}
            loading={loading}
            data-testid="file-browser-refresh-button"
            aria-label={t('common:actions.refresh')}
          />
        </Tooltip>,
        <Tooltip key="pull" title={t('resources:remoteFiles.pull')}>
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            onClick={handlePull}
            disabled={!selectedFile}
            data-testid="file-browser-pull-button"
            aria-label={t('resources:remoteFiles.pull')}
          />
        </Tooltip>,
      ]}
    >
      <Flex vertical className="w-full">
        <Flex vertical data-testid="file-browser-source-container">
          <Typography.Text data-testid="file-browser-source-label">
            {t('resources:remoteFiles.sourceLabel')}
          </Typography.Text>
          <Flex justify="space-between" className="w-full">
            <Space>
              <Flex className="min-w-0 flex-1 max-w-select">
                <Select
                  placeholder={t('resources:remoteFiles.selectSource')}
                  value={selectedSource}
                  onChange={(value) => {
                    setSelectedSource(value);
                    setCurrentPath('');
                    setSelectedFile('');
                    setFiles([]);
                  }}
                  loading={isLoadingStorage || isLoadingMachines}
                  notFoundContent={(() => {
                    if (isLoadingStorage || isLoadingMachines) {
                      return (
                        <Flex>
                          <InlineLoadingIndicator
                            width="100%"
                            height={18}
                            data-testid="file-browser-source-loading"
                          />
                        </Flex>
                      );
                    } else if (storageSources.length === 0) {
                      return (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={t('resources:remoteFiles.noSources')}
                        />
                      );
                    }
                    return null;
                  })()}
                  options={storageSources}
                  data-testid="file-browser-source-select"
                />
              </Flex>
              <Tooltip title={t('resources:remoteFiles.loadFiles')}>
                <Button
                  icon={<FolderOpenOutlined />}
                  onClick={loadFiles}
                  loading={loading}
                  disabled={!selectedSource}
                  data-testid="file-browser-load-files-button"
                  aria-label={t('resources:remoteFiles.loadFiles')}
                />
              </Tooltip>
            </Space>
            <Flex className="min-w-0 search-input-constrained">
              <Input
                placeholder={t('common:actions.search')}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                data-testid="file-browser-search-input"
              />
            </Flex>
          </Flex>
        </Flex>

        <BrowserBreadcrumb currentPath={currentPath} onNavigate={handleNavigate} />

        <BrowserFileTable
          files={files}
          loading={loading}
          searchText={searchText}
          selectedFile={selectedFile}
          currentPath={currentPath}
          onNavigate={handleNavigate}
          onSelectFile={setSelectedFile}
        />

        <Alert
          type="info"
          message={t('resources:remoteFiles.info')}
          data-testid="file-browser-info-alert"
        />
      </Flex>
    </SizedModal>
  );
};
