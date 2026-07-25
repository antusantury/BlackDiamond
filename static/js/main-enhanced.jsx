// Enhanced Main JavaScript for Black Diamond Web Application
// Orchestrates all modules with modern performance optimizations

// Import all modules with optimized loading
const modules = {
    utils: import('./modules/utils.jsx'),
    theme: import('./modules/theme.jsx'),
    animations: import('./modules/animations.jsx'),
    language: import('./modules/language.jsx'),
    accessibility: import('./modules/accessibility.jsx'),
    state: import('./modules/state-management.jsx'),
    ui: import('./modules/ui-components.jsx'),
    performance: import('./modules/performance-monitor.jsx')
};

// Global configuration
const CONFIG = {
    DEBUG: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1',
    VERSION: '2.1.0',
    BUILD_DATE: new Date().toISOString(),
    PERFORMANCE_MONITORING: true,
    ACCESSIBILITY_MONITORING: true
};

/**
 * Main Application Class
 */
class BlackDiamondApp {
    constructor() {
        this.isInitialized = false;
        this.modules = {};
        this.performanceMarks = new Map();
        this.errorHandler = this.setupGlobalErrorHandling();
        this.init();
    }

    /**
     * Initialize the application
     */
    async init() {
        if (this.isInitialized) return;

        try {
            // Performance mark: App start
            this.markPerformance('app_start');

            // Setup global error handling
            this.setupGlobalErrorHandling();

            // Initialize core modules
            await this.initializeModules();

            // Setup cross-module communication
            this.setupEventSystem();

            // Initialize UI enhancements
            await this.initializeUI();

            // Start monitoring and analytics
            this.startMonitoring();

            // Setup cleanup on page unload
            this.setupCleanup();

            // Mark initialization complete
            this.markPerformance('app_initialized');
            this.isInitialized = true;

            this.log('🎉 Black Diamond App initialized successfully', 'success');
            this.dispatchEvent('appInitialized', { timestamp: Date.now() });

        } catch (error) {
            this.log(`❌ Failed to initialize app: ${error.message}`, 'error');
            console.error('App initialization error:', error);
        }
    }

    /**
     * Initialize all modules with dependency management
     */
    async initializeModules() {
        const moduleOrder = [
            'utils',      // Base utilities
            'theme',      // Theme system
            'animations', // Animation engine
            'accessibility', // A11y features
            'language',   // i18n system
            'state',      // State management
            'ui',         // UI components
            'performance' // Performance monitoring
        ];

        for (const moduleName of moduleOrder) {
            try {
                const module = await modules[moduleName];
                this.modules[moduleName] = module.default || module;
                
                // Initialize module if it has an init method
                if (this.modules[moduleName] && typeof this.modules[moduleName].init === 'function') {
                    await this.modules[moduleName].init();
                }
                
                this.log(`✅ Module loaded: ${moduleName}`, 'info');
            } catch (error) {
                this.log(`❌ Failed to load module ${moduleName}: ${error.message}`, 'error');
            }
        }
    }

    /**
     * Initialize UI enhancements
     */
    async initializeUI() {
        // Enhance existing elements
        this.enhanceNavigation();
        this.enhanceModals();
        this.enhanceForms();
        this.enhanceLoadingStates();

        // Initialize new UI components
        if (this.modules.ui) {
            // Setup toast notifications
            if (this.modules.ui.toasts) {
                this.setupToastNotifications();
            }

            // Setup modal system
            if (this.modules.ui.modals) {
                this.setupModalSystem();
            }

            // Setup dropdown system
            if (this.modules.ui.dropdowns) {
                this.setupDropdownSystem();
            }
        }

        // Setup accessibility features
        if (this.modules.accessibility) {
            this.initializeAccessibility();
        }

        // Setup theme system
        if (this.modules.theme) {
            this.initializeTheme();
        }

        // Setup language system
        if (this.modules.language) {
            this.initializeLanguage();
        }
    }

