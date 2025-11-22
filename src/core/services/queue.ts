import { minifyJSON } from '../utils/json'
import functionsData from '../data/functions.json'
import type {
  QueueRequestContext,
  FunctionRequirements,
  QueueItem,
  QueueItemData,
  QueueItemStatus,
  ActiveTask,
} from '../types/queue'
import type { VaultContextData, VaultData, StorageSystemContextData } from '../types/vault'

// Optional chrome declaration for browser extensions
declare const chrome:
  | {
      runtime?: {
        id?: string
      }
    }
  | undefined

export type QueueNotificationLevel = 'info' | 'success' | 'warning' | 'error'

export interface QueueNotification {
  level: QueueNotificationLevel
  message: string
}

export type QueueMonitoringEvent =
  | { type: 'task-start'; taskId: string; data: QueueItemData }
  | { type: 'task-status'; taskId: string; status: 'completed' | 'failed' | 'cancelled' }

export interface QueueServiceDependencies {
  emitNotification?: (notification: QueueNotification) => void
  emitMonitoringEvent?: (event: QueueMonitoringEvent) => void
}

type QueueListener = (queue: QueueItem[]) => void
type QueueItemListener = (item: QueueItem | undefined) => void

export class QueueService {
  private readonly builder = new QueueVaultBuilder()
  private readonly manager: QueueStateManager

  constructor(dependencies: QueueServiceDependencies = {}) {
    this.manager = new QueueStateManager({
      emitNotification: dependencies.emitNotification,
      emitMonitoringEvent: dependencies.emitMonitoringEvent,
    })
  }

  getFunctionRequirements(functionName: string): FunctionRequirements {
    return this.builder.getFunctionRequirements(functionName)
  }

  async buildQueueVault(context: QueueRequestContext): Promise<string> {
    return this.builder.buildQueueVault(context)
  }

  async addToQueue(data: QueueItemData, submitFunction: QueueItem['submitFunction']): Promise<string> {
    return this.manager.addToQueue(data, submitFunction)
  }

  getQueue(): QueueItem[] {
    return this.manager.getQueue()
  }

  getQueueStats() {
    return this.manager.getQueueStats()
  }

  subscribe(listener: QueueListener): () => void {
    return this.manager.subscribe(listener)
  }

  subscribeToQueueItem(queueId: string, listener: QueueItemListener): () => void {
    return this.manager.subscribeToQueueItem(queueId, listener)
  }

  retryItem(id: string) {
    this.manager.retryItem(id)
  }

  removeFromQueue(id: string) {
    this.manager.removeFromQueue(id)
  }

  clearCompleted() {
    this.manager.clearCompleted()
  }

  getQueuePosition(id: string): number {
    return this.manager.getQueuePosition(id)
  }

  getQueueItem(queueId: string) {
    return this.manager.getQueueItem(queueId)
  }

  updateTaskStatus(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    this.manager.updateTaskStatus(taskId, status)
  }

  getActiveTasks(): ActiveTask[] {
    return this.manager.getActiveTasks()
  }
}

class QueueStateManager {
  private queue: QueueItem[] = []
  private listeners: QueueListener[] = []
  private readonly MAX_RETRIES = 3
  private readonly SUBMISSION_DELAY = 100
  private readonly HIGHEST_PRIORITY = 1
  private isProcessing = false
  private processingInterval: ReturnType<typeof setInterval> | null = null
  private activeTasks: Map<string, ActiveTask> = new Map()
  private taskIdToBridge: Map<string, string> = new Map()

  constructor(
    private readonly options: {
      emitNotification?: (notification: QueueNotification) => void
      emitMonitoringEvent?: (event: QueueMonitoringEvent) => void
    },
  ) {
    if (this.isExtensionContext()) {
      setTimeout(() => this.startProcessing(), 1200)
    } else {
      this.startProcessing()
    }
  }

  private isExtensionContext(): boolean {
    try {
      return typeof chrome !== 'undefined' && chrome?.runtime !== undefined && chrome.runtime.id !== undefined
    } catch {
      return false
    }
  }

