import { Command } from 'commander'
import { createResourceCommands } from '../utils/commandFactory.js'

export function registerStorageCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'storage',
    resourceNamePlural: 'storage systems',
    nameField: 'storageName',
    parentOption: 'team',
    endpoints: {
      list: '/GetTeamStorages',
      create: '/CreateStorage',
      rename: '/UpdateStorageName',
      delete: '/DeleteStorage'
    },
    vaultConfig: {
      endpoint: '/GetCompanyVaults',
      vaultType: 'Storage'
    }
  })
}
