import React from 'react';
import { Button, Card, Flex, Tooltip, Typography } from 'antd';
import { BankOutlined, SettingOutlined } from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface CompanyVaultSectionProps {
  t: TFunction<'settings'>;
  showConfigureVault: boolean;
  onConfigureVault: () => void;
}

export const CompanyVaultSection: React.FC<CompanyVaultSectionProps> = ({
  t,
  showConfigureVault,
  onConfigureVault,
}) => (
  <Card>
    <Flex align="flex-start" justify="space-between" gap={16} wrap>
      {/* eslint-disable-next-line no-restricted-syntax */}
      <Flex vertical gap={8} style={{ flex: 1, minWidth: 240 }}>
        <Flex align="center" gap={8}>
          <BankOutlined />
          <Typography.Title level={4}>{t('company.title')}</Typography.Title>
        </Flex>

        <Typography.Paragraph>{t('company.description')}</Typography.Paragraph>
      </Flex>

      {showConfigureVault && (
        <Tooltip title={t('company.configureVault')}>
          <Button
            icon={<SettingOutlined />}
            onClick={onConfigureVault}
            data-testid="system-company-vault-button"
            aria-label={t('company.configureVault')}
          />
        </Tooltip>
      )}
    </Flex>
  </Card>
);
