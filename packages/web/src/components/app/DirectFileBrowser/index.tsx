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
  Input,
  Modal,
  Space,
  Table,
  Tooltip,
  Typography,
  Upload,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { SizedModal } from '@/components/common';
import { useSftp, type SFTPFile } from '@/hooks/sftp/useSftp';
import { ModalSize } from '@/types/modal';
import { isElectron } from '@/utils/environment';
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
            File Browser
          </Space>
        }
      >
        <DesktopPrompt
          featureName="File Browser"
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
          <span onClick={() => sftp.navigate('/')} style={{ cursor: 'pointer' }}>
            <HomeOutlined /> root
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
              style={{ cursor: index < parts.length - 1 ? 'pointer' : 'default' }}
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
    showMessage('success', `Downloaded: ${selectedFile.name}`);
  };

  // Handle delete
  const handleDelete = async () => {
    if (!selectedFile) return;

    Modal.confirm({
      title: `Delete ${selectedFile.isDirectory ? 'folder' : 'file'}?`,
      content: `Are you sure you want to delete "${selectedFile.name}"?${
        selectedFile.isDirectory ? ' This will delete all contents.' : ''
      }`,
      okType: 'danger',
      onOk: async () => {
        await sftp.deleteFile(selectedFile.path, selectedFile.isDirectory);
        setSelectedFile(null);
        showMessage('success', `Deleted: ${selectedFile.name}`);
      },
    });
  };

  // Handle new folder
  const handleNewFolder = async () => {
    if (!newFolderName.trim()) return;
    await sftp.createFolder(newFolderName.trim());
    setNewFolderModalOpen(false);
    setNewFolderName('');
    showMessage('success', `Created folder: ${newFolderName}`);
  };

  // Handle rename
  const handleRename = async () => {
    if (!selectedFile || !renameValue.trim()) return;
    await sftp.rename(selectedFile.path, renameValue.trim());
    setRenameModalOpen(false);
    setRenameValue('');
    setSelectedFile(null);
    showMessage('success', 'Renamed successfully');
  };

  // Handle file upload
  const handleFileUpload = async (file: File) => {
    await sftp.uploadFile(file);
    showMessage('success', `Uploaded: ${file.name}`);
    return false; // Prevent default upload behavior
  };

  // Context menu for files
  const getContextMenu = (file: SFTPFile): MenuProps['items'] => [
    {
      key: 'download',
      label: 'Download',
      icon: <DownloadOutlined />,
      disabled: file.isDirectory,
      onClick: () => {
        setSelectedFile(file);
        sftp.downloadFile(file.path).then(() => {
          showMessage('success', `Downloaded: ${file.name}`);
        });
      },
    },
    {
      key: 'rename',
      label: 'Rename',
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
      label: 'Delete',
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
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      sorter: (a, b) => a.name.localeCompare(b.name),
      render: (name: string, file: SFTPFile) => (
        <Dropdown menu={{ items: getContextMenu(file) }} trigger={['contextMenu']}>
          <Space
            style={{ cursor: file.isDirectory ? 'pointer' : 'default' }}
            onClick={() => handleItemClick(file)}
          >
            {file.isDirectory ? (
              <FolderOpenOutlined style={{ color: '#1890ff' }} />
            ) : file.isSymlink ? (
              <LinkOutlined style={{ color: '#722ed1' }} />
            ) : (
              <FileOutlined />
            )}
            <Text ellipsis style={{ maxWidth: 300 }}>
              {name}
            </Text>
          </Space>
        </Dropdown>
      ),
    },
    {
      title: 'Size',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      sorter: (a, b) => a.size - b.size,
      render: (size: number, file: SFTPFile) => (file.isDirectory ? '-' : formatBytes(size)),
    },
    {
      title: 'Modified',
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
      title: 'Permissions',
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
            File Browser - {machineName}
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
          <Tooltip key="newFolder" title="New Folder">
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
            <Tooltip title="Upload File">
              <Button icon={<UploadOutlined />} disabled={!sftp.isConnected} />
            </Tooltip>
          </Upload>,
          <Tooltip key="download" title="Download Selected">
            <Button
              icon={<DownloadOutlined />}
              onClick={handleDownload}
              disabled={!selectedFile || selectedFile.isDirectory}
            />
          </Tooltip>,
          <Tooltip key="delete" title="Delete Selected">
            <Button
              icon={<DeleteOutlined />}
              onClick={handleDelete}
              disabled={!selectedFile}
              danger
            />
          </Tooltip>,
        ]}
      >
        <Flex vertical gap={16}>
          {/* Error Alert */}
          {sftp.error && (
            <Alert
              type="error"
              message="Error"
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
              message="Connecting..."
              description={`Establishing SFTP connection to ${host}...`}
              showIcon
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
                  prefix={<span style={{ marginRight: 4 }}>🔍</span>}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  style={{ width: 200 }}
                  allowClear
                />
              </Flex>

              {/* File Table */}
              <Table
                columns={columns}
                dataSource={filteredFiles}
                rowKey="path"
                size="small"
                loading={sftp.isLoading}
                pagination={{
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `${total} items`,
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

              {/* Path info */}
              <Flex justify="space-between">
                <Text type="secondary">
                  Path: <Text code>{sftp.currentPath}</Text>
                </Text>
                <Text type="secondary">{filteredFiles.length} items</Text>
              </Flex>
            </>
          )}
        </Flex>
      </SizedModal>

      {/* New Folder Modal */}
      <Modal
        title="Create New Folder"
        open={newFolderModalOpen}
        onOk={handleNewFolder}
        onCancel={() => {
          setNewFolderModalOpen(false);
          setNewFolderName('');
        }}
        okText="Create"
      >
        <Input
          placeholder="Folder name"
          value={newFolderName}
          onChange={(e) => setNewFolderName(e.target.value)}
          onPressEnter={handleNewFolder}
          autoFocus
        />
      </Modal>

      {/* Rename Modal */}
      <Modal
        title="Rename"
        open={renameModalOpen}
        onOk={handleRename}
        onCancel={() => {
          setRenameModalOpen(false);
          setRenameValue('');
        }}
        okText="Rename"
      >
        <Input
          placeholder="New name"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={handleRename}
          autoFocus
        />
      </Modal>
    </>
  );
};

export default DirectFileBrowser;
