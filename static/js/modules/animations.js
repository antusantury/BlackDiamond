// Animation and Effects Module for Black Diamond Web Application
// Handles animations, scroll effects, and interactive elements

import { 
    throttle, 
    debounce, 
    prefersReducedMotion, 
    isLowEndDevice, 
    isSlowConnection,
    isInViewport 
} from './utils.js';

/**
 * Animation manager for coordinating all animations
 */
class AnimationManager {
    constructor() {
        this.isInitialized = false;
        this.observers = new Map();
        this.animationQueue = [];
        this.isProcessingQueue = false;
        this.animatedElements = new WeakSet();
    }

    /**
     * Initialize animation system
     */
    init() {
        if (this.isInitialized) return;

        this.checkPerformanceConstraints();
        this.setupIntersectionObserver();
        this.setupScrollEffects();
        this.setupParallax();
        this.setupButtonEffects();
        this.setupCardAnimations();
        this.setupStatsAnimation();
        this.isInitialized = true;
    }

    /**
     * Check performance constraints and disable animations if needed
     */
    checkPerformanceConstraints() {
        const shouldDisableAnimations = 
            isLowEndDevice() || 
            isSlowConnection() || 
            prefersReducedMotion();

        if (shouldDisableAnimations) {
            console.log('Animations disabled for performance');
            document.documentElement.classList.add('reduced-motion');
        }
    }

