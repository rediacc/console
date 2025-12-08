import React from 'react';
import { Collapse, Descriptions, Empty, Space, Tabs } from 'antd';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import { RediaccAlert, RediaccCard, RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { spacing } from '@/utils/styleConstants';
import type { QueueVaultSnapshot } from '@rediacc/shared/types';
import { InfoList, SectionMargin } from '../styles';
import type { ResponseViewerProps } from '../types';

export const ResponseViewer: React.FC<ResponseViewerProps> = ({ responseVaultContent }) => {
  const renderRequestVault = (vaultContent: QueueVaultSnapshot | null) => {
    if (!vaultContent || !vaultContent.hasContent) {
      return <Empty description="No request vault content" />;
    }

    try {
      const content =
        typeof vaultContent.vaultContent === 'string'
          ? JSON.parse(vaultContent.vaultContent)
          : vaultContent.vaultContent || {};
      return (
        <SimpleJsonEditor value={JSON.stringify(content, null, 2)} readOnly={true} height="300px" />
      );
    } catch {
      return <Empty description="Invalid request vault content format" />;
    }
  };

  const renderResponseVault = (responseVaultContent: QueueVaultSnapshot | null) => {
    if (!responseVaultContent || !responseVaultContent.hasContent) {
      return null;
    }

    try {
      const content =
        typeof responseVaultContent.vaultContent === 'string'
          ? JSON.parse(responseVaultContent.vaultContent)
          : responseVaultContent.vaultContent || {};

      // Check if this is an SSH test result with kernel compatibility data
      if (content.result && typeof content.result === 'string') {
        try {
          const result = JSON.parse(content.result);
          if (result.status === 'success' && result.kernel_compatibility) {
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
                icon: <QuestionCircleOutlined />,
                color: 'var(--color-info)',
              },
            };

            const config =
              statusConfig[status as keyof typeof statusConfig] || statusConfig.unknown;

            return (
              <RediaccStack variant="column" fullWidth>
                {/* SSH Test Result Summary */}
                <RediaccCard
                  size="sm"
                  spacing="default"
                  style={{ marginBottom: '16px' }}
                  title="SSH Test Result"
                >
                  <Descriptions column={2} size="small">
                    <Descriptions.Item label="Status">
                      <RediaccTag variant="success">{result.status}</RediaccTag>
                    </Descriptions.Item>
                    <Descriptions.Item label="Machine">{result.machine || 'N/A'}</Descriptions.Item>
                    <Descriptions.Item label="IP Address">{result.ip}</Descriptions.Item>
                    <Descriptions.Item label="User">{result.user}</Descriptions.Item>
                    <Descriptions.Item label="Auth Method">
                      <RediaccTag variant="default">{result.auth_method}</RediaccTag>
                    </Descriptions.Item>
                    <Descriptions.Item label="SSH Key">
                      {result.ssh_key_configured ? (
                        <RediaccTag variant="success">Configured</RediaccTag>
                      ) : (
                        <RediaccTag variant="warning">Not Configured</RediaccTag>
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                </RediaccCard>

                {/* System Information */}
                <RediaccCard
                  size="sm"
                  spacing="default"
                  style={{ marginBottom: '16px' }}
                  title="System Information"
                >
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="Operating System">
                      {osInfo.pretty_name || 'Unknown'}
                    </Descriptions.Item>
                    <Descriptions.Item label="Kernel Version">
                      <RediaccText code>{compatibility.kernel_version || 'Unknown'}</RediaccText>
                    </Descriptions.Item>
                    <Descriptions.Item label="OS ID">{osInfo.id || 'Unknown'}</Descriptions.Item>
                    <Descriptions.Item label="Version">
                      {osInfo.version_id || 'Unknown'}
                    </Descriptions.Item>
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
                        } else if (sudoStatus === 'password_required') {
                          return <RediaccTag variant="warning">Password Required</RediaccTag>;
                        } else if (sudoStatus === 'not_installed') {
                          return <RediaccTag variant="error">Not Installed</RediaccTag>;
                        } else {
                          return <RediaccTag variant="default">Unknown</RediaccTag>;
                        }
                      })()}
                    </Descriptions.Item>
                  </Descriptions>
                </RediaccCard>

                {/* Compatibility Status */}
                <RediaccAlert
                  data-testid="queue-trace-ssh-compatibility-alert"
                  variant={config.type}
                  icon={config.icon}
                  message={
                    <Space>
                      <RediaccText weight="bold">Compatibility Status:</RediaccText>
                      <RediaccText
                        style={{
                          color: config.color,
                          textTransform: 'capitalize',
                        }}
                      >
                        {status}
                      </RediaccText>
                    </Space>
                  }
                  description={
                    <>
                      {compatibility.compatibility_issues &&
                        compatibility.compatibility_issues.length > 0 && (
                          <SectionMargin $top={spacing('SM')}>
                            <RediaccText weight="bold">Known Issues:</RediaccText>
                            <InfoList $top={spacing('XS')} $bottom={spacing('SM')}>
                              {compatibility.compatibility_issues.map(
                                (issue: string, index: number) => (
                                  <li key={index}>{issue}</li>
                                )
                              )}
                            </InfoList>
                          </SectionMargin>
                        )}
                      {compatibility.recommendations &&
                        compatibility.recommendations.length > 0 && (
                          <SectionMargin>
                            <RediaccText weight="bold">Recommendations:</RediaccText>
                            <InfoList $top={spacing('XS')}>
                              {compatibility.recommendations.map((rec: string, index: number) => (
                                <li key={index}>{rec}</li>
                              ))}
                            </InfoList>
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
          }
        } catch {
          // Fall through to default JSON display
        }
      }

      // Default JSON display for non-SSH test results
      return (
        <SimpleJsonEditor value={JSON.stringify(content, null, 2)} readOnly={true} height="300px" />
      );
    } catch {
      return <Empty description="Invalid response vault content format" />;
    }
  };

  return (
    <Tabs
      data-testid="queue-trace-vault-tabs"
      items={[
        {
          key: 'request',
          label: (
            <Space>
              <FileTextOutlined />
              Request Vault
            </Space>
          ),
          children: renderRequestVault(responseVaultContent),
        },
        ...(responseVaultContent && responseVaultContent.hasContent
          ? [
              {
                key: 'response',
                label: (
                  <Space>
                    <FileTextOutlined />
                    Response Vault
                  </Space>
                ),
                children: renderResponseVault(responseVaultContent),
              },
            ]
          : []),
      ]}
    />
  );
};
