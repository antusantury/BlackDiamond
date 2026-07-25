/**
 * Black Diamond - JavaScript for interactivity
 */

// Telegram Android WebView can be unstable with heavy effects. We compute a best-effort hint early.
// Telegram may expose `window.Telegram.WebApp` late, so also rely on query/cookie hints.
function hasTelegramWebViewHints() {
    try {
        if (window.Telegram && window.Telegram.WebApp) return true;
        const cookie = String(document.cookie || '');
        if (cookie.includes('tg_webview=1')) return true;
        const qs = String((window.location && window.location.search) || '');
        if (qs.includes('tgWebApp')) return true;
    } catch (_) {}
    return false;
}

function isTelegramAndroidWebView() {
    try {
        const ua = (navigator.userAgent || '').toLowerCase();
        return ua.includes('android') && hasTelegramWebViewHints();
    } catch (_) {
        return false;
    }
}

try {
    window.__isTelegramAndroidWebView = isTelegramAndroidWebView();
    if (window.__isTelegramAndroidWebView) {
        document.documentElement.classList.add('no-effects', 'reduced-motion');
    }
} catch (_) {}

// Safe HTML escaping helper
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Global performance controller
window.PerformanceController = {
    animationsEnabled: true,
    parallaxEnabled: true,
    effectsEnabled: true,

    disableAnimations() {
        this.animationsEnabled = false;
        document.documentElement.classList.add('reduced-motion');
        console.log('Animations disabled for performance');
    },

    disableParallax() {
        this.parallaxEnabled = false;
        console.log('Parallax disabled for performance');
    },

    disableEffects() {
        this.effectsEnabled = false;
        document.documentElement.classList.add('no-effects');
        console.log('✨ Effects disabled for performance');
    },

    enableAll() {
        this.animationsEnabled = true;
        this.parallaxEnabled = true;
        this.effectsEnabled = true;
        document.documentElement.classList.remove('reduced-motion', 'no-effects');
        console.log('✅ All effects enabled');
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    const tgAndroid = isTelegramAndroidWebView();
    try { window.__isTelegramAndroidWebView = tgAndroid; } catch (_) {}

    // Ensure default theme and language for first-time visitors
    try {
        // Theme: default to black (dark) if not set
        if (!localStorage.getItem('theme')) {
            localStorage.setItem('theme', 'black');
        }
        if (window.initTheme) {
            window.initTheme();
        }
        // Language: default to English if not set in localStorage
        if (!localStorage.getItem('lang')) {
            localStorage.setItem('lang', 'en');
        }
    } catch (_) {}

    // Check device performance before initializing
    const isLowEndDevice = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2;
    const isSlowConnection = navigator.connection && (
        navigator.connection.effectiveType === 'slow-2g' ||
        navigator.connection.effectiveType === '2g' ||
        navigator.connection.downlink < 1
    );

    if (isLowEndDevice || isSlowConnection) {
        console.warn('Low-performance device/connection detected. Enabling performance mode...');
        window.PerformanceController.disableEffects();
    }

    // Telegram Android WebView can be unstable with heavy animations/parallax (may show Telegram "duck" error).
    // Use a lightweight mode there.
    if (!tgAndroid) {
        initAnimations();
        initScrollEffects();
        initParallax();
        initCardAnimations();
        initStatsAnimation();
        initPageTransitions();
    } else {
        // Minimal initialization for Telegram Android
        window.PerformanceController.disableAnimations();
        window.PerformanceController.disableParallax();
        window.PerformanceController.disableEffects();
    }

    // initMobileMenu(); // Disabled per user request
    // In Telegram Android, skip non-essential UI flourishes to reduce crash risk.
    if (!tgAndroid) {
        initInteractiveElements();
        initButtonEffects();
        initMobileOptimizations();
        initPerformanceOptimizations();
    }

    // Add debug helpers only in development mode
    const isDevMode = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (isDevMode) {
        window.debugPerformance = () => {
            console.group('Performance Debug Info:');
            console.log('Device cores:', navigator.hardwareConcurrency || 'Unknown');
            console.log('Connection:', navigator.connection ? navigator.connection.effectiveType : 'Unknown');
            console.log('Memory:', performance.memory ? `${Math.round(performance.memory.usedJSHeapSize / 1048576)}MB` : 'Not available');
            console.log('Animations enabled:', window.PerformanceController.animationsEnabled);
            console.log('Parallax enabled:', window.PerformanceController.parallaxEnabled);
            console.log('Effects enabled:', window.PerformanceController.effectsEnabled);
            console.groupEnd();
        };

        window.quickPerfTest = () => {
            console.clear();
            console.log('Running Quick Performance Test...\n');

            const cores = navigator.hardwareConcurrency || 'Unknown';
            const connection = navigator.connection ? navigator.connection.effectiveType : 'Unknown';
            console.log(`Device: ${cores} cores, ${connection} connection`);

            const startTime = performance.now();
            for (let i = 0; i < 50000; i++) { // Reduced load
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
});

// Optimized reveal animations
function initAnimations() {
    // Check performance settings
    const isLowEndDevice = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if ((window.PerformanceController && !window.PerformanceController.animationsEnabled) ||
        document.documentElement.classList.contains('reduced-motion') ||
        isLowEndDevice || prefersReducedMotion) {
        console.log('Scroll animations disabled for performance');
        // Just show all elements without animation
        const elements = document.querySelectorAll('.feature-card, .step, .currency-card, .stat-card, .hero-feature-card');
        elements.forEach(el => {
            el.style.opacity = '1';
            el.style.transform = 'translateY(0)';
        });
        return;
    }

    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px' // Extended margin for better performance
    };

    const animatedElements = new WeakSet(); // Use WeakSet for automatic memory cleanup
    let animationQueue = [];
    let isProcessingQueue = false;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && !animatedElements.has(entry.target)) {
                animatedElements.add(entry.target);
                animationQueue.push(entry.target);
            }
        });

        // Process animation queue
        if (!isProcessingQueue && animationQueue.length > 0) {
            isProcessingQueue = true;
            requestAnimationFrame(processAnimationQueue);
        }
    }, observerOptions);

    function processAnimationQueue() {
        const batchSize = 3; // Process 3 items per batch
        const batch = animationQueue.splice(0, batchSize);

        batch.forEach(element => {
            element.classList.add('fade-in-up');
            element.style.willChange = 'transform, opacity';
        });

        // Clear will-change after animation completes
        batch.forEach(element => {
            element.addEventListener('animationend', function cleanup() {
                element.style.willChange = 'auto';
                element.removeEventListener('animationend', cleanup);
            }, { once: true });
        });

        if (animationQueue.length > 0) {
            requestAnimationFrame(processAnimationQueue);
        } else {
            isProcessingQueue = false;
        }
    }

    // Observe elements for animation
    const elements = document.querySelectorAll('.feature-card, .step, .currency-card, .stat-card, .hero-feature-card');
    elements.forEach(el => observer.observe(el));

    // Limit the number of concurrent observers
    if (elements.length > 20) {
        console.warn('Large number of animated elements detected. Consider reducing for better performance.');
    }
}

