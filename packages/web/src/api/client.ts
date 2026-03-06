import {
  createApiClient,
  createTypedApi,
  type FullApiClient,
  type HttpClient,
} from '@rediacc/shared/api';
import { createVaultEncryptor } from '@rediacc/shared/encryption';
import axios from 'axios';
import { webCryptoProvider } from '@/adapters/crypto';
import {
  errorHandler,
  masterPasswordAdapter,
  telemetryAdapter,
  tokenAdapter,
  urlAdapter,
} from './adapters';

// Create axios instance
const axiosInstance = axios.create({
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Create the unified API client using the factory
const client: FullApiClient = createApiClient({
  httpClient: axiosInstance as unknown as HttpClient,
  tokenAdapter,
  urlProvider: urlAdapter,
  vaultEncryptor: createVaultEncryptor(webCryptoProvider),
  masterPasswordProvider: masterPasswordAdapter,
  errorHandler,
  telemetry: telemetryAdapter,
});

// Export the client and typed API
export const apiClient = client;
export const typedApi = createTypedApi(client, { errorHandler });
export default apiClient;