  private notify(level: QueueNotificationLevel, message: string) {
    this.options.emitNotification?.({ level, message })
  }

  private emitMonitoringEvent(event: QueueMonitoringEvent) {
    this.options.emitMonitoringEvent?.(event)
  }

  private hasActivePriorityTask(bridgeName?: string, excludeItemId?: string): boolean {
    if (!bridgeName) {
      return false
    }
    const activeTask = this.activeTasks.get(bridgeName)
    if (activeTask && activeTask.priority === this.HIGHEST_PRIORITY) {
      return true
    }

    return this.queue.some(
      (item) =>
        item.id !== excludeItemId &&
        item.data.bridgeName === bridgeName &&
        item.data.priority === this.HIGHEST_PRIORITY &&
        ['pending', 'submitting'].includes(item.status),
    )
  }

  private cancelExistingTasks(bridgeName?: string, machineName?: string) {
    if (!bridgeName || !machineName) {
      return
    }
    this.queue.forEach((item) => {
      if (
        item.data.bridgeName === bridgeName &&
        item.data.machineName === machineName &&
        item.status === 'pending'
      ) {
        item.status = 'cancelled'
      }
    })
  }

  private trackActiveTask(task: ActiveTask) {
    this.activeTasks.set(task.bridgeName, task)
    if (task.priority === this.HIGHEST_PRIORITY) {
      this.taskIdToBridge.set(task.taskId, task.bridgeName)
    }
  }

  private async startMonitoringTask(taskId: string, data: QueueItemData) {
    this.emitMonitoringEvent({
      type: 'task-start',
      taskId,
      data,
    })
  }

  async addToQueue(data: QueueItemData, submitFunction: QueueItem['submitFunction']): Promise<string> {
    const id = this.generateQueueId()
    const queuedItem: QueueItem = {
      id,
      data,
      retryCount: 0,
      status: 'pending',
      timestamp: Date.now(),
      submitFunction,
    }

    const isHighestPriority = data.priority === this.HIGHEST_PRIORITY
    if (isHighestPriority) {
      if (this.hasActivePriorityTask(data.bridgeName)) {
        this.notify(
          'warning',
          `You already have a highest priority task running on bridge ${data.bridgeName}. Please wait for it to complete.`,
        )
        throw new Error('Already have a priority 1 task on this bridge')
      }

      this.cancelExistingTasks(data.bridgeName, data.machineName)
      this.queue.push(queuedItem)
      this.notifyListeners()
      this.notify('info', `Highest priority task queued. Position: ${this.queue.length}`)
      if (!this.isProcessing) {
        this.startProcessing()
      }
      return id
    }

    try {
      queuedItem.status = 'submitting'
      const response = await submitFunction(data)
      queuedItem.status = 'submitted'
      return (response as { taskId?: string })?.taskId || id
    } catch (error) {
      queuedItem.status = 'failed'
      throw error instanceof Error ? error : new Error('Failed to submit queue item')
    }
  }

  getQueue(): QueueItem[] {
    return [...this.queue]
  }

  getQueueStats() {
    return {
      total: this.queue.length,
      pending: this.queue.filter((item) => item.status === 'pending').length,
      submitting: this.queue.filter((item) => item.status === 'submitting').length,
      submitted: this.queue.filter((item) => item.status === 'submitted').length,
      failed: this.queue.filter((item) => item.status === 'failed').length,
      highestPriority: this.queue.filter((item) => item.data.priority === this.HIGHEST_PRIORITY).length,
    }
  }