// Scroll effects with performance optimizations
function initScrollEffects() {
    const header = document.querySelector('.header');
    const hero = document.querySelector('.hero');
    const mobileMq = window.matchMedia('(max-width: 768px)');
    let ticking = false;
    let lastScrollY = window.scrollY;

    function updateScrollEffects() {
        const scrollY = window.scrollY;
        const deltaY = scrollY - lastScrollY;

        // Header opacity effect with smooth transition (respects current theme)
        // Robust theme detection: prefer <html>, then <body>, then localStorage
        const htmlTheme = document.documentElement.className.match(/theme-(\w+)/);
        const bodyTheme = document.body.className.match(/theme-(\w+)/);
        const lsTheme = (function(){ try { return localStorage.getItem('theme'); } catch(_) { return null; } })();
        const currentTheme = (htmlTheme && htmlTheme[1]) || (bodyTheme && bodyTheme[1]) || (lsTheme || 'current');

        let scrolledBg, defaultBg;

        if (currentTheme === 'white') {
            // Light theme: use white/gray background on scroll
            scrolledBg = mobileMq.matches ? 'rgb(255, 255, 255)' : 'rgba(255, 255, 255, 0.95)';
            defaultBg = mobileMq.matches ? 'rgb(255, 255, 255)' : 'rgba(255, 255, 255, 0.9)';
        } else if (currentTheme === 'black') {
            // Dark theme: use black background
            scrolledBg = mobileMq.matches ? 'rgb(0, 0, 0)' : 'rgba(0, 0, 0, 0.98)';
            defaultBg = mobileMq.matches ? 'rgb(0, 0, 0)' : 'rgba(0, 0, 0, 0.95)';
        } else {
            // Current/dark theme: use a dark background
            scrolledBg = mobileMq.matches ? 'rgb(15, 15, 15)' : 'rgba(10, 10, 10, 0.98)';
            defaultBg = mobileMq.matches ? 'rgb(15, 15, 15)' : 'rgba(10, 10, 10, 0.95)';
        }

        if (scrollY > 100) {
            header.style.background = scrolledBg;
            header.style.backdropFilter = mobileMq.matches ? 'none' : 'blur(20px)';
        } else {
            header.style.background = defaultBg;
            header.style.backdropFilter = mobileMq.matches ? 'none' : 'blur(20px)';
        }

        // Parallax effect for hero background (optimized)
        // IMPORTANT: do not transform the whole hero section, otherwise it visually overlaps the next section on scroll (especially on mobile).
        if (hero && Math.abs(deltaY) > 1) {
            const offset = mobileMq.matches ? 0 : Math.min(scrollY * 0.3, 120);
            requestAnimationFrame(() => {
                hero.style.setProperty('--hero-parallax-offset', `${offset}px`);
            });
        }

        lastScrollY = scrollY;
        ticking = false;
    }

    // Debounced scroll handler
    function onScroll() {
        if (!ticking) {
            requestAnimationFrame(updateScrollEffects);
            ticking = true;
        }
    }

    window.addEventListener('scroll', onScroll, { passive: true });
}

