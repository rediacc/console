import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import LanguageSelector from '@/components/common/LanguageSelector';
import { ThemeToggle } from '@/components/common/ThemeToggle';
import { RediaccDivider, RediaccText } from '@/components/ui';
import {
  LogoutOutlined,
  SafetyCertificateOutlined,
  SmileOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import type { CompanyDashboardData } from '@rediacc/shared/types';
import {
  AppearanceRow,
  LanguageSection,
  LogoutButton,
  MenuContainer,
  ModeSegmented,
  PlanBadge,
  UserAvatar,
  UserDetails,
  UserInfo,
} from './styles';

type UserMenuProps = {
  user: { email: string } | null;
  company: string | null;
  companyData?: Pick<CompanyDashboardData, 'companyInfo' | 'activeSubscription'>;
  uiMode: 'simple' | 'expert';
  onModeToggle: () => void;
  onLogout: () => void;
};

export const UserMenu: React.FC<UserMenuProps> = ({
  user,
  company,
  companyData,
  uiMode,
  onModeToggle,
  onLogout,
}) => {
  const { t } = useTranslation('common');

  return (
    <MenuContainer>
      <UserInfo>
        <UserAvatar icon={<UserOutlined />} size={DESIGN_TOKENS.DIMENSIONS.ICON_XXL} />
        <UserDetails>
          <RediaccText variant="value" weight="semibold" style={{ display: 'block' }}>
            {user?.email}
          </RediaccText>
          {company && (
            <RediaccText variant="caption" style={{ display: 'block' }}>
              {company}
            </RediaccText>
          )}
          {companyData?.activeSubscription && (
            <PlanBadge>{companyData.activeSubscription.planCode ?? 'UNKNOWN'}</PlanBadge>
          )}
        </UserDetails>
      </UserInfo>

      <RediaccDivider spacing="none" />

      <div>
        <RediaccText variant="label">
          {t('uiMode.label', { defaultValue: 'Interface Mode' })}
        </RediaccText>
        <ModeSegmented
          block
          value={uiMode}
          onChange={(value) => {
            if (value !== uiMode) {
              onModeToggle();
            }
          }}
          options={[
            {
              label: (
                <Space size={4}>
                  <SmileOutlined />
                  <span>{t('uiMode.simple')}</span>
                </Space>
              ),
              value: 'simple',
            },
            {
              label: (
                <Space size={4}>
                  <SafetyCertificateOutlined />
                  <span>{t('uiMode.expert')}</span>
                </Space>
              ),
              value: 'expert',
            },
          ]}
          data-testid="main-mode-toggle"
        />
      </div>

      <RediaccDivider spacing="none" />

      <AppearanceRow>
        <div>
          <RediaccText variant="value" weight="semibold" style={{ display: 'block' }}>
            {t('appearance.label', { defaultValue: 'Appearance' })}
          </RediaccText>
          <RediaccText variant="caption">
            {t('appearance.description', { defaultValue: 'Device theme' })}
          </RediaccText>
        </div>
        <ThemeToggle />
      </AppearanceRow>

      <RediaccDivider spacing="none" />

      <LanguageSection>
        <RediaccText
          variant="value"
          weight="semibold"
          style={{ display: 'block', marginBottom: '8px' }}
        >
          {t('language.label', { defaultValue: 'Language' })}
        </RediaccText>
        <LanguageSelector iconOnly={false} />
      </LanguageSection>

      <RediaccDivider spacing="none" />

      <LogoutButton
        variant="danger"
        icon={<LogoutOutlined />}
        onClick={onLogout}
        data-testid="main-logout-button"
      >
        {t('navigation.logout')}
      </LogoutButton>
    </MenuContainer>
  );
};
