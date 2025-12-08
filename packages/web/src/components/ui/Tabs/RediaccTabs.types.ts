import type { CSSProperties, ReactNode } from 'react';

export type TabsVariant = 'default' | 'card' | 'pills';
export type TabsSize = 'sm' | 'md';

export interface TabItem {
  key: string;
  label: ReactNode;
  children?: ReactNode;
  disabled?: boolean;
  icon?: ReactNode;
}

export interface RediaccTabsProps {
  /** Tabs style variant */
  variant?: TabsVariant;
  /** Size of tab labels */
  size?: TabsSize;
  /** Center tab labels */
  centered?: boolean;
  /** Stretch tabs to full width */
  fullWidth?: boolean;
  /** Tab items */
  items?: TabItem[];
  /** Active tab key */
  activeKey?: string;
  /** Default active tab key */
  defaultActiveKey?: string;
  /** Tab change callback */
  onChange?: (key: string) => void;
  /** Tab click callback */
  onTabClick?: (key: string, e: React.MouseEvent | React.KeyboardEvent) => void;
  /** Extra content on the right */
  tabBarExtraContent?: ReactNode;
  /** Destroy inactive tab content */
  destroyInactiveTabPane?: boolean;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
