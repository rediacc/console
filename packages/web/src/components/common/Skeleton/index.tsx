import React from 'react';
import { Flex } from 'antd';

const baseStyle: React.CSSProperties = {
  borderRadius: 4,
};

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
  return (
    <Flex
      style={{
        ...baseStyle,
        width: width ?? '100%',
        height: height ?? '16px',
      }}
    />
  );
};

export interface SkeletonRowProps {
  /** Number of cells in the row */
  columns?: number;
}

export const SkeletonRow: React.FC<SkeletonRowProps> = ({ columns = 4 }) => {
  return (
    <Flex align="center" style={{ padding: '12px 0', width: '100%' }}>
      {Array.from({ length: columns }).map((_, index) => (
        <Flex key={index} style={{ ...baseStyle, height: 20, flex: 1 }} />
      ))}
    </Flex>
  );
};

export interface SkeletonCardProps {
  /** Number of text lines to show in the card */
  lines?: number;
}

export const SkeletonCard: React.FC<SkeletonCardProps> = ({ lines = 3 }) => {
  return (
    <Flex
      vertical
      style={{
        borderRadius: 6,
        padding: 24,
      }}
    >
      {Array.from({ length: lines }).map((_, index) => (
        <SkeletonText key={index} width={index === lines - 1 ? '60%' : '100%'} height="16px" />
      ))}
    </Flex>
  );
};

export const SkeletonButton: React.FC = () => {
  return <Flex style={{ ...baseStyle, height: 40, width: 120, borderRadius: 6 }} />;
};

export const SkeletonInput: React.FC = () => {
  return <Flex style={{ ...baseStyle, height: 40, width: '100%' }} />;
};

export const SkeletonBase = (props: React.HTMLAttributes<HTMLDivElement>) => (
  <Flex style={{ ...baseStyle, ...props.style }} {...props} />
);
