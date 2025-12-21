import React, { useMemo, useState } from 'react';
import { Alert, Button, Checkbox, Collapse, Flex, Modal, Space, Tabs, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCopyToClipboard, useMessage } from '@/hooks';
import { InstallOptions, pipInstallationService } from '@/services/pipInstallationService';
import { ModalSize } from '@/types/modal';
import {
  AppleOutlined,
  CheckOutlined,
  CodeOutlined,
  CopyOutlined,
  DesktopOutlined,
  QuestionCircleOutlined,
  RocketOutlined,
  WindowsOutlined,
} from '@/utils/optimizedIcons';

const { Text, Title } = Typography;

interface PipInstallationModalProps {
  open: boolean;
  onClose: () => void;
  errorType?: 'not-installed' | 'protocol-not-registered' | 'permission-denied';
}

interface CommandDisplayProps {
  command: string;
  description?: string;
  showCopy?: boolean;
}

const CommandDisplay: React.FC<CommandDisplayProps> = ({
  command,
  description,
  showCopy = true,
}) => {
  const { copy, copied } = useCopyToClipboard({
    successMessage: 'common:commandCopied',
    errorMessage: 'common:commandCopyFailed',
  });

  const handleCopy = () => copy(command);

  const formattedCommands = pipInstallationService.formatCommandsForDisplay([command]);
  const { isComment } = formattedCommands[0];

  return (
    <Flex vertical data-testid="pip-install-command-display">
      {description && (
        <Flex>
          <Typography.Text type="secondary">{description}</Typography.Text>
        </Flex>
      )}
      <Flex data-testid="pip-install-command-text" align="center" justify="space-between">
        <Typography.Text style={{ fontFamily: 'monospace' }}>
          <Typography.Text type={isComment ? 'secondary' : undefined} style={{ fontSize: 12 }}>
            {command}
          </Typography.Text>
        </Typography.Text>
        {showCopy && (
          <Button
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            onClick={handleCopy}
            data-testid="pip-install-command-copy"
          />
        )}
      </Flex>
    </Flex>
  );
};

