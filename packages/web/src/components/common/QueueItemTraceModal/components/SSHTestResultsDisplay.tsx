import React from 'react';
import { Alert, Card, Collapse, Descriptions, Flex, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { SSHTestResult } from '../utils/sshTestResultParser';

interface SSHTestResultsDisplayProps {
  result: SSHTestResult;
}

export const SSHTestResultsDisplay: React.FC<SSHTestResultsDisplayProps> = ({ result }) => {
  const { t } = useTranslation(['queue', 'common']);
  const compatibility = result.kernel_compatibility;
  const osInfo = compatibility.os_info;
  const status = compatibility.compatibility_status;

  const statusConfig = {
    compatible: {
      type: 'success' as const,
      icon: <CheckCircleOutlined />,
    },
    warning: {
      type: 'warning' as const,
      icon: <WarningOutlined />,
    },
    incompatible: {
      type: 'error' as const,
      icon: <ExclamationCircleOutlined />,
    },
    unknown: {
      type: 'info' as const,
      icon: <ExclamationCircleOutlined />,
    },
  };

  const config = statusConfig[status];

  return (
    <Flex vertical gap={16} className="w-full">
      {/* SSH Test Result Summary */}
      <Card size="small" title={t('trace.sshTestResult')}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Status">
            <Tag>{result.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Machine">{result.machine ?? 'N/A'}</Descriptions.Item>
          <Descriptions.Item label="IP Address">{result.ip}</Descriptions.Item>
          <Descriptions.Item label="User">{result.user}</Descriptions.Item>
          <Descriptions.Item label="Auth Method">
            <Tag>{result.auth_method}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="SSH Key">
            {result.ssh_key_configured ? <Tag>Configured</Tag> : <Tag>Not Configured</Tag>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* System Information */}
      <Card size="small" title={t('trace.systemInfo')}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="Operating System">
            {osInfo?.pretty_name ?? 'Unknown'}
          </Descriptions.Item>
          <Descriptions.Item label="Kernel Version">
            <Typography.Text code>{compatibility.kernel_version}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="OS ID">{osInfo?.id ?? 'Unknown'}</Descriptions.Item>
          <Descriptions.Item label="Version">{osInfo?.version_id ?? 'Unknown'}</Descriptions.Item>
          <Descriptions.Item label="BTRFS Support">
            {compatibility.btrfs_available ? <Tag>Available</Tag> : <Tag>Not Available</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="Sudo Support">
            {(() => {
              const sudoStatus = compatibility.sudo_available;
              if (sudoStatus === 'available') {
                return <Tag>Available</Tag>;
              }
              if (sudoStatus === 'password_required') {
                return <Tag>Password Required</Tag>;
              }
              if (sudoStatus === 'not_installed') {
                return <Tag>Not Installed</Tag>;
              }
              return <Tag>Unknown</Tag>;
            })()}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Compatibility Status */}
      <Alert
        data-testid="queue-trace-ssh-compatibility-alert"
        type={config.type}
        icon={config.icon}
        message={
          <Space>
            <Typography.Text strong>Compatibility Status:</Typography.Text>
            <Typography.Text
              // eslint-disable-next-line no-restricted-syntax
              style={{ textTransform: 'capitalize' }}
            >
              {status}
            </Typography.Text>
          </Space>
        }
        description={
          <>
            {compatibility.compatibility_issues &&
              compatibility.compatibility_issues.length > 0 && (
                <Flex
                  vertical
                  // eslint-disable-next-line no-restricted-syntax
                  style={{ marginTop: 8 }}
                >
                  <Typography.Text strong>Known Issues:</Typography.Text>
                  <ul>
                    {compatibility.compatibility_issues.map((issue: string, index: number) => (
                      <li key={index}>{issue}</li>
                    ))}
                  </ul>
                </Flex>
              )}
            {compatibility.recommendations && compatibility.recommendations.length > 0 && (
              <Flex
                vertical
                // eslint-disable-next-line no-restricted-syntax
                style={{ marginTop: 16 }}
              >
                <Typography.Text strong>Recommendations:</Typography.Text>
                <ul>
                  {compatibility.recommendations.map((rec: string, index: number) => (
                    <li key={index}>{rec}</li>
                  ))}
                </ul>
              </Flex>
            )}
          </>
        }
        showIcon
      />

      {/* Raw JSON fallback */}
      <Flex
        vertical
        // eslint-disable-next-line no-restricted-syntax
        style={{ marginTop: 16 }}
      >
        <Collapse
          items={[
            {
              key: 'raw',
              label: 'Raw Response Data',
              children: (
                <SimpleJsonEditor value={JSON.stringify(result, null, 2)} readOnly height="200px" />
              ),
            },
          ]}
        />
      </Flex>
    </Flex>
  );
};
