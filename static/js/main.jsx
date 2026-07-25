// Main Application Entry Point for Black Diamond Web Application
// Coordinates all modules and initializes the application

// Import modules (Note: Using .jsx extension for frontend compatibility)
import { themeManager } from './modules/theme.jsx';
import { animationManager } from './modules/animations.jsx';
import { languageManager } from './modules/language.jsx';

/**
 * Performance monitoring and optimization controller
 */
class PerformanceController {
    constructor() {
        this.animationsEnabled = true;
        this.parallaxEnabled = true;
        this.effectsEnabled = true;
        this.isInitialized = false;
    }

    /**
     * Initialize performance monitoring
     */
    init() {
        if (this.isInitialized) return;

        this.detectPerformanceConstraints();
        this.setupOptimizationStrategies();
        this.initializeMonitoring();
        this.isInitialized = true;
    }

    /**
     * Detect device performance constraints
     */
    detectPerformanceConstraints() {
        const isLowEndDevice = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2;
        const isSlowConnection = navigator.connection && (
            navigator.connection.effectiveType === 'slow-2g' ||
            navigator.connection.effectiveType === '2g' ||
            navigator.connection.downlink < 1
        );

        if (isLowEndDevice || isSlowConnection) {
            console.warn('Low-performance device/connection detected. Enabling performance mode...');
            this.disableEffects();
        }
    }

    /**
     * Setup optimization strategies
     */
    setupOptimizationStrategies() {
        // Debounce for frequent events
        this.debounce = (func, wait) => {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        };

        // Throttle for scroll events
        this.throttle = (func, limit) => {
            let inThrottle;
            return function() {
                const args = arguments;
                const context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        };

        // Intersection Observer with optimized options
        this.observerOptions = {
            threshold: 0.1,
            rootMargin: '50px 0px'
        };
    }

    /**
     * Initialize performance monitoring
     */
    initializeMonitoring() {
        const isDevMode = window.location.hostname === 'localhost' || 
                         window.location.hostname === '127.0.0.1';

        if (isDevMode) {
            this.setupDevTools();
        }
    }

    /**
     * Setup development tools
     */
    setupDevTools() {
        window.debugPerformance = () => {
            console.group('Performance Debug Info:');
            console.log('Device cores:', navigator.hardwareConcurrency || 'Unknown');
            console.log('Connection:', navigator.connection ? navigator.connection.effectiveType : 'Unknown');
            console.log('Memory:', performance.memory ? `${Math.round(performance.memory.usedJSHeapSize / 1048576)}MB` : 'Not available');
            console.log('Animations enabled:', this.animationsEnabled);
            console.log('Parallax enabled:', this.parallaxEnabled);
            console.log('Effects enabled:', this.effectsEnabled);
            console.groupEnd();
        };

        window.quickPerfTest = () => {
            console.clear();
            console.log('Running Quick Performance Test...\n');

            const cores = navigator.hardwareConcurrency || 'Unknown';
            const connection = navigator.connection ? navigator.connection.effectiveType : 'Unknown';
            console.log(`Device: ${cores} cores, ${connection} connection`);

            const startTime = performance.now();
            for (let i = 0; i < 50000; i++) {
                Math.sqrt(i);
            }
            const computeTime = performance.now() - startTime;
            console.log(`⚡ Compute performance: ${computeTime.toFixed(1)}ms`);

            if ('memory' in performance) {
                const memUsage = Math.round(performance.memory.usedJSHeapSize / 1048576);
                console.log(`Memory usage: ${memUsage}MB`);
            }

            console.log('\nPerformance controls available:');
            console.log('• PerformanceController.disableAnimations()');
            console.log('• PerformanceController.disableParallax()');
            console.log('• PerformanceController.disableEffects()');
        };

        console.log('Dev mode: Type "quickPerfTest()" for performance analysis');
    }

    /**
     * Disable animations for performance
     */
    disableAnimations() {
        this.animationsEnabled = false;
        document.documentElement.classList.add('reduced-motion');
        console.log('Animations disabled for performance');
    }

    /**
     * Disable parallax for performance
     */
    disableParallax() {
        this.parallaxEnabled = false;
        console.log('Parallax disabled for performance');
    }

    /**
     * Disable effects for performance
     */
    disableEffects() {
        this.effectsEnabled = false;
        document.documentElement.classList.add('no-effects');
        console.log('✨ Effects disabled for performance');
    }

    /**
     * Enable all performance features
     */
    enableAll() {
        this.animationsEnabled = true;
        this.parallaxEnabled = true;
        this.effectsEnabled = true;
        document.documentElement.classList.remove('reduced-motion', 'no-effects');
        console.log('✅ All effects enabled');
    }
}

/**
 * Main application class that coordinates all modules
 */
class BlackDiamondApp {
    constructor() {
        this.modules = {};
        this.isInitialized = false;
        this.performanceController = new PerformanceController();
    }

