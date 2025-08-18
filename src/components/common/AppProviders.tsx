import React from 'react';
import { ConfigProvider, App as AntApp, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { ThemeProvider, useTheme } from '@/context/ThemeContext';
import enUS from 'antd/locale/en_US';
import esES from 'antd/locale/es_ES';
import frFR from 'antd/locale/fr_FR';
import deDE from 'antd/locale/de_DE';
import zhCN from 'antd/locale/zh_CN';
import jaJP from 'antd/locale/ja_JP';
import arEG from 'antd/locale/ar_EG';
import trTR from 'antd/locale/tr_TR';
import ruRU from 'antd/locale/ru_RU';

const antdLocales = {
  en: enUS,
  es: esES,
  fr: frFR,
  de: deDE,
  zh: zhCN,
  ja: jaJP,
  ar: arEG,
  tr: trTR,
  ru: ruRU,
};

interface AppProvidersProps {
  children: React.ReactNode;
}

export const AppProviders: React.FC<AppProvidersProps> = ({ children }) => {
  const { i18n } = useTranslation();
  const currentLocale = antdLocales[i18n.language as keyof typeof antdLocales] || enUS;

  return (
    <ThemeProvider>
      <AppProvidersContent currentLocale={currentLocale} language={i18n.language}>
        {children}
      </AppProvidersContent>
    </ThemeProvider>
  );
};

interface AppProvidersContentProps {
  children: React.ReactNode;
  currentLocale: any;
  language: string;
}

const AppProvidersContent: React.FC<AppProvidersContentProps> = ({ children, currentLocale, language }) => {
  const { theme: currentTheme } = useTheme();

  return (
    <div data-testid="app-providers-container">
      <ConfigProvider
        key={language} // Force re-render when language changes
        locale={currentLocale}
        theme={{
          algorithm: currentTheme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            // Design system color integration
            colorPrimary: '#556b2f', // --color-primary from design system
            colorPrimaryHover: '#4c6029', // --color-primary-hover
            borderRadius: 8, // Consistent with design system border radius
            borderRadiusLG: 12,
            borderRadiusSM: 6,
            
            // Background colors from design system variables
            colorBgContainer: currentTheme === 'dark' ? '#1a1a1a' : '#ffffff', // --color-bg-secondary / --color-bg-primary
            colorBgElevated: currentTheme === 'dark' ? '#2a2a2a' : '#ffffff', // --color-bg-tertiary / --color-bg-primary
            colorBgLayout: currentTheme === 'dark' ? '#0a0a0a' : '#f8f9fa', // --color-bg-primary / --color-bg-secondary
            colorBgBase: currentTheme === 'dark' ? '#0a0a0a' : '#ffffff', // Base background
            
            // Text colors from design system
            colorText: currentTheme === 'dark' ? '#ffffff' : '#1a1a1a', // --color-text-primary
            colorTextSecondary: currentTheme === 'dark' ? '#e5e7eb' : '#3d4852', // --color-text-secondary
            colorTextTertiary: currentTheme === 'dark' ? '#d1d5db' : '#5a6570', // --color-text-tertiary
            colorTextQuaternary: currentTheme === 'dark' ? '#9ca3af' : '#9ca3af', // --color-text-muted
            
            // Border colors from design system
            colorBorder: currentTheme === 'dark' ? '#27272a' : '#dee2e6', // --color-border-primary
            colorBorderSecondary: currentTheme === 'dark' ? '#3f3f46' : '#e9ecef', // --color-border-secondary
            
            // Spacing from design system
            marginXS: 4, // --space-xs
            marginSM: 8, // --space-sm
            margin: 16, // --space-md
            marginLG: 24, // --space-lg
            marginXL: 32, // --space-xl
            
            // Component specific design system integration
            boxShadow: currentTheme === 'dark' 
              ? '0 1px 2px 0 rgba(0, 0, 0, 0.3)' 
              : '0 1px 2px 0 rgba(0, 0, 0, 0.1)', // --shadow-sm
            boxShadowSecondary: currentTheme === 'dark'
              ? '0 4px 6px -1px rgba(0, 0, 0, 0.3)'
              : '0 4px 6px -1px rgba(0, 0, 0, 0.1)', // --shadow-md
              
            // Focus states
            colorPrimaryBg: 'rgba(85, 107, 47, 0.1)', // --color-primary-bg
          },
        }}
      >
        <AntApp>
          {children}
        </AntApp>
      </ConfigProvider>
    </div>
  );
};