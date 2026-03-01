import React, { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';

interface ThemeToggleProps {
  label?: string;
}

const ThemeToggle: React.FC<ThemeToggleProps> = ({ label = 'Toggle theme' }) => {
  const [theme, setTheme] = useState<Theme>('light');

  useEffect(() => {
    // Read the theme already set by the inline <head> script
    const current = document.documentElement.dataset.theme as Theme | undefined;
    if (current === 'dark' || current === 'light') {
      setTheme(current);
    }
  }, []);

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem('theme', next);

    // Update theme-color meta tag for browser chrome
    const meta = document.querySelector('meta[name="theme-color"][media]') as HTMLMetaElement | null;
    if (meta) {
      meta.content = next === 'dark' ? '#0f0f10' : '#556b2f';
    }
  };

  return (
    <button
      type="button"
      className="theme-toggle-btn"
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      {theme === 'dark' ? (
        // Sun icon — switch to light
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <circle cx="10" cy="10" r="4" stroke="currentColor" strokeWidth="2" />
          <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.93 4.93l1.41 1.41M13.66 13.66l1.41 1.41M4.93 15.07l1.41-1.41M13.66 6.34l1.41-1.41" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ) : (
        // Moon icon — switch to dark
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M17.09 11.18A7 7 0 018.82 2.91a7 7 0 108.27 8.27z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
};

export default ThemeToggle;
