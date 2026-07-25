// Theme Management Module for Black Diamond Web Application
// Handles theme switching and persistence

import { safeGetStorage, safeSetStorage } from './utils.js';

/**
 * Theme management system
 * Handles theme switching, persistence, and accessibility preferences
 */
class ThemeManager {
    constructor() {
        this.currentTheme = 'current';
        this.themes = ['current', 'white', 'black'];
        this.isInitialized = false;
    }

    /**
     * Initialize theme system
     */
    init() {
        if (this.isInitialized) return;
        
        this.setupEventListeners();
        this.restoreTheme();
        this.setupSystemPreferenceListener();
        this.isInitialized = true;
    }

    /**
     * Setup event listeners for theme toggles
     */
    setupEventListeners() {
        // Theme toggle buttons
        const themeToggleBtn = document.getElementById('themeToggleBtn');
        const mobileThemeToggleBtn = document.getElementById('mobileThemeToggleBtn');

        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', () => this.cycleTheme());
        }

        if (mobileThemeToggleBtn) {
            mobileThemeToggleBtn.addEventListener('click', () => this.cycleTheme());
        }

        // Theme option buttons
        document.addEventListener('click', (e) => {
            if (e.target.matches('[data-theme]') || e.target.closest('[data-theme]')) {
                const themeOption = e.target.matches('[data-theme]') 
                    ? e.target 
                    : e.target.closest('[data-theme]');
                this.switchToTheme(themeOption.dataset.theme);
            }
        });
    }

    /**
     * Restore theme from storage or system preference
     */
    restoreTheme() {
        const savedTheme = safeGetStorage('theme');
        
        if (savedTheme && this.themes.includes(savedTheme)) {
            this.applyTheme(savedTheme);
        } else {
            // Use system preference as default
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            const systemTheme = prefersDark ? 'black' : 'white';
            this.applyTheme(systemTheme);
            safeSetStorage('theme', systemTheme);
        }
    }

    /**
     * Setup listener for system theme preference changes
     */
    setupSystemPreferenceListener() {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        
        const handleChange = (e) => {
            // Only auto-switch if user hasn't explicitly set a theme
            if (!safeGetStorage('theme')) {
                const newTheme = e.matches ? 'black' : 'white';
                this.applyTheme(newTheme);
                safeSetStorage('theme', newTheme);
            }
        };

        // Modern browsers
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', handleChange);
        } else {
            // Legacy browsers
            mediaQuery.addListener(handleChange);
        }
    }

    /**
     * Apply theme to document
     * @param {string} theme - Theme name
     */
    applyTheme(theme) {
        if (!this.themes.includes(theme)) {
            console.warn(`Unknown theme: ${theme}`);
            return;
        }

        // Remove all theme classes
        document.documentElement.classList.remove('theme-white', 'theme-black', 'theme-current');
        document.body.classList.remove('theme-white', 'theme-black', 'theme-current');

        // Add new theme class
        document.documentElement.classList.add(`theme-${theme}`);
        document.body.classList.add(`theme-${theme}`);

        // Store current theme
        this.currentTheme = theme;
        safeSetStorage('theme', theme);

        // Update UI indicators
        this.updateThemeSelectors(theme);
        
        // Trigger scroll event to update header background
        this.updateHeaderBackground();
    }

    /**
     * Switch to specific theme
     * @param {string} theme - Theme name
     */
    switchToTheme(theme) {
        this.applyTheme(theme);
        this.dispatchThemeChange(theme);
    }

    /**
     * Cycle through available themes
     */
    cycleTheme() {
        const currentIndex = this.themes.indexOf(this.currentTheme);
        const nextIndex = (currentIndex + 1) % this.themes.length;
        const nextTheme = this.themes[nextIndex];
        
        this.switchToTheme(nextTheme);
    }

    /**
     * Update theme selector UI
     * @param {string} activeTheme - Active theme name
     */
    updateThemeSelectors(activeTheme) {
        // Remove active class from all options
        document.querySelectorAll('.theme-option.active, .mobile-theme-option.active').forEach(option => {
            option.classList.remove('active');
        });

        // Add active class to current theme option
        document.querySelectorAll(`[data-theme="${activeTheme}"]`).forEach(option => {
            option.classList.add('active');
        });
    }

    /**
     * Update header background based on theme and scroll position
     */
    updateHeaderBackground() {
        const header = document.querySelector('.header');
        if (!header) return;

        const scrollY = window.scrollY;
        const threshold = 100;

        // Determine current theme
        const theme = this.currentTheme;
        
        let backgroundColor;
        if (scrollY > threshold) {
            // Scrolled background
            if (theme === 'white') {
                backgroundColor = 'rgba(255, 255, 255, 0.95)';
            } else if (theme === 'black') {
                backgroundColor = 'rgba(0, 0, 0, 0.98)';
            } else {
                backgroundColor = 'rgba(10, 10, 10, 0.98)';
            }
        } else {
            // Default background
            if (theme === 'white') {
                backgroundColor = 'rgba(255, 255, 255, 0.9)';
            } else if (theme === 'black') {
                backgroundColor = 'rgba(0, 0, 0, 0.95)';
            } else {
                backgroundColor = 'rgba(10, 10, 10, 0.95)';
            }
        }

        header.style.backgroundColor = backgroundColor;
        header.style.backdropFilter = 'blur(20px)';
    }

    /**
     * Dispatch custom theme change event
     * @param {string} theme - New theme name
     */
    dispatchThemeChange(theme) {
        const event = new CustomEvent('themechange', {
            detail: { theme, previousTheme: this.currentTheme }
        });
        document.dispatchEvent(event);
    }

    /**
     * Get current theme
     * @returns {string} - Current theme name
     */
    getCurrentTheme() {
        return this.currentTheme;
    }

    /**
     * Get theme display name
     * @param {string} theme - Theme code
     * @returns {string} - Human readable name
     */
    getThemeDisplayName(theme) {
        const names = {
            'white': 'White',
            'black': 'Black',
            'current': 'Current'
        };
        return names[theme] || theme;
    }

    /**
     * Check if theme is active
     * @param {string} theme - Theme to check
     * @returns {boolean} - True if active
     */
    isThemeActive(theme) {
        return this.currentTheme === theme;
    }

    /**
     * Get all available themes
     * @returns {Array<string>} - Array of theme names
     */
    getAvailableThemes() {
        return [...this.themes];
    }

    /**
     * Setup performance mode for theme switching
     */
    enablePerformanceMode() {
        // Reduce backdrop blur for better performance
        document.documentElement.classList.add('reduced-blur');
        
        // Listen for theme changes to maintain performance
        document.addEventListener('themechange', (e) => {
            if (e.detail.theme !== 'white') {
                document.documentElement.classList.add('performance-mode');
            }
        });
    }
}

