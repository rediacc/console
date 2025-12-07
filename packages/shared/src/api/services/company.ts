import { endpoints } from '../../endpoints';
import { normalizeRecord } from '../normalizer';
import { fixTripleEncodedFields, parseDoubleEncodedJson } from '../responseTransforms';
import type { ApiClient } from './types';
import type {
  CompanyProfile,
  CompanyDashboardData,
  CompanyVaultDetails,
  CompanyVaultCollections,
  CompanyVaultUpdateResult,
  CompanyExportData,
  CompanyImportResult,
  CompanyBlockUserRequestsResult,
  CompanyDropdownData,
  CompanyDataGraph,
  CompanySubscription,
  CompanyResourceLimit,
  CompanyAccountHealth,
  CompanyFeatureAccess,
  CompanyPlanLimits,
  CompanyQueueStats,
  CompanyCephStats,
  CompanySubscriptionDetail,
  CephTeamBreakdown,
  QueueTeamIssue,
  QueueMachineIssue,
} from '../../types';
import type { ApiResponse } from '../../types/api';
import type {
  UpdateCompanyVaultParams,
  UpdateCompanyVaultsParams,
  ImportCompanyDataParams,
  UpdateCompanyBlockUserRequestsParams,
  GetLookupDataParams,
} from '../../types';

