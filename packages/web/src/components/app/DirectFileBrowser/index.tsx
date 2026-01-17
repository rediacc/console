/* eslint-disable no-restricted-syntax, react/forbid-elements, @typescript-eslint/no-floating-promises, react-hooks/exhaustive-deps, @typescript-eslint/require-await, max-lines */

import React, { useEffect, useState } from 'react';
import {
  CloseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FileOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  HomeOutlined,
  LinkOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Breadcrumb,
  Button,
  Dropdown,
  Flex,
  Grid,
  Input,
  List,
  Modal,
  Radio,
  Space,
  Table,
  Tooltip,
  Typography,
  theme,
  Upload,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { MobileCard } from '@/components/common/MobileCard';
import { SizedModal } from '@/components/common/SizedModal';
import { type SFTPFile, useSftp } from '@/hooks/sftp/useSftp';
import { isElectron } from '@/types';
import { ModalSize } from '@/types/modal';
import { formatBytes } from '@/utils/formatters';
import { showMessage } from '@/utils/messages';
import { DesktopPrompt } from './DesktopPrompt';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

interface DirectFileBrowserProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal is closed */
  onCancel: () => void;
  /** SSH host */
  host: string;
  /** SSH username */
  user: string;
  /** SSH private key */
  privateKey: string;
  /** SSH port (default: 22) */
  port?: number;
  /** Initial path to navigate to */
  initialPath?: string;
  /** Machine name for display */
  machineName: string;
  /** Repository name for display (optional) */
  repositoryName?: string;
}

/**
 * Direct SFTP file browser for Electron desktop app
 *
 * Connects directly to remote machines via SSH/SFTP for file operations.
 * Only functional in Electron - shows a desktop prompt in browser.
 */
