import { Flex, Typography } from 'antd';
import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('common');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Derive validation error from value (pure computation, no side effects)
  const error = useMemo(() => {
    if (!value.trim()) return null;
    try {
      JSON.parse(value);
      return null;
    } catch (e) {
      return (e as Error).message;
    }
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    onChange?.(newValue);
  };

  const formatJson = useCallback(() => {
    if (!value.trim()) return;

    try {
      const parsed = JSON.parse(value);
      const formatted = JSON.stringify(parsed, null, 2);
      onChange?.(formatted);
    } catch {
      // Error is already shown via the derived error state
    }
  }, [value, onChange]);

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
      const newValue = `${value.substring(0, start)}  ${value.substring(end)}`;
      onChange?.(newValue);

      // Set cursor position after React updates the value
      requestAnimationFrame(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + 2;
        }
      });
    }
  };

  return (
    <Flex
      vertical
      className={`relative overflow-hidden ${className}`}
      // eslint-disable-next-line no-restricted-syntax
      style={{
        height: typeof height === 'number' ? `${height}px` : height,
        fontFamily: 'monospace',
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        data-testid={dataTestId}
        className="w-full h-full"
        // eslint-disable-next-line no-restricted-syntax
        style={{
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
          className="absolute"
          // eslint-disable-next-line no-restricted-syntax
          style={{
            bottom: 0,
            left: 0,
            right: 0,
            fontSize: 12,
            fontWeight: 500,
          }}
        >
          {t('defaults.jsonError')}: {error}
        </Typography.Text>
      )}
    </Flex>
  );
};