// Optimized parallax effects
function initParallax() {
    const parallaxElements = document.querySelectorAll('.diamond-pattern, .flowing-lines');
    if (parallaxElements.length === 0) return;

    // Check device performance
    const isLowEndDevice = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (isLowEndDevice || prefersReducedMotion || !window.PerformanceController.parallaxEnabled) {
        console.log('Parallax disabled for performance');
        return;
    }

    let ticking = false;
    let lastScrollY = window.scrollY;
    let updateCount = 0;

    function updateParallax() {
        const scrollY = window.scrollY;
        const deltaY = Math.abs(scrollY - lastScrollY);

        // Update only on significant scroll changes and at most ~30fps
        if (deltaY > 10 && updateCount % 2 === 0) { // Every second update
            parallaxElements.forEach((element, index) => {
                const speed = (index + 1) * 0.2; // Further reduced speed
                element.style.transform = `translateY(${scrollY * speed}px)`;
            });
        }

        lastScrollY = scrollY;
        ticking = false;
        updateCount++;
    }

    function onScroll() {
        if (!ticking) {
            ticking = true;
            requestAnimationFrame(updateParallax);
        }
    }

    window.addEventListener('scroll', onScroll, { passive: true });
}

// Mobile menu - disabled per user request
// function initMobileMenu() {
//     // Create mobile menu button
//     const header = document.querySelector('.header-content');
//     const nav = document.querySelector('.nav');

//     if (window.innerWidth <= 768) {
//         // Create hamburger button
//         const mobileMenuBtn = document.createElement('button');
//         mobileMenuBtn.className = 'mobile-menu-btn';
//         mobileMenuBtn.innerHTML = '☰';
//         mobileMenuBtn.style.cssText = `
//             background: none;
//             border: none;
//             color: var(--light-gray);
//             font-size: 24px;
//             cursor: pointer;
//             display: block;
//         `;

//         header.appendChild(mobileMenuBtn);

//         // Hide navigation by default
//         nav.style.display = 'none';

//         // Click handler
//         mobileMenuBtn.addEventListener('click', () => {
//             if (nav.style.display === 'none') {
//                 nav.style.display = 'flex';
//                 nav.style.flexDirection = 'column';
//                 nav.style.position = 'absolute';
//                 nav.style.top = '100%';
//                 nav.style.left = '0';
//                 nav.style.right = '0';
//                 nav.style.background = 'var(--pure-black)';
//                 nav.style.padding = '20px';
//                 nav.style.borderTop = '1px solid var(--light-gray)';
//                 mobileMenuBtn.innerHTML = '✕';
//             } else {
//                 nav.style.display = 'none';
//                 mobileMenuBtn.innerHTML = '☰';
//             }
//         });
//     }
// }