// Create global theme manager instance
export const themeManager = new ThemeManager();

// Global theme functions (backward compatibility)
window.initTheme = () => themeManager.init();
window.switchTheme = (theme) => themeManager.switchToTheme(theme);

// Enhanced theme toggle functionality
function setupThemeToggle() {
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    const mobileThemeToggleBtn = document.getElementById('mobileThemeToggleBtn');

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => themeManager.cycleTheme());
    }

    if (mobileThemeToggleBtn) {
        mobileThemeToggleBtn.addEventListener('click', () => themeManager.cycleTheme());
    }
}

// Listen for theme changes to update UI elements
document.addEventListener('themechange', (e) => {
    const { theme } = e.detail;
    
    // Update any theme-dependent elements
    updateThemeDependentElements(theme);
    
    // Dispatch event for other modules
    window.dispatchEvent(new CustomEvent('ui:themechange', { detail: e.detail }));
});

/**
 * Update elements that depend on theme
 * @param {string} theme - Current theme
 */
function updateThemeDependentElements(theme) {
    // Update header background
    themeManager.updateHeaderBackground();
    
    // Update any theme-specific animations or transitions
    const animatedElements = document.querySelectorAll('.animated');
    animatedElements.forEach(element => {
        element.classList.remove('theme-current', 'theme-white', 'theme-black');
        element.classList.add(`theme-${theme}`);
    });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        themeManager.init();
        setupThemeToggle();
    });
} else {
    themeManager.init();
    setupThemeToggle();
}