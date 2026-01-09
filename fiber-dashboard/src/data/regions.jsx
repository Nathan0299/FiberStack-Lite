/**
 * Regional coordinates for probe locations.
 * Lat/Lng for major cities in Ghana, Nigeria, Kenya.
 */
export const REGION_COORDS = {
    // Ghana
    'Accra': { lat: 5.6037, lng: -0.1870, country: 'GH' },
    'Kumasi': { lat: 6.6885, lng: -1.6244, country: 'GH' },
    'Tamale': { lat: 9.4034, lng: -0.8393, country: 'GH' },

    // Nigeria
    'Lagos': { lat: 6.5244, lng: 3.3792, country: 'NG' },
    'Abuja': { lat: 9.0765, lng: 7.3986, country: 'NG' },
    'Kano': { lat: 12.0022, lng: 8.5919, country: 'NG' },

    // Kenya
    'Nairobi': { lat: -1.2921, lng: 36.8219, country: 'KE' },
    'Mombasa': { lat: -4.0435, lng: 39.6682, country: 'KE' },
    'Kisumu': { lat: -0.0917, lng: 34.7680, country: 'KE' },
};

// Aliases for fuzzy matching
const REGION_ALIASES = {
    'greater accra': 'Accra',
    'accra region': 'Accra',
    'lagos mainland': 'Lagos',
    'lagos island': 'Lagos',
    'fct': 'Abuja',
    'test region': 'Accra',
};

/**
 * Get coordinates with fuzzy matching.
 * Returns null with console warning for unknown regions.
 */
export function getCoords(region) {
    if (!region) {
        console.warn('MapViz: No region provided');
        return null;
    }

    // Direct match
    if (REGION_COORDS[region]) {
        return REGION_COORDS[region];
    }

    // Fuzzy match via alias
    const normalized = region.toLowerCase().trim();
    const aliased = REGION_ALIASES[normalized];
    if (aliased && REGION_COORDS[aliased]) {
        return REGION_COORDS[aliased];
    }

    // Partial match (contains)
    for (const key of Object.keys(REGION_COORDS)) {
        if (normalized.includes(key.toLowerCase())) {
            return REGION_COORDS[key];
        }
    }

    console.warn(`MapViz: Unknown region "${region}"`);
    return null;
}

// Latency thresholds (documented)
export const LATENCY_GREEN = 100;   // <100ms = healthy
export const LATENCY_YELLOW = 200; // 100-200ms = degraded
