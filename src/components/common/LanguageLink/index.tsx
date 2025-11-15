
import React from 'react';
import { useTranslation } from 'react-i18next';
import { StyledLanguageLink } from './styles';

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
    <StyledLanguageLink to={localizedTo} className={className} style={style} target={target}>
      {children}
    </StyledLanguageLink>
  );
}
