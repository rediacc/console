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
      className="m-0 max-h-[300px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-[#1e1e1e] p-3 font-mono text-[13px] text-[#d4d4d4]"
      data-testid="queue-trace-console-output"
    >
      {formattedContent}
    </Flex>
  );
};
