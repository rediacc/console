import { theme } from 'antd';
import type { ThemeConfig } from 'antd';

const lightThemeTokens = {
  colorPrimary: '#6B7280',
  colorLink: '#6B7280',
  colorInfo: '#6B7280',
  colorBgBase: '#FFFFFF',
  colorTextBase: '#3B3B3B',
};

const darkThemeTokens = {
  colorPrimary: '#9CA3AF',
  colorLink: '#9CA3AF',
  colorInfo: '#9CA3AF',
  colorBgBase: '#1F1F1F',
  colorTextBase: '#CCCCCC',
};

export const getThemeConfig = (isDark: boolean): ThemeConfig => ({
  cssVar: true,
  algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: isDark ? darkThemeTokens : lightThemeTokens,
});
