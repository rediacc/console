import React, { useMemo } from 'react';
import { Empty, Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { parseLogOutput, unescapeLogOutput } from '@rediacc/shared/utils';
import { StructuredLogView } from './StructuredLogView';
import type { ConsoleOutputProps } from '../types';

export const ConsoleOutput: React.FC<ConsoleOutputProps> = ({
  content,
  consoleOutputRef,
  isEmpty,
  viewMode,
}) => {
  const { t } = useTranslation('queue');

  const formattedContent = useMemo(() => (content ? unescapeLogOutput(content) : ''), [content]);

  const parsedLogs = useMemo(() => (content ? parseLogOutput(content) : []), [content]);

  if (isEmpty || !content) {
    return <Empty description={t('trace.noConsoleOutput')} />;
  }

  if (viewMode === 'structured') {
    return <StructuredLogView entries={parsedLogs} scrollRef={consoleOutputRef} />;
  }

  return (
    <Flex
      ref={consoleOutputRef}
      className="terminal-output"
      data-testid="queue-trace-console-output"
    >
      {formattedContent}
    </Flex>
  );
};