// Stats number animation
function animateNumbers() {
    const statNumbers = document.querySelectorAll('.stat-number');

    statNumbers.forEach(stat => {
        const target = parseInt(stat.textContent.replace(/[^\d]/g, ''));
        if (isNaN(target)) return;

        let current = 0;
        const increment = target / 100;
        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                stat.textContent = target.toLocaleString();
                clearInterval(timer);
            } else {
                stat.textContent = Math.floor(current).toLocaleString();
            }
        }, 20);
    });
}

// Auto-animate numbers on load
if (document.querySelector('.stats')) {
    setTimeout(animateNumbers, 1000);
}

// Smooth scrolling for anchor links
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

// Hero diamond animation (optimized)
function initDiamondAnimation() {
    const diamond = document.querySelector('.diamond-3d');
    if (!diamond) return;

    let rotationX = 0;
    let rotationY = 0;
    let animationId;
    let isAnimating = true;

    function animate() {
        if (!isAnimating) return;

        rotationX += 0.3;
        rotationY += 0.2;

        diamond.style.transform = `rotateX(${rotationX}deg) rotateY(${rotationY}deg)`;
        animationId = requestAnimationFrame(animate);
    }

    // Start animation with a small delay for smoother load
    setTimeout(() => {
        diamond.style.willChange = 'transform';
        animate();
    }, 500);

    // Stop animation when leaving the page
    window.addEventListener('beforeunload', () => {
        isAnimating = false;
        if (animationId) {
            cancelAnimationFrame(animationId);
        }
    });
}

// Start diamond animation (skip for Telegram Android lightweight mode)
try {
    if (!window.__isTelegramAndroidWebView) {
        initDiamondAnimation();
    }
} catch (_) {
    initDiamondAnimation();
}

// Error handling
window.addEventListener('error', function(e) {
    console.error('JavaScript error:', e.error);
});

// Service Worker for PWA (commented out: sw.js does not exist)
// if ('serviceWorker' in navigator) {
//     window.addEventListener('load', () => {
//         navigator.serviceWorker.register('/sw.js')
//             .then(registration => {
//                 console.log('SW registered: ', registration);
//             })
//             .catch(registrationError => {
//                 console.log('SW registration failed: ', registrationError);
//             });
//     });
// }

// Optimized lazy-loading for images
try {
    if (!window.__isTelegramAndroidWebView && ('IntersectionObserver' in window)) {
        const images = document.querySelectorAll('img[data-src]');
        if (images && images.length) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        const src = img.dataset.src;

                        // Preload image
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
            }, {
                rootMargin: '50px 0px',
                threshold: 0.1
            });

            images.forEach(img => imageObserver.observe(img));
        }
    }
} catch (_) {}

// Skeleton loading helpers
function createSkeletonCard() {
    const skeleton = document.createElement('div');
    skeleton.className = 'skeleton-card feature-card';
    skeleton.innerHTML = `
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text" style="width: 70%;"></div>
    `;
    return skeleton;
}

function showSkeletonLoading(container, count = 3) {
    if (!container) return;

    container.innerHTML = '';
    for (let i = 0; i < count; i++) {
        container.appendChild(createSkeletonCard());
    }
}

function hideSkeletonLoading(container) {
    const skeletons = container.querySelectorAll('.skeleton-card');
    skeletons.forEach(skeleton => {
        skeleton.style.opacity = '0';
        setTimeout(() => skeleton.remove(), 300);
    });
}

// Smooth page transitions
function initPageTransitions() {
    const main = document.querySelector('main');
    if (!main) return;

    // Add class for enter animation
    main.classList.add('page-transition');

    // Handle navigation links
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a[href]');
        if (!link || link.getAttribute('href').startsWith('#') || link.getAttribute('href').startsWith('http')) return;

        e.preventDefault();
        const href = link.getAttribute('href');

        // Exit animation
        main.style.opacity = '0';
        main.style.transform = 'translateY(-20px)';

        setTimeout(() => {
            window.location.href = href;
        }, 300);
    });
}

// Ensure content is visible after BFCache restore or history navigation
function resetPageTransitionStyles() {
    try {
        const main = document.querySelector('main');
        if (main) {
            // Clear inline styles that might keep content hidden after back/forward
            main.style.opacity = '';
            main.style.transform = '';
        }
    } catch (_) {}
}

// Restore visibility on page show (including BFCache) and on popstate
window.addEventListener('pageshow', function () {
    resetPageTransitionStyles();
});
window.addEventListener('popstate', function () {
    resetPageTransitionStyles();
});
document.addEventListener('DOMContentLoaded', function () {
    resetPageTransitionStyles();
});

