import React from 'react';
import { Button } from 'antd';
import { SunOutlined, MoonOutlined } from '@/utils/optimizedIcons';
import { useTheme } from '../../context/ThemeContext';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { useTranslation } from 'react-i18next';

export const ThemeToggle: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const styles = useComponentStyles();
  const { t } = useTranslation('common');

  const switchText = theme === 'light' ? t('theme.switchToDark') : t('theme.switchToLight');

  return (
    <Button
      type="text"
      icon={theme === 'light' ?
        <SunOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} /> :
        <MoonOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
      }
      onClick={toggleTheme}
      aria-label={switchText}
      title={switchText}
      data-testid="theme-toggle-button"
      style={{
        ...styles.touchTarget,
        borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG,
        transition: DESIGN_TOKENS.TRANSITIONS.BUTTON,
        color: 'var(--color-text-primary)',
      } as React.CSSProperties}
    />
  );
};