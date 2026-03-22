export type CompanySize = 'smb' | 'mid' | 'enterprise' | 'large';

export interface RoiSliderConfig {
  id: string;
  min: number;
  max: number;
  step: number;
  format?: 'currency' | 'percent' | 'decimal' | 'number';
}

export const HERO_SLIDERS: RoiSliderConfig[] = [
  { id: 'servers', min: 1, max: 1000, step: 1 },
  { id: 'developers', min: 0, max: 500, step: 1 },
  { id: 'dataTB', min: 1, max: 2000, step: 1 },
  { id: 'downtimeCostPerHour', min: 1000, max: 5000000, step: 1000, format: 'currency' },
  { id: 'incidentsPerYear', min: 0, max: 12, step: 1 },
  { id: 'currentRtoHours', min: 1, max: 72, step: 1 },
];

export const ADVANCED_SLIDERS: RoiSliderConfig[] = [
  { id: 'adminHourlyRate', min: 50, max: 200, step: 5, format: 'currency' },
  { id: 'devHourlyRate', min: 50, max: 250, step: 5, format: 'currency' },
  { id: 'adminFte', min: 0.1, max: 10, step: 0.1, format: 'decimal' },
  { id: 'currentBackupSpendMonth', min: 100, max: 50000, step: 100, format: 'currency' },
  { id: 'dataGrowthRate', min: 5, max: 50, step: 5, format: 'percent' },
  { id: 'envRequestsPerDevMonth', min: 1, max: 10, step: 1 },
  { id: 'currentProvisioningHours', min: 1, max: 40, step: 1 },
];

export interface RoiInputs {
  servers: number;
  developers: number;
  dataTB: number;
  downtimeCostPerHour: number;
  incidentsPerYear: number;
  currentRtoHours: number;
  adminHourlyRate: number;
  devHourlyRate: number;
  adminFte: number;
  currentBackupSpendMonth: number;
  dataGrowthRate: number;
  envRequestsPerDevMonth: number;
  currentProvisioningHours: number;
}

export interface RoiOutputs {
  annualSavings: number;
  paybackMonths: number;
  threeYearRoiPct: number;

  currentAnnualTco: number;
  rediaccAnnualTco: number;
  tcoSavings: number;

  devProductivityHours: number;
  devProductivityDollars: number;
  provisioningReduction: string;

  currentDowntimeRisk: number;
  rediaccDowntimeRisk: number;
  drSavings: number;
  rtoImprovement: string;

  storageSavings: number;
  bandwidthSavings: number;

  complianceSavings: number;
  insuranceSavings: number;
  auditHoursSaved: number;
}

/* Benchmark defaults by company size (research Section 10.5) */
export const ROI_DEFAULTS: Record<CompanySize, RoiInputs> = {
  smb: {
    servers: 10,
    developers: 5,
    dataTB: 5,
    downtimeCostPerHour: 25000,
    incidentsPerYear: 2,
    currentRtoHours: 4,
    adminHourlyRate: 75,
    devHourlyRate: 100,
    adminFte: 0.3,
    currentBackupSpendMonth: 500,
    dataGrowthRate: 25,
    envRequestsPerDevMonth: 2,
    currentProvisioningHours: 12,
  },
  mid: {
    servers: 50,
    developers: 20,
    dataTB: 50,
    downtimeCostPerHour: 200000,
    incidentsPerYear: 2,
    currentRtoHours: 6,
    adminHourlyRate: 75,
    devHourlyRate: 100,
    adminFte: 1.0,
    currentBackupSpendMonth: 2000,
    dataGrowthRate: 25,
    envRequestsPerDevMonth: 2,
    currentProvisioningHours: 12,
  },
  enterprise: {
    servers: 200,
    developers: 100,
    dataTB: 500,
    downtimeCostPerHour: 1000000,
    incidentsPerYear: 3,
    currentRtoHours: 8,
    adminHourlyRate: 75,
    devHourlyRate: 100,
    adminFte: 3.0,
    currentBackupSpendMonth: 10000,
    dataGrowthRate: 25,
    envRequestsPerDevMonth: 2,
    currentProvisioningHours: 12,
  },
  large: {
    servers: 500,
    developers: 300,
    dataTB: 2000,
    downtimeCostPerHour: 3000000,
    incidentsPerYear: 4,
    currentRtoHours: 12,
    adminHourlyRate: 75,
    devHourlyRate: 100,
    adminFte: 6.0,
    currentBackupSpendMonth: 30000,
    dataGrowthRate: 25,
    envRequestsPerDevMonth: 2,
    currentProvisioningHours: 12,
  },
};

/* Rediacc RTO by company size (research Section 7.2) */
const REDIACC_RTO_MINUTES: Record<CompanySize, number> = {
  smb: 10,
  mid: 20,
  enterprise: 30,
  large: 45,
};

function inferCompanySize(servers: number): CompanySize {
  if (servers <= 25) return 'smb';
  if (servers <= 125) return 'mid';
  if (servers <= 350) return 'enterprise';
  return 'large';
}

