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
            background: isDark ? '#1f2937' : '#ffffff',
            color: isDark ? '#fff' : '#1f2937',
            border: isDark ? '1px solid #374151' : '1px solid #e5e7eb',
            boxShadow: isDark 
              ? '0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.15)'
              : '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
          },
        success: {
          iconTheme: {
            primary: '#556b2f',
            secondary: '#fff',
          },
          style: {
            background: isDark ? '#1f2937' : '#ffffff',
            color: isDark ? '#fff' : '#1f2937',
          },
        },
        error: {
          iconTheme: {
            primary: '#dc2626',
            secondary: '#fff',
          },
          style: {
            background: isDark ? '#1f2937' : '#ffffff',
            color: isDark ? '#fff' : '#1f2937',
          },
        },
        loading: {
          style: {
            background: isDark ? '#1f2937' : '#ffffff',
            color: isDark ? '#fff' : '#1f2937',
          },
        },
      }}
    />
    </div>
  )
}