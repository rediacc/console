import regionsData from '../../../../regions.json';

export interface Region {
  id: string;
  label: string;
  domain: string;
  default: boolean;
}

export const REGIONS: Region[] = regionsData.regions.map((r) => ({
  id: r.id,
  label: r.label,
  domain: r.domain,
  default: r.default,
}));

export const DEFAULT_REGION = REGIONS.find((r) => r.default) ?? REGIONS[0];