    /**
     * Setup intersection observer for fade-in animations
     */
    setupIntersectionObserver() {
        const observerOptions = {
            threshold: 0.1,
            rootMargin: '0px 0px -100px 0px'
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !this.animatedElements.has(entry.target)) {
                    this.animatedElements.add(entry.target);
                    this.queueAnimation(entry.target, 'fade-in');
                }
            });
        }, observerOptions);

        this.observers.set('fade-in', observer);

        // Observe animated elements
        const animatedElements = document.querySelectorAll(
            '.feature-card, .step, .currency-card, .stat-card, .hero-feature-card'
        );
        animatedElements.forEach(el => observer.observe(el));
    }

    /**
     * Queue element for animation
     * @param {Element} element - Element to animate
     * @param {string} animationType - Type of animation
     */
    queueAnimation(element, animationType) {
        this.animationQueue.push({ element, animationType });
        
        if (!this.isProcessingQueue) {
            this.isProcessingQueue = true;
            requestAnimationFrame(() => this.processAnimationQueue());
        }
    }

    /**
     * Process animation queue in batches
     */
    processAnimationQueue() {
        const batchSize = 3;
        const batch = this.animationQueue.splice(0, batchSize);

        batch.forEach(({ element, animationType }) => {
            this.applyAnimation(element, animationType);
        });

        if (this.animationQueue.length > 0) {
            requestAnimationFrame(() => this.processAnimationQueue());
        } else {
            this.isProcessingQueue = false;
        }
    }

    /**
     * Apply animation to element
     * @param {Element} element - Element to animate
     * @param {string} animationType - Type of animation
     */
    applyAnimation(element, animationType) {
        const animationClasses = {
            'fade-in': 'fade-in-up',
            'slide-in': 'slide-in-left',
            'scale-in': 'scale-in',
            'bounce-in': 'bounce-in'
        };

        const animationClass = animationClasses[animationType] || 'fade-in-up';
        element.classList.add(animationClass);
        element.style.willChange = 'transform, opacity';

        // Clean up will-change after animation
        element.addEventListener('animationend', () => {
            element.style.willChange = 'auto';
        }, { once: true });
    }

    /**
     * Setup scroll effects
     */
    setupScrollEffects() {
        const header = document.querySelector('.header');
        const hero = document.querySelector('.hero');
        const mobileMq = window.matchMedia('(max-width: 768px)');
        
        if (!header && !hero) return;

        const updateScrollEffects = throttle(() => {
            const scrollY = window.scrollY;

            // Header background effect
            if (header) {
                const theme = document.body.className.match(/theme-(\w+)/)?.[1] || 'current';
                const isMobile = mobileMq.matches;
                const threshold = 100;

                const bgForTheme = (isScrolled) => {
                    if (theme === 'white') {
                        return isMobile ? 'rgb(255, 255, 255)' : (isScrolled ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.9)');
                    }
                    if (theme === 'black') {
                        return isMobile ? 'rgb(0, 0, 0)' : (isScrolled ? 'rgba(0, 0, 0, 0.98)' : 'rgba(0, 0, 0, 0.95)');
                    }
                    return isMobile ? 'rgb(15, 15, 15)' : (isScrolled ? 'rgba(10, 10, 10, 0.98)' : 'rgba(10, 10, 10, 0.95)');
                };

                if (scrollY > threshold) {
                    header.style.backgroundColor = bgForTheme(true);
                    header.style.backdropFilter = isMobile ? 'none' : 'blur(20px)';
                } else {
                    header.style.backgroundColor = bgForTheme(false);
                    header.style.backdropFilter = isMobile ? 'none' : 'blur(20px)';
                }
            }

            // Parallax effect for hero background (avoid transforming the whole section; it can overlap the next section on scroll)
            if (hero) {
                const offset = mobileMq.matches ? 0 : Math.min(scrollY * 0.3, 120);
                hero.style.setProperty('--hero-parallax-offset', `${offset}px`);
            }
        }, 16); // ~60fps

        window.addEventListener('scroll', updateScrollEffects, { passive: true });
    }

    /**
     * Get scrolled background color based on theme
     * @returns {string} - Background color
     */
    getScrolledBackground() {
        const theme = document.body.className.match(/theme-(\w+)/)?.[1] || 'current';
        
        switch (theme) {
            case 'white':
                return 'rgba(255, 255, 255, 0.95)';
            case 'black':
                return 'rgba(0, 0, 0, 0.98)';
            default:
                return 'rgba(10, 10, 10, 0.98)';
        }
    }

    /**
     * Get default background color based on theme
     * @returns {string} - Background color
     */
    getDefaultBackground() {
        const theme = document.body.className.match(/theme-(\w+)/)?.[1] || 'current';
        
        switch (theme) {
            case 'white':
                return 'rgba(255, 255, 255, 0.9)';
            case 'black':
                return 'rgba(0, 0, 0, 0.95)';
            default:
                return 'rgba(10, 10, 10, 0.95)';
        }
    }

    /**
     * Setup parallax effects
     */
    setupParallax() {
        const parallaxElements = document.querySelectorAll('.diamond-pattern, .flowing-lines');
        
        if (parallaxElements.length === 0) return;

        const shouldDisableParallax = 
            isLowEndDevice() || 
            isSlowConnection() || 
            prefersReducedMotion();

        if (shouldDisableParallax) {
            console.log('Parallax disabled for performance');
            return;
        }

        const updateParallax = throttle(() => {
            const scrollY = window.scrollY;
            
            parallaxElements.forEach((element, index) => {
                const speed = (index + 1) * 0.2;
                element.style.transform = `translateY(${scrollY * speed}px)`;
            });
        }, 33); // ~30fps

        window.addEventListener('scroll', updateParallax, { passive: true });
    }

    /**
     * Setup button hover and click effects
     */
    setupButtonEffects() {
        const buttons = document.querySelectorAll('button, .btn, .button');
        
        buttons.forEach(button => {
            // Skip footer buttons to prevent artifacts
            if (button.classList.contains('footer-link') ||
                button.classList.contains('terms-btn') ||
                button.classList.contains('support-chat-btn') ||
                button.closest('.footer-section')) {
                return;
            }

            let isHovering = false;

            // Hover effects
            button.addEventListener('mouseenter', () => {
                if (isHovering) return;
                isHovering = true;

                requestAnimationFrame(() => {
                    button.style.transform = 'scale(1.02)';
                    button.style.willChange = 'transform';
                });
            });

            button.addEventListener('mouseleave', () => {
                isHovering = false;

                requestAnimationFrame(() => {
                    button.style.transform = 'scale(1)';
                    button.style.willChange = 'auto';
                });
            });

            // Click ripple effect
            button.addEventListener('click', (e) => {
                this.createRippleEffect(button, e);
            });
        });
    }

    /**
     * Create ripple effect on button click
     * @param {Element} button - Button element
     * @param {Event} event - Click event
     */
    createRippleEffect(button, event) {
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
     * Setup card hover animations
     */
    setupCardAnimations() {
        const cards = document.querySelectorAll('.feature-card, .currency-card, .stat-card, .hero-feature-card');

        cards.forEach(card => {
            let isHovering = false;

            card.addEventListener('mouseenter', () => {
                if (isHovering) return;
                isHovering = true;

                requestAnimationFrame(() => {
                    card.style.transform = 'translateY(-8px) scale(1.01)';
                    card.style.boxShadow = '0 20px 40px rgba(0, 0, 0, 0.4)';
                    card.style.filter = 'brightness(1.05)';
                    card.style.willChange = 'transform, box-shadow, filter';
                });
            });

            card.addEventListener('mouseleave', () => {
                isHovering = false;

                requestAnimationFrame(() => {
                    card.style.transform = 'translateY(0) scale(1)';
                    card.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.3)';
                    card.style.filter = 'brightness(1)';
                    card.style.willChange = 'auto';
                });
            });
        });
    }

    /**
     * Setup statistics counter animations
     */
    setupStatsAnimation() {
        const statsSection = document.querySelector('.stats');
        if (!statsSection) return;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this.animateNumbers();
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        observer.observe(statsSection);
    }

    /**
     * Animate numbers counting up
     */
    animateNumbers() {
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

    /**
     * Create diamond animation
     */
    initDiamondAnimation() {
        const diamond = document.querySelector('.diamond-3d');
        if (!diamond) return;

        let rotationX = 0;
        let rotationY = 0;
        let animationId;
        let isAnimating = true;

        const animate = () => {
            if (!isAnimating) return;

            rotationX += 0.3;
            rotationY += 0.2;

            diamond.style.transform = `rotateX(${rotationX}deg) rotateY(${rotationY}deg)`;
            animationId = requestAnimationFrame(animate);
        };

        setTimeout(() => {
            diamond.style.willChange = 'transform';
            animate();
        }, 500);

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            isAnimating = false;
            if (animationId) {
                cancelAnimationFrame(animationId);
            }
        });
    }

    /**
     * Cleanup all observers and animations
     */
    destroy() {
        this.observers.forEach(observer => observer.disconnect());
        this.observers.clear();
        
        // Cancel any pending animations
        this.isProcessingQueue = false;
        this.animationQueue = [];
    }
}

// Create global animation manager instance
export const animationManager = new AnimationManager();

// Global functions for backward compatibility
window.initAnimations = () => animationManager.init();
window.initScrollEffects = () => animationManager.setupScrollEffects();
window.initParallax = () => animationManager.setupParallax();
window.initInteractiveElements = () => animationManager.setupButtonEffects();
window.initButtonEffects = () => animationManager.setupButtonEffects();
window.initCardAnimations = () => animationManager.setupCardAnimations();
window.initStatsAnimation = () => animationManager.setupStatsAnimation();
window.initDiamondAnimation = () => animationManager.initDiamondAnimation();

// Initialize animations when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        animationManager.init();
        animationManager.initDiamondAnimation();
    });
} else {
    animationManager.init();
    animationManager.initDiamondAnimation();
}
