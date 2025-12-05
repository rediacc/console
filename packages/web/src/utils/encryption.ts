import { cryptoService } from '@/services/cryptoService';

export const encryptString = (plaintext: string, password: string) =>
  cryptoService.encryptString(plaintext, password);

export const decryptString = (ciphertext: string, password: string) =>
  cryptoService.decryptString(ciphertext, password);

export const encryptVaultFields = <T>(data: T, password: string) =>
  cryptoService.encryptVaultFields(data, password);

export const decryptVaultFields = <T>(data: T, password: string) =>
  cryptoService.decryptVaultFields(data, password);

export const hasVaultFields = (data: unknown) => cryptoService.hasVaultFields(data);

export const isCryptoAvailable = () => cryptoService.isAvailable();
