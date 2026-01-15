import {
  CloudOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  DesktopOutlined,
  HistoryOutlined,
  InboxOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';

export type RouteItem = {
  path?: string;
  name?: string;
  icon?: React.ReactNode;
  showInSimple?: boolean;
  requiresPlan?: string[];
  featureFlag?: string;
  'data-testid'?: string;
  routes?: RouteItem[];
};

export const getRoutes = (t: TypedTFunction): { path: string; routes: RouteItem[] } => ({
  path: '/',
  routes: [
    {
      path: '/dashboard',
      name: t('navigation.dashboard'),
      icon: <DashboardOutlined />,
      showInSimple: false,
      'data-testid': 'main-nav-dashboard',
    },
    {
      path: '/organization',
      name: t('navigation.organization'),
      icon: <TeamOutlined />,
      showInSimple: true,
      'data-testid': 'main-nav-organization',
      routes: [
        {
          path: '/organization/users',
          name: t('navigation.organizationUsers'),
          showInSimple: true,
          'data-testid': 'sub-nav-organization-users',
        },
        {
          path: '/organization/teams',
          name: t('navigation.organizationTeams'),
          showInSimple: true,
          'data-testid': 'sub-nav-organization-teams',
        },
        {
          path: '/organization/access',
          name: t('navigation.organizationAccess'),
          showInSimple: false,
          'data-testid': 'sub-nav-organization-access',
        },
      ],
    },
    {
      path: '/machines',
      name: t('navigation.machines'),
      icon: <DesktopOutlined />,
      showInSimple: true,
      'data-testid': 'main-nav-machines',
    },
    {
      path: '/settings',
      name: t('navigation.settings'),
      icon: <SettingOutlined />,
      showInSimple: true,
      'data-testid': 'main-nav-settings',
      routes: [
        {
          path: '/settings/profile',
          name: t('navigation.settingsProfile'),
          showInSimple: true,
          'data-testid': 'sub-nav-settings-profile',
        },
        {
          path: '/settings/organization',
          name: t('navigation.settingsOrganization'),
          showInSimple: false,
          featureFlag: 'organizationSettings',
          'data-testid': 'sub-nav-settings-organization',
        },
        {
          path: '/settings/infrastructure',
          name: t('navigation.settingsInfrastructure'),
          showInSimple: false,
          featureFlag: 'regionsInfrastructure',
          'data-testid': 'sub-nav-settings-infrastructure',
        },
      ],
    },
    {
      path: '/storage',
      name: t('navigation.storage'),
      icon: <CloudOutlined />,
      showInSimple: false,
      'data-testid': 'main-nav-storage',
    },
    {
      path: '/ceph',
      name: t('navigation.ceph'),
      icon: <CloudServerOutlined />,
      showInSimple: false,
      requiresPlan: ['ENTERPRISE', 'BUSINESS', 'Enterprise', 'Business'],
      featureFlag: 'ceph',
      'data-testid': 'main-nav-ceph',
      routes: [
        {
          path: '/ceph/clusters',
          name: t('navigation.cephClusters'),
          showInSimple: false,
          'data-testid': 'sub-nav-ceph-clusters',
        },
        {
          path: '/ceph/pools',
          name: t('navigation.cephPools'),
          showInSimple: false,
          'data-testid': 'sub-nav-ceph-pools',
        },
        {
          path: '/ceph/machines',
          name: t('navigation.cephMachines'),
          showInSimple: false,
          'data-testid': 'sub-nav-ceph-machines',
        },
      ],
    },
    {
      path: '/credentials',
      name: t('navigation.credentials'),
      icon: <InboxOutlined />,
      showInSimple: false,
      'data-testid': 'main-nav-credentials',
    },
    {
      path: '/queue',
      name: t('navigation.queue'),
      icon: <ThunderboltOutlined />,
      showInSimple: false,
      featureFlag: 'queueManagement',
      'data-testid': 'main-nav-queue',
    },
    {
      path: '/audit',
      name: t('navigation.audit'),
      icon: <HistoryOutlined />,
      showInSimple: false,
      featureFlag: 'auditLogs',
      'data-testid': 'main-nav-audit',
    },
  ],
});
