// Core utilities for Black Diamond Web Application
// Essential utility functions shared across all modules

/**
 * Safely escape HTML to prevent XSS attacks
 * @param {string} text - The text to escape
 * @returns {string} - Escaped HTML string
 */
export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Debounce function to limit the rate of function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Time in milliseconds to wait
 * @param {boolean} immediate - Trigger on leading edge
 * @returns {Function} - Debounced function
 */
export function debounce(func, wait, immediate = false) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func(...args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func(...args);
    };
}

/**
 * Throttle function to limit function calls to once per interval
 * @param {Function} func - Function to throttle
 * @param {number} limit - Time in milliseconds between calls
 * @returns {Function} - Throttled function
 */
export function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Check if device has reduced motion preference
 * @returns {boolean} - True if user prefers reduced motion
 */
export function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Check if device has low performance
 * @returns {boolean} - True if device is low-end
 */
export function isLowEndDevice() {
    const cores = navigator.hardwareConcurrency || 4;
    return cores <= 2;
}

/**
 * Check if connection is slow
 * @returns {boolean} - True if connection is slow
 */
export function isSlowConnection() {
    if (!navigator.connection) return false;
    
    const connection = navigator.connection;
    return (
        connection.effectiveType === 'slow-2g' ||
        connection.effectiveType === '2g' ||
        connection.downlink < 1
    );
}

/**
 * Detect if device is mobile
 * @returns {boolean} - True if mobile device
 */
export function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

/**
 * Safe localStorage get item
 * @param {string} key - Storage key
 * @param {any} defaultValue - Default value if not found
 * @returns {any} - Stored value or default
 */
export function safeGetStorage(key, defaultValue = null) {
    try {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : defaultValue;
    } catch (error) {
        console.warn(`Failed to get storage item '${key}':`, error);
        return defaultValue;
    }
}

/**
 * Safe localStorage set item
 * @param {string} key - Storage key
 * @param {any} value - Value to store
 * @returns {boolean} - True if successful
 */
export function safeSetStorage(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch (error) {
        console.warn(`Failed to set storage item '${key}':`, error);
        return false;
    }
}

/**
 * Create a safe ID for elements
 * @param {string} prefix - ID prefix
 * @returns {string} - Unique ID
 */
export function createSafeId(prefix = 'safe') {
    return `${prefix}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Check if element is in viewport
 * @param {Element} element - DOM element to check
 * @param {number} threshold - Visibility threshold (0-1)
 * @returns {boolean} - True if in viewport
 */
export function isInViewport(element, threshold = 0.1) {
    const rect = element.getBoundingClientRect();
    const windowHeight = window.innerHeight || document.documentElement.clientHeight;
    const windowWidth = window.innerWidth || document.documentElement.clientWidth;
    
    return (
        rect.top >= -threshold * windowHeight &&
        rect.left >= -threshold * windowWidth &&
        rect.bottom <= windowHeight + threshold * windowHeight &&
        rect.right <= windowWidth + threshold * windowWidth
    );
}

/**
 * Get computed style value with fallbacks
 * @param {Element} element - DOM element
 * @param {string} property - CSS property name
 * @param {string} fallback - Fallback value
 * @returns {string} - Computed value or fallback
 */
export function getComputedStyleSafe(element, property, fallback = '') {
    try {
        const computed = window.getComputedStyle(element);
        return computed.getPropertyValue(property) || fallback;
    } catch (error) {
        console.warn(`Failed to get computed style for '${property}':`, error);
        return fallback;
    }
}

/**
 * Smooth scroll to element
 * @param {Element|string} target - Element or selector to scroll to
 * @param {Object} options - Scroll options
 */
export function smoothScrollTo(target, options = {}) {
    const defaultOptions = {
        behavior: 'smooth',
        block: 'start',
        inline: 'nearest',
        ...options
    };
    
    try {
        if (typeof target === 'string') {
            const element = document.querySelector(target);
            if (element) {
                element.scrollIntoView(defaultOptions);
            }
        } else if (target instanceof Element) {
            target.scrollIntoView(defaultOptions);
        }
    } catch (error) {
        console.warn('Failed to smooth scroll:', error);
        // Fallback to basic scroll
        window.scrollTo(0, 0);
    }
}

/**
 * Format number with locale
 * @param {number} num - Number to format
 * @param {string} locale - Locale string
 * @returns {string} - Formatted number
 */
export function formatNumber(num, locale = 'en-US') {
    try {
        return new Intl.NumberFormat(locale).format(num);
    } catch (error) {
        console.warn('Failed to format number:', error);
        return num.toString();
    }
}

/**
 * Format currency
 * @param {number} amount - Amount to format
 * @param {string} currency - Currency code
 * @param {string} locale - Locale string
 * @returns {string} - Formatted currency
 */
export function formatCurrency(amount, currency = 'USD', locale = 'en-US') {
    try {
        return new Intl.NumberFormat(locale, {
            style: 'currency',
            currency: currency
        }).format(amount);
    } catch (error) {
        console.warn('Failed to format currency:', error);
        return `${currency} ${amount.toFixed(2)}`;
    }
}

/**
 * Clamp number between min and max
 * @param {number} value - Value to clamp
 * @param {number} min - Minimum value
 * @param {number} max - Maximum value
 * @returns {number} - Clamped value
 */
export function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

/**
 * Linear interpolation
 * @param {number} start - Start value
 * @param {number} end - End value
 * @param {number} factor - Interpolation factor (0-1)
 * @returns {number} - Interpolated value
 */
export function lerp(start, end, factor) {
    return start + (end - start) * factor;
}

/**
 * Check if value is valid email
 * @param {string} email - Email to validate
 * @returns {boolean} - True if valid email
 */
export function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Check if value is valid URL
 * @param {string} url - URL to validate
 * @returns {boolean} - True if valid URL
 */
export function isValidUrl(url) {
    try {
        new URL(url);
        return true;
    } catch {
        return false;
    }
}

/**
 * Generate random ID
 * @param {number} length - ID length
 * @returns {string} - Random ID
 */
export function generateId(length = 8) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

/**
 * Deep clone object
 * @param {any} obj - Object to clone
 * @returns {any} - Cloned object
 */
export function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    if (obj instanceof Date) return new Date(obj.getTime());
    if (obj instanceof Array) return obj.map(item => deepClone(item));
    if (typeof obj === 'object') {
        const clonedObj = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                clonedObj[key] = deepClone(obj[key]);
            }
        }
        return clonedObj;
    }
}

/**
 * Merge objects deeply
 * @param {Object} target - Target object
 * @param {...Object} sources - Source objects to merge
 * @returns {Object} - Merged object
 */
export function deepMerge(target, ...sources) {
    if (!sources.length) return target;
    const source = sources.shift();
    
    if (isObject(target) && isObject(source)) {
        for (const key in source) {
            if (isObject(source[key])) {
                if (!target[key]) Object.assign(target, { [key]: {} });
                deepMerge(target[key], source[key]);
            } else {
                Object.assign(target, { [key]: source[key] });
            }
        }
    }
    
    return deepMerge(target, ...sources);
}

/**
 * Check if value is object
 * @param {any} item - Value to check
 * @returns {boolean} - True if object
 */
function isObject(item) {
    return item && typeof item === 'object' && !Array.isArray(item);
}