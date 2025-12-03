export interface ICryptoProvider {
  encrypt(data: string, password: string): Promise<string>
  decrypt(data: string, password: string): Promise<string>
  deriveKey?(password: string, salt: Uint8Array): Promise<unknown>
  generateHash?(data: string): Promise<string>
}
