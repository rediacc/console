import { Button, Dropdown, Select } from 'antd';
import React from 'react';
import dayjs from 'dayjs';
import 'dayjs/locale/es';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useUpdateUserLanguage } from '@/api/queries/users';
import type { RootState } from '@/store/store';
import { GlobalOutlined } from '@/utils/optimizedIcons';

interface Language {
  code: string;
  name: string;
  flag: string;
}

const languages: Language[] = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'zh', name: '中文', flag: '🇨🇳' },
  { code: 'ja', name: '日本語', flag: '🇯🇵' },
  { code: 'ar', name: 'العربية', flag: '🇸🇦' },
  { code: 'tr', name: 'Türkçe', flag: '🇹🇷' },
  { code: 'ru', name: 'Русский', flag: '🇷🇺' },
];

interface LanguageSelectorProps {
  iconOnly?: boolean;
}

const LanguageSelector: React.FC<LanguageSelectorProps> = ({ iconOnly = false }) => {
  const { i18n, t } = useTranslation('common');
  const updateLanguageMutation = useUpdateUserLanguage();
  const isAuthenticated = useSelector((state: RootState) => state.auth.isAuthenticated);

  const handleChange = (value: string) => {
    i18n.changeLanguage(value);
    // Force a re-render of the entire app by updating the document direction for RTL languages
    // eslint-disable-next-line react-hooks/immutability
    document.documentElement.dir = value === 'ar' ? 'rtl' : 'ltr';

    // Set dayjs locale globally
    const dayjsLocaleMap: Record<string, string> = {
      en: 'en',
      es: 'es',
    };
    dayjs.locale(dayjsLocaleMap[value] || 'en');

    // Save to backend if authenticated
    if (isAuthenticated) {
      updateLanguageMutation.mutate({ preferredLanguage: value });
    }
  };

  if (iconOnly) {
    const menuItems = languages.map((lang) => ({
      key: lang.code,
      label: (
        <span data-testid={`language-option-${lang.code}`}>
          {lang.flag} {lang.name}
        </span>
      ),
      onClick: () => handleChange(lang.code),
    }));

    return (
      <Dropdown menu={{ items: menuItems }} placement="bottomRight" trigger={['click']}>
        <Button
          icon={<GlobalOutlined />}
          aria-label={t('language.switch')}
          data-testid="language-selector-icon"
        />
      </Dropdown>
    );
  }

  return (
    <Select
      value={i18n.language}
      onChange={(value) => handleChange(value as string)}
      suffixIcon={<GlobalOutlined />}
      popupMatchSelectWidth={false}
      options={languages.map((lang) => ({
        value: lang.code,
        label: (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {lang.flag} {lang.name}
          </span>
        ),
      }))}
      data-testid="language-selector"
    />
  );
};

export default LanguageSelector;
