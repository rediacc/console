import { secureMemoryStorage } from '@/services/cryptoService'

export const secureStorage = secureMemoryStorage

export type ISecureStorage = typeof secureStorage
