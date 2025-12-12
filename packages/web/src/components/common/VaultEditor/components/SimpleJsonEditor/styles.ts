import styled from 'styled-components';
import { borderedCard } from '@/styles/mixins';

export const EditorContainer = styled.div<{ $height: number | string }>`
  position: relative;
  height: ${({ $height }) => (typeof $height === 'number' ? `${$height}px` : $height)};
  ${borderedCard('borderPrimary')}
  overflow: hidden;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  box-shadow: ${({ theme }) => theme.shadows.SM};
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};
`;

export const EditorTextarea = styled.textarea`
  width: 100%;
  height: 100%;
  padding: ${({ theme }) => theme.spacing.MD}px;
  border: none;
  outline: none;
  resize: none;
  background-color: transparent;
  color: ${({ theme }) => theme.colors.textPrimary};
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  tab-size: 2;
`;

export const ErrorBanner = styled.div`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
  background-color: ${({ theme }) => theme.colors.bgError};
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  border-top: 1px solid ${({ theme }) => theme.colors.error};
`;
