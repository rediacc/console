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
export const SIDEBAR_COLLAPSED_WIDTH = 64;
