import React from 'react';
import { ConfigProvider, App as AntApp } from 'antd';
import { useTranslation } from 'react-i18next';
import enUS from 'antd/locale/en_US';
import esES from 'antd/locale/es_ES';

const antdLocales = {
  en: enUS,
  es: esES,
};

const theme = {
  token: {
    colorPrimary: '#556b2f',
    colorSuccess: '#22c55e',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    colorInfo: '#3b82f6',
    colorTextBase: '#111827',
    colorBgBase: '#ffffff',
    borderRadius: 6,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  components: {
    Button: {
      primaryShadow: '0 2px 0 rgba(85, 107, 47, 0.1)',
    },
    Card: {
      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px 0 rgba(0, 0, 0, 0.02)',
    },
  },
};

interface AppProvidersProps {
  children: React.ReactNode;
}

export const AppProviders: React.FC<AppProvidersProps> = ({ children }) => {
  const { i18n } = useTranslation();
  const currentLocale = antdLocales[i18n.language as keyof typeof antdLocales] || enUS;

  return (
    <ConfigProvider theme={theme} locale={currentLocale}>
      <AntApp>
        {children}
      </AntApp>
    </ConfigProvider>
  );
};