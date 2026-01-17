import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Flex, Form, Input, Radio, Tabs, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import { SizedModal } from '@/components/common/SizedModal';
import { useMessage } from '@/hooks';
import { createFreshForkToken } from '@/services/auth';
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

type CommandTab = 'vscode' | 'terminal' | 'file-manager';
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

  const buildTermCommand = (token = '<SECURE_TOKEN>') => {
    const params: Record<string, string> = {};
    if (termCommand) {
      params.command = termCommand;
    }
    const protocolUrl = buildProtocolUrl(token, 'terminal', params);
    return `${buildCommandPrefix()} protocol run "${protocolUrl}"`;
  };

  const buildFileManagerCommand = (token = '<SECURE_TOKEN>') => {
    const protocolUrl = buildProtocolUrl(token, 'file-manager');
    return `${buildCommandPrefix()} protocol run "${protocolUrl}"`;
  };

  const buildVSCodeCommand = (token = '<SECURE_TOKEN>') => {
    const protocolUrl = buildProtocolUrl(token, 'vscode');
    return `${buildCommandPrefix()} protocol run "${protocolUrl}"`;
  };

  const buildTermCommandWithoutToken = () => buildTermCommand('MISSING_TOKEN');
  const buildFileManagerCommandWithoutToken = () => buildFileManagerCommand('MISSING_TOKEN');
  const buildVSCodeCommandWithoutToken = () => buildVSCodeCommand('MISSING_TOKEN');

  const copyToClipboard = async () => {
    try {
      setIsGeneratingToken(true);
      const token = await generateForkTokenForCopy(activeTab);

      let commandWithToken: string;
      if (activeTab === 'file-manager') {
        commandWithToken = buildFileManagerCommand(token);
      } else if (activeTab === 'vscode') {
        commandWithToken = buildVSCodeCommand(token);
      } else {
        commandWithToken = buildTermCommand(token);
      }

      await navigator.clipboard.writeText(commandWithToken);
      message.success('common:copiedToClipboard');
      onClose();
    } catch {
      try {
        let fallbackCommand: string;
        if (activeTab === 'file-manager') {
          fallbackCommand = buildFileManagerCommandWithoutToken();
        } else if (activeTab === 'vscode') {
          fallbackCommand = buildVSCodeCommandWithoutToken();
        } else {
          fallbackCommand = buildTermCommandWithoutToken();
        }

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
      case 'file-manager':
        return buildFileManagerCommand();
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
      <Typography.Text className="block">
        {t('resources:localCommandBuilder.description', { machine, repository })}
      </Typography.Text>

      <Form layout="vertical">
        <Form.Item label={t('resources:localCommandBuilder.operatingSystem')}>
          <Radio.Group value={os} onChange={handleOsChange} data-testid="local-command-os-select">
            <Radio.Button value="unix" data-testid="local-command-os-unix">
              <AppleOutlined /> {t('resources:localCommandBuilder.unixLinuxMac')}
            </Radio.Button>
            <Radio.Button value="windows" data-testid="local-command-os-windows">
              <WindowsOutlined /> {t('resources:localCommandBuilder.windows')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        <Form.Item>
          <Checkbox
            checked={useDocker}
            onChange={handleDockerChange}
            data-testid="local-command-docker-checkbox"
          >
            {t('resources:localCommandBuilder.useDocker')}
            <Typography.Text>{t('resources:localCommandBuilder.useDockerHelp')}</Typography.Text>
          </Checkbox>
        </Form.Item>

        {useDocker && (
          <Form.Item>
            <Checkbox
              checked={useNetworkHost}
              onChange={handleNetworkHostChange}
              data-testid="local-command-network-host-checkbox"
            >
              {t('resources:localCommandBuilder.useNetworkHost')}
              <Typography.Text>
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
                    placeholder={t('resources:localCommandBuilder.commandPlaceholder')}
                    value={termCommand}
                    onChange={handleTermCommandChange}
                    autoComplete="off"
                    data-testid="local-command-terminal-input"
                  />
                </Form.Item>
              </Form>
            ),
          },
          {
            key: 'file-manager',
            label: t('resources:localCommandBuilder.fileManagerTab'),
            icon: <DesktopOutlined />,
            children: (
              <Form layout="vertical">
                <Form.Item help={t('resources:localCommandBuilder.fileManagerHelp')}>
                  <Typography.Text>
                    {t('resources:localCommandBuilder.fileManagerDescription')}
                  </Typography.Text>
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />

      <Flex vertical className="w-full gap-2">
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
          <Flex vertical className="gap-2">
            <Typography.Text type="danger">
              {t('resources:localCommandBuilder.tokenGenerationFailed')}: {tokenError}
            </Typography.Text>
            <Typography.Text>
              {t('resources:localCommandBuilder.copyWithoutTokenWarning')}
            </Typography.Text>
          </Flex>
        )}

        <Typography.Paragraph
          code
          copyable={{
            text: getCommand(),
            onCopy: copyToClipboard,
          }}
          // eslint-disable-next-line no-restricted-syntax
          style={{ whiteSpace: 'pre-wrap' }}
        >
          {getCommand()}
        </Typography.Paragraph>

        <Flex justify="space-between" wrap>
          <Typography.Text>
            {t('resources:localCommandBuilder.apiUrl')}: {apiUrl}
          </Typography.Text>
          <Typography.Text>
            {t('resources:localCommandBuilder.token')}:{' '}
            {t('resources:localCommandBuilder.tokenGeneratedOnCopy')}
          </Typography.Text>
        </Flex>
      </Flex>

      <Flex align="center" wrap>
        <Button onClick={onClose} data-testid="local-command-close-button">
          {t('common:close')}
        </Button>
        <Button
          type="primary"
          icon={<CopyOutlined />}
          onClick={copyToClipboard}
          disabled={isGeneratingToken}
          loading={isGeneratingToken}
          data-testid="local-command-copy-button"
        >
          {t('resources:localCommandBuilder.copyCommand')}
        </Button>
      </Flex>
    </SizedModal>
  );
};
