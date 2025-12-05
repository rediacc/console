import { CryptoService, SecureMemoryStorage } from '@/core/utils/crypto';
import { webCryptoProvider } from '@/adapters/crypto';

export const cryptoService = new CryptoService(webCryptoProvider);
export const secureMemoryStorage = new SecureMemoryStorage(cryptoService);
