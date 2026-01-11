/**
 * Utility functions for parsing and formatting data sizes (memory, disk, etc.)
 */

/**
 * Parses memory/disk size strings with units to bytes
 * Supports formats like: "685Mi", "3.8Gi", "2.5 G", "15GB", "1024KB", etc.
 *
 * @param sizeStr - Size string with optional unit
 * @returns Size in bytes, or 0 if invalid
 */
export function parseMemorySize(sizeStr: string): number {
  if (!sizeStr || typeof sizeStr !== 'string') return 0;

  // Extract number and unit from string like "685Mi", "3.8Gi", "2.5 G", "15GB" etc.
  const match = /^([\d.]+)\s*([KMGT]i?B?)?$/i.exec(sizeStr);
  if (!match) return 0;

  const value = Number.parseFloat(match[1]);
  if (Number.isNaN(value)) return 0;

  const unit = (match[2] || '').toUpperCase();

  // Convert to bytes based on unit
  // Binary units (1024-based)
  const binaryMultipliers: Record<string, number> = {
    KI: 1024,
    MI: 1024 * 1024,
    GI: 1024 * 1024 * 1024,
    TI: 1024 * 1024 * 1024 * 1024,
    KIB: 1024,
    MIB: 1024 * 1024,
    GIB: 1024 * 1024 * 1024,
    TIB: 1024 * 1024 * 1024 * 1024,
  };

  // Decimal units (1000-based) - less common for memory but used for disk
  const decimalMultipliers: Record<string, number> = {
    KB: 1000,
    MB: 1000 * 1000,
    GB: 1000 * 1000 * 1000,
    TB: 1000 * 1000 * 1000 * 1000,
  };

  // Common shorthand (usually treated as binary for memory/disk)
  const commonMultipliers: Record<string, number> = {
    K: 1024,
    M: 1024 * 1024,
    G: 1024 * 1024 * 1024,
    T: 1024 * 1024 * 1024 * 1024,
    B: 1,
  };

  const multiplier =
    binaryMultipliers[unit] || decimalMultipliers[unit] || commonMultipliers[unit] || 1;
  return value * multiplier;
}

/**
 * Calculates percentage for resource usage with fallback
 * Uses backend-provided percentage if available, otherwise calculates from used/total
 *
 * @param usePercent - Backend-provided percentage string (optional)
 * @param used - Used amount with unit
 * @param total - Total amount with unit
 * @returns Percentage between 0 and 100
 */
export function calculateResourcePercent(
  usePercent?: string,
  used?: string,
  total?: string
): number {
  // Use backend-provided percentage if available and valid
  if (usePercent) {
    const backendPercent = Number.parseInt(usePercent);
    if (!Number.isNaN(backendPercent) && backendPercent >= 0) {
      return Math.min(100, backendPercent);
    }
  }

  // Fallback: calculate from used/total
  if (!used || !total) return 0;

  const usedBytes = parseMemorySize(used);
  const totalBytes = parseMemorySize(total);

  if (totalBytes === 0) return 0;

  const percentage = Math.round((usedBytes / totalBytes) * 100);
  return Math.min(100, Math.max(0, percentage));
}
