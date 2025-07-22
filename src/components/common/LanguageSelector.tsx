import React from 'react';
import { Select } from 'antd';
import { GlobalOutlined } from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';

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

const LanguageSelector: React.FC = () => {
  const { i18n, t } = useTranslation();

  const handleChange = async (value: string) => {
    await i18n.changeLanguage(value);
    // Force a re-render of the entire app by updating the document direction for RTL languages
    document.documentElement.dir = value === 'ar' ? 'rtl' : 'ltr';
  };

  return (
    <Select
      value={i18n.language}
      onChange={handleChange}
      style={{ width: 140 }}
      suffixIcon={<GlobalOutlined />}
      dropdownMatchSelectWidth={false}
    >
      {languages.map((lang) => (
        <Option key={lang.code} value={lang.code}>
          <span>{lang.flag} {lang.name}</span>
        </Option>
      ))}
    </Select>
  );
};

export default LanguageSelector;