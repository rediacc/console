import React from 'react'
import { Toaster } from 'react-hot-toast'
import { useTheme } from '@/context/ThemeContext'

export const ThemedToaster: React.FC = () => {
  const { theme } = useTheme()

  const isDark = theme === 'dark'

  return (
    <div data-testid="themed-toaster-container">
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 4000,
          style: {
            // Design system background colors
            background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
            color: isDark ? 'var(--color-text-primary)' : 'var(--color-text-primary)',
            border: `1px solid ${isDark ? 'var(--color-border-primary)' : 'var(--color-border-primary)'}`,
            borderRadius: '8px', // Design system border radius
            // Design system shadows
            boxShadow: 'var(--shadow-lg)',
            fontSize: '14px',
            fontWeight: '500',
            padding: 'var(--space-md)',
            minHeight: '44px', // Accessibility compliant touch target
            display: 'flex',
            alignItems: 'center',
          },
        success: {
          iconTheme: {
            primary: 'var(--color-success)', // Design system success color
            secondary: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
          },
          style: {
            background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
            color: isDark ? 'var(--color-text-primary)' : 'var(--color-text-primary)',
            borderColor: 'var(--color-success)',
            borderWidth: '2px',
          },
        },
        error: {
          iconTheme: {
            primary: 'var(--color-error)', // Design system error color
            secondary: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
          },
          style: {
            background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
            color: isDark ? 'var(--color-text-primary)' : 'var(--color-text-primary)',
            borderColor: 'var(--color-error)',
            borderWidth: '2px',
          },
        },
        loading: {
          iconTheme: {
            primary: 'var(--color-info)', // Design system info color
            secondary: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
          },
          style: {
            background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
            color: isDark ? 'var(--color-text-primary)' : 'var(--color-text-primary)',
            borderColor: 'var(--color-info)',
            borderWidth: '2px',
          },
        },
        // Custom styles for warning toasts
        custom: {
          style: {
            background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
            color: isDark ? 'var(--color-text-primary)' : 'var(--color-text-primary)',
            borderColor: 'var(--color-warning)',
            borderWidth: '2px',
          },
        },
      }}
    />
    </div>
  )
}