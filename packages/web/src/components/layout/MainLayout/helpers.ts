import type { MenuConfig } from './types'
import { featureFlags } from '@/config/featureFlags'
import type { CompanyDashboardData } from '@rediacc/shared/types'

export type MenuItem = {
  key: string
  icon?: React.ReactNode
  label: string
  path?: string
  children?: MenuItem[]
}

type CompanyData = Pick<CompanyDashboardData, 'companyInfo'>

type FilterContext = {
  uiMode: 'simple' | 'expert'
  currentPlan: string
  isLocalhost: boolean
}

/**
 * Checks if a menu item should be visible based on UI mode, plan, and feature flags
 */
const shouldShowMenuItem = (
  item: { showInSimple?: boolean; requiresPlan?: string[]; featureFlag?: string },
  context: FilterContext
): boolean => {
  const { uiMode, currentPlan, isLocalhost } = context

  // Filter by UI mode
  if (uiMode === 'simple' && !item.showInSimple) return false

  const flag = item.featureFlag ? featureFlags.getFeature(item.featureFlag) : undefined
  const bypassPlanCheck = isLocalhost && flag?.localhostOnly

  // Filter by plan requirements
  if (!bypassPlanCheck && item.requiresPlan && !item.requiresPlan.includes(currentPlan)) return false

  // Filter by feature flags
  if (item.featureFlag && !featureFlags.isEnabled(item.featureFlag)) return false

  return true
}

/**
 * Builds menu items from configuration
 */
export const buildMenuItems = (
  items: MenuConfig[],
  uiMode: 'simple' | 'expert',
  companyData?: CompanyData
): MenuItem[] => {
  const currentPlan = companyData?.companyInfo?.Plan || 'FREE'
  const isLocalhost = typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')

  const filterContext: FilterContext = { uiMode, currentPlan, isLocalhost }

  return items
    .filter((item) => {
      // Filter out dividers
      if (item.type === 'divider') return false

      // Filter out items without labels
      if (!item.label) return false

      return shouldShowMenuItem(item, filterContext)
    })
    .map((item) => ({
      key: item.key,
      icon: item.icon,
      label: item.label!, // Non-null assertion safe because we filtered out items without labels
      children: item.children
        ? item.children
            .filter((child) => shouldShowMenuItem(child, filterContext))
            .map((child) => ({
              key: child.key,
              label: child.label,
            }))
        : undefined,
    }))
    .filter((item) => {
      // Remove parent items that have no visible children
      if (item.children && item.children.length === 0) return false
      return true
    })
}

/**
 * Flattens menu items to get all routes
 */
export const flattenMenuRoutes = (items: MenuItem[]): string[] => {
  const routes: string[] = []
  
  const flatten = (menuItems: MenuItem[]) => {
    menuItems.forEach((item) => {
      if (item.path) {
        routes.push(item.path)
      }
      if (item.children) {
        flatten(item.children)
      }
    })
  }
  
  flatten(items)
  return routes
}
