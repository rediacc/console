import type { MenuConfig } from './types'
import { featureFlags } from '@/config/featureFlags'

export type MenuItem = {
  key: string
  icon?: React.ReactNode
  label: string
  path?: string
  children?: MenuItem[]
}

type CompanyData = {
  companyInfo?: {
    Plan?: string
  }
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

  return items
    .filter((item) => {
      // Filter out dividers
      if (item.type === 'divider') return false
      
      // Filter out items without labels
      if (!item.label) return false
      
      // Filter by UI mode
      if (uiMode === 'simple' && !item.showInSimple) return false
      
      const flag = item.featureFlag ? featureFlags.getFeature(item.featureFlag) : undefined
      const bypassPlanCheck = isLocalhost && flag?.localhostOnly
      
      // Filter by plan requirements
      if (!bypassPlanCheck && item.requiresPlan && !item.requiresPlan.includes(currentPlan)) return false
      
      // Filter by feature flags
      if (item.featureFlag && !featureFlags.isEnabled(item.featureFlag)) return false
      
      return true
    })
    .map((item) => ({
      key: item.key,
      icon: item.icon,
      label: item.label!, // Non-null assertion safe because we filtered out items without labels
      children: item.children
        ? item.children
            .filter((child) => {
              // Filter children by UI mode
              if (uiMode === 'simple' && !child.showInSimple) return false
              
              const childFlag = child.featureFlag ? featureFlags.getFeature(child.featureFlag) : undefined
              const childBypassPlanCheck = isLocalhost && childFlag?.localhostOnly
              
              // Filter children by plan requirements
              if (!childBypassPlanCheck && child.requiresPlan && !child.requiresPlan.includes(currentPlan)) return false
              
              // Filter children by feature flags
              if (child.featureFlag && !featureFlags.isEnabled(child.featureFlag)) return false
              
              return true
            })
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
