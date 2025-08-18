import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

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
        document.documentElement.className = document.documentElement.className
          .replace(/\btheme-\w+/g, '')
          .trim() + ` theme-${theme}`;
      });
      
      // Save to localStorage
      localStorage.setItem('theme', theme);
    };

    applyTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prevTheme => prevTheme === 'light' ? 'dark' : 'light');
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