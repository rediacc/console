import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Button, Card, Flex, Tooltip, Typography } from 'antd';
import React from 'react';
import { BankOutlined, SettingOutlined } from '@/utils/optimizedIcons';

interface OrganizationVaultSectionProps {
  t: TypedTFunction;
  showConfigureVault: boolean;
  onConfigureVault: () => void;
}

export const OrganizationVaultSection: React.FC<OrganizationVaultSectionProps> = ({
  t,
  showConfigureVault,
  onConfigureVault,
}) => {
  return (
    <Card>
      <Flex align="flex-start" justify="space-between" className="gap-md" wrap>
        {/* eslint-disable-next-line no-restricted-syntax */}
        <Flex vertical className="gap-sm" style={{ flex: 1, minWidth: 240 }}>
          <Flex align="center">
            <BankOutlined />
            <Typography.Title level={4}>{t('organization.title')}</Typography.Title>
          </Flex>

          <Typography.Paragraph>{t('organization.description')}</Typography.Paragraph>
        </Flex>

        {showConfigureVault && (
          <Tooltip title={t('organization.configureVault')}>
            <Button
              icon={<SettingOutlined />}
              onClick={onConfigureVault}
              data-testid="system-organization-vault-button"
              aria-label={t('organization.configureVault')}
            />
          </Tooltip>
        )}
      </Flex>
    </Card>
  );
};
