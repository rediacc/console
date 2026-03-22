/**
 * Calculator compute presets and slider configurations for solution pages.
 * Extracted from SPCostCalculator to keep the component under the max-lines limit.
 */

export interface SliderConfig {
  id: string;
  min: number;
  max: number;
  step?: number;
  defaultValue: number;
}

export interface ComputeOutput {
  results: Record<string, string>;
  annual: string;
  withResults?: Record<string, string>;
  withAnnual?: string;
}

function computeEnvironmentCloning(vals: Record<string, number>): ComputeOutput {
  const devs = vals.devs;
  const reqs = vals.reqs;
  const wait = vals.wait;

  const blockedPerDev = Math.min(reqs * wait, 10);
  const totalBlocked = devs * blockedPerDev;
  const sprintCapacity = devs * 10;
  const pctBlocked = Math.round((totalBlocked / sprintCapacity) * 100);

  let ctxPerDev = Math.round(30000 * ((reqs * wait) / 6));
  ctxPerDev = Math.min(ctxPerDev, 50000);
  const ctxTotal = devs * ctxPerDev;

  const effectiveLost = totalBlocked * 0.6;
  const quarterlySlip = Math.round(effectiveLost * 6 * 0.25);
  const envWaitAnnual = Math.round(effectiveLost * 26 * 92 * 8);
  const annualCost = envWaitAnnual + ctxTotal;

  return {
    results: {
      blockedTime: `${totalBlocked} dev-day${totalBlocked === 1 ? '' : 's'}`,
      sprintCapacity: `${pctBlocked}%`,
      contextSwitching: `$${ctxTotal.toLocaleString()}/yr`,
      quarterlySlip: `~${quarterlySlip} day${quarterlySlip === 1 ? '' : 's'}`,
    },
    annual: `$${annualCost.toLocaleString()}`,
  };
}

function computeInfrastructureCosts(vals: Record<string, number>): ComputeOutput {
  const envs = vals.envs;
  const costPer = vals.cost;
  const util = vals.util;

  const monthly = envs * costPer;
  const wastePct = 100 - util;
  const idle = Math.round(monthly * (wastePct / 100));
  const annualWaste = idle * 12;

  const rMonthly = Math.round(monthly * (util / 100));

  return {
    results: {
      monthly: `$${monthly.toLocaleString()}`,
      waste: `${wastePct}%`,
      idle: `$${idle.toLocaleString()}`,
    },
    annual: `$${annualWaste.toLocaleString()}`,
    withResults: {
      monthly: `$${rMonthly.toLocaleString()}`,
      waste: '0%',
      idle: '~1%',
    },
    withAnnual: `$${annualWaste.toLocaleString()}`,
  };
}

function computeProductionParity(vals: Record<string, number>): ComputeOutput {
  const devs = vals.devs;
  const bugs = vals.bugs;
  const hours = vals.hours;

  const debugHours = bugs * hours;
  const sprintHours = devs * 10 * 8;
  const capacityPct = Math.min(Math.round((debugHours / sprintHours) * 100 * devs), 100);
  const quarterlyIncidents = bugs * 6;
  const annualCost = debugHours * 26 * 75;

  return {
    results: {
      debug: `${debugHours} hrs`,
      capacity: `${capacityPct}%`,
      incidents: `${quarterlyIncidents}`,
    },
    annual: `$${annualCost.toLocaleString()}`,
  };
}

function computeIntegrations(vals: Record<string, number>): ComputeOutput {
  const devs = vals.devs;
  const failures = vals.failures;
  const hours = vals.hours;

  const debugHours = failures * hours;
  const blockedHours = failures * devs;
  const quarterlyBugs = Math.round(failures * 1.5);
  const annualCost = (debugHours + blockedHours) * 12 * 75;

  return {
    results: {
      debug: `${debugHours} hrs`,
      blocked: `${blockedHours} hrs`,
      bugs: `~${quarterlyBugs}/quarter`,
    },
    annual: `$${annualCost.toLocaleString()}`,
  };
}

function computeImmutableBackups(vals: Record<string, number>): ComputeOutput {
  const servers = vals.servers;
  const recovery = vals.recovery;
  const incidents = vals.incidents;

  const revenuePerHour = Math.round(5000 * (servers / 20));
  const revenueLost = revenuePerHour * recovery;
  const engineers = Math.max(2, Math.min(12, Math.round(servers / 8)));
  const laborCost = engineers * recovery * 200;
  const reputationCost = Math.round((revenueLost + laborCost) * 0.3);
  const annualExposure = (revenueLost + laborCost + reputationCost) * incidents;

  return {
    results: {
      downtime: `${recovery} hours`,
      revenue: `$${revenueLost.toLocaleString()}`,
      labor: `$${laborCost.toLocaleString()}`,
      reputation: `$${reputationCost.toLocaleString()}`,
    },
    annual: `$${annualExposure.toLocaleString()}`,
  };
}

