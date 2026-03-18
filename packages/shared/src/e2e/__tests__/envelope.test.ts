import { describe, expect, it } from 'vitest';
import { E2E_VERSION } from '../constants.js';
import {
  deriveAesKey,
  deriveSharedSecret,
  fromBase64,
  generateEphemeralKeyPair,
  importX25519PrivateKey,
  importX25519PublicKey,
  toBase64,
} from '../crypto.js';
import { openRequest, openResponse, sealRequest, sealResponse } from '../envelope.js';

// Fixed test keys (same as test-db.ts / keys.ts)
const TEST_X25519_PRIVATE_PKCS8 =
  'MC4CAQAwBQYDK2VuBCIEICiSVw3fU8IlyE5cO4+51WmfdH1D2mFk5QIxrVYiz117';
const TEST_X25519_PUBLIC_SPKI = 'MCowBQYDK2VuAyEAjX5clh+N8I3DnQU7e6JvuJHJUGBuVb32HrvKLPe4IB4=';
const TEST_KEY_ID = 'v1';

describe('E2E Envelope', () => {
  async function getServerKeys() {
    const publicKey = await importX25519PublicKey(TEST_X25519_PUBLIC_SPKI);
    const privateKey = await importX25519PrivateKey(TEST_X25519_PRIVATE_PKCS8);
    return { publicKey, privateKey };
  }

  describe('Request seal/open round-trip', () => {
    it('should recover original method, path, headers, and body', async () => {
      const server = await getServerKeys();
      const headers = { Authorization: 'Bearer rdt_test123', 'Content-Type': 'application/json' };
      const body = { machineId: 'abc123', requestedSizeGb: 10 };

      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'POST',
        '/account/api/v1/licenses/activate',
        headers,
        body
      );

      const { innerRequest } = await openRequest(server.privateKey, envelope);

      expect(innerRequest.method).toBe('POST');
      expect(innerRequest.path).toBe('/account/api/v1/licenses/activate');
      expect(innerRequest.headers).toEqual(headers);
      expect(innerRequest.body).toEqual(body);
    });

    it('should work with GET requests (null body)', async () => {
      const server = await getServerKeys();

      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/account/api/v1/licenses/status',
        { Authorization: 'Bearer rdt_test' },
        null
      );

      const { innerRequest } = await openRequest(server.privateKey, envelope);

      expect(innerRequest.method).toBe('GET');
      expect(innerRequest.body).toBeNull();
    });

    it('should work with empty headers', async () => {
      const server = await getServerKeys();

      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'POST',
        '/account/api/v1/device-codes',
        {},
        null
      );

      const { innerRequest } = await openRequest(server.privateKey, envelope);
      expect(innerRequest.headers).toEqual({});
    });

    it('should produce a valid envelope structure', async () => {
      const server = await getServerKeys();

      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );

      expect(envelope.v).toBe(E2E_VERSION);
      expect(envelope.kid).toBe(TEST_KEY_ID);
      expect(typeof envelope.eph).toBe('string');
      expect(typeof envelope.salt).toBe('string');
      expect(typeof envelope.iv).toBe('string');
      expect(typeof envelope.ct).toBe('string');

      // eph should decode to 32 bytes (raw X25519 public key)
      expect(fromBase64(envelope.eph).length).toBe(32);
      // salt should decode to 16 bytes
      expect(fromBase64(envelope.salt).length).toBe(16);
      // iv should decode to 12 bytes
      expect(fromBase64(envelope.iv).length).toBe(12);
    });

    it('should produce different envelopes for the same input (fresh ephemeral keys)', async () => {
      const server = await getServerKeys();

      const { envelope: e1 } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );
      const { envelope: e2 } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );

      expect(e1.eph).not.toBe(e2.eph);
      expect(e1.ct).not.toBe(e2.ct);
    });
  });

  describe('Response seal/open round-trip', () => {
    it('should recover original body and status', async () => {
      const server = await getServerKeys();

      // First do a request to get an aesKey
      const { envelope, aesKey } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );
      // Server opens and gets the same aesKey
      const { aesKey: serverAesKey } = await openRequest(server.privateKey, envelope);

      const responseBody = JSON.stringify({ subscriptionId: 'sub_123', planCode: 'BUSINESS' });
      const responseEnvelope = await sealResponse(serverAesKey, 200, responseBody);

      const { status, body } = await openResponse(aesKey, responseEnvelope);
      expect(status).toBe(200);
      expect(JSON.parse(body)).toEqual({ subscriptionId: 'sub_123', planCode: 'BUSINESS' });
    });

    it('should work with empty body', async () => {
      const server = await getServerKeys();
      const { envelope, aesKey } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );
      const { aesKey: serverAesKey } = await openRequest(server.privateKey, envelope);

      const responseEnvelope = await sealResponse(serverAesKey, 204, '');
      const { status, body } = await openResponse(aesKey, responseEnvelope);
      expect(status).toBe(204);
      expect(body).toBe('');
    });

    it('should preserve error status codes', async () => {
      const server = await getServerKeys();
      const { envelope, aesKey } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );
      const { aesKey: serverAesKey } = await openRequest(server.privateKey, envelope);

      for (const code of [400, 401, 403, 404, 500]) {
        const re = await sealResponse(serverAesKey, code, JSON.stringify({ error: 'fail' }));
        const { status } = await openResponse(aesKey, re);
        expect(status).toBe(code);
      }
    });
  });

  describe('Full cycle', () => {
    it('should simulate complete CLI → Server → CLI flow', async () => {
      const server = await getServerKeys();

      // CLI seals the request
      const { envelope, aesKey: clientAesKey } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'POST',
        '/account/api/v1/licenses/activate',
        { Authorization: 'Bearer rdt_token', 'Content-Type': 'application/json' },
        { machineId: 'deadbeef' }
      );

      // Server opens the request
      const { innerRequest, aesKey: serverAesKey } = await openRequest(server.privateKey, envelope);

      // Server processes the request
      expect(innerRequest.method).toBe('POST');
      expect(innerRequest.headers['Authorization']).toBe('Bearer rdt_token');
      expect(innerRequest.body).toEqual({ machineId: 'deadbeef' });

      // Server seals the response
      const responseData = { activation: { id: 'act_1' }, signedBlob: { payload: 'x' } };
      const responseEnvelope = await sealResponse(serverAesKey, 200, JSON.stringify(responseData));

      // CLI opens the response
      const { status, body } = await openResponse(clientAesKey, responseEnvelope);
      expect(status).toBe(200);
      expect(JSON.parse(body)).toEqual(responseData);
    });
  });

  describe('Security properties', () => {
    it('should reject openRequest with wrong server private key', async () => {
      const server = await getServerKeys();
      // Generate a different key pair (attacker)
      const attacker = await generateEphemeralKeyPair();

      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );

      // Try to open with attacker's key — should fail (AES-GCM auth tag mismatch)
      await expect(openRequest(attacker.privateKey, envelope)).rejects.toThrow();
    });

    it('should reject openResponse with wrong aesKey', async () => {
      const server = await getServerKeys();
      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );
      const { aesKey: serverAesKey } = await openRequest(server.privateKey, envelope);

      const responseEnvelope = await sealResponse(serverAesKey, 200, '{"ok":true}');

      // Create a different AES key
      const kp1 = await generateEphemeralKeyPair();
      const kp2 = await generateEphemeralKeyPair();
      const wrongSecret = await deriveSharedSecret(kp1.privateKey, kp2.publicKey);
      const wrongAesKey = await deriveAesKey(wrongSecret, new Uint8Array(16));

      await expect(openResponse(wrongAesKey, responseEnvelope)).rejects.toThrow();
    });

    it('should reject tampered request envelope ciphertext', async () => {
      const server = await getServerKeys();
      const { envelope } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );

      // Tamper with the ciphertext
      const ctBytes = fromBase64(envelope.ct);
      ctBytes[0] ^= 0xff;
      envelope.ct = toBase64(ctBytes);

      await expect(openRequest(server.privateKey, envelope)).rejects.toThrow();
    });

    it('should reject tampered response envelope ciphertext', async () => {
      const server = await getServerKeys();
      const { envelope, aesKey } = await sealRequest(
        server.publicKey,
        TEST_KEY_ID,
        'GET',
        '/test',
        {},
        null
      );
      const { aesKey: serverAesKey } = await openRequest(server.privateKey, envelope);

      const responseEnvelope = await sealResponse(serverAesKey, 200, '{"ok":true}');

      // Tamper with response ciphertext
      const ctBytes = fromBase64(responseEnvelope.ct);
      ctBytes[0] ^= 0xff;
      responseEnvelope.ct = toBase64(ctBytes);

      await expect(openResponse(aesKey, responseEnvelope)).rejects.toThrow();
    });
  });
});
