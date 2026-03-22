import type React from 'react';
import type { SolutionCategory } from '../config/solution-pages';

interface IconProps {
  size?: number;
  className?: string;
}

const iconProps = (size: number, className?: string) =>
  ({
    width: size,
    height: size,
    viewBox: '0 0 20 20',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.75,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true as const,
    className,
  }) satisfies React.SVGProps<SVGSVGElement>;

/** Shield — ransomware survival */
const RansomwareIcon: React.FC<IconProps> = ({ size = 18, className }) => (
  <svg {...iconProps(size, className)}>
    <path d="M10 2L3 5.5v4c0 4.25 3 7.5 7 8.5 4-1 7-4.25 7-8.5v-4L10 2z" />
    <path d="M7.5 10l2 2 3.5-4" />
  </svg>
);

/** Overlapping clouds — multi-cloud */
const MultiCloudIcon: React.FC<IconProps> = ({ size = 18, className }) => (
  <svg {...iconProps(size, className)}>
    <path d="M6.5 15.5A3.5 3.5 0 013 12a3.5 3.5 0 013-3.46A5 5 0 0111 4a5 5 0 015 4.5 3 3 0 01.5 5.96" />
    <path d="M8 15.5h8a2.5 2.5 0 000-5 .5.5 0 010-.05A3.5 3.5 0 0012.5 7a3.5 3.5 0 00-3.46 3H8a2.5 2.5 0 000 5.5z" />
  </svg>
);

/** Database with checkmark — verified backups */
const BackupsIcon: React.FC<IconProps> = ({ size = 18, className }) => (
  <svg {...iconProps(size, className)}>
    <ellipse cx="10" cy="5" rx="6" ry="2.5" />
    <path d="M4 5v4c0 1.38 2.69 2.5 6 2.5" />
    <path d="M4 9v4c0 1.38 2.69 2.5 6 2.5" />
    <path d="M16 5v3" />
    <circle cx="14.5" cy="14" r="3.5" />
    <path d="M13 14l1.2 1.2 2.3-2.4" />
  </svg>
);

/** Key — encryption control */
const EncryptionIcon: React.FC<IconProps> = ({ size = 18, className }) => (
  <svg {...iconProps(size, className)}>
    <circle cx="7.5" cy="7.5" r="4" />
    <circle cx="7.5" cy="7.5" r="1.5" fill="currentColor" strokeWidth="0" />
    <path d="M10.5 10.5L16 16" />
    <path d="M14 14l2-1" />
    <path d="M12.5 12.5l2-1" />
  </svg>
);

/** Code brackets — dev environments */
const DevEnvIcon: React.FC<IconProps> = ({ size = 18, className }) => (
  <svg {...iconProps(size, className)}>
    <path d="M7 5L2.5 10 7 15" />
    <path d="M13 5l4.5 5L13 15" />
    <path d="M11 3l-2 14" />
  </svg>
);

/** Crosshair/target — preemptive defense */
const DefenseIcon: React.FC<IconProps> = ({ size = 18, className }) => (
  <svg {...iconProps(size, className)}>
    <circle cx="10" cy="10" r="7" />
    <circle cx="10" cy="10" r="3.5" />
    <circle cx="10" cy="10" r="1" fill="currentColor" strokeWidth="0" />
    <path d="M10 2v2.5" />
    <path d="M10 15.5V18" />
    <path d="M2 10h2.5" />
    <path d="M15.5 10H18" />
  </svg>
);

export const CATEGORY_ICONS: Record<SolutionCategory, React.FC<IconProps>> = {
  ransomware: RansomwareIcon,
  'multi-cloud': MultiCloudIcon,
  backups: BackupsIcon,
  encryption: EncryptionIcon,
  'dev-env': DevEnvIcon,
  defense: DefenseIcon,
};
