import styled from 'styled-components';

export const LoadingContainer = styled.div<{
  $width?: number | string;
  $height?: number;
  $borderRadius?: number;
}>`
  width: ${({ $width }) => (typeof $width === 'number' ? `${$width}px` : $width)};
  height: ${({ $height }) => $height}px;
  border-radius: ${({ $borderRadius }) => $borderRadius}px;
  background-color: var(--color-fill-tertiary);
`;
