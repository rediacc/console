import { theme } from 'antd';
import type { ThemeConfig } from 'antd';

// Light: bg #FFFFFF, text #3B3B3B, accent #6B7280
const lightThemeTokens = {
  colorPrimary: '#6B7280',
  colorLink: '#6B7280',
  colorInfo: '#6B7280',
  colorBgBase: '#FFFFFF',
  colorTextBase: '#3B3B3B',
};

// Dark: bg #1F1F1F, text #CCCCCC, accent #9CA3AF
const darkThemeTokens = {
  colorPrimary: '#9CA3AF',
  colorLink: '#9CA3AF',
  colorInfo: '#9CA3AF',
  colorBgBase: '#1F1F1F',
  colorTextBase: '#CCCCCC',
};

export const getThemeConfig = (isDark: boolean): ThemeConfig => ({
  algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: isDark ? darkThemeTokens : lightThemeTokens,
  components: {
    Card: {
      bodyPadding: 0,
      bodyPaddingSM: 0,
    },
  },
});
