import React, { useState, useEffect } from 'react';
import { EditorContainer, EditorTextarea, ErrorBanner } from './styles';

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
  onFormatReady
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

  const formatJson = () => {
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
  };

  // Pass format function to parent
  useEffect(() => {
    if (onFormatReady) {
      onFormatReady(formatJson);
    }
  }, [onFormatReady]);

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
    <EditorContainer className={className} $height={height}>
      <EditorTextarea
        value={internalValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        data-testid={dataTestId}
      />
      
      {error && (
        <ErrorBanner>
          JSON Error: {error}
        </ErrorBanner>
      )}
    </EditorContainer>
  );
};