export function createCompanyService(client: ApiClient) {
  return {
    getInfo: async (): Promise<CompanyProfile | null> => {
      const response = await client.get(endpoints.company.getUserCompany);
      const row = getRowByIndex<CompanyProfile>(response, 0);
      return row ? (normalizeRecord(row as Record<string, unknown>) as CompanyProfile) : null;
    },

    getDashboard: async (): Promise<CompanyDashboardData> => {
      const response = await client.post(endpoints.company.getCompanyDashboard, {});
      return parseDashboard(response);
    },

    getDataGraph: async (): Promise<CompanyDataGraph> => {
      const response = await client.post(endpoints.company.getCompanyDataGraph, {});
      return parseCompanyDataGraph(response);
    },

    getVault: async (): Promise<CompanyVaultDetails> => {
      const response = await client.get(endpoints.company.getCompanyVault);
      const row = getRowByIndex<{
        vaultContent?: string;
        vaultVersion?: number;
        companyCredential?: string | null;
      }>(response, 1);
      return {
        vault: row?.vaultContent || '{}',
        vaultVersion: row?.vaultVersion ?? 1,
        companyCredential: row?.companyCredential ?? null,
      };
    },

    getAllVaults: async (filters?: Record<string, unknown>): Promise<CompanyVaultCollections> => {
      const response = await client.get(endpoints.company.getCompanyVaults, filters);
      const vaults = getRowsByIndex<Record<string, unknown>>(response, 1).map((vault) =>
        normalizeRecord(vault)
      );
      const bridgesWithRequestToken = getRowsByIndex<Record<string, unknown>>(response, 2).map(
        (vault) => normalizeRecord(vault)
      );
      return {
        vaults,
        bridgesWithRequestToken,
      };
    },

    updateVault: (params: UpdateCompanyVaultParams) =>
      client.post(endpoints.company.updateCompanyVault, params),

    updateAllVaults: async (params: UpdateCompanyVaultsParams): Promise<CompanyVaultUpdateResult> => {
      const response = await client.post(endpoints.company.updateCompanyVaults, params);

      const row = getRowByIndex<{ result?: { totalUpdated?: number; failedCount?: number } }>(
        response,
        0
      );
      const result = row?.result ?? {};
      return {
        totalUpdated: result.totalUpdated ?? 0,
        failedCount: result.failedCount ?? 0,
      };
    },

    updateVaultProtocol: async (vaultCompany: string | null): Promise<void> => {
      await client.post(endpoints.company.updateCompanyVaultProtocol, { vaultCompany });
    },

    exportData: async (): Promise<CompanyExportData> => {
      const response = await client.get(endpoints.company.exportCompanyData);
      const row = getRowByIndex<Record<string, unknown>>(response, 1);
      return row ? normalizeRecord(row) : {};
    },

    importData: async (params: ImportCompanyDataParams): Promise<CompanyImportResult> => {
      const response = await client.post(endpoints.company.importCompanyData, params);
      const row = getRowByIndex<CompanyImportResult>(response, 0);
      return {
        importedCount: row?.importedCount ?? 0,
        skippedCount: row?.skippedCount ?? 0,
        errorCount: row?.errorCount ?? 0,
      };
    },

    updateBlockUserRequests: async (
      params: UpdateCompanyBlockUserRequestsParams
    ): Promise<CompanyBlockUserRequestsResult> => {
      const response = await client.post(endpoints.company.updateCompanyBlockUserRequests, params);
      const row = getRowByIndex<CompanyBlockUserRequestsResult>(response, 0);
      return {
        deactivatedCount: row?.deactivatedCount ?? 0,
      };
    },

    getLookupData: async (params?: GetLookupDataParams): Promise<CompanyDropdownData> => {
      const response = await client.get(endpoints.company.getLookupData, params ?? {});
      const row =
        getRowByIndex<Record<string, unknown>>(response, 1) ??
        getRowByIndex<Record<string, unknown>>(response, 0);

      if (!row) {
        return createEmptyDropdownData();
      }

      const dropdownValuesRaw =
        typeof row.dropdownValues === 'string'
          ? safeJsonParse(row.dropdownValues, {})
          : row.dropdownValues;
      const parsedValues: Record<string, unknown> =
        dropdownValuesRaw && typeof dropdownValuesRaw === 'object'
          ? { ...(dropdownValuesRaw as Record<string, unknown>) }
          : {};

      DROPDOWN_FIELDS.forEach((field) => {
        parsedValues[field] = parseJsonField(parsedValues, field);
      });

      if (Array.isArray(parsedValues.bridgesByRegion)) {
        parsedValues.bridgesByRegion = (
          parsedValues.bridgesByRegion as Array<Record<string, unknown>>
        ).map((region) => ({
          ...region,
          bridges: parseJsonField(region, 'bridges'),
        }));
      }

      const baseData = createEmptyDropdownData();
      const baseRow = row && typeof row === 'object' ? (row as Record<string, unknown>) : {};
      const parsedRecord =
        parsedValues && typeof parsedValues === 'object'
          ? (parsedValues as Record<string, unknown>)
          : {};

      return {
        ...baseData,
        ...baseRow,
        ...parsedRecord,
      } as CompanyDropdownData;
    },

    registerCompany: (
      companyName: string,
      userEmail: string,
      passwordHash: string,
      captchaToken?: string,
      languagePreference: string = 'en'
    ) => {
      const payload: Record<string, unknown> = {
        companyName,
        userEmailAddress: userEmail,
        languagePreference,
      };
      if (captchaToken && captchaToken.trim() !== '') {
        payload.captchaToken = captchaToken;
      }
      return client.post(endpoints.company.createCompany, payload, {
        headers: {
          'Rediacc-UserEmail': userEmail,
          'Rediacc-UserHash': passwordHash,
        },
      });
    },
  };
}

const DROPDOWN_FIELDS = [
  'teams',
  'allTeams',
  'regions',
  'bridgesByRegion',
  'machines',
  'bridges',
  'machinesByTeam',
  'users',
  'permissionGroups',
  'permissions',
  'subscriptionPlans',
] as const;

function createEmptyDropdownData(): CompanyDropdownData {
  return {
    teams: [],
    allTeams: [],
    regions: [],
    machines: [],
    bridges: [],
    bridgesByRegion: [],
    machinesByTeam: [],
    users: [],
    permissionGroups: [],
    permissions: [],
    subscriptionPlans: [],
  };
}

