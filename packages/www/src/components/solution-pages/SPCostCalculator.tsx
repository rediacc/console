import React, { useState, useCallback, useMemo } from 'react';

interface CalculatorContent {
  overline: string;
  title: string;
  description: string;
  headerTitle: string;
  sliders: Record<string, string>;
  withoutTag: string;
  withTag: string;
  results: Record<string, string>;
  annualLabel: string;
  withResults: Record<string, string>;
  withResultLabels?: Record<string, string>;
  withAnnual: string;
  withAnnualLabel?: string;
  footnote: string;
}

interface SliderConfig {
  id: string;
  min: number;
  max: number;
  step?: number;
  defaultValue: number;
}

interface ComputeOutput {
  results: Record<string, string>;
  annual: string;
  withResults?: Record<string, string>;
  withAnnual?: string;
}

interface Props {
  content: CalculatorContent;
  preset: string;
}

/** Calculator compute presets — each page can have different formulas */
function computeEnvironmentCloning(
  vals: Record<string, number>
): ComputeOutput {
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
      blockedTime: `${totalBlocked} dev-day${totalBlocked !== 1 ? 's' : ''}`,
      sprintCapacity: `${pctBlocked}%`,
      contextSwitching: `$${ctxTotal.toLocaleString()}/yr`,
      quarterlySlip: `~${quarterlySlip} day${quarterlySlip !== 1 ? 's' : ''}`,
    },
    annual: `$${annualCost.toLocaleString()}`,
  };
}