export function computeRoi(inputs: RoiInputs): RoiOutputs {
  const {
    servers,
    developers,
    dataTB,
    downtimeCostPerHour,
    incidentsPerYear,
    currentRtoHours,
    adminHourlyRate,
    devHourlyRate,
    adminFte,
    currentBackupSpendMonth,
    envRequestsPerDevMonth,
    currentProvisioningHours,
  } = inputs;

  const size = inferCompanySize(servers);

  // --- TCO ---
  const currentAdminCost = adminFte * adminHourlyRate * 2080;
  const currentDrTesting = 4 * Math.max(8, servers / 5) * adminHourlyRate * 3;
  const currentMaintenance = servers * 40 * adminHourlyRate;
  const currentLicense = currentBackupSpendMonth * 12;
  const currentAnnualTco =
    currentLicense + currentAdminCost + currentDrTesting + currentMaintenance;

  const rediaccAdminCost = adminFte * 0.3 * adminHourlyRate * 2080;
  const rediaccMaintenance = servers * 8 * adminHourlyRate;
  const rediaccLicense = servers * 100 * 12;
  const rediaccAnnualTco = rediaccLicense + rediaccAdminCost + rediaccMaintenance;

  const tcoSavings = currentAnnualTco - rediaccAnnualTco;

  // --- Dev Productivity (research Section 6.3) ---
  const provisioningSavedHours =
    developers * envRequestsPerDevMonth * 12 * Math.max(0, currentProvisioningHours - 0.08);
  const devProductivityDollars = provisioningSavedHours * devHourlyRate * 0.4;
  const provisioningReduction =
    currentProvisioningHours > 0 ? `${currentProvisioningHours}h → <5 min` : '—';

  // --- DR & Availability (research Section 7.3) ---
  const rediaccRtoMin = REDIACC_RTO_MINUTES[size];
  const currentDowntimeRisk = incidentsPerYear * currentRtoHours * downtimeCostPerHour;
  const rediaccDowntimeRisk = incidentsPerYear * (rediaccRtoMin / 60) * downtimeCostPerHour;
  const drSavings = currentDowntimeRisk - rediaccDowntimeRisk;
  const rtoImprovement = `${currentRtoHours}h → ${rediaccRtoMin} min`;

  // --- Storage & Bandwidth (research Sections 8.1, 8.4) ---
  // Traditional: ~6× source for retention; CoW: ~0.35× source → save 5.65× at $40/TB/yr
  const storageSavings = dataTB * 5.65 * 40;
  // WAN bandwidth: 98% reduction on annual replication cost (~$635/TB/yr baseline)
  const bandwidthSavings = dataTB * 635 * 0.98;

  // --- Compliance (research Section 9.2) ---
  const currentAuditHours = Math.max(400, servers * 6);
  const rediaccAuditHours = currentAuditHours * 0.15;
  const complianceSavings = (currentAuditHours - rediaccAuditHours) * adminHourlyRate;
  const auditHoursSaved = currentAuditHours - rediaccAuditHours;

  // --- Insurance (research Section 9.4) ---
  // 30% premium reduction on estimated premium (~10% of annual downtime risk)
  const insuranceSavings = incidentsPerYear > 0 ? currentDowntimeRisk * 0.03 : 0;

  // --- Summary ---
  const annualSavings =
    tcoSavings +
    devProductivityDollars +
    drSavings +
    storageSavings +
    bandwidthSavings +
    complianceSavings +
    insuranceSavings;
  const investment = rediaccAnnualTco;
  const paybackMonths =
    annualSavings > 0 ? Math.max(1, Math.round((investment / annualSavings) * 12)) : 0;
  const threeYearRoiPct =
    investment > 0 ? Math.round(((annualSavings * 3 - investment) / investment) * 100) : 0;

  return {
    annualSavings,
    paybackMonths,
    threeYearRoiPct,
    currentAnnualTco,
    rediaccAnnualTco,
    tcoSavings,
    devProductivityHours: provisioningSavedHours,
    devProductivityDollars,
    provisioningReduction,
    currentDowntimeRisk,
    rediaccDowntimeRisk,
    drSavings,
    rtoImprovement,
    storageSavings,
    bandwidthSavings,
    complianceSavings,
    insuranceSavings,
    auditHoursSaved,
  };
}

/** Format a number as compact currency: $1.2M, $450K, $3,200 */
export function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${sign}$${Math.round(abs / 1_000)}K`;
  if (abs >= 1_000) return `${sign}$${Number(abs.toFixed(0)).toLocaleString('en-US')}`;
  return `${sign}$${abs.toFixed(0)}`;
}

/** Format a slider display value based on its format type */
export function formatSliderValue(value: number, format?: string): string {
  if (format === 'currency') return formatCurrency(value);
  if (format === 'percent') return `${value}%`;
  if (format === 'decimal') return value.toFixed(1);
  return String(value);
}
