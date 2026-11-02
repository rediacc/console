/**
 * Telemetry identity of `serve --mode container`.
 *
 * The container initialises the SDK once, at process start, under its own service
 * name: every dispatched request after that reuses it and only adds spans.
 */

import type { Command } from 'commander';
import { VERSION } from '../../version.js';
import { getSubscriptionServerUrl } from '../account/subscription-auth.js';
import { fetchOtlpCredentials } from './otlp-credentials.js';
import { isTelemetryDisabled, type TelemetryInitConfig, telemetryService } from './telemetry.js';

const CONTAINER_EXECUTOR_SERVICE_NAME = 'rediacc-proxy-executor';

/** True for the one command that runs the container tier: `serve --mode container`. */
export function isContainerServe(command: Command): boolean {
  return command.name() === 'serve' && command.opts<{ mode?: string }>().mode === 'container';
}

/**
 * The SDK configuration of the container executor. `rediacc.region` comes from the
 * Worker's executor env (`REDIACC_REGION`); a container without it reports none
 * rather than a guess.
 */
export function containerTelemetryConfig(): TelemetryInitConfig {
  const region = process.env.REDIACC_REGION;
  return {
    serviceName: CONTAINER_EXECUTOR_SERVICE_NAME,
    serviceVersion: VERSION,
    environment: 'production',
    ...(region ? { region } : {}),
  };
}

/**
 * Start the container's telemetry. The credential is fetched from the container's
 * own account server, and only when telemetry is enabled: CI and
 * REDIACC_TELEMETRY_DISABLED=1 must not cost a network call or start the SDK.
 */
export async function initContainerTelemetry(): Promise<void> {
  if (isTelemetryDisabled()) return;
  const otlpCreds = await fetchOtlpCredentials(getSubscriptionServerUrl());
  telemetryService.setRuntimeOtlpCredentials(otlpCreds);
  await telemetryService.initialize(containerTelemetryConfig());
}
