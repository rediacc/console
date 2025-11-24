import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import { createResourceCommands } from '../utils/commandFactory.js'
import { getFirstRow, type BridgeAuthResponse } from '../types/api-responses.js'

export function registerBridgeCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const bridge = createResourceCommands(program, {
    resourceName: 'bridge',
    resourceNamePlural: 'bridges',
    nameField: 'bridgeName',
    parentOption: 'region',
    endpoints: {
      list: '/GetRegionBridges',
      create: '/CreateBridge',
      rename: '/UpdateBridgeName',
      delete: '/DeleteBridge'
    }
  })

  // Add custom reset-auth command
  bridge
    .command('reset-auth <name>')
    .description('Reset bridge authorization token')
    .option('-r, --region <name>', 'Region name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          `Resetting authorization for bridge "${name}"...`,
          () => apiClient.post('/ResetBridgeAuthorization', {
            bridgeName: name,
            regionName: opts.region,
          }),
          'Authorization reset'
        )

        const data = getFirstRow<BridgeAuthResponse>(response.resultSets)
        if (data?.authToken) {
          outputService.success(`New token: ${data.authToken}`)
        }
      } catch (error) {
        handleError(error)
      }
    })
}
