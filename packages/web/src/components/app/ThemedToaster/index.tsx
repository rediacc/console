import React, { useMemo } from 'react';
import { Flex } from 'antd';
import { Toaster } from 'react-hot-toast';
const createToastOptions = () => ({
  duration: 4000,
});

export const ThemedToaster: React.FC = () => {
  const toastOptions = useMemo(() => createToastOptions(), []);

  return (
    <Flex
      data-testid="themed-toaster-container"
      className="relative"
      // eslint-disable-next-line no-restricted-syntax
      style={{ zIndex: 1000 }}
    >
      <Toaster position="top-center" toastOptions={toastOptions} />
    </Flex>
  );
};
