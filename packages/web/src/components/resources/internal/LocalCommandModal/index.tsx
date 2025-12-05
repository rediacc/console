import React, { useEffect, useState } from 'react';
import { Form, Input, Checkbox, Button, Typography, message, Radio } from 'antd';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import type { RadioChangeEvent } from 'antd/es/radio';
import {
  CopyOutlined,
  CodeOutlined,
  WindowsOutlined,
  AppleOutlined,
  DesktopOutlined,
  FileTextOutlined,
} from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { createFreshForkToken } from '@/services/forkTokenService';
import type { PluginContainer } from '@/types';
import {
  StyledModal,
  Description,
  SettingsForm,
  CheckboxHelper,
  TabsWrapper,
  CommandPreview,
  PreviewHeader,
  PreviewTitle,
  PreviewError,
  PreviewErrorText,
  PreviewHelper,
  CommandParagraph,
  PreviewMetaRow,
  PreviewMetaText,
  ActionsRow,
} from './styles';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';

const { Text } = Typography;

type CommandTab = 'vscode' | 'terminal' | 'desktop';
type OperatingSystem = 'unix' | 'windows';

interface LocalCommandModalProps {
  open: boolean;
  onClose: () => void;
  machine: string;
  repo?: string;
  userEmail: string;
  pluginContainers?: PluginContainer[];
}

export const LocalCommandModal: React.FC<LocalCommandModalProps> = ({
  open,
  onClose,
  machine,
  repo,
  pluginContainers: _pluginContainers = [],
}) => {
  const { t } = useTranslation();
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
    const encodedRepo = repo ? encodeURIComponent(repo) : '';

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
      message.error(`Token generation failed: ${errorMessage}`);
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
      message.success(t('common:copiedToClipboard'));
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
        message.warning('Copied without secure token - please login manually');
        onClose();
      } catch {
        message.error(t('common:copyFailed'));
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
    <StyledModal
      title={t('resources:localCommandBuilder.title')}
      open={open}
      onCancel={onClose}
      footer={null}
    >
      <Description>{t('resources:localCommandBuilder.description', { machine, repo })}</Description>

      <SettingsForm layout="vertical">
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
            <CheckboxHelper>{t('resources:localCommandBuilder.useDockerHelp')}</CheckboxHelper>
          </Checkbox>
        </Form.Item>

        {useDocker && (
          <Form.Item>
            <Checkbox checked={useNetworkHost} onChange={handleNetworkHostChange}>
              {t('resources:localCommandBuilder.useNetworkHost')}
              <CheckboxHelper>
                {t('resources:localCommandBuilder.useNetworkHostHelp')}
              </CheckboxHelper>
            </Checkbox>
          </Form.Item>
        )}
      </SettingsForm>

      <TabsWrapper
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
                  <Text type="secondary">
                    {t('resources:localCommandBuilder.vscodeDescription')}
                  </Text>
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
                  <Text type="secondary">
                    {t('resources:localCommandBuilder.desktopDescription')}
                  </Text>
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />

      <CommandPreview>
        <PreviewHeader>
          <PreviewTitle>{t('resources:localCommandBuilder.generatedCommand')}:</PreviewTitle>
          {isGeneratingToken && (
            <InlineLoadingIndicator
              width={64}
              height={12}
              style={{ marginLeft: 8 }}
              data-testid="local-command-token-loading"
            />
          )}
        </PreviewHeader>

        {tokenError && (
          <PreviewError>
            <PreviewErrorText>Token generation failed: {tokenError}</PreviewErrorText>
            <PreviewHelper>
              Copy will attempt without secure token. You may need to login manually.
            </PreviewHelper>
          </PreviewError>
        )}

        <CommandParagraph
          code
          copyable={{
            text: getCommand(),
            icon: <CopyOutlined />,
            onCopy: copyToClipboard,
          }}
        >
          {getCommand()}
        </CommandParagraph>

        <PreviewMetaRow>
          <PreviewMetaText>
            {t('resources:localCommandBuilder.apiUrl')}: {apiUrl}
          </PreviewMetaText>
          <PreviewMetaText>Token: Secure token will be generated on copy</PreviewMetaText>
        </PreviewMetaRow>
      </CommandPreview>

      <ActionsRow>
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
      </ActionsRow>
    </StyledModal>
  );
};
