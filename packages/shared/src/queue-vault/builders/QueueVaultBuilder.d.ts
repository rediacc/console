import type { QueueRequestContext, FunctionRequirements } from '../types';
export interface QueueVaultBuilderConfig {
  getApiUrl: () => string;
  encodeBase64: (value: string) => string;
}
export declare class QueueVaultBuilder {
  private config;
  constructor(config: QueueVaultBuilderConfig);
  getFunctionRequirements(functionName: string): FunctionRequirements;
  buildQueueVault(context: QueueRequestContext): Promise<string>;
  private extractCompanyData;
  private extractMachineData;
  private extractRepositoryData;
  private extractStorageData;
  private extractBridgeData;
  private extractPluginData;
  private buildStorageConfig;
  private buildGeneralSettings;
  private addCompanyVaultToGeneralSettings;
  private addTeamVaultToGeneralSettings;
  private ensureBase64;
}
//# sourceMappingURL=QueueVaultBuilder.d.ts.map
