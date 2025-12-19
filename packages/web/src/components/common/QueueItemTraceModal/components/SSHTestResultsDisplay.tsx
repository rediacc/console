import React from 'react';
import { Collapse, Descriptions, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import { RediaccAlert, RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { spacing } from '@/utils/styleConstants';
import { SpacedCardBottom, CompatibilityStatusText, IssuesList, RecommendationsList, SectionMargin } from '../styles';
import type { SSHTestResult } from '../utils/sshTestResultParser';

interface SSHTestResultsDisplayProps {
  result: SSHTestResult;
}

export const SSHTestResultsDisplay: React.FC<SSHTestResultsDisplayProps> = ({ result }) => {
  const { t } = useTranslation(['queue', 'common']);
  const compatibility = result.kernel_compatibility;
  const osInfo = compatibility.os_info || {};
  const status = compatibility.compatibility_status || 'unknown';

  const statusConfig = {
    compatible: {
      type: 'success' as const,
      icon: <CheckCircleOutlined />,
      color: 'var(--color-success)',
    },
    warning: {
      type: 'warning' as const,
      icon: <WarningOutlined />,
      color: 'var(--color-warning)',
    },
    incompatible: {
      type: 'error' as const,
      icon: <ExclamationCircleOutlined />,
      color: 'var(--color-error)',
    },
    unknown: {
      type: 'info' as const,
      icon: <ExclamationCircleOutlined />,
      color: 'var(--color-info)',
    },
  };

  const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.unknown;

  return (
    <RediaccStack variant="column" fullWidth>
      {/* SSH Test Result Summary */}
      <SpacedCardBottom size="sm" title={t('trace.sshTestResult')}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Status">
            <RediaccTag variant="success">{result.status}</RediaccTag>
          </Descriptions.Item>
          <Descriptions.Item label="Machine">{result.machine || 'N/A'}</Descriptions.Item>
          <Descriptions.Item label="IP Address">{result.ip}</Descriptions.Item>
          <Descriptions.Item label="User">{result.user}</Descriptions.Item>
          <Descriptions.Item label="Auth Method">
            <RediaccTag variant="neutral">{result.auth_method}</RediaccTag>
          </Descriptions.Item>
          <Descriptions.Item label="SSH Key">
            {result.ssh_key_configured ? (
              <RediaccTag variant="success">Configured</RediaccTag>
            ) : (
              <RediaccTag variant="warning">Not Configured</RediaccTag>
            )}
          </Descriptions.Item>
        </Descriptions>
      </SpacedCardBottom>

      {/* System Information */}
      <SpacedCardBottom size="sm" title={t('trace.systemInfo')}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="Operating System">
            {osInfo.pretty_name || 'Unknown'}
          </Descriptions.Item>
          <Descriptions.Item label="Kernel Version">
            <RediaccText code>{compatibility.kernel_version || 'Unknown'}</RediaccText>
          </Descriptions.Item>
          <Descriptions.Item label="OS ID">{osInfo.id || 'Unknown'}</Descriptions.Item>
          <Descriptions.Item label="Version">{osInfo.version_id || 'Unknown'}</Descriptions.Item>
          <Descriptions.Item label="BTRFS Support">
            {compatibility.btrfs_available ? (
              <RediaccTag variant="success">Available</RediaccTag>
            ) : (
              <RediaccTag variant="warning">Not Available</RediaccTag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Sudo Support">
            {(() => {
              const sudoStatus = compatibility.sudo_available || 'unknown';
              if (sudoStatus === 'available') {
                return <RediaccTag variant="success">Available</RediaccTag>;
              }
              if (sudoStatus === 'password_required') {
                return <RediaccTag variant="warning">Password Required</RediaccTag>;
              }
              if (sudoStatus === 'not_installed') {
                return <RediaccTag variant="error">Not Installed</RediaccTag>;
              }
              return <RediaccTag variant="neutral">Unknown</RediaccTag>;
            })()}
          </Descriptions.Item>
        </Descriptions>
      </SpacedCardBottom>

      {/* Compatibility Status */}
      <RediaccAlert
        data-testid="queue-trace-ssh-compatibility-alert"
        variant={config.type}
        icon={config.icon}
        message={
          <Space>
            <RediaccText weight="bold">Compatibility Status:</RediaccText>
            <CompatibilityStatusText
              $status={status as 'compatible' | 'warning' | 'incompatible' | 'unknown'}
            >
              {status}
            </CompatibilityStatusText>
          </Space>
        }
        description={
          <>
            {compatibility.compatibility_issues && compatibility.compatibility_issues.length > 0 && (
              <SectionMargin $top={spacing('SM')}>
                <RediaccText weight="bold">Known Issues:</RediaccText>
                <IssuesList>
                  {compatibility.compatibility_issues.map((issue: string, index: number) => (
                    <li key={index}>{issue}</li>
                  ))}
                </IssuesList>
              </SectionMargin>
            )}
            {compatibility.recommendations && compatibility.recommendations.length > 0 && (
              <SectionMargin>
                <RediaccText weight="bold">Recommendations:</RediaccText>
                <RecommendationsList>
                  {compatibility.recommendations.map((rec: string, index: number) => (
                    <li key={index}>{rec}</li>
                  ))}
                </RecommendationsList>
              </SectionMargin>
            )}
          </>
        }
        showIcon
      />

      {/* Raw JSON fallback */}
      <SectionMargin $top={spacing('MD')}>
        <Collapse
          items={[
            {
              key: 'raw',
              label: 'Raw Response Data',
              children: (
                <SimpleJsonEditor
                  value={JSON.stringify(result, null, 2)}
                  readOnly={true}
                  height="200px"
                />
              ),
            },
          ]}
        />
      </SectionMargin>
    </RediaccStack>
  );
};
