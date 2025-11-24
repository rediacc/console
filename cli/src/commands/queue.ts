import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { queueService } from '../services/queue.js'
import { withSpinner, startSpinner, stopSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'
import { getFirstRow, type QueueItemResponse } from '../types/api-responses.js'

export function registerQueueCommands(program: Command): void {
  const queue = program
    .command('queue')
    .description('Queue management commands')

  // queue list
  queue
    .command('list')
    .description('List queue items')
    .option('-t, --team <name>', 'Team name')
    .option('--status <status>', 'Filter by status')
    .option('--limit <n>', 'Limit results', '50')
    .action(async (options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching queue items...',
          () => apiClient.get('/GetTeamQueueItems', {
            teamName: opts.team,
            limit: parseInt(options.limit, 10),
          }),
          'Queue items fetched'
        )

        let items = response.resultSets?.[0]?.data || []

        // Filter by status if specified
        if (options.status) {
          items = items.filter((item: any) =>
            item.status?.toLowerCase() === options.status.toLowerCase()
          )
        }

        const format = program.opts().output as OutputFormat
        outputService.print(items, format)
      } catch (error) {
        handleError(error)
      }
    })

  // queue create
  queue
    .command('create')
    .description('Create a new queue item')
    .requiredOption('-f, --function <name>', 'Function name')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-b, --bridge <name>', 'Bridge name')
    .option('-p, --priority <1-5>', 'Priority (1=highest)', '3')
    .option('--param <key=value>', 'Function parameters', (val, acc: string[]) => {
      acc.push(val)
      return acc
    }, [])
    .action(async (options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        // Parse parameters
        const params: Record<string, string> = {}
        for (const param of options.param || []) {
          const [key, ...valueParts] = param.split('=')
          params[key] = valueParts.join('=')
        }

        // Build proper queue vault using the queue service
        const queueVault = await withSpinner(
          'Building queue vault...',
          () => queueService.buildQueueVault({
            teamName: opts.team as string,
            machineName: opts.machine,
            bridgeName: opts.bridge,
            functionName: options.function,
            params,
            priority: parseInt(options.priority, 10),
          }),
          'Queue vault built'
        )

        const response = await withSpinner(
          `Creating queue item for function "${options.function}"...`,
          () => apiClient.post('/CreateQueueItem', {
            teamName: opts.team,
            machineName: opts.machine,
            bridgeName: opts.bridge,
            queueVault,
            priority: parseInt(options.priority, 10),
          }),
          'Queue item created'
        )

        const data = getFirstRow<QueueItemResponse>(response.resultSets)
        if (data?.taskId) {
          outputService.success(`Task ID: ${data.taskId}`)
        }
      } catch (error) {
        handleError(error)
      }
    })

  // queue trace
  queue
    .command('trace <taskId>')
    .description('Trace a queue item')
    .option('-w, --watch', 'Watch for updates')
    .option('--interval <ms>', 'Poll interval in milliseconds', '2000')
    .action(async (taskId, options) => {
      try {
        await authService.requireAuth()

        const fetchTrace = async () => {
          return apiClient.get('/GetQueueItemTrace', { taskId })
        }

        if (options.watch) {
          // Watch mode - poll until complete
          const interval = parseInt(options.interval, 10)
          let isComplete = false

          const spinner = startSpinner('Watching queue item...')

          while (!isComplete) {
            const response = await fetchTrace()
            const trace = getFirstRow<QueueItemResponse>(response.resultSets)

            if (trace) {
              spinner.text = `Status: ${trace.status} | ${trace.progress || 'No progress'}`

              // Check for terminal status
              const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED']
              if (trace.status && terminalStatuses.includes(trace.status.toUpperCase())) {
                isComplete = true
                stopSpinner(trace.status === 'COMPLETED', `Final status: ${trace.status}`)

                // Output final trace
                const format = program.opts().output as OutputFormat
                outputService.print(trace, format)
              }
            }

            if (!isComplete) {
              await new Promise(resolve => setTimeout(resolve, interval))
            }
          }
        } else {
          // Single fetch
          const response = await withSpinner(
            'Fetching queue trace...',
            fetchTrace,
            'Trace fetched'
          )

          const trace = getFirstRow<QueueItemResponse>(response.resultSets)
          const format = program.opts().output as OutputFormat

          if (trace) {
            outputService.print(trace, format)
          } else {
            outputService.info('No trace found for this task')
          }
        }
      } catch (error) {
        handleError(error)
      }
    })

  // queue cancel
  queue
    .command('cancel <taskId>')
    .description('Cancel a queue item')
    .action(async (taskId) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Cancelling task ${taskId}...`,
          () => apiClient.post('/CancelQueueItem', { taskId }),
          'Task cancelled'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // queue retry
  queue
    .command('retry <taskId>')
    .description('Retry a failed queue item')
    .action(async (taskId) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Retrying task ${taskId}...`,
          () => apiClient.post('/RetryFailedQueueItem', { taskId }),
          'Task retry initiated'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // queue delete
  queue
    .command('delete <taskId>')
    .description('Delete a queue item')
    .option('-f, --force', 'Skip confirmation')
    .action(async (taskId, options) => {
      try {
        await authService.requireAuth()

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete task ${taskId}? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting task ${taskId}...`,
          () => apiClient.post('/DeleteQueueItem', { taskId }),
          'Task deleted'
        )
      } catch (error) {
        handleError(error)
      }
    })
}
