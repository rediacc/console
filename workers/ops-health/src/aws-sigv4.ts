/**
 * The minimal AWS Signature Version 4 helper for the SES v2 call, copied from private/account/src/utils/aws-sigv4.ts (F14): that file lives in another repository, and this Worker deploys on its own. WebCrypto only, so it runs in a Worker and under vitest alike.
 */

export interface AwsCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  region: string;
  service: string;
}

export interface SignedRequest {
  url: string;
  headers: Record<string, string>;
}

const encoder = new TextEncoder();

function hexEncode(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function sha256Hex(data: string): Promise<string> {
  return hexEncode(await crypto.subtle.digest('SHA-256', encoder.encode(data)));
}

async function hmacSha256(key: ArrayBuffer | Uint8Array, data: string): Promise<ArrayBuffer> {
  const raw: Uint8Array<ArrayBuffer> =
    key instanceof ArrayBuffer ? new Uint8Array(key) : Uint8Array.from(key);
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    raw,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  return crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(data));
}

async function getSigningKey(
  secret: string,
  dateStamp: string,
  region: string,
  service: string
): Promise<ArrayBuffer> {
  const kDate = await hmacSha256(encoder.encode(`AWS4${secret}`), dateStamp);
  const kRegion = await hmacSha256(kDate, region);
  const kService = await hmacSha256(kRegion, service);
  return hmacSha256(kService, 'aws4_request');
}

export async function signAwsRequest(
  credentials: AwsCredentials,
  method: string,
  url: string,
  headers: Record<string, string>,
  body: string,
  now: Date = new Date()
): Promise<SignedRequest> {
  const parsed = new URL(url);
  const amzDate = now
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d+Z$/, 'Z');
  const dateStamp = amzDate.slice(0, 8);

  const allHeaders: Record<string, string> = {
    ...headers,
    host: parsed.host,
    'x-amz-date': amzDate,
  };
  // SigV4 orders header names by code point, which localeCompare does not promise.
  const sortedKeys = Object.keys(allHeaders).sort((a, b) => (a < b ? -1 : Number(a > b)));
  const canonicalHeaders = sortedKeys
    .map((k) => `${k.toLowerCase()}:${allHeaders[k].trim()}`)
    .join('\n');
  const signedHeaders = sortedKeys.map((k) => k.toLowerCase()).join(';');

  const canonicalRequest = [
    method,
    parsed.pathname,
    parsed.search.slice(1),
    `${canonicalHeaders}\n`,
    signedHeaders,
    await sha256Hex(body),
  ].join('\n');

  const credentialScope = `${dateStamp}/${credentials.region}/${credentials.service}/aws4_request`;
  const stringToSign = [
    'AWS4-HMAC-SHA256',
    amzDate,
    credentialScope,
    await sha256Hex(canonicalRequest),
  ].join('\n');

  const signingKey = await getSigningKey(
    credentials.secretAccessKey,
    dateStamp,
    credentials.region,
    credentials.service
  );
  const signature = hexEncode(await hmacSha256(signingKey, stringToSign));

  return {
    url,
    headers: {
      ...allHeaders,
      authorization: `AWS4-HMAC-SHA256 Credential=${credentials.accessKeyId}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`,
    },
  };
}
