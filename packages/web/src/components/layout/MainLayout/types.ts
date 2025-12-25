export type MenuBaseConfig = {
  key: string;
  label?: string;
  showInSimple: boolean;
  requiresPlan?: string[];
  featureFlag?: string;
  'data-testid'?: string;
};

export type MenuChildConfig = MenuBaseConfig & {
  label: string;
};

export type MenuConfig = MenuBaseConfig & {
  icon?: React.ReactNode;
  type?: 'divider';
  children?: MenuChildConfig[];
};

export const SIDEBAR_EXPANDED_WIDTH = 200;
const SIDEBAR_COLLAPSED_WIDTH = 64;

// Keep reference to satisfy TypeScript and prevent dead code elimination warnings
void SIDEBAR_COLLAPSED_WIDTH;
