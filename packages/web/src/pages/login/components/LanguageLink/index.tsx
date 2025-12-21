import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

interface LanguageLinkProps {
  to: string;
  className?: string;
  style?: React.CSSProperties;
  target?: string;
  children: React.ReactNode;
}

export function LanguageLink({ to, className, style, target, children }: LanguageLinkProps) {
  const { i18n } = useTranslation();
  const hasLanguage = /^\/[a-z]{2}(\/|$)/.test(to);
  const localizedTo = hasLanguage ? to : `/${i18n.language}${to}`;
  return (
    <Link
      to={localizedTo}
      className={className}
      style={{ textDecoration: 'none', ...style }}
      target={target}
    >
      {children}
    </Link>
  );
}
