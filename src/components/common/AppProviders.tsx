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
            colorPrimary: '#333333',
            borderRadius: 6,
            colorBgContainer: currentTheme === 'dark' ? '#1a1a1a' : '#ffffff',
            colorBgElevated: currentTheme === 'dark' ? '#2a2a2a' : '#ffffff',
            colorBgLayout: currentTheme === 'dark' ? '#0a0a0a' : '#f5f5f5',
            colorText: currentTheme === 'dark' ? '#fafafa' : '#09090b',
            colorTextSecondary: currentTheme === 'dark' ? '#a1a1aa' : '#6c757d',
            colorBorder: currentTheme === 'dark' ? '#3f3f46' : '#dee2e6',
            colorBorderSecondary: currentTheme === 'dark' ? '#27272a' : '#e9ecef',
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