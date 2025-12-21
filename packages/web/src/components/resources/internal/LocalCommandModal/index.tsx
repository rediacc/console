import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Flex, Form, Input, Radio, Tabs, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { SizedModal } from '@/components/common';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import { useMessage } from '@/hooks';
import { createFreshForkToken } from '@/services/forkTokenService';
import type { PluginContainer } from '@/types';
import { ModalSize } from '@/types/modal';
import {
  AppleOutlined,
  CodeOutlined,
  CopyOutlined,
  DesktopOutlined,
  FileTextOutlined,
  WindowsOutlined,
} from '@/utils/optimizedIcons';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import type { RadioChangeEvent } from 'antd/es/radio';

type CommandTab = 'vscode' | 'terminal' | 'desktop';
type OperatingSystem = 'unix' | 'windows';

interface LocalCommandModalProps {
  open: boolean;
  onClose: () => void;
  machine: string;
  repository?: string;
  userEmail: string;
  pluginContainers?: PluginContainer[];
}

export const LocalCommandModal: React.FC<LocalCommandModalProps> = ({
  open,
  onClose,
  machine,
  repository,
  pluginContainers: _pluginContainers = [],
}) => {
  const { t } = useTranslation();
  const message = useMessage();
  const [activeTab, setActiveTab] = useState<CommandTab>('vscode');
  const [os, setOs] = useState<OperatingSystem>('unix');
  const [useDocker, setUseDocker] = useState(false);
  const [useNetworkHost, setUseNetworkHost] = useState(true);
  const [apiUrl, setApiUrl] = useState('');
  const [termCommand, setTermCommand] = useState('');
  const [isGeneratingToken, setIsGeneratingToken] = useState(false);
  const [tokenError, setTokenError] = useState('');

  useEffect(() => {
    if (open) {
      const { protocol, host } = window.location;
      setApiUrl(`${protocol}//${host}/api`);
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      setTokenError('');
    }
  }, [open]);

  const buildProtocolUrl = (token: string, action: string, params?: Record<string, string>) => {
    const team = 'Default';
    const encodedToken = encodeURIComponent(token);
    const encodedTeam = encodeURIComponent(team);
    const encodedMachine = encodeURIComponent(machine);
    const encodedRepo = repository ? encodeURIComponent(repository) : '';

    let path = `rediacc://${encodedToken}/${encodedTeam}/${encodedMachine}`;
    if (encodedRepo) {
      path += `/${encodedRepo}`;
    }
    path += `/${action}`;

    const queryParams = new URLSearchParams();
    queryParams.append('apiUrl', apiUrl);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value) {
          queryParams.append(key, value);
        }
      });
    }

    return `${path}?${queryParams.toString()}`;
  };

  const generateForkTokenForCopy = async (action: string): Promise<string> => {
    setIsGeneratingToken(true);
    setTokenError('');

    try {
      return await createFreshForkToken(action);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to generate token';
      setTokenError(errorMessage);
      console.error('Failed to generate fork token:', error);
      message.error('common:tokenGenerationFailed', { error: errorMessage });
      throw error;
    } finally {
      setIsGeneratingToken(false);
    }
  };

  const buildCommandPrefix = () => {
    const networkFlag = useDocker && useNetworkHost ? ' --network=host' : '';
    if (useDocker) {
      return `docker run -it --rm${networkFlag} -e SYSTEM_API_URL="${apiUrl}" rediacc/cli`;
    }
    return os === 'windows' ? 'rediacc.bat' : 'rediacc';
  };

  const buildTermCommand = (token: string = '<SECURE_TOKEN>') => {
    const params: Record<string, string> = {};
    if (termCommand) {
      params.command = termCommand;
    }
    const protocolUrl = buildProtocolUrl(token, 'terminal', params);
    return `${buildCommandPrefix()} protocol run "${protocolUrl}"`;
  };

  const buildDesktopCommand = (token: string = '<SECURE_TOKEN>') => {
    const protocolUrl = buildProtocolUrl(token, 'desktop');
    return `${buildCommandPrefix()} protocol run "${protocolUrl}"`;
  };

  const buildVSCodeCommand = (token: string = '<SECURE_TOKEN>') => {
    const protocolUrl = buildProtocolUrl(token, 'vscode');
    return `${buildCommandPrefix()} protocol run "${protocolUrl}"`;
  };

  const buildTermCommandWithoutToken = () => buildTermCommand('MISSING_TOKEN');
  const buildDesktopCommandWithoutToken = () => buildDesktopCommand('MISSING_TOKEN');
  const buildVSCodeCommandWithoutToken = () => buildVSCodeCommand('MISSING_TOKEN');

  const copyToClipboard = async () => {
    try {
      setIsGeneratingToken(true);
      const token = await generateForkTokenForCopy(activeTab);

      const commandWithToken =
        activeTab === 'desktop'
          ? buildDesktopCommand(token)
          : activeTab === 'vscode'
            ? buildVSCodeCommand(token)
            : buildTermCommand(token);

      await navigator.clipboard.writeText(commandWithToken);
      message.success('common:copiedToClipboard');
      onClose();
    } catch {
      try {
        const fallbackCommand =
          activeTab === 'desktop'
            ? buildDesktopCommandWithoutToken()
            : activeTab === 'vscode'
              ? buildVSCodeCommandWithoutToken()
              : buildTermCommandWithoutToken();

        await navigator.clipboard.writeText(fallbackCommand);
        message.warning('common:copiedWithoutToken');
        onClose();
      } catch {
        message.error('common:copyFailed');
      }
    } finally {
      setIsGeneratingToken(false);
    }
  };

  const getCommand = () => {
    switch (activeTab) {
      case 'terminal':
        return buildTermCommand();
      case 'desktop':
        return buildDesktopCommand();
      case 'vscode':
      default:
        return buildVSCodeCommand();
    }
  };

  const handleOsChange = (event: RadioChangeEvent) => {
    setOs(event.target.value as OperatingSystem);
  };

  const handleDockerChange = (event: CheckboxChangeEvent) => {
    setUseDocker(event.target.checked);
  };

  const handleNetworkHostChange = (event: CheckboxChangeEvent) => {
    setUseNetworkHost(event.target.checked);
  };

  const handleTermCommandChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setTermCommand(event.target.value);
  };

  return (
    <SizedModal
      title={t('resources:localCommandBuilder.title')}
      className="local-command-modal"
      size={ModalSize.Large}
      open={open}
      onCancel={onClose}
      footer={null}
    >
      <Typography.Text style={{ display: 'block' }}>
        {t('resources:localCommandBuilder.description', { machine, repository })}
      </Typography.Text>

      <Form layout="vertical">
        <Form.Item label={t('resources:localCommandBuilder.operatingSystem')}>
          <Radio.Group value={os} onChange={handleOsChange}>
            <Radio.Button value="unix">
              <AppleOutlined /> {t('resources:localCommandBuilder.unixLinuxMac')}
            </Radio.Button>
            <Radio.Button value="windows">
              <WindowsOutlined /> {t('resources:localCommandBuilder.windows')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        <Form.Item>
          <Checkbox checked={useDocker} onChange={handleDockerChange}>
            {t('resources:localCommandBuilder.useDocker')}
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:localCommandBuilder.useDockerHelp')}
            </Typography.Text>
          </Checkbox>
        </Form.Item>

        {useDocker && (
          <Form.Item>
            <Checkbox checked={useNetworkHost} onChange={handleNetworkHostChange}>
              {t('resources:localCommandBuilder.useNetworkHost')}
              <Typography.Text style={{ fontSize: 12 }}>
                {t('resources:localCommandBuilder.useNetworkHostHelp')}
              </Typography.Text>
            </Checkbox>
          </Form.Item>
        )}
      </Form>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as CommandTab)}
        items={[
          {
            key: 'vscode',
            label: t('resources:localCommandBuilder.vscodeTab'),
            icon: <FileTextOutlined />,
            children: (
              <Form layout="vertical">
                <Form.Item help={t('resources:localCommandBuilder.vscodeHelp')}>
                  <Typography.Text>
                    {t('resources:localCommandBuilder.vscodeDescription')}
                  </Typography.Text>
                </Form.Item>
              </Form>
            ),
          },
          {
            key: 'terminal',
            label: t('resources:localCommandBuilder.terminalTab'),
            icon: <CodeOutlined />,
            children: (
              <Form layout="vertical">
                <Form.Item
                  label={t('resources:localCommandBuilder.command')}
                  help={t('resources:localCommandBuilder.commandHelp')}
                >
                  <Input
                    placeholder="docker ps"
                    value={termCommand}
                    onChange={handleTermCommandChange}
                    autoComplete="off"
                  />
                </Form.Item>
              </Form>
            ),
          },
          {
            key: 'desktop',
            label: t('resources:localCommandBuilder.desktopTab'),
            icon: <DesktopOutlined />,
            children: (
              <Form layout="vertical">
                <Form.Item help={t('resources:localCommandBuilder.desktopHelp')}>
                  <Typography.Text>
                    {t('resources:localCommandBuilder.desktopDescription')}
                  </Typography.Text>
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />

      <Flex vertical gap={12} style={{ width: '100%' }}>
        <Flex align="center" justify="space-between" wrap>
          <Typography.Text strong>
            {t('resources:localCommandBuilder.generatedCommand')}:
          </Typography.Text>
          {isGeneratingToken && (
            <Typography.Text>
              <InlineLoadingIndicator
                width={64}
                height={12}
                data-testid="local-command-token-loading"
              />
            </Typography.Text>
          )}
        </Flex>

        {tokenError && (
          <Flex vertical gap={4}>
            <Typography.Text color="danger" type="danger">
              Token generation failed: {tokenError}
            </Typography.Text>
            <Typography.Text style={{ fontSize: 12 }}>
              Copy will attempt without secure token. You may need to login manually.
            </Typography.Text>
          </Flex>
        )}

        <Typography.Paragraph
          code
          copyable={{
            text: getCommand(),
            onCopy: copyToClipboard,
          }}
          style={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', marginBottom: 0 }}
        >
          {getCommand()}
        </Typography.Paragraph>

        <Flex justify="space-between" wrap>
          <Typography.Text style={{ fontSize: 12 }}>
            {t('resources:localCommandBuilder.apiUrl')}: {apiUrl}
          </Typography.Text>
          <Typography.Text style={{ fontSize: 12 }}>
            Token: Secure token will be generated on copy
          </Typography.Text>
        </Flex>
      </Flex>

      <Flex align="center" wrap gap={8}>
        <Button onClick={onClose}>{t('common:close')}</Button>
        <Button
          type="primary"
          icon={<CopyOutlined />}
          onClick={copyToClipboard}
          disabled={isGeneratingToken}
          loading={isGeneratingToken}
        >
          {t('resources:localCommandBuilder.copyCommand')}
        </Button>
      </Flex>
    </SizedModal>
  );
};