    /**
     * Initialize the application
     */
    async init() {
        if (this.isInitialized) return;

        try {
            // Initialize performance monitoring first
            this.performanceController.init();

            // Setup module registry
            this.registerModules();

            // Initialize core modules in dependency order
            await this.initializeCoreModules();

            // Initialize UI modules
            await this.initializeUIModules();

            // Setup global event listeners
            this.setupGlobalListeners();

            // Start the application
            this.start();

            this.isInitialized = true;
            console.log('✅ Black Diamond app initialized successfully');

        } catch (error) {
            console.error('❌ Failed to initialize app:', error);
            this.handleInitializationError(error);
        }
    }

    /**
     * Register all available modules
     */
    registerModules() {
        this.modules = {
            theme: themeManager,
            animations: animationManager,
            language: languageManager,
            performance: this.performanceController
        };
    }

    /**
     * Initialize core modules (no dependencies)
     */
    async initializeCoreModules() {
        // Performance controller is already initialized
        // Language manager doesn't depend on themes
        languageManager.init();
    }

    /**
     * Initialize UI modules (may have dependencies)
     */
    async initializeUIModules() {
        // Theme manager
        themeManager.init();

        // Animation manager (depends on theme)
        animationManager.init();

        // Initialize additional UI components
        this.initializeAdditionalComponents();
    }

    /**
     * Initialize additional UI components
     */
    initializeAdditionalComponents() {
        // Page transitions
        this.initPageTransitions();

        // Mobile optimizations
        this.initMobileOptimizations();

        // Lazy loading
        this.initLazyLoading();

        // Smooth scrolling
        this.initSmoothScrolling();

        // Form enhancements
        this.initFormEnhancements();

        // Notifications
        this.initNotifications();

        // Service Worker (if available)
        this.initServiceWorker();
    }

