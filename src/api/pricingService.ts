// Pricing service to fetch centralized pricing configuration

export interface PricingConfig {
  baseMonthlyPrices: {
    [key: string]: {
      price: number | string;
      originalPrice?: number;
      period: string | null;
    };
  };
  yearlyMultipliers: {
    [key: string]: {
      multiplier: number;
      savePercent: string;
    };
  };
  specialDayDiscounts: {
    [key: string]: {
      name: string;
      startDate: string;
      endDate: string;
      discount: number;
      message: string;
      bannerColor: string;
      backgroundColor: string;
      stripeCouponCode: string;
    };
  };
  plans: {
    [key: string]: {
      name: string;
      isPopular: boolean;
      ctaText: string;
      ctaLink: string;
      ctaVariant: string;
    };
  };
}

const pricingCache = new Map<string, PricingConfig>();
const cacheTimestamps = new Map<string, number>();
const CACHE_DURATION = 1000 * 60 * 60; // 1 hour cache

export const fetchPricingConfig = async (): Promise<PricingConfig | null> => {
  const cacheKey = 'pricing';

  // Return cached data if valid
  const cachedData = pricingCache.get(cacheKey);
  const cacheTimestamp = cacheTimestamps.get(cacheKey);

  if (cachedData && cacheTimestamp && (Date.now() - cacheTimestamp < CACHE_DURATION)) {
    return cachedData;
  }

  try {
    // Always fetch the base pricing.json (English content)
    const response = await fetch('/configs/pricing.json');
    if (!response.ok) {
      throw new Error(`Failed to fetch pricing: ${response.status}`);
    }

    const data: PricingConfig = await response.json();

    // Cache the data
    pricingCache.set(cacheKey, data);
    cacheTimestamps.set(cacheKey, Date.now());

    return data;
  } catch (error) {
    // If fetch fails, return the cached data if available
    if (cachedData) {
      return cachedData;
    }

    // Return null on failure
    return null;
  }
};

// Helper function to get price for a plan
export const getPlanPrice = (pricing: PricingConfig, planCode: string): number | null => {
  // Map plan codes to pricing keys
  const planMap: Record<string, string> = {
    'COMMUNITY': 'community',
    'ADVANCED': 'advanced',
    'PREMIUM': 'premium',
    'ELITE': 'elite'
  };
  
  const pricingKey = planMap[planCode] || planCode.toLowerCase();
  const priceInfo = pricing.baseMonthlyPrices[pricingKey];
  
  if (!priceInfo) return null;
  
  // Handle "Free" or "Gratis" pricing
  if (typeof priceInfo.price === 'string' && (priceInfo.price.toLowerCase() === "free" || priceInfo.price.toLowerCase() === "gratis" || priceInfo.price === "0")) {
    return 0;
  }
  
  // Convert to number if it's a string
  const price = typeof priceInfo.price === 'string' ? parseFloat(priceInfo.price) : priceInfo.price;
  
  return isNaN(price) ? null : price;
};

// Helper function to clear cache (useful for testing)
export const clearPricingCache = () => {
  pricingCache.clear();
  cacheTimestamps.clear();
};