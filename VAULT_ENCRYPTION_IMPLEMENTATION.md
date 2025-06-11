# Vault Encryption Implementation Guide

This document provides a comprehensive guide for implementing client-side vault encryption across different platforms (JavaScript/TypeScript, Python, C++, etc.) to ensure compatibility with the Rediacc vault encryption protocol.

## Overview

The Rediacc vault encryption system uses:
- **Algorithm**: AES-256-GCM (Galois/Counter Mode)
- **Key Derivation**: PBKDF2-HMAC-SHA256
- **Format**: Base64-encoded concatenation of `salt || iv || ciphertext || authTag`

## Protocol Specification

### VaultCompany Sentinel

The `VaultCompany` field serves as a sentinel value to coordinate encryption across all users in a company:

1. **Encrypted VaultCompany**: Company requires master password from all users
2. **Plain JSON VaultCompany** (e.g., `{}`): No encryption required
3. **Validation**: Decrypt VaultCompany and verify it matches the company name

### Encryption Parameters

```
Algorithm: AES-256-GCM
Key Size: 256 bits (32 bytes)
IV Size: 96 bits (12 bytes)
Salt Size: 128 bits (16 bytes)
Tag Size: 128 bits (16 bytes)
PBKDF2 Iterations: 100,000
PBKDF2 Hash: SHA-256
```

### Data Format

Encrypted data is stored as Base64-encoded string containing:
```
[salt(16 bytes)][iv(12 bytes)][ciphertext][authTag(16 bytes)]
```

## Implementation Examples

### JavaScript/TypeScript (Web Crypto API)

```typescript
// Full implementation in src/utils/encryption.ts

async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const encoder = new TextEncoder()
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(password),
    'PBKDF2',
    false,
    ['deriveBits', 'deriveKey']
  )

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt,
      iterations: 100000,
      hash: 'SHA-256'
    },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  )
}

async function encryptString(plaintext: string, password: string): Promise<string> {
  const encoder = new TextEncoder()
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(password, salt)
  
  const encryptedData = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoder.encode(plaintext)
  )
  
  // Combine salt + iv + ciphertext (includes auth tag)
  const combined = new Uint8Array(salt.length + iv.length + encryptedData.byteLength)
  combined.set(salt, 0)
  combined.set(iv, salt.length)
  combined.set(new Uint8Array(encryptedData), salt.length + iv.length)
  
  return btoa(String.fromCharCode(...combined))
}

async function decryptString(encrypted: string, password: string): Promise<string> {
  const combined = new Uint8Array(
    atob(encrypted).split('').map(char => char.charCodeAt(0))
  )
  
  const salt = combined.slice(0, 16)
  const iv = combined.slice(16, 28)
  const ciphertext = combined.slice(28)
  
  const key = await deriveKey(password, salt)
  
  const decryptedData = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ciphertext
  )
  
  return new TextDecoder().decode(decryptedData)
}
```

### Python (cryptography library)

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
import os

ITERATIONS = 100000

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits
        salt=salt,
        iterations=ITERATIONS,
    )
    return kdf.derive(password.encode('utf-8'))

def encrypt_string(plaintext: str, password: str) -> str:
    salt = os.urandom(16)  # 128 bits
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    iv = os.urandom(12)  # 96 bits
    ciphertext = aesgcm.encrypt(iv, plaintext.encode('utf-8'), None)
    # Combine salt + IV + ciphertext (includes auth tag)
    combined = salt + iv + ciphertext
    return base64.b64encode(combined).decode('ascii')

def decrypt_string(encrypted: str, password: str) -> str:
    combined = base64.b64decode(encrypted)
    salt = combined[:16]
    iv = combined[16:28]
    ciphertext = combined[28:]
    
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext.decode('utf-8')

def is_encrypted(value: str) -> bool:
    """Check if a value appears to be encrypted"""
    if not value or len(value) < 20:
        return False
    
    # Check if it's valid JSON (not encrypted)
    try:
        import json
        json.loads(value)
        return False
    except:
        pass
    
    # Check if it's base64 and has reasonable length
    try:
        decoded = base64.b64decode(value)
        return len(decoded) >= 44  # min: salt(16) + iv(12) + data + tag(16)
    except:
        return False

