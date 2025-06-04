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

let pricingCache: PricingConfig | null = null;
let cacheTimestamp: number | null = null;
const CACHE_DURATION = 1000 * 60 * 60; // 1 hour cache

export const fetchPricingConfig = async (): Promise<PricingConfig | null> => {
  // Return cached data if valid
  if (pricingCache && cacheTimestamp && (Date.now() - cacheTimestamp < CACHE_DURATION)) {
    return pricingCache;
  }

  try {
    const response = await fetch('/config/pricing.json');
    if (!response.ok) {
      throw new Error(`Failed to fetch pricing: ${response.status}`);
    }
    
    const data: PricingConfig = await response.json();
    
    // Cache the data
    pricingCache = data;
    cacheTimestamp = Date.now();
    
    return data;
  } catch (error) {
    console.error('Error fetching pricing configuration:', error);
    
    // If fetch fails, return the cached data if available
    if (pricingCache) {
      console.warn('Using cached pricing data due to fetch error');
      return pricingCache;
    }
    
    // Return null on failure (no fallback)
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
  
  // Handle "Free" pricing
  if (priceInfo.price === "Free" || priceInfo.price === "0") {
    return 0;
  }
  
  // Convert to number if it's a string
  const price = typeof priceInfo.price === 'string' ? parseFloat(priceInfo.price) : priceInfo.price;
  
  return isNaN(price) ? null : price;
};

// Helper function to clear cache (useful for testing)
export const clearPricingCache = () => {
  pricingCache = null;
  cacheTimestamp = null;
};