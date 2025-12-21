import React, { useCallback, useEffect, useState } from 'react';
import { Flex, Typography } from 'antd';

interface SimpleJsonEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string | number;
  className?: string;
  language?: string;
  'data-testid'?: string;
  onFormatReady?: (formatFn: () => void) => void;
}

export const SimpleJsonEditor: React.FC<SimpleJsonEditorProps> = ({
  value,
  onChange,
  readOnly = false,
  height = '400px',
  className = '',
  'data-testid': dataTestId,
  onFormatReady,
}) => {
  const [internalValue, setInternalValue] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const [prevValue, setPrevValue] = useState(value);

  // Sync state with value prop during render
  if (value !== prevValue) {
    setPrevValue(value);
    setInternalValue(value);
    // Validate immediately
    if (!value.trim()) {
      setError(null);
    } else {
      try {
        JSON.parse(value);
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
    }
  }

  const validateJson = (text: string) => {
    if (!text.trim()) {
      setError(null);
      return;
    }

    try {
      JSON.parse(text);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setInternalValue(newValue);
    validateJson(newValue);
    onChange?.(newValue);
  };

  const formatJson = useCallback(() => {
    if (!internalValue.trim()) return;

    try {
      const parsed = JSON.parse(internalValue);
      const formatted = JSON.stringify(parsed, null, 2);
      setInternalValue(formatted);
      onChange?.(formatted);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [internalValue, onChange]);

  // Pass format function to parent
  useEffect(() => {
    if (onFormatReady) {
      onFormatReady(formatJson);
    }
  }, [onFormatReady, formatJson]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const target = e.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const newValue = internalValue.substring(0, start) + '  ' + internalValue.substring(end);
      setInternalValue(newValue);
      onChange?.(newValue);

      // Set cursor position immediately - no async operations
      target.selectionStart = target.selectionEnd = start + 2;
    }
  };

  return (
    <Flex
      vertical
      className={className}
      style={{
        position: 'relative',
        height: typeof height === 'number' ? `${height}px` : height,
        overflow: 'hidden',
        fontFamily: 'monospace',
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      <textarea
        value={internalValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        data-testid={dataTestId}
        style={{
          width: '100%',
          height: '100%',
          outline: 'none',
          resize: 'none',
          fontFamily: 'inherit',
          fontSize: 'inherit',
          lineHeight: 'inherit',
          tabSize: 2,
        }}
      />

      {error && (
        <Typography.Text
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            fontSize: 12,
            fontWeight: 500,
          }}
        >
          JSON Error: {error}
        </Typography.Text>
      )}
    </Flex>
  );
};
