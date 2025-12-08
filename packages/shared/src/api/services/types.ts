import type { ApiResponse } from '../../types/api';
import type { StoredProcedureName } from '../../types/api-schema.generated';

/**
 * Endpoint path for a stored procedure (e.g., '/CreateMachine', '/GetTeamStorages')
 * Procedure names are defined in api-schema.generated.ts
 */
export type ProcedureEndpoint = `/${StoredProcedureName}`;

export interface ApiClient {
  get<T = unknown>(
    endpoint: ProcedureEndpoint,
    params?: Record<string, unknown> | object,
    config?: Record<string, unknown>
  ): Promise<ApiResponse<T>>;
  post<T = unknown>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown> | object,
    config?: Record<string, unknown>
  ): Promise<ApiResponse<T>>;
  put<T = unknown>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown> | object,
    config?: Record<string, unknown>
  ): Promise<ApiResponse<T>>;
  delete<T = unknown>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown> | object,
    config?: Record<string, unknown>
  ): Promise<ApiResponse<T>>;
}

export type ApiRequestConfig = Record<string, unknown>;