function parseDashboard(response: ApiResponse): CompanyDashboardData {
  const row = getRowByIndex<{ subscriptionAndResourcesJson?: string }>(response, 1);
  const payload = row?.subscriptionAndResourcesJson
    ? safeJsonParse<Record<string, unknown>>(row.subscriptionAndResourcesJson, {})
    : null;

  if (!payload) {
    throw new Error('Invalid dashboard payload');
  }

  const normalized = normalizeRecord(payload);
  const companyInfo = parseObject<CompanyProfile>(normalized.companyInfo) ?? { companyName: '' };

  const activeSubscription = parseObject<CompanySubscription>(normalized.activeSubscription);
  const resources = parseObjectArray<CompanyResourceLimit>(normalized.resources);
  const accountHealth = parseObject<CompanyAccountHealth>(normalized.accountHealth);
  const featureAccess = parseObject<CompanyFeatureAccess>(normalized.featureAccess);
  const planLimits = parseObject<CompanyPlanLimits>(normalized.planLimits);
  const queueStats = parseObject<CompanyQueueStats>(normalized.queueStats);
  const cephStats = parseObject<CompanyCephStats>(normalized.cephStats);
  const allActiveSubscriptions = parseObjectArray<CompanySubscriptionDetail>(
    normalized.allActiveSubscriptions
  );

  if (cephStats && cephStats.team_breakdown) {
    cephStats.team_breakdown = parseObjectArray<CephTeamBreakdown>(cephStats.team_breakdown);
  }

  if (queueStats) {
    queueStats.teamIssues = parseObjectArray<QueueTeamIssue>(queueStats.teamIssues);
    queueStats.machineIssues = parseObjectArray<QueueMachineIssue>(queueStats.machineIssues);
  }

  return {
    companyInfo,
    activeSubscription: activeSubscription ?? null,
    resources,
    accountHealth: accountHealth ?? null,
    featureAccess: featureAccess ?? null,
    planLimits: planLimits ?? null,
    queueStats: queueStats ?? undefined,
    cephStats: cephStats ?? undefined,
    allActiveSubscriptions,
  };
}

function parseCompanyDataGraph(response: ApiResponse): CompanyDataGraph {
  const row = getRowByIndex<{ companyDataGraph?: string }>(response, 1);
  const graphJson = row?.companyDataGraph;

  if (!graphJson) {
    throw new Error('No company data graph available');
  }

  const graph = parseDoubleEncodedJson<CompanyDataGraph>(graphJson, [
    'metadata',
    'nodes',
    'relationships',
    'summary',
  ]);
  fixTripleEncodedFields(graph.nodes as unknown as Record<string, unknown>, ['users']);

  return graph;
}

function getRowsByIndex<T>(response: ApiResponse, index: number): T[] {
  if (!response.resultSets || !response.resultSets[index]) {
    return [];
  }
  const table = response.resultSets[index];
  return (table?.data as T[]) ?? [];
}

function getRowByIndex<T>(response: ApiResponse, index: number): T | null {
  const rows = getRowsByIndex<T>(response, index);
  return rows.length > 0 ? rows[0] : null;
}

function safeJsonParse<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function parseObject<T>(value: unknown): T | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const parsed = safeJsonParse<Record<string, unknown>>(value, {});
    return normalizeRecord(parsed) as T;
  }
  if (typeof value === 'object') {
    return normalizeRecord(value as Record<string, unknown>) as T;
  }
  return null;
}

function parseObjectArray<T>(value: unknown): T[] {
  if (value === null || value === undefined) return [];
  let arrayValue: unknown = value;
  if (typeof value === 'string') {
    arrayValue = safeJsonParse(value, []);
  }

  if (!Array.isArray(arrayValue)) {
    return [];
  }

  return arrayValue.map((item) => {
    if (typeof item === 'object' && item !== null) {
      return normalizeRecord(item as Record<string, unknown>) as T;
    }
    return item as T;
  });
}

function parseJsonField(source: Record<string, unknown>, field: string): unknown {
  if (!source[field] || typeof source[field] !== 'string') {
    return source[field];
  }
  return safeJsonParse(source[field] as string, source[field]);
}
