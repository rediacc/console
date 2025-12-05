import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Modal,
  Table,
  Button,
  Space,
  Input,
  Select,
  Empty,
  Alert,
  Breadcrumb,
  Tooltip,
} from 'antd';
import { ModalSize } from '@/types/modal';
import {
  ContentSpace,
  SourceLabel,
  SourceContainer,
  SourceSelect,
  SearchInput,
  FolderIcon,
  FileIcon,
} from './styles';
import type { ColumnsType } from 'antd/es/table/interface';
import type { TableProps } from 'antd';
import {
  FolderOutlined,
  FileOutlined,
  CloudDownloadOutlined,
  ReloadOutlined,
  HomeOutlined,
  FolderOpenOutlined,
  RightOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { useStorage } from '@/api/queries/storage';
import { useMachines } from '@/api/queries/machines';
import { useTeams } from '@/api/queries/teams';
import { useRepos } from '@/api/queries/repos';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { waitForQueueItemCompletion } from '@/services/helloService';
import { showMessage } from '@/utils/messages';
import { createSorter, createCustomSorter } from '@/core';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import { createTruncatedColumn } from '@/components/common/columns';

interface RemoteFile {
  name: string;
  originalGuid?: string;
  repoName?: string;
  repoTag?: string;
  isUnmapped?: boolean;
  size: number;
  isDirectory: boolean;
  modTime?: string;
  mimeType?: string;
  path?: string;
}

interface RemoteFileBrowserModalProps {
  open: boolean;
  onCancel: () => void;
  machineName: string;
  teamName: string;
  bridgeName: string;
  onPullSelected?: (files: RemoteFile[], destination: string) => void;
  onClose?: () => void;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
}

type AdditionalVaultData = Record<string, unknown>;

interface RcloneEntry {
  name?: string;
  Name?: string;
  size?: number | string;
  Size?: number | string;
  isDirectory?: boolean;
  IsDir?: boolean;
  permissions?: string;
  date?: string;
  time?: string;
  ModTime?: string;
  Path?: string;
  MimeType?: string;
}

const getStringValue = (value: unknown): string | undefined =>
  typeof value === 'string' ? value : undefined;

const getNumberValue = (value: unknown): number => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
};

