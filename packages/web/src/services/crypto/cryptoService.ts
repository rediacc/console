import { webCryptoProvider } from '@/adapters/crypto';
import { CryptoService, SecureMemoryStorage } from '@/platform/utils/crypto';

export const cryptoService = new CryptoService(webCryptoProvider);
export const secureMemoryStorage = new SecureMemoryStorage(cryptoService);