// Theme system
function initTheme() {
    // Get saved theme or use default
    let currentTheme = localStorage.getItem('theme') || 'current';

    // If theme is not saved, check system preferences
    if (!localStorage.getItem('theme')) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        currentTheme = prefersDark ? 'black' : 'white';
        localStorage.setItem('theme', currentTheme);
    }

    // Check if theme was already applied (via inline script)
    const hasThemeApplied = document.documentElement.classList.contains(`theme-${currentTheme}`) ||
                           (currentTheme === 'white-legacy' && document.documentElement.classList.contains('theme-white'));

    // Apply theme only if it wasn't applied inline
    if (!hasThemeApplied) {
        applyTheme(currentTheme);
    }

    // Update theme selectors
    updateThemeSelectors(currentTheme);

    // Listen for system preference changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            const newTheme = e.matches ? 'black' : 'white';
            applyTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        }
    });
}

function applyTheme(theme) {
    // Remove all theme classes
    document.documentElement.classList.remove('theme-white', 'theme-black', 'theme-current', 'theme-white-legacy');
    document.body.classList.remove('theme-white', 'theme-black', 'theme-current', 'theme-white-legacy');

    // Add class for selected theme
    if (theme === 'white-legacy') {
        document.documentElement.classList.add('theme-white');
        document.body.classList.add('theme-white');
        document.body.classList.add('theme-white-legacy');
    } else {
        document.documentElement.classList.add(`theme-${theme}`);
        document.body.classList.add(`theme-${theme}`);
    }

    // Persist current theme
    localStorage.setItem('theme', theme);

    // Update active indicators in selectors
    updateThemeSelectors(theme);
    // Re-evaluate header/hotbar background based on new theme
    try { window.dispatchEvent(new Event('scroll')); } catch(_) {}
}

function updateThemeSelectors(activeTheme) {
    // Remove active class from all options
    document.querySelectorAll('.theme-option.active, .mobile-theme-option.active').forEach(option => {
        option.classList.remove('active');
    });

    // Add active class to selected theme
    document.querySelectorAll(`.theme-option[data-theme="${activeTheme}"], .mobile-theme-option[data-theme="${activeTheme}"]`).forEach(option => {
        option.classList.add('active');
    });
}

function switchTheme(theme) {
    applyTheme(theme);
}

function getThemeName(theme) {
    const names = {
        'white': 'White',
        'black': 'Black',
        'current': 'Current'
    };
    return names[theme] || theme;
}

// Global theme helpers
window.initTheme = initTheme;
window.switchTheme = switchTheme;

// Window resize handling (optimized)
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // Re-init mobile menu on resize (disabled)
        // initMobileMenu(); // Disabled per user request
        // Update parallax effects
        try {
            if (window.__isTelegramAndroidWebView) return;
            if (window.PerformanceController && !window.PerformanceController.parallaxEnabled) return;
            initParallax();
        } catch (_) {}
    }, 250);
}, { passive: true });

// Mobile optimizations
function initMobileOptimizations() {
    if (window.__isTelegramAndroidWebView) return;
    // Detect mobile device
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

    if (isMobile) {
        // Disable hover effects on touch devices
        document.documentElement.classList.add('touch-device');

        // Scroll optimizations for mobile
        document.body.style.webkitOverflowScrolling = 'touch';

        // Preload critical resources for mobile
        if ('connection' in navigator) {
            const connection = navigator.connection;
            if (connection.effectiveType === 'slow-2g' || connection.effectiveType === '2g') {
                // Simplified animations for slow connections
                document.documentElement.classList.add('reduced-motion');
            }
        }
    }

    // Touch-friendly interactions
    const touchElements = document.querySelectorAll('.btn, .card, .nav-link');
    touchElements.forEach(element => {
        let touchStartY = 0;

        element.addEventListener('touchstart', function(e) {
            touchStartY = e.touches[0].clientY;
            this.classList.add('touch-active');
        }, { passive: true });

        element.addEventListener('touchend', function(e) {
            this.classList.remove('touch-active');

            // Prevent ghost clicks
            const touchEndY = e.changedTouches[0].clientY;
            if (Math.abs(touchStartY - touchEndY) > 10) {
                e.preventDefault();
            }
        }, { passive: true });

        element.addEventListener('touchmove', function(e) {
            // Disable hover effects while scrolling
            if (Math.abs(e.touches[0].clientY - touchStartY) > 10) {
                this.classList.remove('touch-active');
            }
        }, { passive: true });
    });
}