function computeMigrationSafety(vals: Record<string, number>): ComputeOutput {
  const data = vals.data;
  const migrations = vals.migrations;
  const hours = vals.hours;

  const exposureHours = migrations * hours;
  const laborCost = migrations * hours * 200;
  const breachPremium = data * 4880 * 0.01 * migrations;
  const reConfigCost = migrations * data * 80;
  const total = laborCost + breachPremium + reConfigCost;

  return {
    results: {
      windows: `${exposureHours} hrs`,
      risk: `${data} TB`,
      labor: `$${laborCost.toLocaleString()}`,
    },
    annual: `$${Math.round(total).toLocaleString()}`,
  };
}

function computeInstantRecovery(vals: Record<string, number>): ComputeOutput {
  const services = vals.services;
  const revHr = vals.revenue;
  const incidents = vals.incidents;

  const recoveryHrs = Math.round(services * 2.3);
  const revenueLost = recoveryHrs * revHr;
  const laborCost = 2 * recoveryHrs * 200;
  const churn = Math.round(revenueLost * 0.2);
  const total = (revenueLost + laborCost + churn) * incidents;

  const rRevLost = Math.round((revHr * 5) / 60);
  const rTotal = (rRevLost + 17) * incidents;

  return {
    results: {
      recoveryTime: `${recoveryHrs} hrs`,
      revenueLost: `$${revenueLost.toLocaleString()}`,
      labor: `$${laborCost.toLocaleString()}`,
      churn: `$${churn.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
    withResults: {
      revenueLost: `$${rRevLost.toLocaleString()}`,
    },
    withAnnual: `$${rTotal.toLocaleString()}`,
  };
}

function computeSafeOsTesting(vals: Record<string, number>): ComputeOutput {
  const servers = vals.servers;
  const patches = vals.patches;
  const recovery = vals.recovery;

  const exposureDays = patches * 30;
  const failureRate = 0.1;
  const incidentsPerYear = Math.ceil(patches * failureRate);
  const downtimeCost = Math.round(incidentsPerYear * recovery * 60 * 93);
  const laborCost = Math.round(incidentsPerYear * 3 * recovery * 200);
  const breachProb = Math.min((exposureDays / 365) * (servers / 50) * 0.02, 0.25);
  const breachCost = Math.round(4880000 * breachProb);
  const total = downtimeCost + laborCost + breachCost;

  return {
    results: {
      exposure: `${exposureDays} days`,
      downtime: `$${downtimeCost.toLocaleString()}`,
      labor: `$${laborCost.toLocaleString()}`,
      breach: `$${breachCost.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
  };
}

function computeRetentionCompliance(vals: Record<string, number>): ComputeOutput {
  const audits = vals.audits;
  const hours = vals.hours;
  const data = vals.data;

  const prepHours = audits * hours;
  const gaps = Math.max(1, Math.round(data / 5));
  const penalty = 50000;
  const labor = prepHours * 200;
  const total = gaps * penalty + labor;

  return {
    results: {
      prepHours: `${prepHours} hrs`,
      gaps: `${gaps}`,
      penalty: `$${(gaps * penalty).toLocaleString()}`,
      labor: `$${labor.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
  };
}

function computeCloudOutageProtection(vals: Record<string, number>): ComputeOutput {
  const rev = vals.rev;
  const outageHours = vals.hours;
  const failoverHours = vals.failover;

  const revPerHour = rev * 1000;
  const revLost = revPerHour * outageHours;
  const incidents = Math.ceil(outageHours / 4);
  const laborCost = Math.round(incidents * 3 * failoverHours * 200);
  const churnCost = Math.round(revLost * 0.2);
  const slaPenalty = Math.round(revLost * 0.1);
  const total = revLost + laborCost + churnCost + slaPenalty;

  return {
    results: {
      revenue: `$${revLost.toLocaleString()}`,
      labor: `$${laborCost.toLocaleString()}`,
      churn: `$${churnCost.toLocaleString()}`,
      sla: `$${slaPenalty.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
  };
}

function computeFailoverTesting(vals: Record<string, number>): ComputeOutput {
  const services = vals.services;
  const hours = vals.hours;
  const rev = vals.rev;

  const revRisk = rev * 1000 * hours;
  const labor = Math.ceil(services / 4) * 3 * hours * 200;
  const churn = Math.round(revRisk * 0.2);
  const compliance = Math.round(revRisk * 0.1);
  const total = revRisk + labor + churn + compliance;

  return {
    results: {
      revenue: `$${revRisk.toLocaleString()}`,
      labor: `$${labor.toLocaleString()}`,
      churn: `$${churn.toLocaleString()}`,
      compliance: `$${compliance.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
  };
}

function computeBackupVerification(vals: Record<string, number>): ComputeOutput {
  const jobs = vals.jobs;
  const corruption = vals.corruption;
  const recovery = vals.recovery;

  const corrupted = Math.round(jobs * 52 * (corruption / 100));
  const recoveryCost = corrupted * recovery * 100;
  const dataLoss = corrupted * 8 * 173;
  const total = recoveryCost + dataLoss;

  return {
    results: {
      corrupted: `${corrupted}`,
      undetected: `${corrupted}`,
      recoveryCost: `$${recoveryCost.toLocaleString()}`,
      dataLoss: `$${dataLoss.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
  };
}

function computeVulnerabilityManagement(vals: Record<string, number>): ComputeOutput {
  const vulns = vals.vulns;
  const fixDays = vals.fixDays;

  const failedPatches = Math.round(vulns * 12 * 0.25);
  const laborCost = vulns * 12 * Math.round(fixDays / 3) * 150;
  const total = laborCost + failedPatches * 5000;

  const withLabor = vulns * 12 * 300;
  const withTotal = vulns * 12 * 380;

  return {
    results: {
      exposure: `${fixDays} days`,
      failedPatches: `${failedPatches}`,
      labor: `$${laborCost.toLocaleString()}`,
    },
    annual: `$${total.toLocaleString()}`,
    withResults: {
      exposure: '1 day',
      failedPatches: '0',
      labor: `$${withLabor.toLocaleString()}`,
    },
    withAnnual: `$${withTotal.toLocaleString()}`,
  };
}

function computeAiPentesting(vals: Record<string, number>): ComputeOutput {
  const servers = vals.servers;
  const frequency = vals.frequency;
  const fixDays = vals.fixDays;

  const gapDays = Math.round(365 / frequency);
  const exposureWindow = gapDays + fixDays;
  const blindSpotPct = Math.round(((365 - frequency * 3) / 365) * 100);
  const pentestCost = frequency * Math.ceil(servers / 10) * 15000;
  const riskCost = Math.round(servers * (blindSpotPct / 100) * 2800);
  const totalCost = pentestCost + riskCost;

  const rCost = servers * 240;

  return {
    results: {
      exposure: `${exposureWindow} days`,
      blindspot: `${blindSpotPct}%`,
      pentestCost: `$${pentestCost.toLocaleString()}`,
    },
    annual: `$${totalCost.toLocaleString()}`,
    withResults: {
      exposure: `${fixDays} days`,
      blindspot: '0%',
      pentestCost: '$0',
    },
    withAnnual: `$${rCost.toLocaleString()}`,
  };
}

function computeEncryption(vals: Record<string, number>): ComputeOutput {
  const data = vals.data;
  const audits = vals.audits;
  const hours = vals.hours;

  const prepHours = audits * hours;
  const gaps = Math.max(1, Math.round(data / 5));
  const breachPremium = Math.round(data * 4880 * 0.05);
  const auditCost = prepHours * 200;
  const totalCost = auditCost + breachPremium;

  const rPrepHours = audits * 2;
  const rTotal = rPrepHours * 200;

  return {
    results: {
      prepHours: `${prepHours} hours`,
      gaps: `${gaps}`,
      exposure: '365 days',
      premium: `$${breachPremium.toLocaleString()}`,
    },
    annual: `$${totalCost.toLocaleString()}`,
    withResults: {
      prepHours: `${rPrepHours} hours`,
      gaps: '0',
      exposure: '0 days',
      premium: '$0',
    },
    withAnnual: `$${rTotal.toLocaleString()}`,
  };
}

function computeContinuousSecurityTesting(vals: Record<string, number>): ComputeOutput {
  const servers = vals.servers;
  const frequency = vals.frequency;
  const fixDays = vals.fixDays;

  const gapDays = Math.round(365 / frequency);
  const exposureWindow = gapDays + fixDays;
  const blindSpotPct = Math.round(((365 - frequency * 3) / 365) * 100);
  const pentestCost = frequency * Math.ceil(servers / 10) * 15000;
  const riskCost = Math.round(servers * (blindSpotPct / 100) * 2800);
  const totalCost = pentestCost + riskCost;

  const rCost = servers * 240;

  return {
    results: {
      exposure: `${exposureWindow} days`,
      blindspot: `${blindSpotPct}%`,
      pentestCost: `$${pentestCost.toLocaleString()}`,
    },
    annual: `$${totalCost.toLocaleString()}`,
    withResults: {
      exposure: `${fixDays} days`,
      blindspot: '0%',
      pentestCost: '$0',
    },
    withAnnual: `$${rCost.toLocaleString()}`,
  };
}

function computeAuditTrail(vals: Record<string, number>): ComputeOutput {
  const audits = vals.audits;
  const hours = vals.hours;
  const servers = vals.servers;

  const compileHours = audits * hours;
  const gaps = Math.max(1, Math.round(servers / 5));
  const delayCost = gaps * 12000;
  const penaltyCost = gaps * audits * 5000;
  const laborCost = compileHours * 200;
  const totalCost = laborCost + delayCost + penaltyCost;

  const rCompileHours = Number(audits);
  const rTotal = rCompileHours * 200;

  return {
    results: {
      compileHours: `${compileHours} hours`,
      gaps: `${gaps}`,
      delayCost: `$${delayCost.toLocaleString()}`,
      penaltyCost: `$${penaltyCost.toLocaleString()}`,
    },
    annual: `$${totalCost.toLocaleString()}`,
    withResults: {
      compileHours: `${rCompileHours} hours`,
      gaps: '0',
      delayCost: '$0',
      penaltyCost: '$0',
    },
    withAnnual: `$${rTotal.toLocaleString()}`,
  };
}

function computeRapidRecovery(vals: Record<string, number>): ComputeOutput {
  const rev = vals.rev;
  const hours = vals.hours;
  const inc = vals.inc;

  const revLost = rev * hours;
  const laborCost = 6 * hours * 200;
  const churnCost = Math.round(revLost * 0.2);
  const regCost = 50000 + Math.round((revLost + laborCost) * 0.1);
  const annualCost = (revLost + laborCost + churnCost + regCost) * inc;

  return {
    results: {
      revLost: `$${revLost.toLocaleString()}`,
      labor: `$${laborCost.toLocaleString()}`,
      churn: `$${churnCost.toLocaleString()}`,
      regulatory: `$${regCost.toLocaleString()}`,
    },
    annual: `$${annualCost.toLocaleString()}`,
    withResults: {
      revLost: '~$400',
      labor: '~$200',
      churn: '~$0',
      regulatory: '~$0',
    },
    withAnnual: '~$600',
  };
}

function computeVendorLockIn(vals: Record<string, number>): ComputeOutput {
  const spend = vals.spend;
  const years = vals.years;
  const increase = vals.increase;

  const annualSpend = spend * 1000 * 12;
  const markup = Math.round(annualSpend * (((increase / 100) * years) / 2));
  const migrateCost = Math.max(Math.round(2 * 6 * 10000 * (annualSpend / 120000)), 20000);
  const egressCost = Math.round(spend * 1000 * 0.5 * 0.09);
  const totalCost = markup + migrateCost + egressCost;

  return {
    results: {
      markup: `$${markup.toLocaleString()}`,
      migrate: `$${migrateCost.toLocaleString()}`,
      egress: `$${egressCost.toLocaleString()}`,
      leverage: 'None',
    },
    annual: `$${totalCost.toLocaleString()}`,
    withResults: {
      markup: '$0',
      migrate: '$0',
      egress: 'Minimal',
      leverage: 'Full',
    },
    withAnnual: '$0',
  };
}

export const PRESETS: Record<string, (vals: Record<string, number>) => ComputeOutput> = {
  'environment-cloning': computeEnvironmentCloning,
  'infrastructure-costs': computeInfrastructureCosts,
  'production-parity': computeProductionParity,
  integrations: computeIntegrations,
  'immutable-backups': computeImmutableBackups,
  'migration-safety': computeMigrationSafety,
  'instant-recovery': computeInstantRecovery,
  'safe-os-testing': computeSafeOsTesting,
  'retention-compliance': computeRetentionCompliance,
  'cloud-outage-protection': computeCloudOutageProtection,
  'failover-testing': computeFailoverTesting,
  'backup-verification': computeBackupVerification,
  'vulnerability-management': computeVulnerabilityManagement,
  'ai-pentesting': computeAiPentesting,
  encryption: computeEncryption,
  'continuous-security-testing': computeContinuousSecurityTesting,
  'audit-trail': computeAuditTrail,
  'rapid-recovery': computeRapidRecovery,
  'vendor-lock-in': computeVendorLockIn,
};

export { SLIDER_CONFIGS } from './slider-configs';
