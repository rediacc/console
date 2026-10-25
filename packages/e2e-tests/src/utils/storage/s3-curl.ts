import type { S3Config } from './StorageTestHelper';

/** Signing region RustFS accepts for any value; fixed so the signature never depends on the VM. */
const S3_SIGNING_REGION = 'us-east-1';

/** Heredoc delimiter for the credential config that curl reads from stdin. */
const CREDENTIAL_DELIMITER = 'S3_CURL_CREDENTIALS';

/** One S3 request, executed by `curl --aws-sigv4` on whichever VM runs the command. */
export interface S3CurlRequest {
  method: 'GET' | 'PUT' | 'DELETE' | 'HEAD';
  /** Path below the endpoint, bucket first: `bucket/key` or `bucket?list-type=2`; empty for the bucket listing. */
  path?: string;
  /** Local file on the executing VM whose bytes become the request body (PUT). */
  bodyFile?: string;
  /** Local file on the executing VM that receives the response body instead of stdout. */
  outputFile?: string;
}

export interface S3CurlResponse {
  /** True when curl exited 0 and the HTTP status is 2xx. */
  ok: boolean;
  status: number;
  body: string;
}

const shellQuote = (value: string): string => `'${value.replaceAll("'", "'\\''")}'`;

/**
 * Build the shell command for one SigV4-signed S3 request.
 * The credentials travel on curl's stdin (`-K -`), never on argv. The command prints the response
 * body (unless `outputFile` is set) followed by a newline and the HTTP status code on the last line.
 */
export function buildS3CurlCommand(config: S3Config, request: S3CurlRequest): string {
  const url = `${config.endpoint.replace(/\/+$/, '')}/${request.path ?? ''}`;
  const parts = [
    'curl -sS',
    request.method === 'HEAD' ? '-I' : `-X ${request.method}`,
    `--aws-sigv4 ${shellQuote(`aws:amz:${config.region ?? S3_SIGNING_REGION}:s3`)}`,
    '-K -',
  ];
  if (request.bodyFile) parts.push(`--data-binary @${shellQuote(request.bodyFile)}`);
  if (request.outputFile) parts.push(`-o ${shellQuote(request.outputFile)}`);
  parts.push(`-w ${shellQuote('\\n%{http_code}')}`, shellQuote(url));
  return [
    `${parts.join(' ')} <<'${CREDENTIAL_DELIMITER}'`,
    `user = "${config.accessKey}:${config.secretKey}"`,
    CREDENTIAL_DELIMITER,
  ].join('\n');
}

/** Split the output of {@link buildS3CurlCommand} into HTTP status and body. */
export function parseS3CurlOutput(
  result: { code: number; stdout: string },
  request: S3CurlRequest
): S3CurlResponse {
  const trimmed = result.stdout.replace(/\n+$/, '');
  const split = trimmed.lastIndexOf('\n');
  const statusText = split === -1 ? trimmed : trimmed.slice(split + 1);
  const status = Number.parseInt(statusText, 10) || 0;
  // HEAD returns headers on stdout (-I); nothing in them is a body.
  const body = request.method === 'HEAD' || split === -1 ? '' : trimmed.slice(0, split);
  return { ok: result.code === 0 && status >= 200 && status < 300, status, body };
}

/** Every `<tag>value</tag>` text in an S3 XML response, in document order. */
export function xmlValues(xml: string, tag: string): string[] {
  const pattern = new RegExp(`<${tag}>([^<]*)</${tag}>`, 'g');
  return [...xml.matchAll(pattern)].map((match) => match[1]);
}
