import styled from 'styled-components';

export const EditorContainer = styled.div<{ $height: number | string }>`
  position: relative;
  height: ${({ $height }) => (typeof $height === 'number' ? `${$height}px` : $height)};
  overflow: hidden;
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};
`;

export const EditorTextarea = styled.textarea`
  width: 100%;
  height: 100%;
  outline: none;
  resize: none;
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
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;
