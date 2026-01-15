import React from 'react';
import { Empty, Space, Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import { FileTextOutlined } from '@/utils/optimizedIcons';
import type { QueueVaultSnapshot } from '@rediacc/shared/types';
import { SSHTestResultsDisplay } from './SSHTestResultsDisplay';
import { parseSSHTestResults } from '../utils/sshTestResultParser';

interface ResponseVaultContentProps {
  vaultContent: QueueVaultSnapshot | null | undefined;
  responseVaultContent: QueueVaultSnapshot | null | undefined;
}

export const ResponseVaultContent: React.FC<ResponseVaultContentProps> = ({
  vaultContent,
  responseVaultContent,
}) => {
  const { t } = useTranslation('queue');

  const renderRequestVault = () => {
    if (!vaultContent?.hasContent) {
      return <Empty description={t('trace.noRequestVault')} />;
    }

    try {
      // vaultContent.vaultContent is string | null per QueueVaultSnapshot type
      const content =
        typeof vaultContent.vaultContent === 'string' ? JSON.parse(vaultContent.vaultContent) : {};
      return <SimpleJsonEditor value={JSON.stringify(content, null, 2)} readOnly height="300px" />;
    } catch {
      return <Empty description={t('trace.invalidRequestVault')} />;
    }
  };

  const renderResponseVault = () => {
    if (!responseVaultContent?.hasContent || !responseVaultContent.vaultContent) {
      return null;
    }

    const content = responseVaultContent.vaultContent;

    // Try to parse as JSON (for SSH test results or structured responses)
    try {
      const parsed = JSON.parse(content);
      const sshTestResult = parseSSHTestResults(parsed);
      if (sshTestResult.isSSHTest && sshTestResult.result) {
        return <SSHTestResultsDisplay result={sshTestResult.result} />;
      }
      // Valid JSON - display as JSON editor
      return <SimpleJsonEditor value={JSON.stringify(parsed, null, 2)} readOnly height="300px" />;
    } catch {
      // Plain text output from bridge - display as preformatted text
      return <pre className="terminal-output">{content}</pre>;
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
              {t('trace.requestVault')}
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
                    {t('trace.responseVaultTab')}
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
