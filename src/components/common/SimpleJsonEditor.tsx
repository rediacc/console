import React, { useState, useRef, useEffect } from 'react';
import { useTheme } from '../../context/ThemeContext';

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
  const { theme } = useTheme();
  const [internalValue, setInternalValue] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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

  const isDark = theme === 'dark';
  
  const containerStyles: React.CSSProperties = {
    height: typeof height === 'number' ? `${height}px` : height,
    position: 'relative',
    border: `1px solid var(--color-border-primary)`,
    borderRadius: '8px', // Design system border radius
    overflow: 'hidden',
    backgroundColor: 'var(--color-bg-primary)',
    fontFamily: 'Consolas, Monaco, "Courier New", monospace',
    fontSize: '14px',
    lineHeight: '1.5',
    boxShadow: 'var(--shadow-sm)'
  };

  const textareaStyles: React.CSSProperties = {
    width: '100%',
    height: '100%',
    padding: 'var(--space-md)', // Design system spacing
    border: 'none',
    outline: 'none',
    resize: 'none',
    backgroundColor: 'transparent',
    color: 'var(--color-text-primary)', // Design system text color
    fontFamily: 'inherit',
    fontSize: 'inherit',
    lineHeight: 'inherit',
    tabSize: 2
  };

  const errorStyles: React.CSSProperties = {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: 'var(--space-xs) var(--space-sm)', // Design system spacing
    backgroundColor: isDark ? 'var(--color-bg-error)' : '#fee2e2',
    color: 'var(--color-error)', // Design system error color
    fontSize: '12px',
    fontWeight: '500',
    borderTop: `1px solid var(--color-error)`,
    borderRadius: '0 0 8px 8px'
  };

  return (
    <div className={className} style={containerStyles}>
      <textarea
        ref={textareaRef}
        value={internalValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        style={textareaStyles}
        data-testid={dataTestId}
      />
      
      {error && (
        <div style={errorStyles}>
          JSON Error: {error}
        </div>
      )}
    </div>
  );
};