// Preload critical resources
function preloadCriticalResources() {
    const criticalResources = [
        '/static/css/style.css',
        '/static/js/main.js'
    ];

    criticalResources.forEach(resource => {
        const link = document.createElement('link');
        link.rel = 'preload';
        link.href = resource;
        link.as = resource.endsWith('.js') ? 'script' : 'style';
        document.head.appendChild(link);
    });
}

try {
    if (!window.__isTelegramAndroidWebView) {
        preloadCriticalResources();
    }
} catch (_) {}

// Particle animation (optional)
function createParticles() {
    const particlesContainer = document.createElement('div');
    particlesContainer.className = 'particles';
    particlesContainer.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: -1;
    `;

    for (let i = 0; i < 50; i++) {
        const particle = document.createElement('div');
        particle.style.cssText = `
            position: absolute;
            width: 2px;
            height: 2px;
            background: var(--light-gray);
            border-radius: 50%;
            opacity: ${Math.random() * 0.5};
            left: ${Math.random() * 100}%;
            top: ${Math.random() * 100}%;
            animation: particle-float ${Math.random() * 10 + 10}s linear infinite;
        `;
        particlesContainer.appendChild(particle);
    }

    document.body.appendChild(particlesContainer);
}

// CSS for particle animation (only needed if particles are enabled)
try {
    if (!window.__isTelegramAndroidWebView && !document.getElementById('particle-style')) {
        const particleStyle = document.createElement('style');
        particleStyle.id = 'particle-style';
        particleStyle.textContent = `
            @keyframes particle-float {
                0% { transform: translateY(0px) rotate(0deg); }
                100% { transform: translateY(-100vh) rotate(360deg); }
            }
        `;
        document.head.appendChild(particleStyle);
    }
} catch (_) {}

// Uncomment to enable particles
// createParticles();

// Optimized performance monitoring (development only)
function initPerformanceMonitoring() {
    // Check if development mode is enabled
    const isDevMode = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (!isDevMode || !('performance' in window)) {
        return; // Disable monitoring in production
    }

    window.addEventListener('load', () => {
        const perfData = performance.getEntriesByType('navigation')[0];
        const loadTime = perfData.loadEventEnd - perfData.loadEventStart;

        if (loadTime > 3000) { // Only if load is slow
            console.warn(`Slow page load: ${loadTime}ms`);
        }

        // Simplified monitoring to catch severe issues
        let frameCount = 0;
        let lastTime = performance.now();
        let lowFpsCount = 0;

        function monitorFPS() {
            frameCount++;
            const currentTime = performance.now();

            if (currentTime - lastTime >= 5000) { // Check every 5 seconds
                const fps = Math.round((frameCount * 1000) / (currentTime - lastTime));

                if (fps < 20) { // Severe issues only
                    lowFpsCount++;
                    if (lowFpsCount >= 3) { // After 3 consecutive low FPS checks
                        console.warn(`⚠️  Low FPS detected: ${fps}. Consider reducing animations.`);
                        lowFpsCount = 0;
                    }
                } else {
                    lowFpsCount = 0;
                }

                frameCount = 0;
                lastTime = currentTime;
            }

            requestAnimationFrame(monitorFPS);
        }

        monitorFPS();
    });
}

// Suggest optimizations helper
function suggestOptimizations(fps, scrollFrequency) {
    console.group('Performance Optimization Suggestions:');

    if (fps < 30) {
        console.log('• Reduce animation complexity');
        console.log('• Use transform instead of changing layout properties');
        console.log('• Consider using will-change property sparingly');
    }

    if (scrollFrequency > 10) {
        console.log('• Throttle scroll event handlers');
        console.log('• Use passive event listeners');
        console.log('• Debounce animation updates');
    }

    console.log('• Enable "prefers-reduced-motion" for users who prefer it');
    console.log('• Test on actual devices, not just desktop');
    console.log('• Use CSS containment (contain: layout style paint)');

    console.groupEnd();
}

// Additional performance optimizations
function initPerformanceOptimizations() {
    if (window.__isTelegramAndroidWebView) return;
    // Debounce for frequent events
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Throttle for scroll
    function throttle(func, limit) {
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
    }

    // IntersectionObserver optimization
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '50px 0px'
    };

    // Idle-time resource preloading
    let idleCallback = window.requestIdleCallback || function(cb) {
        return setTimeout(cb, 1);
    };

    idleCallback(() => {
        // Preload non-critical resources
        preloadNonCriticalResources();
    });

    function preloadNonCriticalResources() {
        // Preload fonts
        const fontLink = document.createElement('link');
        fontLink.rel = 'preload';
        fontLink.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap';
        fontLink.as = 'style';
        document.head.appendChild(fontLink);
    }
}

// Interactive elements with performance optimizations
function initInteractiveElements() {
    if (window.__isTelegramAndroidWebView) return;
    ensureRippleStyles();
    // Add interactivity to all buttons except footer buttons
    const buttons = document.querySelectorAll('button, .btn, .button');
    let animationFrame;

    buttons.forEach(button => {
        // Skip footer buttons to avoid artifacts
        if (button.classList.contains('footer-link') ||
            button.classList.contains('terms-btn') ||
            button.classList.contains('support-chat-btn') ||
            button.closest('.footer-section')) {
            return;
        }

        let isHovering = false;

        button.addEventListener('mouseenter', function() {
            if (isHovering) return;
            isHovering = true;

            requestAnimationFrame(() => {
                this.style.transform = 'scale(1.02)';
                this.style.willChange = 'transform';
            });
        });

        button.addEventListener('mouseleave', function() {
            isHovering = false;

            requestAnimationFrame(() => {
                this.style.transform = 'scale(1)';
                this.style.willChange = 'auto';
            });
        });

        button.addEventListener('click', function(e) {
            // Create ripple effect (optimized)
            const ripple = document.createElement('span');
            ripple.style.cssText = `
                position: absolute;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.3);
                transform: scale(0);
                animation: ripple 0.6s cubic-bezier(0.4, 0, 0.2, 1);
                pointer-events: none;
                will-change: transform;
            `;

            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
            ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';

            this.style.position = 'relative';
            this.style.overflow = 'hidden';
            this.appendChild(ripple);

            // Remove ripple after animation
            ripple.addEventListener('animationend', () => {
                ripple.remove();
            });
        });
    });
}

// Button effects
function initButtonEffects() {
    if (window.__isTelegramAndroidWebView) return;
    ensureRippleStyles();
    const ctaButtons = document.querySelectorAll('.cta-button, .primary-btn');
    ctaButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Add class for animation
            this.classList.add('button-clicked');

            // Remove class after animation
            setTimeout(() => {
                this.classList.remove('button-clicked');
            }, 300);
        });
    });
}

// Card animations (optimized)
function initCardAnimations() {
    const cards = document.querySelectorAll('.feature-card, .currency-card, .stat-card, .hero-feature-card');
    let animationFrame;

    cards.forEach((card, index) => {
        let isHovering = false;

        card.addEventListener('mouseenter', function() {
            if (isHovering) return;
            isHovering = true;

            requestAnimationFrame(() => {
                this.style.transform = 'translateY(-8px) scale(1.01)';
                this.style.boxShadow = '0 20px 40px rgba(0, 0, 0, 0.4)';
                this.style.filter = 'brightness(1.05)';
                this.style.willChange = 'transform, box-shadow, filter';
            });
        });

        card.addEventListener('mouseleave', function() {
            isHovering = false;

            requestAnimationFrame(() => {
                this.style.transform = 'translateY(0) scale(1)';
                this.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.3)';
                this.style.filter = 'brightness(1)';
                this.style.willChange = 'auto';
            });
        });
    });
}

// Improved stats animation
function initStatsAnimation() {
    const statsSection = document.querySelector('.stats');
    if (!statsSection) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateNumbers();
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });

    observer.observe(statsSection);
}

function ensureRippleStyles() {
    try {
        if (window.__isTelegramAndroidWebView) return;
        if (document.documentElement.classList.contains('reduced-motion')) return;
        if (document.getElementById('ripple-style')) return;

        const rippleStyle = document.createElement('style');
        rippleStyle.id = 'ripple-style';
        rippleStyle.textContent = `
            @keyframes ripple {
                to {
                    transform: scale(4);
                    opacity: 0;
                }
            }

            .button-clicked {
                animation: buttonPulse 0.3s ease;
            }

            @keyframes buttonPulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.1); }
                100% { transform: scale(1); }
            }

            .fade-in-up {
                opacity: 1 !important;
                transform: translateY(0) !important;
                transition: all 0.6s ease;
            }

            .feature-card, .step, .currency-card, .stat-card {
                opacity: 0;
                transform: translateY(30px);
                transition: all 0.6s ease;
            }
        `;
        document.head.appendChild(rippleStyle);
    } catch (_) {}
}

// Insert animation/keyframe helpers early for non-Telegram Android runs.
ensureRippleStyles();

// Toast notification helper
function showNotification(message, type = 'info', duration = 3000) {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div style="
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(255, 255, 255, 0.10);
            color: white;
            padding: 16px 20px;
            border-radius: 12px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.25);
            z-index: 1000;
            font-weight: 500;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            transform: translateX(100%);
            transition: transform 0.3s ease;
        ">
            <div style="display: flex; align-items: center; gap: 12px;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    ${type === 'error' ?
                        '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>' :
                        '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none"/><path d="M12 8V14M8 12H16" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'}
                </svg>
                ${escapeHtml(message)}
            </div>
        </div>
    `;

    document.body.appendChild(notification);

    // Show notification
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);

    // Remove after the configured time
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 300);
    }, duration);
}

