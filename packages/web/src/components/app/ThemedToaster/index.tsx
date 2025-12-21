import React, { useMemo } from 'react';
import { Toaster } from 'react-hot-toast';
const createToastOptions = () => ({
  duration: 4000,
});

export const ThemedToaster: React.FC = () => {
  const toastOptions = useMemo(() => createToastOptions(), []);

  return (
    <div data-testid="themed-toaster-container" style={{ position: 'relative', zIndex: 1000 }}>
      <Toaster position="top-center" toastOptions={toastOptions} />
    </div>
  );
};
