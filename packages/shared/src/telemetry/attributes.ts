/**
 * Canonical telemetry attribute keys shared across TypeScript services.
 * Keep this aligned with private/renet/pkg/telemetry/attributes.go.
 */
export const TELEMETRY_ATTRIBUTES = {
  subscriptionId: 'subscription.id',
  subscriptionPlanCode: 'subscription.plan_code',
  subscriptionStatus: 'subscription.status',
  subscriptionSource: 'subscription.source',
  machineId: 'machine.id',
  machineName: 'machine.name',
  repositoryGuid: 'repository.guid',
  repositoryKind: 'repository.kind',
  teamName: 'team.name',
  functionName: 'function.name',
  executorType: 'executor.type',
  taskId: 'task.id',
} as const;

export const TELEMETRY_SUBSCRIPTION_SOURCES = {
  storedToken: 'stored_token',
  licenseReport: 'license_report',
  repoLicense: 'repo_license',
  subscriptionBlob: 'subscription_blob',
} as const;
