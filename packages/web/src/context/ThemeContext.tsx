import React, { createContext, ReactNode, useContext, useEffect, useRef, useState } from 'react';
import { telemetryService } from '@/services/telemetryService';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() => {
    const savedTheme = localStorage.getItem('theme');
    return (savedTheme as Theme) || 'light';
  });
  const initialTheme = useRef(theme);

  // Track initial theme selection on mount
  useEffect(() => {
    const isSystemDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches || false;
    const savedTheme = localStorage.getItem('theme');

    telemetryService.trackEvent('user.theme_initialized', {
      'theme.current': initialTheme.current,
      'theme.was_saved': !!savedTheme,
      'theme.system_preference': isSystemDark ? 'dark' : 'light',
      'theme.matches_system': initialTheme.current === (isSystemDark ? 'dark' : 'light'),
      'accessibility.prefers_dark': isSystemDark,
    });
  }, []); // Only run on mount

  useEffect(() => {
    const applyTheme = (theme: Theme) => {
      // Batch DOM updates for better performance using design system approach
      requestAnimationFrame(() => {
        // Set data-theme attribute for design system
        document.body.setAttribute('data-theme', theme);
        document.documentElement.setAttribute('data-theme', theme);

        // Add/remove dark class for compatibility
        const isDark = theme === 'dark';
        document.documentElement.classList.toggle('dark', isDark);
        document.body.classList.toggle('dark', isDark);

        // Remove inline styles - let design system CSS handle the colors
        document.body.style.removeProperty('background-color');
        document.body.style.removeProperty('color');

        // Apply theme class to root for design system
        document.documentElement.className =
          document.documentElement.className.replace(/\btheme-\w+/g, '').trim() + ` theme-${theme}`;
      });

      // Save to localStorage
      localStorage.setItem('theme', theme);
    };

    applyTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    const currentTheme = theme;
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';

    // Track theme switching
    telemetryService.trackEvent('user.theme_changed', {
      'theme.from': currentTheme,
      'theme.to': newTheme,
      'theme.method': 'toggle',
      'theme.time_of_day': new Date().getHours(),
      'page.url': window.location.pathname,
      'accessibility.prefers_dark':
        window.matchMedia?.('(prefers-color-scheme: dark)').matches || false,
    });

    setTheme(newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