export const PipInstallationModal: React.FC<PipInstallationModalProps> = ({
  open,
  onClose,
  errorType = 'not-installed',
}) => {
  const { t } = useTranslation();
  const message = useMessage();
  const [useUserInstall, setUseUserInstall] = useState(false);
  const [activeTab, setActiveTab] = useState('quick');

  const platformInstructions = useMemo(() => pipInstallationService.getPlatformInstructions(), []);

  const installOptions: InstallOptions = {
    useUser: useUserInstall,
  };

  const installCommands = pipInstallationService.getInstallationCommands(installOptions);
  const virtualEnvInstructions = pipInstallationService.getVirtualEnvInstructions();
  const uninstallInstructions = pipInstallationService.getUninstallInstructions();

  const handleCopyAllCommands = () => {
    const allCommands = [
      installCommands.install,
      ...installCommands.postInstall.filter((cmd) => !cmd.includes('Restart')),
      ...installCommands.verify,
    ].join('\n');

    navigator.clipboard.writeText(allCommands);
    message.success('common:allCommandsCopied');
  };

  const renderPlatformIcon = () => {
    switch (platformInstructions.platform) {
      case 'windows':
        return <WindowsOutlined />;
      case 'macos':
        return <AppleOutlined />;
      default:
        return <DesktopOutlined />;
    }
  };

  const renderQuickInstall = () => (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      <Alert
        message={t('resources:pipInstall.quickInstallTitle')}
        description={t('resources:pipInstall.quickInstallDesc')}
        type="info"
        showIcon
        icon={<RocketOutlined />}
        data-testid="pip-install-quick-alert"
      />

      <Flex vertical>
        <Title level={5}>{t('resources:pipInstall.step1Install')}</Title>
        <CommandDisplay
          command={pipInstallationService.generateInstallCommand(installOptions)}
          description={t('resources:pipInstall.installCommandDesc')}
        />

        <Space>
          <Checkbox
            checked={useUserInstall}
            onChange={(e) => setUseUserInstall(e.target.checked)}
            data-testid="pip-install-user-checkbox"
          >
            {t('resources:pipInstall.userInstallOnly')}
          </Checkbox>
        </Space>
      </Flex>

      <Flex vertical>
        <Title level={5}>{t('resources:pipInstall.step2Setup')}</Title>
        <CommandDisplay
          command={pipInstallationService.generateSetupCommand()}
          description={t('resources:pipInstall.setupCommandDesc')}
        />
      </Flex>

      <Flex vertical>
        <Title level={5}>{t('resources:pipInstall.step3Verify')}</Title>
        {installCommands.verify.map((cmd, index) => (
          <CommandDisplay key={index} command={cmd} />
        ))}
      </Flex>

      <Alert
        message={
          <Space>
            {renderPlatformIcon()}
            {t('resources:pipInstall.platformSpecific', {
              platform: platformInstructions.platform,
            })}
          </Space>
        }
        description={
          <ul>
            {platformInstructions.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        }
        type="warning"
        data-testid="pip-install-platform-alert"
      />

      <Button
        type="primary"
        icon={<CopyOutlined />}
        onClick={handleCopyAllCommands}
        block
        data-testid="pip-install-copy-all-button"
      >
        {t('resources:pipInstall.copyAllCommands')}
      </Button>
    </Flex>
  );

  const renderAdvancedOptions = () => (
    <Collapse
      defaultActiveKey={[]}
      data-testid="pip-install-advanced-collapse"
      items={[
        {
          key: 'venv',
          label: t('resources:pipInstall.virtualEnvironment'),
          extra: <Tag color="green">{t('resources:pipInstall.recommended')}</Tag>,
          children: (
            <Flex vertical style={{ width: '100%' }}>
              <Text>{virtualEnvInstructions.description}</Text>
              {virtualEnvInstructions.commands.map((cmd, index) => (
                <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
              ))}
            </Flex>
          ),
        },
        {
          key: 'version',
          label: t('resources:pipInstall.specificVersion'),
          children: (
            <Flex vertical style={{ width: '100%' }}>
              <Text>{t('resources:pipInstall.versionDesc')}</Text>
              <CommandDisplay command="pip install rediacc==1.0.0" />
              <CommandDisplay command="pip install rediacc>=1.0.0,<2.0.0" />
              <CommandDisplay
                command="pip install --upgrade rediacc"
                description={t('resources:pipInstall.upgradeDesc')}
              />
            </Flex>
          ),
        },
        {
          key: 'uninstall',
          label: t('resources:pipInstall.uninstall'),
          children: (
            <Flex vertical style={{ width: '100%' }}>
              <Text>{uninstallInstructions.description}</Text>
              {uninstallInstructions.commands.map((cmd, index) => (
                <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
              ))}
            </Flex>
          ),
        },
      ]}
    />
  );

  const renderTroubleshooting = () => (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      <Alert
        message={t('resources:pipInstall.commonIssues')}
        type="info"
        showIcon
        data-testid="pip-install-issues-alert"
      />

      <Collapse
        defaultActiveKey={['pip-not-found']}
        data-testid="pip-install-troubleshooting-collapse"
        items={[
          {
            key: 'pip-not-found',
            label: t('resources:pipInstall.pipNotFound'),
            extra: <Tag color="red">{t('resources:pipInstall.error')}</Tag>,
            children: (() => {
              const troubleshooting =
                pipInstallationService.getTroubleshootingCommands('pip-not-found');
              return (
                <Flex vertical style={{ width: '100%' }}>
                  <Text>{troubleshooting.description}</Text>
                  {troubleshooting.commands.map((cmd, index) => (
                    <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
                  ))}
                </Flex>
              );
            })(),
          },
          {
            key: 'permission',
            label: t('resources:pipInstall.permissionDenied'),
            extra: <Tag color="warning">{t('resources:pipInstall.warning')}</Tag>,
            children: (() => {
              const troubleshooting =
                pipInstallationService.getTroubleshootingCommands('permission-denied');
              return (
                <Flex vertical style={{ width: '100%' }}>
                  <Text>{troubleshooting.description}</Text>
                  {troubleshooting.commands.map((cmd, index) => (
                    <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
                  ))}
                </Flex>
              );
            })(),
          },
          {
            key: 'python-version',
            label: t('resources:pipInstall.pythonVersion'),
            children: (() => {
              const troubleshooting =
                pipInstallationService.getTroubleshootingCommands('python-version');
              return (
                <Flex vertical style={{ width: '100%' }}>
                  <Text>{troubleshooting.description}</Text>
                  {troubleshooting.commands.map((cmd, index) => (
                    <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
                  ))}
                </Flex>
              );
            })(),
          },
        ]}
      />

      <Alert
        message={t('resources:pipInstall.stillNeedHelp')}
        description={
          <Flex vertical style={{ width: '100%' }}>
            <Text>
              {t('resources:pipInstall.checkDocs')}:{' '}
              <a
                href="https://www.rediacc.com/docs/cli/installation"
                target="_blank"
                rel="noopener noreferrer"
                data-testid="pip-install-docs-link"
              >
                {t('resources:pipInstall.installationGuide')}
              </a>
            </Text>
            <Text>
              {t('resources:pipInstall.reportIssue')}:{' '}
              <a
                href="https://github.com/rediacc/desktop/issues"
                target="_blank"
                rel="noopener noreferrer"
                data-testid="pip-install-github-link"
              >
                GitHub Issues
              </a>
            </Text>
          </Flex>
        }
        type="info"
        data-testid="pip-install-help-alert"
      />
    </Flex>
  );

  const getModalTitle = () => {
    switch (errorType) {
      case 'protocol-not-registered':
        return t('resources:pipInstall.protocolNotRegisteredTitle');
      case 'permission-denied':
        return t('resources:pipInstall.permissionDeniedTitle');
      default:
        return t('resources:pipInstall.installRediaccCli');
    }
  };

  return (
    <Modal
      title={
        <Space>
          <RocketOutlined />
          {getModalTitle()}
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose} data-testid="pip-install-close-button">
          {t('common:close')}
        </Button>,
      ]}
      className={ModalSize.Large}
      data-testid="pip-install-modal"
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        data-testid="pip-install-tabs"
        items={[
          {
            key: 'quick',
            label: (
              <Space>
                <RocketOutlined />
                {t('resources:pipInstall.quickInstall')}
              </Space>
            ),
            children: renderQuickInstall(),
          },
          {
            key: 'advanced',
            label: (
              <Space>
                <CodeOutlined />
                {t('resources:pipInstall.advancedOptions')}
              </Space>
            ),
            children: renderAdvancedOptions(),
          },
          {
            key: 'troubleshooting',
            label: (
              <Space>
                <QuestionCircleOutlined />
                {t('resources:pipInstall.troubleshooting')}
              </Space>
            ),
            children: renderTroubleshooting(),
          },
        ]}
      />
    </Modal>
  );
};