// Global toast helper
window.showNotification = showNotification;

// Form interactivity
function initFormEnhancements() {
    const inputs = document.querySelectorAll('input, textarea, select');

    inputs.forEach(input => {
        // Add focus effects
        input.addEventListener('focus', function() {
            this.parentElement.classList.add('input-focused');
        });

        input.addEventListener('blur', function() {
            this.parentElement.classList.remove('input-focused');
        });

        // For number inputs
        if (input.type === 'number') {
            input.addEventListener('input', function() {
                if (this.value < 0) this.value = 0;
            });
        }
    });
}

// Initialize form enhancements
document.addEventListener('DOMContentLoaded', function() {
    initFormEnhancements();
});

// Add styles for interactivity
const interactiveStyles = document.createElement('style');
interactiveStyles.textContent = `
    .input-focused {
        transform: scale(1.02);
        transition: transform 0.2s ease;
    }

    .input-focused input,
    .input-focused textarea,
    .input-focused select {
        border-color: var(--light-gray) !important;
        box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.12) !important;
    }
`;
document.head.appendChild(interactiveStyles);

initPerformanceMonitoring();

// Standalone Theme Toggle Button functionality
const themeToggleBtn = document.getElementById('themeToggleBtn');
const mobileThemeToggleBtn = document.getElementById('mobileThemeToggleBtn');

