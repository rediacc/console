import React, { useMemo } from 'react';
import { FileOutlined, FolderOutlined } from '@ant-design/icons';
import {
  Empty,
  Flex,
  Grid,
  List,
  Radio,
  Space,
  Table,
  type TableProps,
  Tooltip,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { createTruncatedColumn } from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { MobileCard } from '@/components/common/MobileCard';
import { createCustomSorter, createSorter } from '@/platform';
import type { RemoteFile } from './types';
import type { ColumnsType } from 'antd/es/table/interface';

interface BrowserFileTableProps {
  files: RemoteFile[];
  loading: boolean;
  searchText: string;
  selectedFile: string;
  currentPath: string;
  onNavigate: (path: string) => void;
  onSelectFile: (fileName: string) => void;
}

export const BrowserFileTable: React.FC<BrowserFileTableProps> = ({
  files,
  loading,
  searchText,
  selectedFile,
  currentPath,
  onNavigate,
  onSelectFile,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;

  const filteredFiles = useMemo(() => {
    if (!searchText) return files;
    return files.filter((file) => file.name.toLowerCase().includes(searchText.toLowerCase()));
  }, [files, searchText]);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const nameColumn = createTruncatedColumn<RemoteFile>({
    title: t('resources:remoteFiles.name'),
    dataIndex: 'name',
    key: 'name',
    maxLength: 50,
    sorter: createCustomSorter<RemoteFile>(
      (file) => `${file.isDirectory ? '0' : '1'}${file.name.toLowerCase()}`
    ),
  });

  const columns: ColumnsType<RemoteFile> = [
    {
      ...nameColumn,
      render: (name: string, record: RemoteFile) => {
        const icon = record.isDirectory ? (
          <Typography.Text>
            <FolderOutlined />
          </Typography.Text>
        ) : (
          <Typography.Text>
            <FileOutlined />
          </Typography.Text>
        );

        const displayName = record.isDirectory ? (
          <a
            onClick={() => onNavigate(currentPath ? `${currentPath}/${name}` : name)}
            data-testid={`file-browser-folder-${name}`}
          >
            {name}
          </a>
        ) : (
          <Typography.Text data-testid={`file-browser-file-${name}`}>{name}</Typography.Text>
        );

        const content = (
          <Space>
            {icon}
            {displayName}
          </Space>
        );

        if (record.originalGuid) {
          const tooltipContent = (
            <Flex vertical>
              <Typography.Text>{name}</Typography.Text>
              <Typography.Text>
                {t('common:fileBrowser.originalFile')}: {record.originalGuid}
              </Typography.Text>
            </Flex>
          );
          return <Tooltip title={tooltipContent}>{content}</Tooltip>;
        }

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
    const props: React.HTMLAttributes<HTMLElement> & Record<string, string> = {
      'data-testid': `file-browser-row-${record.name}`,
    };
    return props;
  };

  const renderMobileList = () => (
    <List
      dataSource={filteredFiles}
      data-testid="file-browser-table"
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
      renderItem={(record) => {
        const isSelected = selectedFile === record.name;
        const handleClick = () => {
          if (record.isDirectory) {
            onNavigate(currentPath ? `${currentPath}/${record.name}` : record.name);
          } else {
            onSelectFile(record.name);
          }
        };

        return (
          <List.Item
            key={record.name}
            data-testid={`file-browser-row-${record.name}`}
            onClick={handleClick}
            className="cursor-pointer"
          >
            <MobileCard>
              <Flex align="center">
                <Radio
                  checked={isSelected}
                  disabled={record.isDirectory}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!record.isDirectory) onSelectFile(record.name);
                  }}
                />
                {record.isDirectory ? <FolderOutlined /> : <FileOutlined />}
                <Flex vertical className="flex-1 min-w-0">
                  {record.isDirectory ? (
                    <Typography.Link strong className="truncate">
                      {record.name}
                    </Typography.Link>
                  ) : (
                    <Typography.Text strong className="truncate">
                      {record.name}
                    </Typography.Text>
                  )}
                  {!record.isDirectory && (
                    <Typography.Text type="secondary">
                      {formatFileSize(record.size)}
                    </Typography.Text>
                  )}
                </Flex>
              </Flex>
            </MobileCard>
          </List.Item>
        );
      }}
    />
  );

  return (
    <LoadingWrapper loading={loading} centered minHeight={240} tip={t('common:general.loading')}>
      {(() => {
        if (filteredFiles.length === 0) {
          return (
            <Empty
              description={t('resources:remoteFiles.noFiles')}
              data-testid="file-browser-empty-state"
            />
          );
        } else if (isMobile) {
          return renderMobileList();
        }
        return (
          <Table<RemoteFile>
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
              onChange: (keys) => onSelectFile((keys[0] as string) || ''),
              getCheckboxProps: (record) => ({
                disabled: record.isDirectory,
              }),
            }}
            scroll={{ y: 400 }}
            data-testid="file-browser-table"
            onRow={getRowProps}
          />
        );
      })()}
    </LoadingWrapper>
  );
};