const getBooleanValue = (value: unknown): boolean => (typeof value === 'boolean' ? value : false);

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
  const { data: storageData, isLoading: isLoadingStorage } = useStorage(teamName);
  const { data: machinesData, isLoading: isLoadingMachines } = useMachines(teamName);
  const { data: teamsData } = useTeams();
  const { data: teamRepos = [] } = useRepos(teamName);
  const { buildQueueVault } = useQueueVaultBuilder();
  const { mutateAsync: createQueueItem } = useManagedQueueItem();

  // State
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState<RemoteFile[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [searchText, setSearchText] = useState('');
  const [_viewMode, _setViewMode] = useState<'table' | 'grid'>('table');

  // Get available storage sources
  const storageSources = useMemo(() => {
    const sources: { value: string; label: string; type: 'machine' | 'storage' }[] = [];

    // Add machines
    if (machinesData && machinesData.length > 0) {
      machinesData.forEach((machine) => {
        sources.push({
          value: machine.machineName,
          label: `${machine.machineName} (Machine)`,
          type: 'machine',
        });
      });
    }

    // Add storage systems
    if (storageData && storageData.length > 0) {
      storageData.forEach((storage) => {
        sources.push({
          value: storage.storageName,
          label: `${storage.storageName} (Cloud Storage)`,
          type: 'storage',
        });
      });
    }

    return sources;
  }, [machinesData, storageData]);

  // Set default source to current machine
  useEffect(() => {
    if (!selectedSource && machineName) {
      setSelectedSource(machineName);
    }
  }, [machineName, selectedSource]);

  // Helper function to map GUID to repo display name
  const mapGuidToRepo = (guid: string) => {
    const repo = teamRepos.find((r) => r.repoGuid === guid);
    if (!repo) {
      return {
        displayName: guid,
        isUnmapped: true,
      };
    }
    const tag = repo.repoTag || 'latest';
    return {
      displayName: `${repo.repoName}:${tag}`,
      repoName: repo.repoName,
      repoTag: tag,
      isUnmapped: false,
    };
  };

  const loadFiles = async () => {
    if (!selectedSource) {
      return;
    }
    setLoading(true);
    try {
      // Find the source details from storage or machines
      const sourceDetails = storageSources.find((s) => s.value === selectedSource);
      const isStorageSource = sourceDetails?.type === 'storage';

      // Get vault data for the source
      const additionalVaultData: AdditionalVaultData = {};

      // For list function, we always need the current machine's vault data
      // because the command runs on the current machine
      const currentMachine = machinesData?.find((m) => m.machineName === machineName);

      if (currentMachine && currentMachine.vaultContent) {
        additionalVaultData.machineVault = currentMachine.vaultContent;
      }

      // Get team vault data (contains SSH keys)
      const currentTeam = teamsData?.find((t) => t.teamName === teamName);
      if (currentTeam && currentTeam.vaultContent) {
        additionalVaultData.teamVault = currentTeam.vaultContent;
      }

      // If listing from a different machine, we need that machine's vault too
      if (!isStorageSource && selectedSource !== machineName) {
        const sourceMachine = machinesData?.find((m) => m.machineName === selectedSource);
        if (sourceMachine && sourceMachine.vaultContent) {
          // Parse the vault to add it to MACHINES section
          try {
            const sourceMachineData = JSON.parse(sourceMachine.vaultContent);
            // We'll need to manually add this to the context
            additionalVaultData.additionalMachineData = {
              [selectedSource]: sourceMachineData,
            };
          } catch (e) {
            console.error('Failed to parse source machine vault:', e);
          }
        }
      }

      // If listing from storage, add storage vault
      if (isStorageSource) {
        const storage = storageData?.find((s) => s.storageName === selectedSource);
        if (storage && storage.vaultContent) {
          // For storage systems, the vault data needs to be added to STORAGE_SYSTEMS
          try {
            const storageVaultData = JSON.parse(storage.vaultContent);
            additionalVaultData.additionalStorageData = {
              [selectedSource]: storageVaultData,
            };
          } catch (e) {
            console.error('Failed to parse storage vault:', e);
          }
        }
      }

      const vault = await buildQueueVault({
        teamName,
        machineName,
        bridgeName,
        functionName: 'list',
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

      const taskId = result.taskId || result.queueId;
      if (!taskId) {
        throw new Error('Failed to create queue item - no taskId returned');
      }

      // Only wait for completion if it's not queued (priority > 1)
      if (!result.isQueued) {
        const completionResult = await waitForQueueItemCompletion(taskId, 30000);
        if (completionResult.success) {
          // Parse the result based on the format
          let fileList: RemoteFile[] = [];
          let dataToProcess = '';

          try {
            // The response data is in completionResult.responseData (parsed vault content)
            // The actual command output should be in the result field
            const commandResult = completionResult.responseData?.result;

            // If there's no response data, the operation completed but returned no data
            if (!commandResult && !completionResult.responseData) {
              console.warn('Remote file browser received no response data');
              setFiles([]);
              return;
            }

            // Parse the command result which contains command_output
            if (typeof commandResult === 'string') {
              try {
                const parsed = JSON.parse(commandResult);
                dataToProcess = parsed.command_output || '';
              } catch {
                dataToProcess = commandResult;
              }
            }

            // If the data looks like it contains output from the command, extract the JSON array
            if (typeof dataToProcess === 'string') {
              // First check if it starts with debug output
              if (dataToProcess.includes('DEBUG:')) {
                // Find the JSON array after all the debug output
                const jsonStartIndex = dataToProcess.lastIndexOf('[');
                const jsonEndIndex = dataToProcess.lastIndexOf(']');
                if (jsonStartIndex !== -1 && jsonEndIndex !== -1 && jsonStartIndex < jsonEndIndex) {
                  const jsonString = dataToProcess.substring(jsonStartIndex, jsonEndIndex + 1);
                  dataToProcess = jsonString;
                }
              } else if (dataToProcess.includes('[')) {
                // Find the JSON array in the output
                const jsonStartIndex = dataToProcess.indexOf('[');
                const jsonEndIndex = dataToProcess.lastIndexOf(']');
                if (jsonStartIndex !== -1 && jsonEndIndex !== -1) {
                  const jsonString = dataToProcess.substring(jsonStartIndex, jsonEndIndex + 1);

                  // Clean up the JSON string - remove escaped quotes and newlines
                  const cleanedJson = jsonString.replace(/\\\\/g, '\\').replace(/\\n/g, '\n');

                  dataToProcess = cleanedJson;
                }
              }
            }

            // First try to parse as JSON
            const parsedData =
              typeof dataToProcess === 'string' ? JSON.parse(dataToProcess) : dataToProcess;

            if (Array.isArray(parsedData)) {
              // Direct array format (SSH ls output or rclone lsjson)
              fileList = parsedData.map((file: RcloneEntry) => {
                const fileName = getStringValue(file.name) ?? getStringValue(file.Name) ?? '';
                const guidPattern =
                  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
                const isGuid = guidPattern.test(fileName);

                let displayName = fileName;
                let repoInfo = null;

                const isDirectoryFlag =
                  getBooleanValue(file.isDirectory) ||
                  getBooleanValue(file.IsDir) ||
                  Boolean(getStringValue(file.permissions)?.startsWith('d'));

                if (isGuid && !isDirectoryFlag) {
                  repoInfo = mapGuidToRepo(fileName);
                  displayName = repoInfo.displayName;
                }

                return {
                  name: displayName,
                  originalGuid: isGuid && !isDirectoryFlag ? fileName : undefined,
                  repoName: repoInfo?.repoName,
                  repoTag: repoInfo?.repoTag,
                  isUnmapped: repoInfo?.isUnmapped || false,
                  size: getNumberValue(file.size ?? file.Size ?? 0),
                  isDirectory: isDirectoryFlag,
                  modTime:
                    file.date && file.time
                      ? `${file.date} ${file.time}`
                      : getStringValue(file.ModTime),
                  path:
                    getStringValue(file.Path) ||
                    (currentPath && fileName ? `${currentPath}/${fileName}` : fileName),
                };
              });
            } else if (parsedData.entries) {
              // rclone lsjson format with entries wrapper
              const entries = Array.isArray((parsedData as { entries?: RcloneEntry[] }).entries)
                ? (parsedData as { entries?: RcloneEntry[] }).entries!
                : [];
              fileList = entries.map((file) => {
                const fileName = getStringValue(file.Name) || '';
                const guidPattern =
                  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
                const isGuid = guidPattern.test(fileName);

                let displayName = fileName;
                let repoInfo = null;

                const isDirectoryFlag = getBooleanValue(file.IsDir);
                if (isGuid && !isDirectoryFlag) {
                  repoInfo = mapGuidToRepo(fileName);
                  displayName = repoInfo.displayName;
                }

                return {
                  name: displayName,
                  originalGuid: isGuid && !isDirectoryFlag ? fileName : undefined,
                  repoName: repoInfo?.repoName,
                  repoTag: repoInfo?.repoTag,
                  isUnmapped: repoInfo?.isUnmapped || false,
                  size: getNumberValue(file.Size),
                  isDirectory: isDirectoryFlag,
                  modTime: getStringValue(file.ModTime),
                  mimeType: getStringValue(file.MimeType),
                  path:
                    getStringValue(file.Path) ||
                    (currentPath && fileName ? `${currentPath}/${fileName}` : fileName),
                };
              });
            }
          } catch (parseError) {
            console.warn('Parsing remote file data as plain text format failed:', parseError);
            console.warn('Data that failed to parse:', dataToProcess);

            // Check if this looks like rclone JSON output that's malformed
            if (
              typeof dataToProcess === 'string' &&
              dataToProcess.includes('"Path":') &&
              dataToProcess.includes('"Name":')
            ) {
              console.warn('Detected malformed rclone JSON output');
              // Try to extract individual JSON objects
              const jsonObjects = dataToProcess.match(/\{[^}]+\}/g);
              if (jsonObjects) {
                fileList = jsonObjects
                  .map((jsonStr) => {
                    try {
                      const file = JSON.parse(jsonStr);
                      return {
                        name: file.Name || '',
                        size: file.Size || 0,
                        isDirectory: file.IsDir || false,
                        modTime: file.ModTime,
                        mimeType: file.MimeType,
                        path:
                          file.Path || (currentPath ? `${currentPath}/${file.Name}` : file.Name),
                      };
                    } catch {
                      return null;
                    }
                  })
                  .filter((f) => f !== null) as RemoteFile[];
              }
            } else {
              // Handle plain text format (rclone ls)
              const textData =
                typeof dataToProcess === 'string' ? dataToProcess : JSON.stringify(dataToProcess);
              const lines = textData
                .trim()
                .split('\n')
                .filter((line) => line.trim());

              // Filter out any status messages
              const fileLines = lines.filter(
                (line) =>
                  !line.startsWith('Listing') &&
                  !line.startsWith('Setting up') &&
                  !line.startsWith('Error:') &&
                  !line.startsWith('DEBUG:') &&
                  line.trim() !== ''
              );

              fileList = fileLines.map((line) => {
                const match = line.match(/^\s*(\d+)\s+(.+)$/);
                if (match) {
                  const [, sizeStr, name] = match;
                  return {
                    name: name.trim(),
                    size: parseInt(sizeStr),
                    isDirectory: name.endsWith('/'),
                    path: currentPath ? `${currentPath}/${name.trim()}` : name.trim(),
                  };
                }
                // If no size match (might be directory listing)
                return {
                  name: line.trim(),
                  size: 0,
                  isDirectory: line.endsWith('/'),
                  path: currentPath ? `${currentPath}/${line.trim()}` : line.trim(),
                };
              });
            }
          }

          setFiles(fileList.filter((f) => f.name)); // Filter out any empty entries
        } else {
          console.error('List operation failed:', completionResult.message);
          showMessage('error', completionResult.message || t('resources:remoteFiles.loadError'));
          setFiles([]);
        }
      } else {
        // Item is queued, we can't get immediate results
        console.warn('List operation queued with ID:', taskId);
        showMessage('info', 'File listing has been queued. Please try again in a moment.');
        setFiles([]);
      }
    } catch (error: unknown) {
      console.error('Error loading files:', error);
      const errorMessage =
        error instanceof Error ? error.message : t('resources:remoteFiles.loadError');
      showMessage('error', errorMessage);
      setFiles([]);
    } finally {
      setLoading(false);
    }
  };

  const handleNavigate = (path: string) => {
    setCurrentPath(path);
    setSelectedFile('');
    setFiles([]); // Clear files when navigating to require manual load
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
    } else {
      // Direct pull implementation
      const file = selectedFileObject;
      // Get vault data - same pattern as list function
      const additionalVaultData: AdditionalVaultData = {};

      // Find the source details from storage or machines
      const sourceDetails = storageSources.find((s) => s.value === selectedSource);
      const isStorageSource = sourceDetails?.type === 'storage';

      // Always need the current machine's vault data
      const currentMachine = machinesData?.find((m) => m.machineName === machineName);
      if (currentMachine && currentMachine.vaultContent) {
        additionalVaultData.machineVault = currentMachine.vaultContent;
      }

      // Get team vault data (contains SSH keys)
      const currentTeam = teamsData?.find((t) => t.teamName === teamName);
      if (currentTeam && currentTeam.vaultContent) {
        additionalVaultData.teamVault = currentTeam.vaultContent;
      }

      // If pulling from storage, add storage vault
      if (isStorageSource) {
        const storage = storageData?.find((s) => s.storageName === selectedSource);
        if (storage && storage.vaultContent) {
          try {
            const storageVaultData = JSON.parse(storage.vaultContent);
            additionalVaultData.additionalStorageData = {
              [selectedSource]: storageVaultData,
            };
          } catch (e) {
            console.error('Failed to parse storage vault:', e);
          }
        }
      }

      // If pulling from another machine, add that machine's vault
      if (!isStorageSource && selectedSource !== machineName) {
        const sourceMachine = machinesData?.find((m) => m.machineName === selectedSource);
        if (sourceMachine && sourceMachine.vaultContent) {
          try {
            const sourceMachineData = JSON.parse(sourceMachine.vaultContent);
            additionalVaultData.additionalMachineData = {
              [selectedSource]: sourceMachineData,
            };
          } catch (e) {
            console.error('Failed to parse source machine vault:', e);
          }
        }
      }

      const vault = await buildQueueVault({
        teamName,
        machineName,
        bridgeName,
        functionName: 'pull',
        params: {
          from: selectedSource,
          repo: file.originalGuid || file.name, // Use GUID if available, otherwise use name
          grand: file.originalGuid || file.name, // Default to repo name (assume pulling a grand, not a fork)
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

      // Check if response has taskId and open trace modal
      if (response?.taskId && onQueueItemCreated) {
        onQueueItemCreated(response.taskId, machineName);
      } else if (response?.isQueued) {
        showMessage('info', t('resources:messages.pullOperationQueued'));
      }

      showMessage('success', t('resources:remoteFiles.pullStarted'));
      onCancel();
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Filter files based on search
  const filteredFiles = useMemo(() => {
    if (!searchText) return files;
    return files.filter((file) => file.name.toLowerCase().includes(searchText.toLowerCase()));
  }, [files, searchText]);

  const nameColumn = createTruncatedColumn<RemoteFile>({
    title: t('resources:remoteFiles.name'),
    dataIndex: 'name',
    key: 'name',
    maxLength: 50, // Increased from default 12 to show more of the file name
    sorter: createCustomSorter<RemoteFile>(
      (file) => `${file.isDirectory ? '0' : '1'}${file.name.toLowerCase()}`
    ),
  });

  // Table columns
  const columns: ColumnsType<RemoteFile> = [
    {
      ...nameColumn,
      render: (name: string, record: RemoteFile) => {
        // Build the icon content
        const icon = record.isDirectory ? (
          <FolderIcon>
            <FolderOutlined />
          </FolderIcon>
        ) : (
          <FileIcon>
            <FileOutlined />
          </FileIcon>
        );

        // Build the clickable/display name without nested tooltip
        const displayName = record.isDirectory ? (
          <a
            onClick={() => handleNavigate(currentPath ? `${currentPath}/${name}` : name)}
            data-testid={`file-browser-folder-${name}`}
          >
            {name}
          </a>
        ) : (
          <span data-testid={`file-browser-file-${name}`}>{name}</span>
        );

        const content = (
          <Space>
            {icon}
            {displayName}
          </Space>
        );

        // Combine tooltip information: show both full name and original GUID if available
        if (record.originalGuid) {
          const tooltipContent = (
            <div>
              <div>{name}</div>
              <div style={{ marginTop: '4px', opacity: 0.85 }}>
                Original file: {record.originalGuid}
              </div>
            </div>
          );
          return <Tooltip title={tooltipContent}>{content}</Tooltip>;
        }

        // If name is long, show tooltip with full name
        if (name.length > 50) {
          return <Tooltip title={name}>{content}</Tooltip>;
        }

        return content;
      },
    },
    {
      title: t('resources:remoteFiles.size'),
      dataIndex: 'size',
      key: 'size',
      width: 120,
      render: (size: number, record: RemoteFile) =>
        record.isDirectory ? '-' : formatFileSize(size),
      sorter: createSorter<RemoteFile>('size'),
    },
  ];

  const getRowProps: TableProps<RemoteFile>['onRow'] = (record) => {
    return {
      'data-testid': `file-browser-row-${record.name}`,
    } as React.HTMLAttributes<HTMLElement>;
  };

  // Breadcrumb items
  const breadcrumbItems = useMemo(() => {
    const items = [
      {
        title: (
          <span data-testid="file-browser-breadcrumb-home">
            <HomeOutlined />
          </span>
        ),
        onClick: () => handleNavigate(''),
      },
    ];

    if (currentPath) {
      const parts = currentPath.split('/').filter(Boolean);
      parts.forEach((part, index) => {
        const path = parts.slice(0, index + 1).join('/');
        items.push({
          title: <span data-testid={`file-browser-breadcrumb-${part}`}>{part}</span>,
          onClick: () => handleNavigate(path),
        });
      });
    }

    return items;
  }, [currentPath]);

  return (
    <Modal
      data-testid="file-browser-modal"
      title={
        <Space>
          <CloudDownloadOutlined />
          {t('resources:remoteFiles.title')}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      className={ModalSize.Large}
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
      <ContentSpace orientation="vertical" size="middle">
        {/* Source selector with label */}
        <div data-testid="file-browser-source-container">
          <SourceLabel data-testid="file-browser-source-label">
            {t('resources:remoteFiles.sourceLabel')}
          </SourceLabel>
          <SourceContainer>
            <Space>
              <SourceSelect>
                <Select
                  style={{ width: '100%' }}
                  placeholder={t('resources:remoteFiles.selectSource')}
                  value={selectedSource}
                  onChange={(value) => {
                    setSelectedSource(value);
                    setCurrentPath('');
                    setSelectedFile('');
                    setFiles([]); // Clear files when changing source
                  }}
                  loading={isLoadingStorage || isLoadingMachines}
                  notFoundContent={
                    isLoadingStorage || isLoadingMachines ? (
                      <div style={{ padding: 8 }}>
                        <InlineLoadingIndicator
                          width="100%"
                          height={18}
                          data-testid="file-browser-source-loading"
                        />
                      </div>
                    ) : storageSources.length === 0 ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={t('resources:remoteFiles.noSources')}
                      />
                    ) : null
                  }
                  options={storageSources}
                  data-testid="file-browser-source-select"
                />
              </SourceSelect>
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
            <SearchInput>
              <Input
                placeholder={t('common:actions.search')}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                data-testid="file-browser-search-input"
              />
            </SearchInput>
          </SourceContainer>
        </div>

        {/* Breadcrumb navigation */}
        {currentPath && (
          <Breadcrumb
            items={breadcrumbItems}
            separator={<RightOutlined />}
            data-testid="file-browser-breadcrumb"
          />
        )}

        {/* File list */}
        <LoadingWrapper
          loading={loading}
          centered
          minHeight={240}
          tip={t('common:general.loading') as string}
        >
          {filteredFiles.length === 0 ? (
            <Empty
              description={t('resources:remoteFiles.noFiles')}
              data-testid="file-browser-empty-state"
            />
          ) : (
            <Table
              dataSource={filteredFiles}
              columns={columns}
              rowKey="name"
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total, range) =>
                  t('common:table.showingRecords', {
                    start: range[0],
                    end: range[1],
                    total,
                  }),
              }}
              rowSelection={{
                type: 'radio',
                selectedRowKeys: selectedFile ? [selectedFile] : [],
                onChange: (keys) => setSelectedFile((keys[0] as string) || ''),
                getCheckboxProps: (record) => ({
                  disabled: record.isDirectory,
                }),
              }}
              scroll={{ y: 400 }}
              data-testid="file-browser-table"
              onRow={getRowProps}
            />
          )}
        </LoadingWrapper>

        {/* Info message */}
        <Alert
          type="info"
          message={t('resources:remoteFiles.info')}
          showIcon
          data-testid="file-browser-info-alert"
        />
      </ContentSpace>
    </Modal>
  );
};
