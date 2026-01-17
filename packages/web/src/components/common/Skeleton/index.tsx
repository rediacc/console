import React from 'react';
import { Flex } from 'antd';
import { DEFAULTS, UI_SIZING } from '@rediacc/shared/config';

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

const SkeletonText: React.FC<SkeletonTextProps> = ({ width, height }) => {
  return (
    <Flex
      className="rounded"
      // eslint-disable-next-line no-restricted-syntax
      style={{
        width: width ?? DEFAULTS.UI.SKELETON_WIDTH,
        height: height ?? UI_SIZING.SKELETON_HEIGHT,
      }}
    />
  );
};

export interface SkeletonRowProps {
  /** Number of cells in the row */
  columns?: number;
}

const SkeletonRow: React.FC<SkeletonRowProps> = ({ columns = 4 }) => {
  return (
    <Flex
      align="center"
      className="w-full py-3"
    >
      {Array.from({ length: columns }).map((_, index) => (
        <Flex
          key={index}
          className="flex-1 rounded h-5"
        />
      ))}
    </Flex>
  );
};

export interface SkeletonCardProps {
  /** Number of text lines to show in the card */
  lines?: number;
}

const SkeletonCard: React.FC<SkeletonCardProps> = ({ lines = 3 }) => {
  return (
    <Flex
      vertical
      className="rounded-md p-6"
    >
      {Array.from({ length: lines }).map((_, index) => (
        <SkeletonText key={index} width={index === lines - 1 ? '60%' : '100%'} height="16px" />
      ))}
    </Flex>
  );
};

const SkeletonButton: React.FC = () => {
  return (
    <Flex className="h-10 w-[120px] rounded-md" />
  );
};

const SkeletonInput: React.FC = () => {
  return (
    <Flex className="w-full h-10 rounded" />
  );
};

const SkeletonBase = (props: React.HTMLAttributes<HTMLDivElement>) => (
  <Flex
    className="rounded"
    // eslint-disable-next-line no-restricted-syntax
    style={props.style}
    {...props}
  />
);

// Components are available for future use
void SkeletonCard;
void SkeletonRow;
void SkeletonButton;
void SkeletonInput;
void SkeletonBase;
