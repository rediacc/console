import React from 'react';
import { Empty } from 'antd';
import { ConsoleOutputContainer } from '../styles';
import type { ConsoleOutputProps } from '../types';

export const ConsoleOutput: React.FC<ConsoleOutputProps> = ({
  content,
  theme,
  consoleOutputRef,
  isEmpty,
}) => {
  if (isEmpty || !content) {
    return <Empty description="No console output available" />;
  }

  return (
    <ConsoleOutputContainer
      ref={consoleOutputRef}
      data-testid="queue-trace-console-output"
      $theme={theme}
    >
      {content}
    </ConsoleOutputContainer>
  );
};