function computeInfrastructureCosts(
  vals: Record<string, number>
): ComputeOutput {
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

function computeProductionParity(
  vals: Record<string, number>
): ComputeOutput {
  const devs = vals.devs;
  const bugs = vals.bugs;
  const hours = vals.hours;

  const debugHours = bugs * hours;
  const sprintHours = devs * 10 * 8;
  const capacityPct = Math.min(
    Math.round((debugHours / sprintHours) * 100 * devs),
    100
  );
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

function computeIntegrations(
  vals: Record<string, number>
): ComputeOutput {
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

function computeImmutableBackups(
  vals: Record<string, number>
): ComputeOutput {
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

function computeMigrationSafety(
  vals: Record<string, number>
): ComputeOutput {
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

function computeInstantRecovery(
  vals: Record<string, number>
): ComputeOutput {
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

function computeSafeOsTesting(
  vals: Record<string, number>
): ComputeOutput {
  const servers = vals.servers;
  const patches = vals.patches;
  const recovery = vals.recovery;

  const exposureDays = patches * 30;
  const failureRate = 0.1;
  const incidentsPerYear = Math.ceil(patches * failureRate);
  const downtimeCost = Math.round(incidentsPerYear * recovery * 60 * 93);
  const laborCost = Math.round(incidentsPerYear * 3 * recovery * 200);
  const breachProb = Math.min(
    (exposureDays / 365) * (servers / 50) * 0.02,
    0.25
  );
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

function computeRetentionCompliance(
  vals: Record<string, number>
): ComputeOutput {
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

function computeCloudOutageProtection(
  vals: Record<string, number>
): ComputeOutput {
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

function computeFailoverTesting(
  vals: Record<string, number>
): ComputeOutput {
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

function computeBackupVerification(
  vals: Record<string, number>
): ComputeOutput {
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

function computeVulnerabilityManagement(
  vals: Record<string, number>
): ComputeOutput {
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

function computeAiPentesting(
  vals: Record<string, number>
): ComputeOutput {
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

function computeEncryption(
  vals: Record<string, number>
): ComputeOutput {
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

function computeContinuousSecurityTesting(
  vals: Record<string, number>
): ComputeOutput {
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

function computeAuditTrail(
  vals: Record<string, number>
): ComputeOutput {
  const audits = vals.audits;
  const hours = vals.hours;
  const servers = vals.servers;

  const compileHours = audits * hours;
  const gaps = Math.max(1, Math.round(servers / 5));
  const delayCost = gaps * 12000;
  const penaltyCost = gaps * audits * 5000;
  const laborCost = compileHours * 200;
  const totalCost = laborCost + delayCost + penaltyCost;

  const rCompileHours = audits * 1;
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

function computeRapidRecovery(
  vals: Record<string, number>
): ComputeOutput {
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

function computeVendorLockIn(
  vals: Record<string, number>
): ComputeOutput {
  const spend = vals.spend;
  const years = vals.years;
  const increase = vals.increase;

  const annualSpend = spend * 1000 * 12;
  const markup = Math.round(annualSpend * ((increase / 100) * years / 2));
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

const PRESETS: Record<
  string,
  (vals: Record<string, number>) => ComputeOutput
> = {
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

const SLIDER_CONFIGS: Record<string, SliderConfig[]> = {
  'environment-cloning': [
    { id: 'devs', min: 1, max: 50, defaultValue: 10 },
    { id: 'reqs', min: 1, max: 10, defaultValue: 2 },
    { id: 'wait', min: 1, max: 5, defaultValue: 3 },
  ],
  'infrastructure-costs': [
    { id: 'envs', min: 1, max: 50, defaultValue: 15 },
    { id: 'cost', min: 50, max: 1000, step: 50, defaultValue: 200 },
    { id: 'util', min: 10, max: 80, defaultValue: 33 },
  ],
  'production-parity': [
    { id: 'devs', min: 1, max: 50, defaultValue: 10 },
    { id: 'bugs', min: 1, max: 15, defaultValue: 3 },
    { id: 'hours', min: 1, max: 16, defaultValue: 4 },
  ],
  integrations: [
    { id: 'devs', min: 1, max: 50, defaultValue: 10 },
    { id: 'failures', min: 1, max: 20, defaultValue: 4 },
    { id: 'hours', min: 1, max: 8, defaultValue: 3 },
  ],
  'immutable-backups': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'recovery', min: 1, max: 168, defaultValue: 72 },
    { id: 'incidents', min: 1, max: 6, defaultValue: 1 },
  ],
  'migration-safety': [
    { id: 'data', min: 1, max: 100, defaultValue: 20 },
    { id: 'migrations', min: 1, max: 12, defaultValue: 3 },
    { id: 'hours', min: 1, max: 48, defaultValue: 8 },
  ],
  'instant-recovery': [
    { id: 'services', min: 1, max: 30, defaultValue: 8 },
    { id: 'revenue', min: 500, max: 50000, step: 500, defaultValue: 5000 },
    { id: 'incidents', min: 1, max: 12, defaultValue: 2 },
  ],
  'safe-os-testing': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'patches', min: 1, max: 24, defaultValue: 6 },
    { id: 'recovery', min: 1, max: 48, defaultValue: 8 },
  ],
  'retention-compliance': [
    { id: 'audits', min: 1, max: 4, defaultValue: 2 },
    { id: 'hours', min: 8, max: 200, defaultValue: 80 },
    { id: 'data', min: 1, max: 100, defaultValue: 20 },
  ],
  'cloud-outage-protection': [
    { id: 'rev', min: 1, max: 100, defaultValue: 10 },
    { id: 'hours', min: 1, max: 72, defaultValue: 8 },
    { id: 'failover', min: 1, max: 24, defaultValue: 4 },
  ],
  'failover-testing': [
    { id: 'services', min: 1, max: 50, defaultValue: 12 },
    { id: 'hours', min: 1, max: 72, defaultValue: 8 },
    { id: 'rev', min: 1, max: 100, defaultValue: 10 },
  ],
  'backup-verification': [
    { id: 'jobs', min: 1, max: 50, defaultValue: 14 },
    { id: 'corruption', min: 1, max: 20, defaultValue: 5 },
    { id: 'recovery', min: 1, max: 48, defaultValue: 12 },
  ],
  'vulnerability-management': [
    { id: 'vulns', min: 1, max: 20, defaultValue: 5 },
    { id: 'fixDays', min: 1, max: 30, defaultValue: 21 },
  ],
  'ai-pentesting': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'frequency', min: 1, max: 12, defaultValue: 2 },
    { id: 'fixDays', min: 1, max: 30, defaultValue: 14 },
  ],
  encryption: [
    { id: 'data', min: 1, max: 100, defaultValue: 20 },
    { id: 'audits', min: 1, max: 4, defaultValue: 2 },
    { id: 'hours', min: 8, max: 200, defaultValue: 40 },
  ],
  'continuous-security-testing': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'frequency', min: 1, max: 12, defaultValue: 1 },
    { id: 'fixDays', min: 1, max: 30, defaultValue: 14 },
  ],
  'audit-trail': [
    { id: 'audits', min: 1, max: 4, defaultValue: 2 },
    { id: 'hours', min: 8, max: 200, defaultValue: 60 },
    { id: 'servers', min: 1, max: 100, defaultValue: 15 },
  ],
  'rapid-recovery': [
    { id: 'rev', min: 1000, max: 50000, step: 1000, defaultValue: 5000 },
    { id: 'hours', min: 1, max: 168, defaultValue: 72 },
    { id: 'inc', min: 1, max: 6, defaultValue: 1 },
  ],
  'vendor-lock-in': [
    { id: 'spend', min: 1, max: 100, defaultValue: 10 },
    { id: 'years', min: 1, max: 10, defaultValue: 3 },
    { id: 'increase', min: 5, max: 40, defaultValue: 15 },
  ],
};

const SPCostCalculator: React.FC<Props> = ({ content, preset }) => {
  const sliderConfigs = SLIDER_CONFIGS[preset] ?? [];
  const computeFn = PRESETS[preset];

  const initialValues = useMemo(() => {
    const vals: Record<string, number> = {};
    for (const s of sliderConfigs) {
      vals[s.id] = s.defaultValue;
    }
    return vals;
  }, []);

  const [values, setValues] = useState(initialValues);

  const handleChange = useCallback((id: string, val: number) => {
    setValues((prev) => ({ ...prev, [id]: val }));
  }, []);

  const computed = computeFn ? computeFn(values) : { results: {}, annual: '—' };
  const resultKeys = Object.keys(content.results);

  return (
    <section className="sp-cost-section">
      <div className="sp-cost-section-inner">
        <div className="sp-overline">{content.overline}</div>
        <h2>{content.title}</h2>
        <p>{content.description}</p>

        <div className="sp-calculator">
          <div className="sp-calc-header">
            <svg viewBox="0 0 24 24">
              <rect x="4" y="2" width="16" height="20" rx="2" />
              <line x1="8" y1="6" x2="16" y2="6" />
              <line x1="8" y1="10" x2="10" y2="10" />
              <line x1="12" y1="10" x2="14" y2="10" />
              <line x1="8" y1="14" x2="10" y2="14" />
              <line x1="12" y1="14" x2="14" y2="14" />
              <line x1="8" y1="18" x2="16" y2="18" />
            </svg>
            <h3>{content.headerTitle}</h3>
          </div>

          <div className="sp-calc-inputs">
            {sliderConfigs.map((slider) => (
              <div className="sp-calc-input" key={slider.id}>
                <label>
                  {content.sliders[slider.id]}
                  <span className="sp-calc-input-value">{values[slider.id]}</span>
                </label>
                <input
                  type="range"
                  min={slider.min}
                  max={slider.max}
                  step={slider.step ?? 1}
                  value={values[slider.id]}
                  onChange={(e) =>
                    handleChange(slider.id, parseInt(e.target.value))
                  }
                />
              </div>
            ))}
          </div>

          <div className="sp-calc-results">
            <div className="sp-calc-result-col without">
              <div className="sp-calc-result-tag">{content.withoutTag}</div>
              {resultKeys.map((key) => (
                <div className="sp-calc-result-row" key={key}>
                  <span>{content.results[key]}</span>
                  <span className="sp-calc-result-num">
                    {computed.results[key] ?? '—'}
                  </span>
                </div>
              ))}
              <div className="sp-calc-result-big">
                <div className="sp-calc-result-big-label">
                  {content.annualLabel}
                </div>
                <div className="sp-calc-result-big-value">
                  {computed.annual}
                </div>
              </div>
            </div>
            <div className="sp-calc-result-col with">
              <div className="sp-calc-result-tag">{content.withTag}</div>
              {resultKeys.map((key) => (
                <div className="sp-calc-result-row" key={key}>
                  <span>{content.withResultLabels?.[key] ?? content.results[key]}</span>
                  <span className="sp-calc-result-num">
                    {computed.withResults?.[key] ?? content.withResults[key] ?? '—'}
                  </span>
                </div>
              ))}
              <div className="sp-calc-result-big">
                <div className="sp-calc-result-big-label">
                  {content.withAnnualLabel ?? content.annualLabel}
                </div>
                <div className="sp-calc-result-big-value">
                  {computed.withAnnual ?? content.withAnnual}
                </div>
              </div>
            </div>
          </div>

          <div className="sp-calc-footnote">{content.footnote}</div>
        </div>
      </div>
    </section>
  );
};

export default SPCostCalculator;
