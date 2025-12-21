import React from 'react';
import { Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/context/ThemeContext';
import { MoonOutlined, SunOutlined } from '@/utils/optimizedIcons';

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { t } = useTranslation('common');

  const switchText = theme === 'light' ? t('theme.switchToDark') : t('theme.switchToLight');

  return (
    <Button
      type="text"
      icon={theme === 'light' ? <SunOutlined /> : <MoonOutlined />}
      onClick={toggleTheme}
      aria-label={switchText}
      title={switchText}
      data-testid="theme-toggle-button"
    />
  );
};