  subscribe(listener: QueueListener): () => void {
    this.listeners.push(listener)
    listener(this.getQueue())
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener)
    }
  }

  subscribeToQueueItem(queueId: string, callback: QueueItemListener): () => void {
    const listener = (queue: QueueItem[]) => {
      const item = queue.find((q) => q.id === queueId)
      callback(item)
    }
    this.listeners.push(listener)
    listener(this.queue)
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener)
    }
  }

  private notifyListeners() {
    const queue = this.getQueue()
    this.listeners.forEach((listener) => listener(queue))
  }

  private startProcessing() {
    if (this.isProcessing) return
    this.isProcessing = true
    this.processingInterval = setInterval(() => {
      void this.processQueue()
    }, this.SUBMISSION_DELAY)
  }

  stopProcessing() {
    this.isProcessing = false
    if (this.processingInterval) {
      clearInterval(this.processingInterval)
      this.processingInterval = null
    }
  }

  private async processQueue() {
    const pendingItem = this.queue.find((item) => item.status === 'pending')

    if (!pendingItem) {
      this.queue = this.queue.filter((item) => item.status === 'pending' || item.status === 'submitting')
      if (this.queue.length === 0) {
        this.stopProcessing()
      }
      this.notifyListeners()
      return
    }

    if (
      pendingItem.data.priority === this.HIGHEST_PRIORITY &&
      this.hasActivePriorityTask(pendingItem.data.bridgeName, pendingItem.id)
    ) {
      pendingItem.status = 'cancelled'
      this.notifyListeners()
      this.notify('info', 'Task cancelled: Already have a priority 1 task on this bridge')
      return
    }

    pendingItem.status = 'submitting'
    this.notifyListeners()

    try {
      const response = await pendingItem.submitFunction(pendingItem.data)
      const taskId = (response as { taskId?: string })?.taskId

      if (taskId && pendingItem.data.priority === this.HIGHEST_PRIORITY && pendingItem.data.bridgeName) {
        pendingItem.taskId = taskId
        const activeTask: ActiveTask = {
          bridgeName: pendingItem.data.bridgeName,
          machineName: pendingItem.data.machineName ?? '',
          taskId,
          priority: pendingItem.data.priority ?? this.HIGHEST_PRIORITY,
          status: 'pending',
          timestamp: Date.now(),
        }
        this.trackActiveTask(activeTask)
        await this.startMonitoringTask(taskId, pendingItem.data)
      }

      pendingItem.status = 'submitted'
      this.notifyListeners()
      if (taskId) {
        this.notify('success', `Queue item submitted successfully (ID: ${taskId})`)
      } else {
        this.notify('success', 'Queue item submitted successfully')
      }
    } catch (error) {
      pendingItem.retryCount += 1
      if (pendingItem.retryCount < this.MAX_RETRIES) {
        pendingItem.status = 'pending'
        this.notify('warning', `Queue submission failed, will retry (${pendingItem.retryCount}/${this.MAX_RETRIES})`)
      } else {
        pendingItem.status = 'failed'
        const message = error instanceof Error ? error.message : 'Unknown error'
        this.notify('error', `Queue submission failed after ${this.MAX_RETRIES} attempts: ${message}`)
      }
      this.notifyListeners()
    }
  }

  removeFromQueue(id: string) {
    this.queue = this.queue.filter((item) => item.id !== id)
    this.notifyListeners()
  }

  retryItem(id: string) {
    const item = this.queue.find((queueItem) => queueItem.id === id)
    if (item && item.status === 'failed') {
      item.status = 'pending'
      item.retryCount = 0
      this.notifyListeners()
      if (!this.isProcessing) {
        this.startProcessing()
      }
    }
  }

  clearCompleted() {
    this.queue = this.queue.filter((item) => item.status === 'pending' || item.status === 'submitting')
    this.notifyListeners()
  }

  getQueuePosition(id: string): number {
    const pendingItems = this.queue.filter((item) => item.status === 'pending')
    const index = pendingItems.findIndex((item) => item.id === id)
    return index === -1 ? -1 : index + 1
  }

  getQueueItem(queueId: string): QueueItem | undefined {
    return this.queue.find((item) => item.id === queueId)
  }

  updateTaskStatus(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    let bridgeCleared: string | null = null
    const mappedBridge = this.taskIdToBridge.get(taskId)
    if (mappedBridge) {
      const activeTask = this.activeTasks.get(mappedBridge)
      if (activeTask && activeTask.taskId === taskId) {
        if (this.isTerminalStatus(status)) {
          this.activeTasks.delete(mappedBridge)
          this.taskIdToBridge.delete(taskId)
          bridgeCleared = mappedBridge
        }
      }
    }

    if (!bridgeCleared) {
      for (const [bridgeName, task] of this.activeTasks) {
        if (task.taskId === taskId && task.priority === this.HIGHEST_PRIORITY) {
          if (this.isTerminalStatus(status)) {
            this.activeTasks.delete(bridgeName)
            this.taskIdToBridge.delete(taskId)
            bridgeCleared = bridgeName
            break
          }
        }
      }
    }

    if (!bridgeCleared) {
      const queueItem = this.queue.find((item) => item.taskId === taskId)
      if (queueItem && queueItem.data.priority === this.HIGHEST_PRIORITY) {
        const bridgeName = queueItem.data.bridgeName
        if (bridgeName && this.activeTasks.has(bridgeName)) {
          const activeTask = this.activeTasks.get(bridgeName)
          if (activeTask && activeTask.taskId === taskId) {
            this.activeTasks.delete(bridgeName)
            this.taskIdToBridge.delete(taskId)
            bridgeCleared = bridgeName
          }
        }

        if (this.isTerminalStatus(status)) {
          queueItem.status = 'submitted'
        }
      }
    }

    this.emitMonitoringEvent({
      type: 'task-status',
      taskId,
      status,
    })

    this.notifyListeners()
  }

  getActiveTasks(): ActiveTask[] {
    return Array.from(this.activeTasks.values())
  }

  private generateQueueId(): string {
    return `queue-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
  }

  private isTerminalStatus(status: QueueItemStatus): boolean {
    return status === 'completed' || status === 'failed' || status === 'cancelled'
  }
}

class QueueVaultBuilder {
  getFunctionRequirements(functionName: string): FunctionRequirements {
    const functionKey = functionName as keyof typeof functionsData.functions
    return functionsData.functions[functionKey]?.requirements || {}
  }

  async buildQueueVault(context: QueueRequestContext): Promise<string> {
    try {
      const requirements = this.getFunctionRequirements(context.functionName)
      const queueVaultData: {
        function: string
        machine: string
        team: string
        params: Record<string, unknown>
        contextData: VaultContextData
      } = {
        function: context.functionName,
        machine: context.machineName || '',
        team: context.teamName,
        params: context.params,
        contextData: {
          GENERAL_SETTINGS: this.buildGeneralSettings(context),
        } as VaultContextData,
      }

      if (requirements.machine && context.machineVault && context.machineName) {
        queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {}
        queueVaultData.contextData.MACHINES[context.machineName] = this.extractMachineData(context.machineVault)
        const destinationName = (context.params as Record<string, string>).to
        if (
          context.functionName === 'deploy' &&
          destinationName &&
          destinationName !== context.machineName &&
          context.destinationMachineVault
        ) {
          queueVaultData.contextData.MACHINES[destinationName] = this.extractMachineData(
            context.destinationMachineVault,
          )
        }
      }

      // For ssh_test with bridge-only tasks (no machine name), include SSH details directly in vault data
      if (context.functionName === 'ssh_test' && context.machineVault && !context.machineName) {
        const machineData = this.extractMachineData(context.machineVault)
        const parsedVault =
          typeof context.machineVault === 'string' ? JSON.parse(context.machineVault) : context.machineVault
        if ((parsedVault as Record<string, unknown>).ssh_password) {
          ;(machineData as Record<string, unknown>).ssh_password = (parsedVault as Record<string, unknown>).ssh_password
        }
        // Include the SSH connection info directly in the root vault data for bridge-only tasks
        Object.assign(queueVaultData, machineData)
      }

      if (context.functionName === 'backup') {
        const targets = this.getParamArray(context.params as Record<string, unknown>, 'storages')
        if (!targets.length) {
          const fallbackTarget = this.getParamValue(context.params as Record<string, unknown>, 'to')
          if (fallbackTarget) {
            targets.push(fallbackTarget)
          }
        }
        if (targets.length > 0) {
          queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {}
          targets.forEach((storageName, index) => {
            const storageVault =
              context.additionalStorageData?.[storageName] ||
              (index === 0 ? context.destinationStorageVault : undefined)
            if (storageVault) {
              queueVaultData.contextData.STORAGE_SYSTEMS![storageName] = this.buildStorageConfig(storageVault)
            }
          })
        }
      }

      if (context.functionName === 'list') {
        const sourceName = this.getParamValue(context.params as Record<string, unknown>, 'from')
        if (sourceName && context.additionalStorageData?.[sourceName]) {
          queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {}
          queueVaultData.contextData.STORAGE_SYSTEMS[sourceName] = this.buildStorageConfig(
            context.additionalStorageData[sourceName],
          )
        }

        if (sourceName && context.additionalMachineData?.[sourceName]) {
          queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {}
          queueVaultData.contextData.MACHINES[sourceName] = this.extractMachineData(
            context.additionalMachineData[sourceName],
          )
        }
      }

      // Handle pull function with other machines (via additionalMachineData)
      if (
        context.functionName === 'pull' &&
        (context.params as Record<string, string>).sourceType === 'machine' &&
        (context.params as Record<string, string>).from
      ) {
        const fromName = (context.params as Record<string, string>).from
        if (context.additionalMachineData?.[fromName]) {
          queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {}
          queueVaultData.contextData.MACHINES[fromName] = this.extractMachineData(
            context.additionalMachineData[fromName],
          )
        }
      }

      // Handle pull function with storage systems (via additionalStorageData)
      if (
        context.functionName === 'pull' &&
        (context.params as Record<string, string>).sourceType === 'storage' &&
        (context.params as Record<string, string>).from
      ) {
        const fromName = (context.params as Record<string, string>).from
        if (context.additionalStorageData?.[fromName]) {
          queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {}
          queueVaultData.contextData.STORAGE_SYSTEMS[fromName] = this.buildStorageConfig(
            context.additionalStorageData[fromName],
          )
        }
      }

      // Add REPO_CREDENTIALS after MACHINES if repository is required
      if (requirements.repository && context.repositoryGuid && context.repositoryVault) {
        try {
          const repoVault =
            typeof context.repositoryVault === 'string'
              ? JSON.parse(context.repositoryVault)
              : context.repositoryVault

          if (repoVault.credential) {
            queueVaultData.contextData.REPO_CREDENTIALS = {
              [context.repositoryGuid]: repoVault.credential,
            }
          }
        } catch {
          // Ignore vault parsing errors - repository vault is optional
        }
      }

      // Add REPO_LOOPBACK_IP if repository loopback IP is provided
      if (requirements.repository && context.repositoryLoopbackIp) {
        queueVaultData.contextData.REPO_LOOPBACK_IP = context.repositoryLoopbackIp
      }

      // Add REPO_NETWORK_MODE if repository network mode is provided
      if (requirements.repository && context.repositoryNetworkMode) {
        queueVaultData.contextData.REPO_NETWORK_MODE = context.repositoryNetworkMode
      }

      // Add REPO_TAG if repository tag is provided
      if (requirements.repository && context.repositoryTag !== undefined) {
        queueVaultData.contextData.REPO_TAG = context.repositoryTag
      }

      // For functions like 'list' that need all REPO_CREDENTIALS
      // Repository credentials are passed separately, not from company vault
      if (context.functionName === 'list' && context.allRepositoryCredentials) {
        queueVaultData.contextData.REPO_CREDENTIALS = context.allRepositoryCredentials
      }

      // For 'mount', 'unmount', 'new', and 'up' functions that need PLUGINS
      if (
        ['mount', 'unmount', 'new', 'up'].includes(context.functionName) &&
        context.companyVault &&
        (context.companyVault as VaultData).PLUGINS
      ) {
        queueVaultData.contextData.PLUGINS = (context.companyVault as VaultData).PLUGINS as VaultData
      }

      const dataExtractors: Array<[boolean | undefined, keyof VaultContextData, () => VaultData]> = [
        [requirements.company, 'company', () => this.extractCompanyData(context.companyVault)],
        [
          Boolean(requirements.repository && context.repositoryGuid),
          'repository',
          () => this.extractRepositoryData(context.repositoryVault, context.repositoryGuid ?? '', context.companyVault),
        ],
        [
          requirements.storage && Boolean(context.storageName),
          'storage',
          () => this.extractStorageData(context.storageVault, context.storageName!),
        ],
        [
          requirements.bridge && Boolean(context.bridgeName),
          'bridge',
          () => this.extractBridgeData(context.bridgeVault, context.bridgeName!),
        ],
        [requirements.plugin, 'plugins', () => this.extractPluginData(context.companyVault)],
      ]

      dataExtractors.forEach(([condition, key, extractor]) => {
        if (condition) {
          queueVaultData.contextData[key] = extractor()
        }
      })

      return minifyJSON(JSON.stringify(queueVaultData))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      throw new Error(`Failed to build queue vault: ${message}`)
    }
  }

  private extractCompanyData(companyVault: VaultData | string | null | undefined): VaultData {
    if (!companyVault) return {}
    if (typeof companyVault === 'string') {
      try {
        return JSON.parse(companyVault) as VaultData
      } catch {
        return {}
      }
    }
    const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS } =
      companyVault as Record<string, unknown>
    return { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS }
  }

  private extractMachineData(machineVault: VaultData | string | null | undefined): VaultData {
    if (!machineVault) return {}
    const vault = typeof machineVault === 'string' ? JSON.parse(machineVault) : machineVault
    const fieldMappings = [
      { targetKey: 'IP', sources: ['ip', 'IP'] },
      { targetKey: 'USER', sources: ['user', 'USER'] },
      { targetKey: 'DATASTORE', sources: ['datastore', 'DATASTORE'] },
      { targetKey: 'HOST_ENTRY', sources: ['host_entry', 'HOST_ENTRY'] },
    ]
    return fieldMappings.reduce<Record<string, unknown>>((target, { targetKey, sources }) => {
      const sourceKey = sources.find((source) => (vault as Record<string, unknown>)[source] !== undefined)
      if (sourceKey) {
        target[targetKey] = (vault as Record<string, unknown>)[sourceKey]
      }
      return target
    }, {})
  }

  private extractRepositoryData(
    repositoryVault: VaultData | string | null | undefined,
    repositoryGuid: string,
    _companyVault: VaultData | string | null | undefined,
  ): VaultData {
    const repository = typeof repositoryVault === 'string' ? JSON.parse(repositoryVault) : repositoryVault
    return {
      guid: repositoryGuid,
      ...(repository && {
        size: (repository as Record<string, unknown>).size,
        credential: (repository as Record<string, unknown>).credential,
      }),
    }
  }

  private extractStorageData(storageVault: VaultData | string | null | undefined, storageName: string): VaultData {
    if (!storageVault) return { name: storageName }
    if (typeof storageVault === 'string') {
      return { name: storageName, ...JSON.parse(storageVault) }
    }
    return { name: storageName, ...storageVault }
  }

  private extractBridgeData(bridgeVault: VaultData | string | null | undefined, bridgeName: string): VaultData {
    if (!bridgeVault) return { name: bridgeName }
    if (typeof bridgeVault === 'string') {
      return { name: bridgeName, ...JSON.parse(bridgeVault) }
    }
    return { name: bridgeName, ...bridgeVault }
  }

  private extractPluginData(companyVault: VaultData | string | null | undefined): VaultData {
    const company = typeof companyVault === 'string' ? JSON.parse(companyVault) : companyVault
    return (company as Record<string, unknown>)?.PLUGINS ? ((company as Record<string, unknown>).PLUGINS as VaultData) : {}
  }

  private buildStorageConfig(vault: VaultData | string): StorageSystemContextData {
    const parsedVault = typeof vault === 'string' ? JSON.parse(vault) : vault
    const provider = (parsedVault as Record<string, string>).provider
    if (!provider) {
      throw new Error('Storage provider type is required')
    }

    const storageConfig: StorageSystemContextData = {
      RCLONE_REDIACC_BACKEND: provider,
    }

    const folder = (parsedVault as Record<string, unknown>).folder
    if (folder !== undefined && folder !== null) {
      storageConfig.RCLONE_REDIACC_FOLDER = folder
    }

    const parameters = (parsedVault as Record<string, unknown>).parameters
    if (parameters) {
      storageConfig.RCLONE_PARAMETERS = parameters
    }

    const providerPrefix = `RCLONE_${provider.toUpperCase()}`
    Object.entries(parsedVault).forEach(([key, value]) => {
      if (['provider', 'folder', 'parameters'].includes(key)) {
        return
      }
      const envKey = `${providerPrefix}_${key.toUpperCase()}`
      storageConfig[envKey] = value
    })

    return storageConfig
  }

  private getParamArray(params: Record<string, unknown>, key: string): string[] {
    const value = params[key]
    if (Array.isArray(value)) {
      return value.filter((item): item is string => typeof item === 'string')
    }
    if (typeof value === 'string' && value.length > 0) {
      return [value]
    }
    return []
  }

  private getParamValue(params: Record<string, unknown>, key: string): string | undefined {
    const value = params[key]
    return typeof value === 'string' && value.length > 0 ? value : undefined
  }

  private buildGeneralSettings(context: QueueRequestContext): VaultData {
    const generalSettings: VaultData = {}
    if (context.companyCredential) {
      generalSettings.COMPANY_ID = context.companyCredential
    }

    generalSettings.SYSTEM_API_URL = this.getSystemApiUrl()
    generalSettings.TEAM_NAME = context.teamName
    if (context.machineName) {
      generalSettings.MACHINE_NAME = context.machineName
    }

    if (context.companyVault && typeof context.companyVault === 'object') {
      this.addCompanyVaultToGeneralSettings(generalSettings, context.companyVault)
    }

    if (context.teamVault && typeof context.teamVault === 'object') {
      this.addTeamVaultToGeneralSettings(generalSettings, context.teamVault)
    }

    return generalSettings
  }

  private addCompanyVaultToGeneralSettings(generalSettings: VaultData, companyVault: VaultData) {
    const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, PLUGINS } = companyVault as Record<string, unknown>
    if (UNIVERSAL_USER_ID) generalSettings.UNIVERSAL_USER_ID = UNIVERSAL_USER_ID
    if (UNIVERSAL_USER_NAME) generalSettings.UNIVERSAL_USER_NAME = UNIVERSAL_USER_NAME
    if (DOCKER_JSON_CONF) generalSettings.DOCKER_JSON_CONF = DOCKER_JSON_CONF
    if (PLUGINS) generalSettings.PLUGINS = PLUGINS
  }

  private addTeamVaultToGeneralSettings(generalSettings: VaultData, teamVault: VaultData) {
    const sshKeyFields = ['SSH_PRIVATE_KEY', 'SSH_PUBLIC_KEY']
    sshKeyFields.forEach((field) => {
      const value = (teamVault as Record<string, unknown>)[field]
      if (value && typeof value === 'string') {
        generalSettings[field] = this.ensureBase64(value)
      }
    })
  }

  private getSystemApiUrl(): string {
    if (typeof window !== 'undefined') {
      const baseUrl = window.location.origin
      return `${baseUrl}/api`
    }
    return ''
  }

  private ensureBase64(value: string): string {
    if (!value) return value
    return this.isBase64(value) ? value : this.encodeToBase64(value)
  }

  private isBase64(value: string): boolean {
    const base64Pattern = /^[A-Za-z0-9+/]*={0,2}$/
    const valueWithoutWhitespace = value.replace(/\s/g, '')
    return base64Pattern.test(valueWithoutWhitespace) && valueWithoutWhitespace.length % 4 === 0
  }

  private encodeToBase64(value: string): string {
    try {
      return btoa(value)
    } catch {
      // Handle non-Latin1 characters by encoding to UTF-8 first
      const utf8Bytes = new TextEncoder().encode(value)
      const binaryString = Array.from(utf8Bytes)
        .map((byte) => String.fromCharCode(byte))
        .join('')
      return btoa(binaryString)
    }
  }
}
