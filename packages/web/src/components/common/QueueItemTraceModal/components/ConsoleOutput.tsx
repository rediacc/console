import React from 'react';
import { Empty } from 'antd';
import type { ConsoleOutputProps } from '../types';

export const ConsoleOutput: React.FC<ConsoleOutputProps> = ({
  content,
  consoleOutputRef,
  isEmpty,
}) => {
  if (isEmpty || !content) {
    return <Empty description="No console output available" />;
  }

  return (
    <div ref={consoleOutputRef} data-testid="queue-trace-console-output">
      {content}
    </div>
  );
};
