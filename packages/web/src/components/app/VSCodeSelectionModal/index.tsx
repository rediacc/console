import { Button, Checkbox, Flex, Radio, Space, Typography } from 'antd';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SizedModal } from '@/components/common/SizedModal';
import type { VSCodeInstallations } from '@/types/electron';
import { ModalSize } from '@/types/modal';
import { CodeOutlined, WindowsOutlined } from '@/utils/optimizedIcons';

interface VSCodeSelectionModalProps {
  open: boolean;
  onClose: () => void;
  installations: VSCodeInstallations;
  onSelect: (preference: 'windows' | 'wsl', remember: boolean) => void;
}

export const VSCodeSelectionModal: React.FC<VSCodeSelectionModalProps> = ({
  open,
  onClose,
  installations,
  onSelect,
}) => {
  const { t } = useTranslation('common');
  const [selected, setSelected] = useState<'windows' | 'wsl'>(
    installations.wsl ? 'wsl' : 'windows'
  );
  const [remember, setRemember] = useState(false);

  const handleConfirm = () => {
    onSelect(selected, remember);
    onClose();
  };

  const getVersionText = (
    installation: VSCodeInstallations['windows'] | VSCodeInstallations['wsl']
  ) => {
    if (!installation) return '';
    if (installation.version) {
      return ` (${installation.version})`;
    }
    return '';
  };

  return (
    <SizedModal
      title={
        <Flex align="center" gap={8}>
          <CodeOutlined />
          <Typography.Title level={4} className="m-0">
            {t('vscodeSelection.title')}
          </Typography.Title>
        </Flex>
      }
      open={open}
      onCancel={onClose}
      closable
      maskClosable={false}
      centered
      size={ModalSize.Small}
      data-testid="vscode-selection-modal"
      footer={[
        <Button key="cancel" onClick={onClose} data-testid="vscode-selection-cancel">
          {t('cancel')}
        </Button>,
        <Button
          key="confirm"
          type="primary"
          onClick={handleConfirm}
          data-testid="vscode-selection-confirm"
        >
          {t('vscodeSelection.open')}
        </Button>,
      ]}
    >
      <Flex vertical gap={16}>
        <Typography.Text>{t('vscodeSelection.description')}</Typography.Text>

        <Radio.Group
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="w-full"
          data-testid="vscode-selection-group"
        >
          <Space direction="vertical" className="w-full">
            {installations.windows && (
              <Radio value="windows" data-testid="vscode-selection-windows" className="w-full">
                <Flex align="center" gap={8}>
                  <WindowsOutlined />
                  <Typography.Text>
                    {t('vscodeSelection.windowsVSCode')}
                    {getVersionText(installations.windows)}
                  </Typography.Text>
                </Flex>
              </Radio>
            )}
            {installations.wsl && (
              <Radio value="wsl" data-testid="vscode-selection-wsl" className="w-full">
                <Flex align="center" gap={8}>
                  <CodeOutlined />
                  <Typography.Text>
                    {t('vscodeSelection.wslVSCode')}
                    {getVersionText(installations.wsl)}
                    {installations.wsl.wslDistro && (
                      <Typography.Text type="secondary" className="ml-1">
                        [{installations.wsl.wslDistro}]
                      </Typography.Text>
                    )}
                  </Typography.Text>
                </Flex>
              </Radio>
            )}
          </Space>
        </Radio.Group>

        <Checkbox
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
          data-testid="vscode-selection-remember"
        >
          {t('vscodeSelection.rememberChoice')}
        </Checkbox>
      </Flex>
    </SizedModal>
  );
};