function cycleTheme() {
    const themes = ['current', 'white', 'black'];
    const currentTheme = localStorage.getItem('theme') || 'current';
    const currentIndex = themes.indexOf(currentTheme);
    const nextIndex = (currentIndex + 1) % themes.length;
    const nextTheme = themes[nextIndex];

    if (window.switchTheme) {
        window.switchTheme(nextTheme);
    }
}

// Toast notifications (lightweight, reusable)
window.showToast = function(message, type = 'info', opts = {}) {
    try {
        const duration = opts.duration || 2500;
        const safeMessage = (typeof window.escapeHtml === 'function')
            ? window.escapeHtml(String(message ?? ''))
            : String(message ?? '');
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.setAttribute('aria-live', 'polite');
            container.setAttribute('aria-atomic', 'true');
            container.style.position = 'fixed';
            container.style.top = '16px';
            container.style.right = '16px';
            container.style.zIndex = '2000';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.gap = '8px';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `bd-toast bd-toast-${type}`;
        toast.role = 'status';
        toast.style.transform = 'translateX(120%)';
        toast.style.transition = 'transform 280ms cubic-bezier(0.4, 0, 0.2, 1), opacity 280ms';
        toast.style.opacity = '0.98';

        const iconSVG = {
            success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm-1 14l-4-4 1.4-1.4L11 12.2l5.6-5.6L18 8l-7 8z"/></svg>',
            error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 13h-2v2h2v-2zm0-8h-2v6h2V7z"/></svg>',
            info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>'
        }[type] || '';

        toast.innerHTML = `<div style="display:flex;align-items:center;gap:10px">
            <span class="bd-toast-icon">${iconSVG}</span>
            <span class="bd-toast-text">${safeMessage}</span>
        </div>`;

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
        // Fallback
        try { console.log('[toast]', type, message); } catch(_) {}
    }
}

if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', cycleTheme);
}

if (mobileThemeToggleBtn) {
    mobileThemeToggleBtn.addEventListener('click', cycleTheme);
}
