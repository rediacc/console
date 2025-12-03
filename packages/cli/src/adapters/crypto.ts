import { createCipheriv, createDecipheriv, pbkdf2, randomBytes, createHash } from 'node:crypto'
import { promisify } from 'node:util'
import type { ICryptoProvider } from '@rediacc/shared/encryption'

const pbkdf2Async = promisify(pbkdf2)

// Must match web implementation exactly
const ENCRYPTION_CONFIG = {
  SALT_LENGTH: 16,
  ITERATIONS: 100000,
  KEY_LENGTH: 32, // 256 bits = 32 bytes
  IV_LENGTH: 12,
  TAG_LENGTH: 16,
  ALGORITHM: 'aes-256-gcm',
  HASH: 'sha256',
} as const

class NodeCryptoProvider implements ICryptoProvider {
  async encrypt(data: string, password: string): Promise<string> {
    const salt = randomBytes(ENCRYPTION_CONFIG.SALT_LENGTH)
    const key = await this.deriveKeyBuffer(password, salt)
    const iv = randomBytes(ENCRYPTION_CONFIG.IV_LENGTH)

    const cipher = createCipheriv(ENCRYPTION_CONFIG.ALGORITHM, key, iv, {
      authTagLength: ENCRYPTION_CONFIG.TAG_LENGTH,
    })

    const encrypted = Buffer.concat([
      cipher.update(data, 'utf8'),
      cipher.final(),
    ])

    const authTag = cipher.getAuthTag()

    // Combine: salt + iv + ciphertext + authTag
    // Note: In web crypto, authTag is appended to ciphertext automatically
    const combined = Buffer.concat([salt, iv, encrypted, authTag])

    return combined.toString('base64')
  }

  async decrypt(data: string, password: string): Promise<string> {
    const combined = Buffer.from(data, 'base64')

    const salt = combined.subarray(0, ENCRYPTION_CONFIG.SALT_LENGTH)
    const iv = combined.subarray(
      ENCRYPTION_CONFIG.SALT_LENGTH,
      ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH
    )
    const authTag = combined.subarray(-ENCRYPTION_CONFIG.TAG_LENGTH)
    const ciphertext = combined.subarray(
      ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH,
      -ENCRYPTION_CONFIG.TAG_LENGTH
    )

    const key = await this.deriveKeyBuffer(password, salt)

    const decipher = createDecipheriv(ENCRYPTION_CONFIG.ALGORITHM, key, iv, {
      authTagLength: ENCRYPTION_CONFIG.TAG_LENGTH,
    })

    decipher.setAuthTag(authTag)

    const decrypted = Buffer.concat([
      decipher.update(ciphertext),
      decipher.final(),
    ])

    return decrypted.toString('utf8')
  }

  async deriveKey(password: string, salt: Uint8Array): Promise<string> {
    const key = await pbkdf2Async(
      password,
      Buffer.from(salt),
      ENCRYPTION_CONFIG.ITERATIONS,
      ENCRYPTION_CONFIG.KEY_LENGTH,
      ENCRYPTION_CONFIG.HASH
    )
    return key.toString('base64')
  }

  private async deriveKeyBuffer(password: string, salt: Buffer): Promise<Buffer> {
    return pbkdf2Async(
      password,
      salt,
      ENCRYPTION_CONFIG.ITERATIONS,
      ENCRYPTION_CONFIG.KEY_LENGTH,
      ENCRYPTION_CONFIG.HASH
    )
  }

  async generateHash(data: string): Promise<string> {
    const hash = createHash(ENCRYPTION_CONFIG.HASH)
    hash.update(data)
    return hash.digest('hex')
  }
}

export const nodeCryptoProvider = new NodeCryptoProvider()
export default nodeCryptoProvider
