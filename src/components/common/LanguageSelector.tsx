import React from 'react';
import { Select, Button, Dropdown } from 'antd';
import { GlobalOutlined } from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import 'dayjs/locale/es';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { useComponentStyles } from '@/hooks/useComponentStyles';
const { Option } = Select;

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
  const styles = useComponentStyles();

  const handleChange = (value: string) => {
    i18n.changeLanguage(value);
    // Force a re-render of the entire app by updating the document direction for RTL languages
    document.documentElement.dir = value === 'ar' ? 'rtl' : 'ltr';

    // Set dayjs locale globally
    const dayjsLocaleMap: Record<string, string> = {
      en: 'en',
      es: 'es'
    };
    dayjs.locale(dayjsLocaleMap[value] || 'en');
  };

  const currentLanguage = languages.find(lang => lang.code === i18n.language) || languages[0];

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
      <Dropdown
        menu={{ items: menuItems }}
        placement="bottomRight"
        trigger={['click']}
      >
        <Button
          type="text"
          icon={<GlobalOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />}
          aria-label={t('language.switch')}
          title={`${currentLanguage.flag} ${currentLanguage.name}`}
          data-testid="language-selector-icon"
          style={{
            ...styles.touchTarget,
            borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG,
            transition: DESIGN_TOKENS.TRANSITIONS.BUTTON,
            color: 'var(--color-text-primary)',
          } as React.CSSProperties}
        />
      </Dropdown>
    );
  }

  return (
    <Select
      value={i18n.language}
      onChange={handleChange}
      suffixIcon={<GlobalOutlined />}
      popupMatchSelectWidth={false}
      style={{ width: 140 }}
      data-testid="language-selector"
    >
      {languages.map((lang) => (
        <Option key={lang.code} value={lang.code} data-testid={`language-option-${lang.code}`}>
          <span>{lang.flag} {lang.name}</span>
        </Option>
      ))}
    </Select>
  );
};

export default LanguageSelector;