    /**
     * Initialize page transitions
     */
    initPageTransitions() {
        const main = document.querySelector('main');
        if (!main) return;

        // Add transition class
        main.classList.add('page-transition');

        // Handle navigation links
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a[href]');
            if (!link || 
                link.getAttribute('href').startsWith('#') || 
                link.getAttribute('href').startsWith('http') ||
                link.getAttribute('target')) return;

            e.preventDefault();
            const href = link.getAttribute('href');

            // Animate exit
            main.style.opacity = '0';
            main.style.transform = 'translateY(-20px)';

            setTimeout(() => {
                window.location.href = href;
            }, 300);
        });
    }

    /**
     * Initialize mobile optimizations
     */
    initMobileOptimizations() {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        if (isMobile) {
            // Add touch device class
            document.documentElement.classList.add('touch-device');

            // Optimize scrolling
            document.body.style.webkitOverflowScrolling = 'touch';

            // Check connection quality
            if ('connection' in navigator) {
                const connection = navigator.connection;
                if (connection.effectiveType === 'slow-2g' || connection.effectiveType === '2g') {
                    document.documentElement.classList.add('reduced-motion');
                }
            }
        }
    }

    /**
     * Initialize lazy loading for images
     */
    initLazyLoading() {
        const images = document.querySelectorAll('img[data-src]');
        
        if (images.length === 0) return;

        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    const src = img.dataset.src;

                    const newImg = new Image();
                    newImg.onload = () => {
                        img.src = src;
                        img.classList.remove('lazy');
                        img.classList.add('loaded');
                        observer.unobserve(img);
                    };
                    newImg.src = src;
                }
            });
        }, this.performanceController.observerOptions);

        images.forEach(img => imageObserver.observe(img));
    }

    /**
     * Initialize smooth scrolling
     */
    initSmoothScrolling() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }

    /**
     * Initialize form enhancements
     */
    initFormEnhancements() {
        const inputs = document.querySelectorAll('input, textarea, select');

        inputs.forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement.classList.add('input-focused');
            });

            input.addEventListener('blur', function() {
                this.parentElement.classList.remove('input-focused');
            });

            // Number input validation
            if (input.type === 'number') {
                input.addEventListener('input', function() {
                    if (this.value < 0) this.value = 0;
                });
            }
        });
    }

    /**
     * Initialize notification system
     */
    initNotifications() {
        // Global notification function
        window.showToast = (message, type = 'info', opts = {}) => {
            try {
                const duration = opts.duration || 2500;
                let container = document.getElementById('toastContainer');
                
                if (!container) {
                    container = document.createElement('div');
                    container.id = 'toastContainer';
                    container.setAttribute('aria-live', 'polite');
                    container.setAttribute('aria-atomic', 'true');
                    container.style.cssText = `
                        position: fixed;
                        top: 16px;
                        right: 16px;
                        z-index: 2000;
                        display: flex;
                        flex-direction: column;
                        gap: 8px;
                    `;
                    document.body.appendChild(container);
                }

                const toast = document.createElement('div');
                toast.className = `bd-toast bd-toast-${type}`;
                toast.style.cssText = `
                    transform: translateX(120%);
                    transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
                    opacity: 0.98;
                    min-width: 240px;
                    max-width: 420px;
                    padding: 12px 16px;
                    border-radius: 10px;
                    border: 1px solid var(--border);
                    background: var(--header-bg);
                    color: var(--primary);
                    box-shadow: var(--shadow-subtle);
                    backdrop-filter: blur(10px);
                `;

                const icons = {
                    success: '✓',
                    error: '✗',
                    info: 'ℹ'
                };

                toast.innerHTML = `
                    <div style="display:flex;align-items:center;gap:10px">
                        <span style="font-weight:bold">${icons[type] || icons.info}</span>
                        <span>${message}</span>
                    </div>
                `;

                container.appendChild(toast);

                requestAnimationFrame(() => {
                    toast.style.transform = 'translateX(0)';
                });

                setTimeout(() => {
                    toast.style.transform = 'translateX(120%)';
                    toast.style.opacity = '0';
                    setTimeout(() => toast.remove(), 320);
                }, duration);

            } catch (e) {
                console.log('[toast]', type, message);
            }
        };
    }

    /**
     * Initialize Service Worker if available
     */
    initServiceWorker() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js')
                    .then(registration => {
                        console.log('SW registered: ', registration);
                    })
                    .catch(registrationError => {
                        console.log('SW registration failed: ', registrationError);
                    });
            });
        }
    }

    /**
     * Setup global event listeners
     */
    setupGlobalListeners() {
        // Handle resize with debouncing
        const handleResize = this.performanceController.debounce(() => {
            // Reinitialize parallax on resize
            animationManager.setupParallax();
        }, 250);

        window.addEventListener('resize', handleResize, { passive: true });

        // Handle visibility change (BFCache)
        window.addEventListener('pageshow', () => {
            // Reset any transition styles
            const main = document.querySelector('main');
            if (main) {
                main.style.opacity = '';
                main.style.transform = '';
            }
        });

        // Handle errors
        window.addEventListener('error', (e) => {
            console.error('JavaScript error:', e.error);
            if (window.showToast) {
                window.showToast('An error occurred. Please refresh the page.', 'error');
            }
        });

        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (e) => {
            console.error('Unhandled promise rejection:', e.reason);
        });
    }

    /**
     * Start the application after initialization
     */
    start() {
        // Preload critical resources
        this.preloadCriticalResources();

        // Initialize additional features
        this.initializeAdditionalFeatures();

        // Dispatch ready event
        this.dispatchReadyEvent();
    }

    /**
     * Preload critical resources
     */
    preloadCriticalResources() {
        const criticalResources = [
            { href: '/static/css/style.css', as: 'style' },
            { href: 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap', as: 'style' }
        ];

        criticalResources.forEach(resource => {
            const link = document.createElement('link');
            link.rel = 'preload';
            link.href = resource.href;
            link.as = resource.as;
            document.head.appendChild(link);
        });
    }

    /**
     * Initialize additional features
     */
    initializeAdditionalFeatures() {
        // Initialize skeleton loading
        this.initSkeletonLoading();

        // Setup event delegation
        this.setupEventDelegation();
    }

    /**
     * Initialize skeleton loading functionality
     */
    initSkeletonLoading() {
        window.showSkeletonLoading = (container, count = 3) => {
            if (!container) return;

            container.innerHTML = '';
            for (let i = 0; i < count; i++) {
                const skeleton = document.createElement('div');
                skeleton.className = 'skeleton-card feature-card';
                skeleton.innerHTML = `
                    <div class="skeleton skeleton-title"></div>
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text" style="width: 70%;"></div>
                `;
                container.appendChild(skeleton);
            }
        };

        window.hideSkeletonLoading = (container) => {
            const skeletons = container.querySelectorAll('.skeleton-card');
            skeletons.forEach(skeleton => {
                skeleton.style.opacity = '0';
                setTimeout(() => skeleton.remove(), 300);
            });
        };
    }

    /**
     * Setup event delegation for dynamic content
     */
    setupEventDelegation() {
        document.addEventListener('click', (e) => {
            // Handle dynamic button clicks
            if (e.target.matches('.dynamic-button') || e.target.closest('.dynamic-button')) {
                const button = e.target.matches('.dynamic-button') ? e.target : e.target.closest('.dynamic-button');
                this.handleDynamicButtonClick(button, e);
            }
        });
    }

    /**
     * Handle dynamic button clicks
     */
    handleDynamicButtonClick(button, event) {
        // Add ripple effect
        const ripple = document.createElement('span');
        ripple.className = 'ripple-effect';
        ripple.style.cssText = `
            position: absolute;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.3);
            transform: scale(0);
            animation: ripple 0.6s ease;
            pointer-events: none;
        `;

        const rect = button.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = (event.clientX - rect.left - size / 2) + 'px';
        ripple.style.top = (event.clientY - rect.top - size / 2) + 'px';

        button.style.position = 'relative';
        button.style.overflow = 'hidden';
        button.appendChild(ripple);

        ripple.addEventListener('animationend', () => {
            ripple.remove();
        });
    }

    /**
     * Dispatch ready event
     */
    dispatchReadyEvent() {
        const event = new CustomEvent('bd:ready', {
            detail: {
                modules: this.modules,
                version: '2.0.0'
            }
        });
        document.dispatchEvent(event);
    }

    /**
     * Handle initialization errors
     */
    handleInitializationError(error) {
        // Show fallback UI or error message
        const errorContainer = document.createElement('div');
        errorContainer.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--error);">
                <h2>Failed to load application</h2>
                <p>Please refresh the page or contact support if the problem persists.</p>
                <button onclick="location.reload()" style="margin-top: 1rem; padding: 0.5rem 1rem; background: var(--primary); color: white; border: none; border-radius: 4px; cursor: pointer;">
                    Reload Page
                </button>
            </div>
        `;
        
        const main = document.querySelector('main') || document.body;
        main.appendChild(errorContainer);
    }

    /**
     * Get module by name
     */
    getModule(name) {
        return this.modules[name];
    }

    /**
     * Check if app is initialized
     */
    isReady() {
        return this.isInitialized;
    }
}

// Create global app instance
export const blackDiamondApp = new BlackDiamondApp();

// Global performance controller for backward compatibility
window.PerformanceController = {
    disableAnimations: () => blackDiamondApp.performanceController.disableAnimations(),
    disableParallax: () => blackDiamondApp.performanceController.disableParallax(),
    disableEffects: () => blackDiamondApp.performanceController.disableEffects(),
    enableAll: () => blackDiamondApp.performanceController.enableAll()
};

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        blackDiamondApp.init();
    });
} else {
    blackDiamondApp.init();
}