export const DirectFileBrowser: React.FC<DirectFileBrowserProps> = ({
  open,
  onCancel,
  host,
  user,
  privateKey,
  port,
  initialPath = '/',
  machineName,
  repositoryName,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;
  const [searchText, setSearchText] = useState('');
  const [selectedFile, setSelectedFile] = useState<SFTPFile | null>(null);
  const [newFolderModalOpen, setNewFolderModalOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameValue, setRenameValue] = useState('');

  const sftp = useSftp({ host, user, privateKey, port }, initialPath);

  // Connect when modal opens
  useEffect(() => {
    if (open && isElectron() && !sftp.isConnected && !sftp.isConnecting) {
      sftp.connect();
    }
  }, [open, sftp.isConnected, sftp.isConnecting]);

  // Disconnect when modal closes
  useEffect(() => {
    if (!open && sftp.isConnected) {
      sftp.disconnect();
    }
  }, [open, sftp.isConnected]);

  // Show prompt for browser users
  if (!isElectron()) {
    return (
      <SizedModal
        open={open}
        onCancel={onCancel}
        size={ModalSize.Large}
        footer={null}
        title={
          <Space>
            <FolderOpenOutlined />
            {t('common:fileBrowser.fileBrowser')}
          </Space>
        }
      >
        <DesktopPrompt
          featureName={t('common:fileBrowser.fileBrowser')}
          machineName={machineName}
          repositoryName={repositoryName}
          initialPath={initialPath}
        />
      </SizedModal>
    );
  }

  // Build breadcrumb items
  const breadcrumbItems = (() => {
    const items = [
      {
        key: 'home',
        title: (
          <span onClick={() => sftp.navigate('/')} className="cursor-pointer">
            <HomeOutlined /> {t('common:fileBrowser.root')}
          </span>
        ),
      },
    ];

    if (sftp.currentPath && sftp.currentPath !== '/') {
      const parts = sftp.currentPath.split('/').filter(Boolean);
      let accumulatedPath = '';

      parts.forEach((part, index) => {
        accumulatedPath += `/${part}`;
        const pathCopy = accumulatedPath;
        items.push({
          key: pathCopy,
          title: (
            <span
              onClick={() => sftp.navigate(pathCopy)}
              className={index < parts.length - 1 ? 'cursor-pointer' : 'cursor-default'}
            >
              {part}
            </span>
          ),
        });
      });
    }

    return items;
  })();

  // Filter files based on search
  const filteredFiles = sftp.files.filter((file) =>
    file.name.toLowerCase().includes(searchText.toLowerCase())
  );

  // Handle file/folder click
  const handleItemClick = (file: SFTPFile) => {
    if (file.isDirectory) {
      sftp.navigate(file.path);
      setSelectedFile(null);
    } else {
      setSelectedFile(file);
    }
  };

  // Handle download
  const handleDownload = async () => {
    if (!selectedFile || selectedFile.isDirectory) return;
    await sftp.downloadFile(selectedFile.path);
    showMessage('success', t('common:fileBrowser.downloaded', { name: selectedFile.name }));
  };

  // Handle delete
  const handleDelete = async () => {
    if (!selectedFile) return;

    Modal.confirm({
      title: selectedFile.isDirectory
        ? t('common:fileBrowser.deleteFolderConfirm')
        : t('common:fileBrowser.deleteFileConfirm'),
      content: `${t('common:fileBrowser.deleteConfirmMessage', { name: selectedFile.name })}${
        selectedFile.isDirectory ? t('common:fileBrowser.deleteFolderWarning') : ''
      }`,
      okType: 'danger',
      onOk: async () => {
        await sftp.deleteFile(selectedFile.path, selectedFile.isDirectory);
        setSelectedFile(null);
        showMessage('success', t('common:fileBrowser.downloaded', { name: selectedFile.name }));
      },
    });
  };

  // Handle new folder
  const handleNewFolder = async () => {
    if (!newFolderName.trim()) return;
    await sftp.createFolder(newFolderName.trim());
    setNewFolderModalOpen(false);
    setNewFolderName('');
    showMessage('success', t('common:fileBrowser.created', { name: newFolderName }));
  };

  // Handle rename
  const handleRename = async () => {
    if (!selectedFile || !renameValue.trim()) return;
    await sftp.rename(selectedFile.path, renameValue.trim());
    setRenameModalOpen(false);
    setRenameValue('');
    setSelectedFile(null);
    showMessage('success', t('common:fileBrowser.renamedSuccessfully'));
  };

  // Handle file upload
  const handleFileUpload = async (file: File) => {
    await sftp.uploadFile(file);
    showMessage('success', t('common:fileBrowser.uploaded', { name: file.name }));
    return false; // Prevent default upload behavior
  };

  // Context menu for files
  const getContextMenu = (file: SFTPFile): MenuProps['items'] => [
    {
      key: 'download',
      label: t('common:actions.download'),
      icon: <DownloadOutlined />,
      disabled: file.isDirectory,
      onClick: () => {
        setSelectedFile(file);
        sftp.downloadFile(file.path).then(() => {
          showMessage('success', t('common:fileBrowser.downloaded', { name: file.name }));
        });
      },
    },
    {
      key: 'rename',
      label: t('common:actions.rename'),
      icon: <EditOutlined />,
      onClick: () => {
        setSelectedFile(file);
        setRenameValue(file.name);
        setRenameModalOpen(true);
      },
    },
    { type: 'divider' },
    {
      key: 'delete',
      label: t('common:actions.delete'),
      icon: <DeleteOutlined />,
      danger: true,
      onClick: () => {
        setSelectedFile(file);
        handleDelete();
      },
    },
  ];

  // Table columns
  const columns: ColumnsType<SFTPFile> = [
    {
      title: t('common:fileBrowser.name'),
      dataIndex: 'name',
      key: 'name',
      sorter: (a, b) => a.name.localeCompare(b.name),
      render: (name: string, file: SFTPFile) => {
        let fileIcon: React.ReactNode;
        if (file.isDirectory) {
          fileIcon = <FolderOpenOutlined style={{ color: token.colorPrimary }} />;
        } else if (file.isSymlink) {
          fileIcon = <LinkOutlined style={{ color: token.purple }} />;
        } else {
          fileIcon = <FileOutlined />;
        }
        return (
          <Dropdown menu={{ items: getContextMenu(file) }} trigger={['contextMenu']}>
            <Space
              className={file.isDirectory ? 'cursor-pointer' : 'cursor-default'}
              onClick={() => handleItemClick(file)}
            >
              {fileIcon}
              <Text className="max-w-[300px]">{name}</Text>
            </Space>
          </Dropdown>
        );
      },
    },
    {
      title: t('common:fileBrowser.size'),
      dataIndex: 'size',
      key: 'size',
      width: 100,
      sorter: (a, b) => a.size - b.size,
      render: (size: number, file: SFTPFile) => (file.isDirectory ? '-' : formatBytes(size)),
    },
    {
      title: t('common:fileBrowser.modified'),
      dataIndex: 'modifiedAt',
      key: 'modifiedAt',
      width: 180,
      sorter: (a, b) => new Date(a.modifiedAt).getTime() - new Date(b.modifiedAt).getTime(),
      render: (date: Date) =>
        new Date(date).toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }),
    },
    {
      title: t('common:fileBrowser.permissions'),
      dataIndex: 'permissions',
      key: 'permissions',
      width: 100,
      render: (perms: string) => <Text code>{perms}</Text>,
    },
  ];

  return (
    <>
      <SizedModal
        open={open}
        onCancel={onCancel}
        size={ModalSize.Large}
        title={
          <Space>
            <FolderOpenOutlined />
            {t('common:fileBrowser.fileBrowser')} - {machineName}
            {repositoryName && <Text type="secondary">/ {repositoryName}</Text>}
          </Space>
        }
        footer={[
          <Tooltip key="close" title={t('common:actions.cancel')}>
            <Button icon={<CloseOutlined />} onClick={onCancel} />
          </Tooltip>,
          <Tooltip key="refresh" title={t('common:actions.refresh')}>
            <Button icon={<ReloadOutlined />} onClick={sftp.refresh} loading={sftp.isLoading} />
          </Tooltip>,
          <Tooltip key="newFolder" title={t('common:actions.newFolder')}>
            <Button
              icon={<FolderAddOutlined />}
              onClick={() => setNewFolderModalOpen(true)}
              disabled={!sftp.isConnected}
            />
          </Tooltip>,
          <Upload
            key="upload"
            showUploadList={false}
            beforeUpload={handleFileUpload}
            disabled={!sftp.isConnected}
          >
            <Tooltip title={t('common:actions.uploadFile')}>
              <Button icon={<UploadOutlined />} disabled={!sftp.isConnected} />
            </Tooltip>
          </Upload>,
          <Tooltip key="download" title={t('common:actions.downloadSelected')}>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleDownload}
              disabled={!selectedFile || selectedFile.isDirectory}
            />
          </Tooltip>,
          <Tooltip key="delete" title={t('common:actions.deleteSelected')}>
            <Button
              icon={<DeleteOutlined />}
              onClick={handleDelete}
              disabled={!selectedFile}
              danger
            />
          </Tooltip>,
        ]}
      >
        <Flex vertical>
          {/* Error Alert */}
          {sftp.error && (
            <Alert
              type="error"
              message={t('common:fileBrowser.error')}
              description={sftp.error}
              closable
              onClose={() => {
                // Clear error - would need setState exposed from hook
              }}
            />
          )}

          {/* Connecting state */}
          {sftp.isConnecting && (
            <Alert
              type="info"
              message={t('common:fileBrowser.connecting')}
              description={t('common:fileBrowser.establishingConnection', { host })}
            />
          )}

          {/* Connected content */}
          {sftp.isConnected && (
            <>
              {/* Toolbar */}
              <Flex justify="space-between" align="center">
                <Breadcrumb items={breadcrumbItems} />
                <Input
                  placeholder={t('common:actions.search')}
                  prefix={<span className="mr-1">🔍</span>}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  className="w-[200px]"
                  allowClear
                  data-testid="direct-file-browser-search"
                />
              </Flex>

              {/* File Table / List */}
              {isMobile ? (
                <List
                  dataSource={filteredFiles}
                  loading={sftp.isLoading}
                  pagination={{
                    pageSize: 20,
                    showSizeChanger: true,
                    showTotal: (total) => t('common:fileBrowser.items', { count: total }),
                  }}
                  renderItem={(file) => {
                    const isSelected = selectedFile?.path === file.path;
                    return (
                      <List.Item
                        key={file.path}
                        onClick={() => handleItemClick(file)}
                        className="cursor-pointer"
                      >
                        <MobileCard>
                          <Flex align="center">
                            <Radio
                              checked={isSelected}
                              disabled={file.isDirectory}
                              onClick={(e) => {
                                e.stopPropagation();
                                if (!file.isDirectory) setSelectedFile(file);
                              }}
                            />
                            {(() => {
                              if (file.isDirectory) {
                                return <FolderOpenOutlined style={{ color: token.colorPrimary }} />;
                              } else if (file.isSymlink) {
                                return <LinkOutlined style={{ color: token.purple }} />;
                              }
                              return <FileOutlined />;
                            })()}
                            <Flex vertical className="flex-1 min-w-0">
                              {file.isDirectory ? (
                                <Typography.Link strong className="truncate">
                                  {file.name}
                                </Typography.Link>
                              ) : (
                                <Text strong className="truncate">
                                  {file.name}
                                </Text>
                              )}
                              <Flex>
                                <Text type="secondary">
                                  {file.isDirectory
                                    ? t('common:fileBrowser.folder')
                                    : formatBytes(file.size)}
                                </Text>
                                <Text type="secondary" code>
                                  {file.permissions}
                                </Text>
                              </Flex>
                            </Flex>
                          </Flex>
                        </MobileCard>
                      </List.Item>
                    );
                  }}
                />
              ) : (
                <Table
                  columns={columns}
                  dataSource={filteredFiles}
                  rowKey="path"
                  loading={sftp.isLoading}
                  pagination={{
                    pageSize: 20,
                    showSizeChanger: true,
                    showTotal: (total) => t('common:fileBrowser.items', { count: total }),
                  }}
                  rowSelection={{
                    type: 'radio',
                    selectedRowKeys: selectedFile ? [selectedFile.path] : [],
                    onChange: (_, selectedRows) => {
                      setSelectedFile(selectedRows[0] || null);
                    },
                  }}
                  onRow={(record) => ({
                    onClick: () => setSelectedFile(record),
                    onDoubleClick: () => handleItemClick(record),
                  })}
                  scroll={{ y: 400 }}
                />
              )}

              {/* Path info */}
              <Flex justify="space-between">
                <Text type="secondary">
                  {t('common:general.path')}: <Text code>{sftp.currentPath}</Text>
                </Text>
                <Text type="secondary">
                  {t('common:fileBrowser.items', { count: filteredFiles.length })}
                </Text>
              </Flex>
            </>
          )}
        </Flex>
      </SizedModal>

      {/* New Folder Modal */}
      <Modal
        title={t('common:fileBrowser.createNewFolder')}
        open={newFolderModalOpen}
        onOk={handleNewFolder}
        onCancel={() => {
          setNewFolderModalOpen(false);
          setNewFolderName('');
        }}
        okText={t('common:actions.create')}
        data-testid="direct-file-browser-new-folder-modal"
      >
        <Input
          placeholder={t('common:fileBrowser.folderName')}
          value={newFolderName}
          onChange={(e) => setNewFolderName(e.target.value)}
          onPressEnter={handleNewFolder}
          autoFocus
          data-testid="direct-file-browser-new-folder-input"
        />
      </Modal>

      {/* Rename Modal */}
      <Modal
        title={t('common:actions.rename')}
        open={renameModalOpen}
        onOk={handleRename}
        onCancel={() => {
          setRenameModalOpen(false);
          setRenameValue('');
        }}
        okText={t('common:actions.rename')}
        data-testid="direct-file-browser-rename-modal"
      >
        <Input
          placeholder={t('common:fileBrowser.newName')}
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={handleRename}
          autoFocus
          data-testid="direct-file-browser-rename-input"
        />
      </Modal>
    </>
  );
};

export default DirectFileBrowser;
