import { Command } from 'commander'
import { createResourceCommands } from '../utils/commandFactory.js'

export function registerRegionCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'region',
    resourceNamePlural: 'regions',
    nameField: 'regionName',
    parentOption: 'none',
    endpoints: {
      list: '/GetCompanyRegions',
      create: '/CreateRegion',
      rename: '/UpdateRegionName',
      delete: '/DeleteRegion'
    },
    vaultConfig: {
      endpoint: '/GetCompanyVaults',
      vaultType: 'Region'
    },
    vaultUpdateConfig: {
      endpoint: '/UpdateRegionVault',
      vaultFieldName: 'regionVault'
    }
  })
}
