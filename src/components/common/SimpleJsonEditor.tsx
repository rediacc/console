import React, { useState, useEffect, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';

interface SimpleJsonEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string | number;
  className?: string;
  language?: string;
}

export const SimpleJsonEditor: React.FC<SimpleJsonEditorProps> = ({
  value,
  onChange,
  readOnly = false,
  height = '400px',
  className = '',
  language = 'json'
}) => {
  const { theme } = useTheme();
  const [internalValue, setInternalValue] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setInternalValue(value);
    validateJson(value);
  }, [value]);

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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const target = e.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const newValue = internalValue.substring(0, start) + '  ' + internalValue.substring(end);
      setInternalValue(newValue);
      onChange?.(newValue);
      
      setTimeout(() => {
        target.selectionStart = target.selectionEnd = start + 2;
      }, 0);
    }
  };

  const isDark = theme === 'dark';
  
  const containerStyles: React.CSSProperties = {
    height: typeof height === 'number' ? `${height}px` : height,
    position: 'relative',
    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
    borderRadius: '0.375rem',
    overflow: 'hidden',
    backgroundColor: isDark ? '#1f2937' : '#ffffff',
    fontFamily: 'Consolas, Monaco, "Courier New", monospace',
    fontSize: '14px',
    lineHeight: '1.5'
  };

  const textareaStyles: React.CSSProperties = {
    width: '100%',
    height: '100%',
    padding: '12px',
    border: 'none',
    outline: 'none',
    resize: 'none',
    backgroundColor: 'transparent',
    color: isDark ? '#e5e7eb' : '#1f2937',
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
    padding: '4px 8px',
    backgroundColor: isDark ? '#991b1b' : '#fee2e2',
    color: isDark ? '#fca5a5' : '#dc2626',
    fontSize: '12px',
    borderTop: `1px solid ${isDark ? '#dc2626' : '#fca5a5'}`
  };

  const buttonStyles: React.CSSProperties = {
    position: 'absolute',
    top: '8px',
    right: '8px',
    padding: '4px 12px',
    backgroundColor: isDark ? '#374151' : '#e5e7eb',
    color: isDark ? '#e5e7eb' : '#1f2937',
    border: 'none',
    borderRadius: '0.25rem',
    fontSize: '12px',
    cursor: 'pointer',
    zIndex: 10
  };

  return (
    <div className={className} style={containerStyles}>
      {!readOnly && (
        <button
          type="button"
          onClick={formatJson}
          style={buttonStyles}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = isDark ? '#4b5563' : '#d1d5db';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = isDark ? '#374151' : '#e5e7eb';
          }}
        >
          Format
        </button>
      )}
      
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
      />
      
      {error && (
        <div style={errorStyles}>
          JSON Error: {error}
        </div>
      )}
    </div>
  );
};