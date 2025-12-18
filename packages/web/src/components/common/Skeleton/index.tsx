import React from 'react';
import {
  SkeletonButtonContainer,
  SkeletonCardContainer,
  SkeletonCell,
  SkeletonInputContainer,
  SkeletonRowContainer,
  SkeletonTextContainer,
} from './styles';

/**
 * Skeleton Loader Components
 *
 * Replaces opacity-dimmed loading indicators throughout the application.
 * Uses shimmer animation with solid colors (NO opacity).
 *
 * Usage:
 * - SkeletonText: Generic text placeholder
 * - SkeletonRow: Table row placeholder
 * - SkeletonCard: Card content placeholder
 * - SkeletonButton: Button placeholder
 * - SkeletonInput: Input field placeholder
 */

export interface SkeletonTextProps {
  width?: string;
  height?: string;
}

export const SkeletonText: React.FC<SkeletonTextProps> = ({ width, height }) => {
  return <SkeletonTextContainer $width={width} $height={height} />;
};

export interface SkeletonRowProps {
  /** Number of cells in the row */
  columns?: number;
}

export const SkeletonRow: React.FC<SkeletonRowProps> = ({ columns = 4 }) => {
  return (
    <SkeletonRowContainer>
      {Array.from({ length: columns }).map((_, index) => (
        <SkeletonCell key={index} />
      ))}
    </SkeletonRowContainer>
  );
};

export interface SkeletonCardProps {
  /** Number of text lines to show in the card */
  lines?: number;
}

export const SkeletonCard: React.FC<SkeletonCardProps> = ({ lines = 3 }) => {
  return (
    <SkeletonCardContainer>
      {Array.from({ length: lines }).map((_, index) => (
        <SkeletonText key={index} width={index === lines - 1 ? '60%' : '100%'} height="16px" />
      ))}
    </SkeletonCardContainer>
  );
};

export const SkeletonButton: React.FC = () => {
  return <SkeletonButtonContainer />;
};

export const SkeletonInput: React.FC = () => {
  return <SkeletonInputContainer />;
};

// Re-export for convenience
export { SkeletonBase } from './styles';
