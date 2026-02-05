#!/usr/bin/env npx tsx
/**
 * License Schema Generator
 *
 * Generates a JSON schema snapshot from TypeScript license types.
 * This snapshot is used by Go tests to validate schema consistency.
 *
 * Usage:
 *   npx tsx packages/shared/scripts/generate-license-schema.ts
 *   npm run generate:license-schema
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

// Get directory paths
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const licenseDir = path.join(__dirname, '../src/license');
const outputPath = path.join(licenseDir, 'schema.generated.json');

// Import license constants dynamically to get actual values
import {
  LICENSE_CONFIG,
  PLAN_FEATURES,
  PLAN_ORDER,
  PLAN_RESOURCES,
} from '../src/license/constants.js';

/**
 * Schema definition types
 */
interface FieldDef {
  type: 'string' | 'number' | 'boolean' | 'object';
  jsonKey: string;
  optional?: boolean;
  nestedType?: string;
}

interface TypeDef {
  kind: 'enum' | 'struct';
  values?: string[];
  fields?: Record<string, FieldDef>;
}

interface SchemaConstants {
  gracePeriodDays: number;
  degradedPlan: string;
  schemaVersion: number;
  checkInIntervalHours: number;
  planResources: Record<string, Record<string, number>>;
  planFeatures: Record<string, Record<string, boolean>>;
}

interface LicenseSchema {
  version: number;
  generatedAt: string;
  types: Record<string, TypeDef>;
  constants: SchemaConstants;
}

/**
 * Define the schema based on TypeScript types
 */
function generateSchema(): LicenseSchema {
  const schema: LicenseSchema = {
    version: 1,
    generatedAt: new Date().toISOString(),
    types: {
      PlanCode: {
        kind: 'enum',
        values: [...PLAN_ORDER],
      },
      LicenseStatus: {
        kind: 'enum',
        values: ['ACTIVE', 'INACTIVE', 'EXPIRED', 'SUSPENDED', 'GRACE'],
      },
      ResourceLimits: {
        kind: 'struct',
        fields: {
          bridges: { type: 'number', jsonKey: 'bridges' },
          maxActiveJobs: { type: 'number', jsonKey: 'maxActiveJobs' },
          maxReservedJobs: { type: 'number', jsonKey: 'maxReservedJobs' },
          jobTimeoutHours: { type: 'number', jsonKey: 'jobTimeoutHours' },
          maxRepositorySizeGb: { type: 'number', jsonKey: 'maxRepositorySizeGb' },
          maxJobsPerMonth: { type: 'number', jsonKey: 'maxJobsPerMonth' },
          maxPendingPerUser: { type: 'number', jsonKey: 'maxPendingPerUser' },
          maxTasksPerMachine: { type: 'number', jsonKey: 'maxTasksPerMachine' },
          cephPoolsPerTeam: { type: 'number', jsonKey: 'cephPoolsPerTeam' },
        },
      },
      FeatureFlags: {
        kind: 'struct',
        fields: {
          permissionGroups: { type: 'boolean', jsonKey: 'permissionGroups' },
          ceph: { type: 'boolean', jsonKey: 'ceph' },
          queuePriority: { type: 'boolean', jsonKey: 'queuePriority' },
          advancedAnalytics: { type: 'boolean', jsonKey: 'advancedAnalytics' },
          prioritySupport: { type: 'boolean', jsonKey: 'prioritySupport' },
          auditLog: { type: 'boolean', jsonKey: 'auditLog' },
          advancedQueue: { type: 'boolean', jsonKey: 'advancedQueue' },
          customBranding: { type: 'boolean', jsonKey: 'customBranding' },
          dedicatedAccount: { type: 'boolean', jsonKey: 'dedicatedAccount' },
        },
      },
      LicenseData: {
        kind: 'struct',
        fields: {
          version: { type: 'number', jsonKey: 'version' },
          licenseId: { type: 'string', jsonKey: 'licenseId' },
          organizationId: { type: 'number', jsonKey: 'organizationId' },
          customerId: { type: 'string', jsonKey: 'customerId' },
          planCode: { type: 'string', jsonKey: 'planCode', nestedType: 'PlanCode' },
          status: { type: 'string', jsonKey: 'status', nestedType: 'LicenseStatus' },
          issuedAt: { type: 'string', jsonKey: 'issuedAt' },
          expiresAt: { type: 'string', jsonKey: 'expiresAt' },
          lastCheckIn: { type: 'string', jsonKey: 'lastCheckIn' },
          gracePeriodEnds: { type: 'string', jsonKey: 'gracePeriodEnds' },
          resources: { type: 'object', jsonKey: 'resources', nestedType: 'ResourceLimits' },
          features: { type: 'object', jsonKey: 'features', nestedType: 'FeatureFlags' },
          maxActivations: { type: 'number', jsonKey: 'maxActivations' },
          activationCount: { type: 'number', jsonKey: 'activationCount' },
        },
      },
      SignedLicenseBlob: {
        kind: 'struct',
        fields: {
          payload: { type: 'string', jsonKey: 'payload' },
          signature: { type: 'string', jsonKey: 'signature' },
          publicKeyId: { type: 'string', jsonKey: 'publicKeyId' },
        },
      },
      CachedLicenseData: {
        kind: 'struct',
        fields: {
          planCode: { type: 'string', jsonKey: 'planCode', nestedType: 'PlanCode' },
          status: { type: 'string', jsonKey: 'status', nestedType: 'LicenseStatus' },
          resources: { type: 'object', jsonKey: 'resources', nestedType: 'ResourceLimits' },
          features: { type: 'object', jsonKey: 'features', nestedType: 'FeatureFlags' },
          expiresAt: { type: 'string', jsonKey: 'expiresAt' },
          gracePeriodEnds: { type: 'string', jsonKey: 'gracePeriodEnds' },
        },
      },
      OrganizationLicense: {
        kind: 'struct',
        fields: {
          signedBlob: {
            type: 'object',
            jsonKey: 'signedBlob',
            nestedType: 'SignedLicenseBlob',
            optional: true,
          },
          cachedData: {
            type: 'object',
            jsonKey: 'cachedData',
            nestedType: 'CachedLicenseData',
            optional: true,
          },
        },
      },
    },
    constants: {
      gracePeriodDays: LICENSE_CONFIG.gracePeriodDays,
      degradedPlan: LICENSE_CONFIG.degradedPlan,
      schemaVersion: LICENSE_CONFIG.schemaVersion,
      checkInIntervalHours: LICENSE_CONFIG.checkInIntervalHours,
      planResources: PLAN_RESOURCES as unknown as Record<string, Record<string, number>>,
      planFeatures: PLAN_FEATURES as unknown as Record<string, Record<string, boolean>>,
    },
  };

  return schema;
}

/**
 * Main entry point
 */
function main(): void {
  const schema = generateSchema();

  // Remove generatedAt for deterministic output (avoids unnecessary diffs)
  const outputSchema = { ...schema };
  delete (outputSchema as Record<string, unknown>).generatedAt;

  const json = JSON.stringify(outputSchema, null, 2);
  fs.writeFileSync(outputPath, json + '\n');

  console.log(`✓ Generated license schema: ${outputPath}`);
  console.log(`  Types: ${Object.keys(schema.types).join(', ')}`);
  console.log(
    `  Constants: gracePeriodDays=${schema.constants.gracePeriodDays}, degradedPlan=${schema.constants.degradedPlan}`
  );
}

main();
