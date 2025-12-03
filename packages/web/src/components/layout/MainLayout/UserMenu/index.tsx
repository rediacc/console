import React from 'react'
import { Space } from 'antd'
import {
  UserOutlined,
  LogoutOutlined,
  SmileOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import LanguageSelector from '@/components/common/LanguageSelector'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import type { CompanyDashboardData } from '@rediacc/shared/types'
import {
  MenuContainer,
  UserInfo,
  UserDetails,
  UserEmail,
  CompanyName,
  PlanBadge,
  MenuDivider,
  SectionLabel,
  ModeSegmented,
  AppearanceRow,
  SectionTitle,
  SectionDescription,
  LanguageSection,
  LanguageTitle,
  LogoutButton,
  UserAvatar,
} from './styles'

type UserMenuProps = {
  user: { email: string } | null
  company: string | null
  companyData?: Pick<CompanyDashboardData, 'companyInfo' | 'activeSubscription'>
  uiMode: 'simple' | 'expert'
  onModeToggle: () => void
  onLogout: () => void
}

export const UserMenu: React.FC<UserMenuProps> = ({
  user,
  company,
  companyData,
  uiMode,
  onModeToggle,
  onLogout,
}) => {
  const { t } = useTranslation('common')

  return (
    <MenuContainer>
      <UserInfo>
        <UserAvatar icon={<UserOutlined />} size={DESIGN_TOKENS.DIMENSIONS.ICON_XXL} />
        <UserDetails>
          <UserEmail strong>{user?.email}</UserEmail>
          {company && <CompanyName>{company}</CompanyName>}
          {companyData?.activeSubscription && (
            <PlanBadge count={companyData.activeSubscription.planCode ?? 'UNKNOWN'} />
          )}
        </UserDetails>
      </UserInfo>

      <MenuDivider />

      <div>
        <SectionLabel>{t('uiMode.label', { defaultValue: 'Interface Mode' })}</SectionLabel>
        <ModeSegmented
          block
          value={uiMode}
          onChange={(value) => {
            if (value !== uiMode) {
              onModeToggle()
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

      <MenuDivider />

      <AppearanceRow>
        <div>
          <SectionTitle strong>{t('appearance.label', { defaultValue: 'Appearance' })}</SectionTitle>
          <SectionDescription>
            {t('appearance.description', { defaultValue: 'Device theme' })}
          </SectionDescription>
        </div>
        <ThemeToggle />
      </AppearanceRow>

      <MenuDivider />

      <LanguageSection>
        <LanguageTitle strong>{t('language.label', { defaultValue: 'Language' })}</LanguageTitle>
        <LanguageSelector iconOnly={false} />
      </LanguageSection>

      <MenuDivider />

      <LogoutButton
        type="text"
        icon={<LogoutOutlined />}
        onClick={onLogout}
        data-testid="main-logout-button"
      >
        {t('navigation.logout')}
      </LogoutButton>
    </MenuContainer>
  )
}