def encrypt_vault_fields(obj: dict, password: str) -> dict:
    """Recursively encrypt fields containing 'vault' in their name"""
    result = {}
    for key, value in obj.items():
        if 'vault' in key.lower() and isinstance(value, str) and value:
            if not is_encrypted(value):
                result[key] = encrypt_string(value, password)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = encrypt_vault_fields(value, password)
        elif isinstance(value, list):
            result[key] = [
                encrypt_vault_fields(item, password) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result
```

### C++ (OpenSSL)

```cpp
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/hmac.h>
#include <openssl/aes.h>
#include <string>
#include <vector>
#include <memory>

const int ITERATIONS = 100000;
const int KEY_SIZE = 32;  // 256 bits
const int IV_SIZE = 12;   // 96 bits
const int SALT_SIZE = 16; // 128 bits
const int TAG_SIZE = 16;  // 128 bits

std::vector<uint8_t> deriveKey(const std::string& password, 
                                const std::vector<uint8_t>& salt) {
    std::vector<uint8_t> key(KEY_SIZE);
    
    PKCS5_PBKDF2_HMAC(
        password.c_str(), password.length(),
        salt.data(), salt.size(),
        ITERATIONS,
        EVP_sha256(),
        KEY_SIZE, key.data()
    );
    
    return key;
}

std::string encryptString(const std::string& plaintext, 
                          const std::string& password) {
    // Generate random salt and IV
    std::vector<uint8_t> salt(SALT_SIZE);
    std::vector<uint8_t> iv(IV_SIZE);
    RAND_bytes(salt.data(), SALT_SIZE);
    RAND_bytes(iv.data(), IV_SIZE);
    
    // Derive key
    auto key = deriveKey(password, salt);
    
    // Setup encryption context
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, key.data(), iv.data());
    
    // Encrypt
    std::vector<uint8_t> ciphertext(plaintext.length() + EVP_CIPHER_block_size(EVP_aes_256_gcm()));
    int len;
    int ciphertext_len;
    
    EVP_EncryptUpdate(ctx, ciphertext.data(), &len, 
                      reinterpret_cast<const uint8_t*>(plaintext.data()), 
                      plaintext.length());
    ciphertext_len = len;
    
    EVP_EncryptFinal_ex(ctx, ciphertext.data() + len, &len);
    ciphertext_len += len;
    
    // Get tag
    std::vector<uint8_t> tag(TAG_SIZE);
    EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, TAG_SIZE, tag.data());
    
    EVP_CIPHER_CTX_free(ctx);
    
    // Combine salt + iv + ciphertext + tag
    std::vector<uint8_t> combined;
    combined.insert(combined.end(), salt.begin(), salt.end());
    combined.insert(combined.end(), iv.begin(), iv.end());
    combined.insert(combined.end(), ciphertext.begin(), ciphertext.begin() + ciphertext_len);
    combined.insert(combined.end(), tag.begin(), tag.end());
    
    // Base64 encode
    return base64_encode(combined);
}