    /**
     * Setup toast notification system
     */
    setupToastNotifications() {
        const toastContainer = document.getElementById('toast-container') || 
                              this.createToastContainer();
        
        // Listen for custom toast events
        document.addEventListener('showToast', (event) => {
            const { message, options } = event.detail;
            if (this.modules.ui && this.modules.ui.toasts) {
                this.modules.ui.toasts.show(message, options);
            }
        });
    }

    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            pointer-events: none;
            max-width: 400px;
        `;
        document.body.appendChild(container);
        return container;
    }

    /**
     * Setup modal system
     */
    setupModalSystem() {
        // Enhance existing modal triggers
        document.querySelectorAll('[data-modal]').forEach(trigger => {
            trigger.addEventListener('click', (e) => {
                e.preventDefault();
                const modalId = trigger.getAttribute('data-modal');
                const modal = document.getElementById(modalId);
                
                if (modal && this.modules.ui.modals) {
                    this.modules.ui.modals.open(modalId, modal.innerHTML, {
                        title: modal.getAttribute('data-title'),
                        closable: true,
                        trapFocus: true
                    });
                }
            });
        });
    }

    /**
     * Setup dropdown system
     */
    setupDropdownSystem() {
        document.querySelectorAll('[data-dropdown]').forEach(trigger => {
            const dropdownId = trigger.getAttribute('data-dropdown');
            const dropdown = document.getElementById(dropdownId);
            
            if (dropdown) {
                trigger.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (this.modules.ui.dropdowns) {
                        this.modules.ui.dropdowns.toggle(trigger, dropdownId);
                    }
                });

                // Add ARIA attributes
                trigger.setAttribute('aria-haspopup', 'true');
                trigger.setAttribute('aria-expanded', 'false');
                
                dropdown.setAttribute('role', 'menu');
                dropdown.setAttribute('aria-labelledby', trigger.id || `dropdown-${dropdownId}`);
            }
        });
    }

    /**
     * Initialize accessibility features
     */
    initializeAccessibility() {
        if (!this.modules.accessibility) return;

        // Skip links
        this.createSkipLinks();

        // Focus management
        this.setupFocusManagement();

        // Live regions
        this.createLiveRegions();

        // Keyboard navigation
        this.setupKeyboardNavigation();

        // High contrast detection
        this.detectHighContrast();
    }

    /**
     * Create skip links for keyboard navigation
     */
    createSkipLinks() {
        const skipLinks = document.createElement('div');
        skipLinks.className = 'skip-links';
        skipLinks.innerHTML = `
            <a href="#main-content" class="skip-link">Skip to main content</a>
            <a href="#navigation" class="skip-link">Skip to navigation</a>
        `;
        
        skipLinks.style.cssText = `
            position: absolute;
            top: -40px;
            left: 6px;
            background: var(--accent);
            color: white;
            padding: 8px;
            text-decoration: none;
            border-radius: 4px;
            z-index: 1000;
            transition: top 0.3s;
        `;
        
        document.body.insertBefore(skipLinks, document.body.firstChild);
        
        // Show skip links on focus
        skipLinks.addEventListener('focus', () => {
            skipLinks.style.top = '6px';
        });
        
        skipLinks.addEventListener('blur', () => {
            skipLinks.style.top = '-40px';
        });
    }

    /**
     * Setup focus management
     */
    setupFocusManagement() {
        // Enhanced focus indicators
        const style = document.createElement('style');
        style.textContent = `
            *:focus {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
                box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3);
            }
            
            .skip-links:focus-within {
                top: 6px !important;
            }
        `;
        document.head.appendChild(style);

        // Focus trap for modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                const modal = document.querySelector('.bd-modal');
                if (modal && modal.offsetParent !== null) {
                    this.trapFocus(e, modal);
                }
            }
        });
    }

    /**
     * Trap focus within modal
     */
    trapFocus(event, container) {
        const focusableElements = container.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (event.shiftKey) {
            if (document.activeElement === firstElement) {
                event.preventDefault();
                lastElement.focus();
            }
        } else {
            if (document.activeElement === lastElement) {
                event.preventDefault();
                firstElement.focus();
            }
        }
    }

    /**
     * Create live regions for screen readers
     */
    createLiveRegions() {
        // Politeness live region
        const politeRegion = document.createElement('div');
        politeRegion.id = 'aria-live-polite';
        politeRegion.setAttribute('aria-live', 'polite');
        politeRegion.setAttribute('aria-atomic', 'true');
        politeRegion.style.cssText = `
            position: absolute;
            left: -10000px;
            width: 1px;
            height: 1px;
            overflow: hidden;
        `;

        // Assertive live region
        const assertiveRegion = document.createElement('div');
        assertiveRegion.id = 'aria-live-assertive';
        assertiveRegion.setAttribute('aria-live', 'assertive');
        assertiveRegion.setAttribute('aria-atomic', 'true');
        assertiveRegion.style.cssText = politeRegion.style.cssText;

        document.body.appendChild(politeRegion);
        document.body.appendChild(assertiveRegion);

        // Store references for use
        window.ariaLivePolite = politeRegion;
        window.ariaLiveAssertive = assertiveRegion;
    }

    /**
     * Setup keyboard navigation
     */
    setupKeyboardNavigation() {
        // ESC to close modals and dropdowns
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                // Close all modals
                document.querySelectorAll('.bd-modal').forEach(modal => {
                    if (modal.parentElement) {
                        modal.parentElement.remove();
                    }
                });

                // Close all dropdowns
                document.querySelectorAll('.dropdown.show').forEach(dropdown => {
                    dropdown.classList.remove('show');
                    const trigger = document.querySelector(`[data-dropdown="${dropdown.id}"]`);
                    if (trigger) {
                        trigger.setAttribute('aria-expanded', 'false');
                    }
                });
            }
        });

        // Arrow key navigation for menu items
        document.addEventListener('keydown', (e) => {
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                const currentElement = document.activeElement;
                const menuItems = document.querySelectorAll('[role="menuitem"], .menu-item');
                
                if (menuItems.length > 0) {
                    e.preventDefault();
                    const currentIndex = Array.from(menuItems).indexOf(currentElement);
                    let nextIndex;

                    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                        nextIndex = (currentIndex + 1) % menuItems.length;
                    } else {
                        nextIndex = currentIndex > 0 ? currentIndex - 1 : menuItems.length - 1;
                    }

                    menuItems[nextIndex].focus();
                }
            }
        });
    }

    /**
     * Detect high contrast mode
     */
    detectHighContrast() {
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-contrast: high)');
            
            const handleChange = (e) => {
                document.body.classList.toggle('high-contrast', e.matches);
                
                if (e.matches) {
                    this.announceToScreenReader('High contrast mode enabled', 'assertive');
                }
            };

            mediaQuery.addListener(handleChange);
            handleChange(mediaQuery);
        }
    }

    /**
     * Initialize theme system
     */
    initializeTheme() {
        if (!this.modules.theme) return;

        // Theme toggle buttons
        document.querySelectorAll('[data-theme-toggle]').forEach(button => {
            button.addEventListener('click', () => {
                const currentTheme = document.body.className.match(/theme-(\w+)/)?.[1] || 'current';
                const themes = ['current', 'black', 'white'];
                const currentIndex = themes.indexOf(currentTheme);
                const nextTheme = themes[(currentIndex + 1) % themes.length];
                
                if (this.modules.theme.switchToTheme) {
                    this.modules.theme.switchToTheme(nextTheme);
                }
                
                this.announceToScreenReader(`Switched to ${nextTheme} theme`, 'polite');
            });
        });
    }

    /**
     * Initialize language system
     */
    initializeLanguage() {
        if (!this.modules.language) return;

        // Language selector enhancement
        document.querySelectorAll('[data-language]').forEach(selector => {
            selector.addEventListener('change', (e) => {
                const language = e.target.value;
                
                if (this.modules.language.setLanguage) {
                    this.modules.language.setLanguage(language);
                }
                
                this.announceToScreenReader(`Language changed to ${language}`, 'polite');
            });
        });
    }

    /**
     * Setup event system for cross-module communication
     */
    setupEventSystem() {
        // Global event dispatcher
        window.BDEvents = {
            on: (event, callback) => {
                document.addEventListener(`bd:${event}`, callback);
            },
            off: (event, callback) => {
                document.removeEventListener(`bd:${event}`, callback);
            },
            emit: (event, data) => {
                document.dispatchEvent(new CustomEvent(`bd:${event}`, { detail: data }));
            }
        };

        // Performance events
        if (this.modules.performance && window.BDPerformance) {
            window.BDPerformance.monitor.markPerformance('app_modules_loaded');
        }
    }

    /**
     * Start monitoring and analytics
     */
    startMonitoring() {
        // Performance monitoring
        if (this.modules.performance && window.BDPerformance) {
            // Record custom performance marks
            this.markPerformance('app_ui_enhanced');
            
            // Setup performance alerts
            document.addEventListener('performanceMetric', (event) => {
                const { name, status } = event.detail;
                if (status === 'warning' && CONFIG.DEBUG) {
                    this.showWarning(`Performance issue detected: ${name}`);
                }
            });
        }

        // Error tracking
        if (window.BDPerformance && window.BDPerformance.rum) {
            window.BDPerformance.rum.markPerformance('app_monitoring_started');
        }

        // User interaction tracking
        this.setupInteractionTracking();
    }

    /**
     * Setup interaction tracking
     */
    setupInteractionTracking() {
        // Track button clicks
        document.addEventListener('click', (e) => {
            if (e.target.matches('button, .btn, [role="button"]')) {
                const buttonText = e.target.textContent.trim();
                this.dispatchEvent('userInteraction', {
                    type: 'click',
                    element: e.target.tagName,
                    text: buttonText,
                    timestamp: Date.now()
                });
            }
        });

        // Track form submissions
        document.addEventListener('submit', (e) => {
            this.dispatchEvent('userInteraction', {
                type: 'form_submit',
                formId: e.target.id,
                formName: e.target.name,
                timestamp: Date.now()
            });
        });
    }

    /**
     * Enhance navigation
     */
    enhanceNavigation() {
        // Add active state management
        const currentPath = window.location.pathname;
        document.querySelectorAll('nav a').forEach(link => {
            if (link.getAttribute('href') === currentPath) {
                link.setAttribute('aria-current', 'page');
                link.classList.add('active');
            }
        });

        // Smooth scroll for anchor links
        document.querySelectorAll('a[href^="#"]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const target = document.querySelector(link.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                    
                    // Focus target for accessibility
                    target.setAttribute('tabindex', '-1');
                    target.focus();
                    
                    this.announceToScreenReader(`Navigated to ${target.textContent}`, 'polite');
                }
            });
        });
    }

    /**
     * Enhance modals
     */
    enhanceModals() {
        // Add backdrop click to close
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-backdrop')) {
                const modal = e.target.querySelector('.bd-modal');
                if (modal) {
                    modal.parentElement.remove();
                }
            }
        });

        // Trap focus when modal opens
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('bd-modal')) {
                            this.trapFocus({ preventDefault: () => {} }, node);
                        }
                    });
                }
            });
        });

        observer.observe(document.body, { childList: true });
    }

    /**
     * Enhance forms
     */
    enhanceForms() {
        // Add form validation feedback
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (e) => {
                if (!form.checkValidity()) {
                    e.preventDefault();
                    
                    // Find first invalid field
                    const firstInvalid = form.querySelector(':invalid');
                    if (firstInvalid) {
                        firstInvalid.focus();
                        
                        this.announceToScreenReader(`Please correct the ${firstInvalid.validationMessage}`, 'assertive');
                    }
                }
            });

            // Real-time validation feedback
            form.querySelectorAll('input, select, textarea').forEach(field => {
                field.addEventListener('blur', () => {
                    if (field.checkValidity()) {
                        field.classList.remove('invalid');
                        field.classList.add('valid');
                    } else {
                        field.classList.remove('valid');
                        field.classList.add('invalid');
                    }
                });
            });
        });
    }

    /**
     * Enhance loading states
     */
    enhanceLoadingStates() {
        // Add loading indicators for async operations
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            this.showLoadingState();
            try {
                const result = await originalFetch(...args);
                this.hideLoadingState();
                return result;
            } catch (error) {
                this.hideLoadingState();
                throw error;
            }
        };
    }

    /**
     * Setup cleanup on page unload
     */
    setupCleanup() {
        window.addEventListener('beforeunload', () => {
            // Cleanup performance marks
            performance.clearMarks();
            performance.clearMeasures();
            
            // Cleanup observers
            if (window.ResizeObserver) {
                // ResizeObserver cleanup would go here
            }
            
            // Send final performance data
            if (window.BDPerformance && window.BDPerformance.rum) {
                window.BDPerformance.rum.markPerformance('page_unload');
            }
        });
    }

    /**
     * Setup global error handling
     */
    setupGlobalErrorHandling() {
        // JavaScript errors
        window.addEventListener('error', (event) => {
            this.log(`JavaScript Error: ${event.error?.message || event.message}`, 'error');
            
            if (window.BDPerformance && window.BDPerformance.rum) {
                window.BDPerformance.rum.trackInteraction('js_error', {
                    message: event.error?.message || event.message,
                    filename: event.filename,
                    line: event.lineno
                });
            }
        });

        // Promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            this.log(`Unhandled Promise Rejection: ${event.reason}`, 'error');
        });

        // Custom error handler
        return (error, context = 'Unknown') => {
            this.log(`Error in ${context}: ${error.message}`, 'error');
            console.error(`Error in ${context}:`, error);
            
            // Show user-friendly error message
            this.showError('Something went wrong. Please try again.');
        };
    }

    /**
     * Performance marking helper
     */
    markPerformance(name) {
        this.performanceMarks.set(name, Date.now());
        performance.mark(name);
    }

    /**
     * Get performance time between marks
     */
    getPerformanceTime(startMark, endMark = 'app_initialized') {
        const startTime = this.performanceMarks.get(startMark);
        const endTime = this.performanceMarks.get(endMark);
        
        if (startTime && endTime) {
            return endTime - startTime;
        }
        
        return 0;
    }

    /**
     * Announce to screen reader
     */
    announceToScreenReader(message, priority = 'polite') {
        const region = priority === 'assertive' ? window.ariaLiveAssertive : window.ariaLivePolite;
        
        if (region) {
            region.textContent = '';
            
            // Small delay to ensure screen reader picks up the change
            setTimeout(() => {
                region.textContent = message;
            }, 100);
        }
    }

    /**
     * Show loading state
     */
    showLoadingState() {
        let loader = document.getElementById('app-loader');
        
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'app-loader';
            loader.innerHTML = `
                <div class="loader-spinner">
                    <svg width="40" height="40" viewBox="0 0 40 40">
                        <circle cx="20" cy="20" r="18" fill="none" stroke="var(--accent)" stroke-width="4" stroke-linecap="round"/>
                    </svg>
                </div>
            `;
            
            loader.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10001;
                backdrop-filter: blur(4px);
            `;
            
            document.body.appendChild(loader);
        }
        
        loader.style.display = 'flex';
    }

    /**
     * Hide loading state
     */
    hideLoadingState() {
        const loader = document.getElementById('app-loader');
        if (loader) {
            loader.style.display = 'none';
        }
    }

    /**
     * Show warning message
     */
    showWarning(message) {
        if (this.modules.ui && this.modules.ui.toasts) {
            this.modules.ui.toasts.show(message, {
                type: 'warning',
                duration: 5000
            });
        } else {
            console.warn('⚠️', message);
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        if (this.modules.ui && this.modules.ui.toasts) {
            this.modules.ui.toasts.show(message, {
                type: 'error',
                duration: 8000
            });
        } else {
            console.error('❌', message);
        }
    }

    /**
     * Dispatch custom event
     */
    dispatchEvent(type, data) {
        document.dispatchEvent(new CustomEvent(`bd:${type}`, { detail: data }));
    }

    /**
     * Logging helper
     */
    log(message, level = 'info') {
        if (CONFIG.DEBUG || level === 'error') {
            const timestamp = new Date().toISOString();
            const formattedMessage = `[${timestamp}] ${message}`;
            
            switch (level) {
                case 'error':
                    console.error(formattedMessage);
                    break;
                case 'warning':
                    console.warn(formattedMessage);
                    break;
                case 'success':
                    console.log('%c✅ ' + formattedMessage, 'color: #22c55e');
                    break;
                default:
                    console.log(formattedMessage);
            }
        }
    }

    /**
     * Get app status
     */
    getStatus() {
        return {
            isInitialized: this.isInitialized,
            version: CONFIG.VERSION,
            buildDate: CONFIG.BUILD_DATE,
            loadedModules: Object.keys(this.modules),
            performanceMarks: Array.from(this.performanceMarks.keys()),
            debug: CONFIG.DEBUG
        };
    }
}

// Initialize the application
const app = new BlackDiamondApp();

// Export for global access
window.BlackDiamondApp = app;

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        app.init();
    });
} else {
    app.init();
}

console.log('🚀 Black Diamond Web Application loaded');