import { useState, useRef, useEffect } from 'react';

/**
 * useThrottle Hook
 * Limits the rate at which a value updates. Includes trailing flush to ensure
 * final value is captured after the throttle period ends.
 * 
 * @param {any} value - The value to throttle
 * @param {number} limit - The throttle limit in ms (default 500ms / 2fps)
 * @returns {any} - The throttled value
 */
export function useThrottle(value, limit = 500) {
    const [throttledValue, setThrottledValue] = useState(value);
    const lastRan = useRef(Date.now());
    const lastValue = useRef(value);

    // Update ref immediately so we always have the latest "real" value
    lastValue.current = value;

    useEffect(() => {
        const handler = setTimeout(function () {
            if (Date.now() - lastRan.current >= limit) {
                setThrottledValue(lastValue.current); // Flush latest
                lastRan.current = Date.now();
            }
        }, limit - (Date.now() - lastRan.current));

        return () => clearTimeout(handler);
    }, [value, limit]);

    return throttledValue;
}
