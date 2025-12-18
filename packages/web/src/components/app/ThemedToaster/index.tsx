import React, { useMemo } from 'react';
import { Toaster } from 'react-hot-toast';
import { createToastOptions, ToasterContainer } from './styles';

export const ThemedToaster: React.FC = () => {
  const toastOptions = useMemo(() => createToastOptions(), []);

  return (
    <ToasterContainer data-testid="themed-toaster-container">
      <Toaster position="top-center" toastOptions={toastOptions} />
    </ToasterContainer>
  );
};
