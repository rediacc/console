import styled from 'styled-components';

export const LoadingContainer = styled.div<{
  $width?: number | string;
  $height?: number | string;
  $borderRadius?: number | string;
}>`
  width: ${({ $width }) => (typeof $width === 'number' ? `${$width}px` : $width)};
  height: ${({ $height }) => (typeof $height === 'number' ? `${$height}px` : $height)};
  border-radius: ${({ $borderRadius }) => (typeof $borderRadius === 'number' ? `${$borderRadius}px` : $borderRadius)};
  background-color: var(--color-fill-tertiary);
`;
