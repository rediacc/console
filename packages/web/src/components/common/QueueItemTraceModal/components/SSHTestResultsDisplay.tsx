import { Alert, Card, Collapse, Descriptions, Flex, Space, Tag, Typography } from 'antd';
import React from 'react';
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
    <Flex vertical className="w-full">
      {/* SSH Test Result Summary */}
      <Card size="small" title={t('trace.sshTestResult')}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label={t('trace.status')}>
            <Tag>{result.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.machine')}>
            {result.machine ?? 'N/A'}
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.ipAddress')}>{result.ip}</Descriptions.Item>
          <Descriptions.Item label={t('trace.user')}>{result.user}</Descriptions.Item>
          <Descriptions.Item label={t('trace.authMethod')}>
            <Tag>{result.auth_method}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.sshKeyConfigured')}>
            {result.ssh_key_configured ? (
              <Tag>{t('trace.configured')}</Tag>
            ) : (
              <Tag>{t('trace.notConfigured')}</Tag>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* System Information */}
      <Card size="small" title={t('trace.systemInfo')}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label={t('trace.operatingSystem')}>
            {osInfo?.pretty_name ?? t('trace.unknown')}
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.kernelVersion')}>
            <Typography.Text code>{compatibility.kernel_version}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.osId')}>
            {osInfo?.id ?? t('trace.unknown')}
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.version')}>
            {osInfo?.version_id ?? t('trace.unknown')}
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.btrfsSupport')}>
            {compatibility.btrfs_available ? (
              <Tag>{t('trace.available')}</Tag>
            ) : (
              <Tag>{t('trace.notAvailable')}</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t('trace.sudoSupport')}>
            {(() => {
              const sudoStatus = compatibility.sudo_available;
              if (sudoStatus === 'available') {
                return <Tag>{t('trace.available')}</Tag>;
              }
              if (sudoStatus === 'password_required') {
                return <Tag>{t('trace.passwordRequired')}</Tag>;
              }
              if (sudoStatus === 'not_installed') {
                return <Tag>{t('trace.notInstalled')}</Tag>;
              }
              return <Tag>{t('trace.unknown')}</Tag>;
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
            <Typography.Text strong>{t('trace.compatibilityStatus')}</Typography.Text>
            <Typography.Text className="capitalize">{status}</Typography.Text>
          </Space>
        }
        description={
          <>
            {compatibility.compatibility_issues &&
              compatibility.compatibility_issues.length > 0 && (
                <Flex vertical className="mt-2">
                  <Typography.Text strong>{t('trace.knownIssues')}</Typography.Text>
                  <ul>
                    {compatibility.compatibility_issues.map((issue: string, index: number) => (
                      <li key={index}>{issue}</li>
                    ))}
                  </ul>
                </Flex>
              )}
            {compatibility.recommendations && compatibility.recommendations.length > 0 && (
              <Flex vertical className="mt-4">
                <Typography.Text strong>{t('trace.recommendations')}</Typography.Text>
                <ul>
                  {compatibility.recommendations.map((rec: string, index: number) => (
                    <li key={index}>{rec}</li>
                  ))}
                </ul>
              </Flex>
            )}
          </>
        }
      />

      {/* Raw JSON fallback */}
      <Flex vertical className="mt-4">
        <Collapse
          items={[
            {
              key: 'raw',
              label: t('trace.rawResponseData'),
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
