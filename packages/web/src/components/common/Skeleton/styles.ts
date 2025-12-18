import styled from 'styled-components';

/**
 * Skeleton Loader Styles
 *
 * Replacement for opacity-based loading indicators.
 * Uses solid color for loading state indication.
 * NO opacity, gradients, or animations.
 */

export const SkeletonBase = styled.div`
  background: ${({ theme }) => theme.colors.borderPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
`;

export const SkeletonTextContainer = styled(SkeletonBase)<{
  $width?: string;
  $height?: string;
}>`
  width: ${({ $width }) => $width || '100%'};
  height: ${({ $height }) => $height || '16px'};
`;

export const SkeletonButtonContainer = styled(SkeletonBase)`
  height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  width: 120px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`;

export const SkeletonInputContainer = styled(SkeletonBase)`
  height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  width: 100%;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
`;

export const SkeletonCardContainer = styled.div`
  background-color: ${({ theme }) => theme.colors.bgContainer};
  border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  padding: ${({ theme }) => theme.spacing.LG}px;
  display: flex;
  flex-direction: column;
`;

export const SkeletonRowContainer = styled.div`
  display: flex;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.SM}px 0;
  width: 100%;
`;

export const SkeletonCell = styled(SkeletonBase)`
  height: 20px;
  flex: 1;

  &:not(:last-child) {
    margin-right: ${({ theme }) => theme.spacing.SM}px;
  }
`;
