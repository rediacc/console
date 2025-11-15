import React from 'react';
import { SunOutlined, MoonOutlined } from '@/utils/optimizedIcons';
import { useTheme } from '@/context/ThemeContext';
import { useTranslation } from 'react-i18next';
import { ToggleButton } from './styles';

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { t } = useTranslation('common');

  const switchText = theme === 'light' ? t('theme.switchToDark') : t('theme.switchToLight');

  return (
    <ToggleButton
      type="text"
      icon={theme === 'light' ? <SunOutlined /> : <MoonOutlined />}
      onClick={toggleTheme}
      aria-label={switchText}
      title={switchText}
      data-testid="theme-toggle-button"
    />
  );
};
