import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Modal,
  Table,
  Button,
  Space,
  
  Input,
  Select,
  Spin,
  Empty,
  Alert,
  Breadcrumb,
  
  Tooltip,
  
} from 'antd';
import { ModalSize } from '@/types/modal';
import { ContentSpace, SourceLabel, SourceContainer, SourceSelect, SearchInput, FolderIcon, FileIcon } from './styles';
import type { ColumnsType } from 'antd/es/table/interface';
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
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { waitForQueueItemCompletion } from '@/services/helloService';
import { showMessage } from '@/utils/messages';
import { formatTimestamp } from '@/utils/timeUtils';

interface RemoteFile {
  name: string;
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
      machinesData.forEach(machine => {
        sources.push({
          value: machine.machineName,
          label: `${machine.machineName} (Machine)`,
          type: 'machine'
        });
      });
    }

    // Add storage systems
    if (storageData && storageData.length > 0) {
      storageData.forEach(storage => {
        sources.push({
          value: storage.storageName,
          label: `${storage.storageName} (Cloud Storage)`,
          type: 'storage'
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

  const loadFiles = async () => {
    if (!selectedSource) {
      console.log('No source selected, skipping file load');
      return;
    }

    console.log('Loading files from:', selectedSource, 'path:', currentPath);
    setLoading(true);
    try {
      // Find the source details from storage or machines
      const sourceDetails = storageSources.find(s => s.value === selectedSource);
      const isStorageSource = sourceDetails?.type === 'storage';
      
      // Get vault data for the source
      const additionalVaultData: Record<string, any> = {};
      
      // For list function, we always need the current machine's vault data
      // because the command runs on the current machine
      const currentMachine = machinesData?.find(m => m.machineName === machineName);
      console.log('Current machine data:', currentMachine);
      console.log('Machine vault content:', currentMachine?.vaultContent);
      
      if (currentMachine && currentMachine.vaultContent) {
        additionalVaultData.machineVault = currentMachine.vaultContent;
      }
      
      // Get team vault data (contains SSH keys)
      const currentTeam = teamsData?.find(t => t.teamName === teamName);
      console.log('Current team data:', currentTeam);
      if (currentTeam && currentTeam.vaultContent) {
        additionalVaultData.teamVault = currentTeam.vaultContent;
      }
      
      // If listing from a different machine, we need that machine's vault too
      if (!isStorageSource && selectedSource !== machineName) {
        const sourceMachine = machinesData?.find(m => m.machineName === selectedSource);
        if (sourceMachine && sourceMachine.vaultContent) {
          // Parse the vault to add it to MACHINES section
          try {
            const sourceMachineData = JSON.parse(sourceMachine.vaultContent);
            // We'll need to manually add this to the context
            additionalVaultData.additionalMachineData = {
              [selectedSource]: sourceMachineData
            };
          } catch (e) {
            console.error('Failed to parse source machine vault:', e);
          }
        }
      }
      
      // If listing from storage, add storage vault
      if (isStorageSource) {
        const storage = storageData?.find(s => s.storageName === selectedSource);
        if (storage && storage.vaultContent) {
          // For storage systems, the vault data needs to be added to STORAGE_SYSTEMS
          try {
            const storageVaultData = JSON.parse(storage.vaultContent);
            additionalVaultData.additionalStorageData = {
              [selectedSource]: storageVaultData
            };
          } catch (e) {
            console.error('Failed to parse storage vault:', e);
          }
        }
      }

      console.log('Building vault with data:', {
        teamName,
        machineName,
        bridgeName,
        functionName: 'list',
        params: {
          from: selectedSource,
          path: currentPath || '',
          format: 'json'
        },
        additionalVaultData
      });
      
      const vault = await buildQueueVault({
        teamName,
        machineName,
        bridgeName,
        functionName: 'list',
        params: {
          from: selectedSource,
          path: currentPath || '',
          format: 'json'
        },
        priority: 4,
        description: `List files from ${selectedSource}`,
        addedVia: 'file-browser',
        ...additionalVaultData
      });

      console.log('Creating queue item with vault:', vault);
      const result = await createQueueItem({
        teamName,
        machineName,
        bridgeName,
        queueVault: vault,
        priority: 4
      });

      console.log('Queue result:', result);
      const taskId = result.taskId || result.queueId;
      if (!taskId) {
        throw new Error('Failed to create queue item - no taskId returned');
      }

      // Only wait for completion if it's not queued (priority > 1)
      if (!result.isQueued) {
        console.log('Waiting for task completion:', taskId);
        const completionResult = await waitForQueueItemCompletion(taskId, 30000);
        
        console.log('Completion result:', completionResult);
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
            console.log('No response data received');
            setFiles([]);
            return;
          }
          
          // Parse the command result which contains command_output
          if (typeof commandResult === 'string') {
            try {
              const parsed = JSON.parse(commandResult);
              dataToProcess = parsed.command_output || '';
            } catch (e) {
              dataToProcess = commandResult;
            }
          }
          
          // If the data looks like it contains output from the command, extract the JSON array
          if (typeof dataToProcess === 'string') {
            // First check if it starts with debug output
            if (dataToProcess.includes('DEBUG:')) {
              console.log('Raw data with debug output:', dataToProcess);
              // Find the JSON array after all the debug output
              const jsonStartIndex = dataToProcess.lastIndexOf('[');
              const jsonEndIndex = dataToProcess.lastIndexOf(']');
              if (jsonStartIndex !== -1 && jsonEndIndex !== -1 && jsonStartIndex < jsonEndIndex) {
                const jsonString = dataToProcess.substring(jsonStartIndex, jsonEndIndex + 1);
                console.log('Extracted JSON after debug:', jsonString);
                dataToProcess = jsonString;
              }
            } else if (dataToProcess.includes('[')) {
              // Find the JSON array in the output
              const jsonStartIndex = dataToProcess.indexOf('[');
              const jsonEndIndex = dataToProcess.lastIndexOf(']');
              if (jsonStartIndex !== -1 && jsonEndIndex !== -1) {
                const jsonString = dataToProcess.substring(jsonStartIndex, jsonEndIndex + 1);
                console.log('Extracted JSON:', jsonString);
                
                // Clean up the JSON string - remove escaped quotes and newlines
                const cleanedJson = jsonString
                  .replace(/\\\\/g, '\\')
                  .replace(/\\n/g, '\n');
                
                dataToProcess = cleanedJson;
              }
            }
          }
          
          // First try to parse as JSON
          const parsedData = typeof dataToProcess === 'string' ? JSON.parse(dataToProcess) : dataToProcess;
          console.log('Parsed data:', parsedData);
          
          if (Array.isArray(parsedData)) {
            // Direct array format (SSH ls output or rclone lsjson)
            fileList = parsedData.map((file: any) => ({
              name: file.name || file.Name || '',
              size: parseInt(file.size || file.Size || '0'),
              isDirectory: file.isDirectory !== undefined ? file.isDirectory : (file.permissions?.startsWith('d') || file.IsDir || false),
              modTime: file.date ? `${file.date} ${file.time}` : file.ModTime,
              path: file.Path || (currentPath ? `${currentPath}/${file.name || file.Name}` : file.name || file.Name)
            }));
          } else if (parsedData.entries) {
            // rclone lsjson format with entries wrapper
            fileList = parsedData.entries.map((file: any) => ({
              name: file.Name,
              size: file.Size || 0,
              isDirectory: file.IsDir || false,
              modTime: file.ModTime,
              mimeType: file.MimeType,
              path: file.Path || (currentPath ? `${currentPath}/${file.Name}` : file.Name)
            }));
          }
        } catch (parseError) {
          console.log('Parsing as plain text format:', parseError);
          console.log('Data that failed to parse:', dataToProcess);
          
          // Check if this looks like rclone JSON output that's malformed
          if (typeof dataToProcess === 'string' && dataToProcess.includes('"Path":') && dataToProcess.includes('"Name":')) {
            console.log('Detected malformed rclone JSON output');
            // Try to extract individual JSON objects
            const jsonObjects = dataToProcess.match(/\{[^}]+\}/g);
            if (jsonObjects) {
              fileList = jsonObjects.map(jsonStr => {
                try {
                  const file = JSON.parse(jsonStr);
                  return {
                    name: file.Name || '',
                    size: file.Size || 0,
                    isDirectory: file.IsDir || false,
                    modTime: file.ModTime,
                    mimeType: file.MimeType,
                    path: file.Path || (currentPath ? `${currentPath}/${file.Name}` : file.Name)
                  };
                } catch (e) {
                  return null;
                }
              }).filter(f => f !== null) as RemoteFile[];
            }
          } else {
            // Handle plain text format (rclone ls)
            const textData = typeof dataToProcess === 'string' ? dataToProcess : JSON.stringify(dataToProcess);
            const lines = textData.trim().split('\n').filter(line => line.trim());
            
            // Filter out any status messages
            const fileLines = lines.filter(line => 
              !line.startsWith('Listing') && 
              !line.startsWith('Setting up') &&
              !line.startsWith('Error:') &&
              !line.startsWith('DEBUG:') &&
              line.trim() !== ''
            );
          
            fileList = fileLines.map(line => {
              const match = line.match(/^\s*(\d+)\s+(.+)$/);
              if (match) {
                const [, sizeStr, name] = match;
                return {
                  name: name.trim(),
                  size: parseInt(sizeStr),
                  isDirectory: name.endsWith('/'),
                  path: currentPath ? `${currentPath}/${name.trim()}` : name.trim()
                };
              }
              // If no size match (might be directory listing)
              return {
                name: line.trim(),
                size: 0,
                isDirectory: line.endsWith('/'),
                path: currentPath ? `${currentPath}/${line.trim()}` : line.trim()
              };
            });
          }
        }

          setFiles(fileList.filter(f => f.name)); // Filter out any empty entries
        } else {
          console.error('List operation failed:', completionResult.message);
          showMessage('error', completionResult.message || t('resources:remoteFiles.loadError'));
          setFiles([]);
        }
      } else {
        // Item is queued, we can't get immediate results
        console.log('List operation queued with ID:', taskId);
        showMessage('info', 'File listing has been queued. Please try again in a moment.');
        setFiles([]);
      }
    } catch (error: any) {
      console.error('Error loading files:', error);
      console.error('Error details:', {
        message: error.message,
        stack: error.stack,
        response: error.response
      });
      showMessage('error', error.message || t('resources:remoteFiles.loadError'));
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

    const selectedFileObject = files.find(f => f.name === selectedFile);
    if (!selectedFileObject) return;
    
    if (onPullSelected) {
      onPullSelected([selectedFileObject], selectedSource);
      onCancel();
    } else {
      // Direct pull implementation
      const file = selectedFileObject;
        // Get vault data - same pattern as list function
        const additionalVaultData: Record<string, any> = {};
        
        // Find the source details from storage or machines
        const sourceDetails = storageSources.find(s => s.value === selectedSource);
        const isStorageSource = sourceDetails?.type === 'storage';
        
        // Always need the current machine's vault data
        const currentMachine = machinesData?.find(m => m.machineName === machineName);
        if (currentMachine && currentMachine.vaultContent) {
          additionalVaultData.machineVault = currentMachine.vaultContent;
        }
        
        // Get team vault data (contains SSH keys)
        const currentTeam = teamsData?.find(t => t.teamName === teamName);
        if (currentTeam && currentTeam.vaultContent) {
          additionalVaultData.teamVault = currentTeam.vaultContent;
        }
        
        // If pulling from storage, add storage vault
        if (isStorageSource) {
          const storage = storageData?.find(s => s.storageName === selectedSource);
          if (storage && storage.vaultContent) {
            try {
              const storageVaultData = JSON.parse(storage.vaultContent);
              additionalVaultData.additionalStorageData = {
                [selectedSource]: storageVaultData
              };
            } catch (e) {
              console.error('Failed to parse storage vault:', e);
            }
          }
        }
        
        // If pulling from another machine, add that machine's vault
        if (!isStorageSource && selectedSource !== machineName) {
          const sourceMachine = machinesData?.find(m => m.machineName === selectedSource);
          if (sourceMachine && sourceMachine.vaultContent) {
            try {
              const sourceMachineData = JSON.parse(sourceMachine.vaultContent);
              additionalVaultData.additionalMachineData = {
                [selectedSource]: sourceMachineData
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
            repo: file.name,
            path: currentPath || '',
            sourceType: isStorageSource ? 'storage' : 'machine'
          },
          priority: 3,
          description: `Pull ${file.name} from ${selectedSource}`,
          addedVia: 'file-browser',
          ...additionalVaultData
        });

        const response = await createQueueItem({
          teamName,
          machineName,
          bridgeName,
          queueVault: vault,
          priority: 3
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
    return files.filter(file => 
      file.name.toLowerCase().includes(searchText.toLowerCase())
    );
  }, [files, searchText]);

  // Table columns
  const columns: ColumnsType<RemoteFile> = [
    {
      title: t('resources:remoteFiles.name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: RemoteFile) => (
        <Space>
          {record.isDirectory ? (
            <FolderIcon><FolderOutlined /></FolderIcon>
          ) : (
            <FileIcon><FileOutlined /></FileIcon>
          )}
          {record.isDirectory ? (
            <a 
              onClick={() => handleNavigate(currentPath ? `${currentPath}/${name}` : name)}
              data-testid={`file-browser-folder-${name}`}
            >
              {name}
            </a>
          ) : (
            <span data-testid={`file-browser-file-${name}`}>{name}</span>
          )}
        </Space>
      ),
      sorter: (a, b) => {
        // Directories first
        if (a.isDirectory && !b.isDirectory) return -1;
        if (!a.isDirectory && b.isDirectory) return 1;
        return a.name.localeCompare(b.name);
      },
    },
    {
      title: t('resources:remoteFiles.size'),
      dataIndex: 'size',
      key: 'size',
      width: 120,
      render: (size: number, record: RemoteFile) => 
        record.isDirectory ? '-' : formatFileSize(size),
      sorter: (a, b) => a.size - b.size,
    },
    {
      title: t('resources:remoteFiles.modified'),
      dataIndex: 'modTime',
      key: 'modTime',
      width: 200,
      render: (time: string) => time ? formatTimestamp(time) : '-',
      sorter: (a, b) => {
        if (!a.modTime || !b.modTime) return 0;
        return new Date(a.modTime).getTime() - new Date(b.modTime).getTime();
      },
    },
  ];

  // Breadcrumb items
  const breadcrumbItems = useMemo(() => {
    const items = [
      {
        title: <span data-testid="file-browser-breadcrumb-home"><HomeOutlined /></span>,
        onClick: () => handleNavigate(''),
      }
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
      <ContentSpace direction="vertical" size="middle">
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
                    <Spin size="small" />
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
        <Spin spinning={loading}>
          {filteredFiles.length === 0 ? (
            <Empty 
              description={
                loading 
                  ? t('common:general.loading') 
                  : t('resources:remoteFiles.noFiles')
              } 
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
                    total 
                  }),
              }}
              rowSelection={{
                type: 'radio',
                selectedRowKeys: selectedFile ? [selectedFile] : [],
                onChange: (keys) => setSelectedFile(keys[0] as string || ''),
                getCheckboxProps: (record) => ({
                  disabled: record.isDirectory,
                }),
              }}
              scroll={{ y: 400 }}
              data-testid="file-browser-table"
              onRow={(record) => ({
                'data-testid': `file-browser-row-${record.name}`,
              } as any)}
            />
          )}
        </Spin>

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