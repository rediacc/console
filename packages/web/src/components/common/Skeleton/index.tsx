import React from 'react';
const baseStyle: React.CSSProperties = {
  background: 'var(--ant-color-border)',
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
    <div
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
    <div style={{ display: 'flex', alignItems: 'center', padding: '12px 0', width: '100%' }}>
      {Array.from({ length: columns }).map((_, index) => (
        <div key={index} style={{ ...baseStyle, height: 20, flex: 1 }} />
      ))}
    </div>
  );
};

export interface SkeletonCardProps {
  /** Number of text lines to show in the card */
  lines?: number;
}

export const SkeletonCard: React.FC<SkeletonCardProps> = ({ lines = 3 }) => {
  return (
    <div
      style={{
        backgroundColor: 'var(--ant-color-bg-container)',
        border: '1px solid var(--ant-color-border)',
        borderRadius: 6,
        padding: 24,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {Array.from({ length: lines }).map((_, index) => (
        <SkeletonText key={index} width={index === lines - 1 ? '60%' : '100%'} height="16px" />
      ))}
    </div>
  );
};

export const SkeletonButton: React.FC = () => {
  return <div style={{ ...baseStyle, height: 40, width: 120, borderRadius: 6 }} />;
};

export const SkeletonInput: React.FC = () => {
  return <div style={{ ...baseStyle, height: 40, width: '100%' }} />;
};

export const SkeletonBase = (props: React.HTMLAttributes<HTMLDivElement>) => (
  <div style={{ ...baseStyle, ...props.style }} {...props} />
);
