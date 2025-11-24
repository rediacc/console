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

export function registerShortcuts(program: Command): void {
  // run - shortcut for queue create
  program
    .command('run <function>')
    .description('Run a function (shortcut for: queue create)')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-b, --bridge <name>', 'Bridge name')
    .option('-p, --priority <1-5>', 'Priority (1=highest)', '3')
    .option('--param <key=value>', 'Function parameters', (val, acc: string[]) => {
      acc.push(val)
      return acc
    }, [])
    .option('-w, --watch', 'Watch for completion')
    .action(async (functionName, options) => {
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
            functionName,
            params,
            priority: parseInt(options.priority, 10),
          }),
          'Queue vault built'
        )

        const response = await withSpinner(
          `Creating queue item for "${functionName}"...`,
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

          // Watch if requested
          if (options.watch) {
            outputService.info('Watching for completion...')
            const interval = 2000
            let isComplete = false

            const spinner = startSpinner('Monitoring task...')

            while (!isComplete) {
              const traceResponse = await apiClient.get('/GetQueueItemTrace', { taskId: data.taskId })
              const trace = getFirstRow<QueueItemResponse>(traceResponse.resultSets)

              if (trace) {
                spinner.text = `Status: ${trace.status} | ${trace.progress || 'No progress'}`

                const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED']
                if (trace.status && terminalStatuses.includes(trace.status.toUpperCase())) {
                  isComplete = true
                  stopSpinner(trace.status === 'COMPLETED', `Final status: ${trace.status}`)

                  const format = program.opts().output as OutputFormat
                  outputService.print(trace, format)
                }
              }

              if (!isComplete) {
                await new Promise(resolve => setTimeout(resolve, interval))
              }
            }
          }
        }
      } catch (error) {
        handleError(error)
      }
    })

  // trace - shortcut for queue trace
  program
    .command('trace <taskId>')
    .description('Trace a task (shortcut for: queue trace)')
    .option('-w, --watch', 'Watch for updates')
    .option('--interval <ms>', 'Poll interval in milliseconds', '2000')
    .action(async (taskId, options) => {
      try {
        await authService.requireAuth()

        const fetchTrace = async () => {
          return apiClient.get('/GetQueueItemTrace', { taskId })
        }

        if (options.watch) {
          const interval = parseInt(options.interval, 10)
          let isComplete = false

          const spinner = startSpinner('Watching task...')

          while (!isComplete) {
            const response = await fetchTrace()
            const trace = getFirstRow<QueueItemResponse>(response.resultSets)

            if (trace) {
              spinner.text = `Status: ${trace.status} | ${trace.progress || 'No progress'}`

              const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED']
              if (trace.status && terminalStatuses.includes(trace.status.toUpperCase())) {
                isComplete = true
                stopSpinner(trace.status === 'COMPLETED', `Final status: ${trace.status}`)

                const format = program.opts().output as OutputFormat
                outputService.print(trace, format)
              }
            }

            if (!isComplete) {
              await new Promise(resolve => setTimeout(resolve, interval))
            }
          }
        } else {
          const response = await withSpinner(
            'Fetching trace...',
            fetchTrace,
            'Trace fetched'
          )

          const trace = getFirstRow<QueueItemResponse>(response.resultSets)
          const format = program.opts().output as OutputFormat

          if (trace) {
            outputService.print(trace, format)
          } else {
            outputService.info('No trace found')
          }
        }
      } catch (error) {
        handleError(error)
      }
    })

  // cancel - shortcut for queue cancel
  program
    .command('cancel <taskId>')
    .description('Cancel a task (shortcut for: queue cancel)')
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

  // retry - shortcut for queue retry
  program
    .command('retry <taskId>')
    .description('Retry a failed task (shortcut for: queue retry)')
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
}
