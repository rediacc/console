import React, { useEffect, useState } from 'react';
import { Form, Input, Button, message } from 'antd';
import { useTranslation } from 'react-i18next';
import InlineLoadingIndicator from '@/components/common/InlineLoadingIndicator';
import {
  RediaccCheckbox,
  RediaccRadio,
  type CheckboxChangeEvent,
  type RadioChangeEvent,
  RediaccText,
} from '@/components/ui';
import { createFreshForkToken } from '@/services/forkTokenService';
import type { PluginContainer } from '@/types';
import {
  CopyOutlined,
  CodeOutlined,
  WindowsOutlined,
  AppleOutlined,
  DesktopOutlined,
  FileTextOutlined,
} from '@/utils/optimizedIcons';
import {
  StyledModal,
  SettingsForm,
  TabsWrapper,
  CommandPreview,
  PreviewHeader,
  PreviewError,
  CommandParagraph,
  PreviewMetaRow,
  ActionsRow,
} from './styles';

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
      <RediaccText variant="description" style={{ display: 'block' }}>
        {t('resources:localCommandBuilder.description', { machine, repo })}
      </RediaccText>

      <SettingsForm layout="vertical">
        <Form.Item label={t('resources:localCommandBuilder.operatingSystem')}>
          <RediaccRadio.Group value={os} onChange={handleOsChange}>
            <RediaccRadio.Button value="unix">
              <AppleOutlined /> {t('resources:localCommandBuilder.unixLinuxMac')}
            </RediaccRadio.Button>
            <RediaccRadio.Button value="windows">
              <WindowsOutlined /> {t('resources:localCommandBuilder.windows')}
            </RediaccRadio.Button>
          </RediaccRadio.Group>
        </Form.Item>

        <Form.Item>
          <RediaccCheckbox checked={useDocker} onChange={handleDockerChange}>
            {t('resources:localCommandBuilder.useDocker')}
            <RediaccText variant="helper" style={{ marginLeft: 8 }}>
              {t('resources:localCommandBuilder.useDockerHelp')}
            </RediaccText>
          </RediaccCheckbox>
        </Form.Item>

        {useDocker && (
          <Form.Item>
            <RediaccCheckbox checked={useNetworkHost} onChange={handleNetworkHostChange}>
              {t('resources:localCommandBuilder.useNetworkHost')}
              <RediaccText variant="helper" style={{ marginLeft: 8 }}>
                {t('resources:localCommandBuilder.useNetworkHostHelp')}
              </RediaccText>
            </RediaccCheckbox>
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
                  <RediaccText color="secondary">
                    {t('resources:localCommandBuilder.vscodeDescription')}
                  </RediaccText>
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
                  <RediaccText color="secondary">
                    {t('resources:localCommandBuilder.desktopDescription')}
                  </RediaccText>
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />

      <CommandPreview>
        <PreviewHeader>
          <RediaccText weight="semibold">
            {t('resources:localCommandBuilder.generatedCommand')}:
          </RediaccText>
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
            <RediaccText color="danger">Token generation failed: {tokenError}</RediaccText>
            <RediaccText variant="helper">
              Copy will attempt without secure token. You may need to login manually.
            </RediaccText>
          </PreviewError>
        )}

        <CommandParagraph
          code
          copyable={{
            text: getCommand(),
            onCopy: copyToClipboard,
          }}
        >
          {getCommand()}
        </CommandParagraph>

        <PreviewMetaRow>
          <RediaccText variant="caption">
            {t('resources:localCommandBuilder.apiUrl')}: {apiUrl}
          </RediaccText>
          <RediaccText variant="caption">Token: Secure token will be generated on copy</RediaccText>
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
