import React from 'react';
import { Empty, Space, Tabs } from 'antd';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import { FileTextOutlined } from '@/utils/optimizedIcons';
import { SSHTestResultsDisplay } from './SSHTestResultsDisplay';
import { parseSSHTestResults } from '../utils/sshTestResultParser';

interface VaultContent {
  hasContent: boolean;
  vaultContent?: string | Record<string, unknown>;
}

interface ResponseVaultContentProps {
  vaultContent: VaultContent | null | undefined;
  responseVaultContent: VaultContent | null | undefined;
}

export const ResponseVaultContent: React.FC<ResponseVaultContentProps> = ({
  vaultContent,
  responseVaultContent,
}) => {
  const renderRequestVault = () => {
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

  const renderResponseVault = () => {
    if (!responseVaultContent || !responseVaultContent.hasContent) {
      return null;
    }

    try {
      const content =
        typeof responseVaultContent.vaultContent === 'string'
          ? JSON.parse(responseVaultContent.vaultContent)
          : responseVaultContent.vaultContent || {};

      // Try to parse as SSH test result
      const sshTestResult = parseSSHTestResults(content);
      if (sshTestResult.isSSHTest && sshTestResult.result) {
        return <SSHTestResultsDisplay result={sshTestResult.result} />;
      }

      // Default JSON display
      return (
        <SimpleJsonEditor value={JSON.stringify(content, null, 2)} readOnly={true} height="300px" />
      );
    } catch {
      return <Empty description="Invalid response vault content format" />;
    }
  };

  const responseTab = renderResponseVault();

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
          children: renderRequestVault(),
        },
        ...(responseTab
          ? [
              {
                key: 'response',
                label: (
                  <Space>
                    <FileTextOutlined />
                    Response Vault
                  </Space>
                ),
                children: responseTab,
              },
            ]
          : []),
      ]}
    />
  );
};
