import React, { useMemo } from 'react';
import { Toaster } from 'react-hot-toast';
import { useTheme } from '@/context/ThemeContext';
import { createToastOptions, ToasterContainer } from './styles';

export const ThemedToaster: React.FC = () => {
  const { theme } = useTheme();

  const toastOptions = useMemo(() => createToastOptions(theme), [theme]);

  return (
    <ToasterContainer data-testid="themed-toaster-container">
      <Toaster position="top-center" toastOptions={toastOptions} />
    </ToasterContainer>
  );
};