std::string decryptString(const std::string& encrypted, 
                          const std::string& password) {
    // Base64 decode
    auto combined = base64_decode(encrypted);
    
    // Extract components
    std::vector<uint8_t> salt(combined.begin(), combined.begin() + SALT_SIZE);
    std::vector<uint8_t> iv(combined.begin() + SALT_SIZE, combined.begin() + SALT_SIZE + IV_SIZE);
    std::vector<uint8_t> ciphertext(combined.begin() + SALT_SIZE + IV_SIZE, combined.end() - TAG_SIZE);
    std::vector<uint8_t> tag(combined.end() - TAG_SIZE, combined.end());
    
    // Derive key
    auto key = deriveKey(password, salt);
    
    // Setup decryption context
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, key.data(), iv.data());
    
    // Set tag
    EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, TAG_SIZE, tag.data());
    
    // Decrypt
    std::vector<uint8_t> plaintext(ciphertext.size());
    int len;
    int plaintext_len;
    
    EVP_DecryptUpdate(ctx, plaintext.data(), &len, ciphertext.data(), ciphertext.size());
    plaintext_len = len;
    
    int ret = EVP_DecryptFinal_ex(ctx, plaintext.data() + len, &len);
    EVP_CIPHER_CTX_free(ctx);
    
    if (ret <= 0) {
        throw std::runtime_error("Decryption failed");
    }
    
    plaintext_len += len;
    return std::string(plaintext.begin(), plaintext.begin() + plaintext_len);
}
```

## Vault Field Processing

### Field Detection

Fields are considered "vault fields" if their name contains "vault" (case-insensitive):
- `repositoryVault` ✓
- `storageVault` ✓
- `vaultConfig` ✓
- `vault_settings` ✓

### Recursive Processing

The implementation should recursively process objects and arrays:

```typescript
function processVaultFields(obj: any, password: string, operation: 'encrypt' | 'decrypt'): any {
  if (!obj || typeof obj !== 'object') return obj
  
  if (Array.isArray(obj)) {
    return obj.map(item => processVaultFields(item, password, operation))
  }
  
  const result: any = {}
  for (const [key, value] of Object.entries(obj)) {
    if (key.toLowerCase().includes('vault') && typeof value === 'string' && value) {
      result[key] = operation === 'encrypt' 
        ? encryptString(value, password)
        : decryptString(value, password)
    } else if (typeof value === 'object') {
      result[key] = processVaultFields(value, password, operation)
    } else {
      result[key] = value
    }
  }
  return result
}
```

## Integration with API

### Request Interceptor

```typescript
// Before sending request
const encryptedData = await encryptVaultFields(requestData, masterPassword)
```

### Response Interceptor

```typescript
// After receiving response
try {
  const decryptedData = await decryptVaultFields(responseData, masterPassword)
} catch (error) {
  // Show toast: "Failed to decrypt vault data - check master password"
  // Return original data to allow app to continue
}
```

## Testing

### Test Vectors

```javascript
// Test with known values
const password = "test-password-123"
const plaintext = "Hello, Vault!"

// Encrypt
const encrypted = await encryptString(plaintext, password)
console.log("Encrypted:", encrypted)

// Decrypt
const decrypted = await decryptString(encrypted, password)
console.assert(decrypted === plaintext, "Decryption failed")

// Test vault field processing
const testData = {
  name: "Test Repo",
  repositoryVault: JSON.stringify({ key: "value" }),
  nested: {
    storageVault: JSON.stringify({ secret: "data" })
  }
}

const encryptedData = await encryptVaultFields(testData, password)
const decryptedData = await decryptVaultFields(encryptedData, password)
console.assert(JSON.stringify(decryptedData) === JSON.stringify(testData), "Field processing failed")
```

## Security Considerations

1. **Never store the master password** - Keep it only in memory
2. **Use cryptographically secure random generators** for salt and IV
3. **Validate decryption** - Always verify the authentication tag
4. **Handle errors gracefully** - Don't expose cryptographic errors to users
5. **Clear sensitive data** from memory when done

## Common Pitfalls

1. **Base64 Encoding**: Ensure proper encoding/decoding of binary data
2. **Byte Order**: Maintain consistent byte order when concatenating components
3. **Character Encoding**: Always use UTF-8 for string/byte conversions
4. **Error Handling**: Distinguish between wrong password and corrupted data
5. **JSON Detection**: Check if a value is valid JSON before treating it as encrypted

## References

- [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)
- [Python cryptography](https://cryptography.io/)
- [OpenSSL EVP](https://www.openssl.org/docs/man1.1.1/man3/EVP_aes_256_gcm.html)
- [AES-GCM](https://en.wikipedia.org/wiki/Galois/Counter_Mode)
- [PBKDF2](https://en.wikipedia.org/wiki/PBKDF2)