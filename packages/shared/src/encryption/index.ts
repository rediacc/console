import type { ICryptoProvider } from './types'
import { hasVaultFields, isVaultField, transformVaultFields } from './vaultTransform'

const BASE64_REGEX = /^[A-Za-z0-9+/]+=*$/

export interface VaultEncryptor {
  encrypt<T>(value: T, password: string): Promise<T>
  decrypt<T>(value: T, password: string): Promise<T>
  hasVaultFields(value: unknown): boolean
}

export function createVaultEncryptor(provider: ICryptoProvider): VaultEncryptor {
  const encrypt = async <T>(value: T, password: string): Promise<T> => {
    if (!password || value == null) return value
    return transformVaultFields(value, (input) => provider.encrypt(input, password))
  }

  const decrypt = async <T>(value: T, password: string): Promise<T> => {
    if (!password || value == null) return value
    return transformVaultFields(value, async (input) => {
      if (!BASE64_REGEX.test(input)) {
        return input
      }
      try {
        return await provider.decrypt(input, password)
      } catch {
        return input
      }
    })
  }

  return {
    encrypt,
    decrypt,
    hasVaultFields,
  }
}

export { hasVaultFields, isVaultField, transformVaultFields }
export type { ICryptoProvider }
