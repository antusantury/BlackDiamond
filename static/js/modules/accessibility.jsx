// Accessibility Module for Black Diamond Web Application
// Enhances keyboard navigation, screen reader support, and WCAG compliance

import { prefersReducedMotion, debounce } from './utils.js';

/**
 * Accessibility manager for enhanced user experience
 */
class AccessibilityManager {
    constructor() {
        this.isInitialized = false;
        this.focusableElements = [
            'a[href]',
            'button:not([disabled])',
            'textarea:not([disabled])',
            'input[type="text"]:not([disabled])',
            'input[type="radio"]:not([disabled])',
            'input[type="checkbox"]:not([disabled])',
            'select:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ];
        this.announcementElement = null;
        this.skipLinks = [];
    }

    /**
     * Initialize accessibility features
     */
    init() {
        if (this.isInitialized) return;

        this.createSkipLinks();
        this.setupAriaSupport();
        this.enhanceKeyboardNavigation();
        this.setupFocusManagement();
        this.createAnnouncementSystem();
        this.enhanceFormAccessibility();
        this.setupReducedMotion();
        this.enhanceColorContrast();
        this.isInitialized = true;
    }

    /**
     * Create skip navigation links
     */
    createSkipLinks() {
        const skipLinksContainer = document.createElement('nav');
        skipLinksContainer.setAttribute('aria-label', 'Skip navigation');
        skipLinksContainer.className = 'skip-links';
        skipLinksContainer.style.cssText = `
            position: absolute;
            top: -40px;
            left: 6px;
            background: var(--primary);
            color: white;
            padding: 8px;
            text-decoration: none;
            border-radius: 4px;
            z-index: 1000;
            transition: top 0.3s;
        `;

        skipLinksContainer.innerHTML = `
            <a href="#main-content" class="skip-link">Skip to main content</a>
            <a href="#navigation" class="skip-link">Skip to navigation</a>
            <a href="#footer" class="skip-link">Skip to footer</a>
        `;

        document.body.insertBefore(skipLinksContainer, document.body.firstChild);
        
        // Show skip links on keyboard focus
        skipLinksContainer.addEventListener('focusin', () => {
            skipLinksContainer.style.top = '6px';
        });
        
        skipLinksContainer.addEventListener('focusout', () => {
            skipLinksContainer.style.top = '-40px';
        });
    }

    /**
     * Setup ARIA support and live regions
     */
    setupAriaSupport() {
        // Create live region for announcements
        this.announcementElement = document.createElement('div');
        this.announcementElement.setAttribute('aria-live', 'polite');
        this.announcementElement.setAttribute('aria-atomic', 'true');
        this.announcementElement.className = 'sr-only';
        this.announcementElement.style.cssText = `
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        `;
        document.body.appendChild(this.announcementElement);

        // Enhance existing ARIA labels
        this.enhanceExistingAriaLabels();
        
        // Setup role attributes
        this.setupRoleAttributes();
    }

    /**
     * Enhance existing ARIA labels
     */
    enhanceExistingAriaLabels() {
        // Add missing labels to interactive elements
        const buttons = document.querySelectorAll('button:not([aria-label]):not([aria-labelledby])');
        buttons.forEach(button => {
            if (!button.textContent.trim()) {
                const buttonText = this.generateButtonLabel(button);
                if (buttonText) {
                    button.setAttribute('aria-label', buttonText);
                }
            }
        });

        // Add labels to icons
        const iconButtons = document.querySelectorAll('button svg');
        iconButtons.forEach(icon => {
            const button = icon.closest('button');
            if (button && !button.getAttribute('aria-label')) {
                const iconLabel = this.getIconLabel(icon);
                if (iconLabel) {
                    button.setAttribute('aria-label', iconLabel);
                }
            }
        });
    }

    /**
     * Generate button label from context
     */
    generateButtonLabel(button) {
        // Check for data attributes
        const dataLabel = button.getAttribute('data-label');
        if (dataLabel) return dataLabel;

        // Check for nearby text
        const nearbyText = this.getNearbyText(button);
        if (nearbyText) return nearbyText;

        // Generate contextual label
        const context = this.getButtonContext(button);
        return context;
    }

    /**
     * Get nearby text content
     */
    getNearbyText(element) {
        // Look for adjacent text
        const previousSibling = element.previousElementSibling;
        const nextSibling = element.nextElementSibling;
        
        if (previousSibling && previousSibling.textContent.trim()) {
            return previousSibling.textContent.trim();
        }
        
        if (nextSibling && nextSibling.textContent.trim()) {
            return nextSibling.textContent.trim();
        }

        // Look in parent container
        const parent = element.closest('[aria-label], [title]');
        if (parent) {
            return parent.getAttribute('aria-label') || parent.getAttribute('title');
        }

        return null;
    }

    /**
     * Get button context for labeling
     */
    getButtonContext(button) {
        const classes = Array.from(button.classList);
        
        if (classes.includes('theme-toggle-btn')) return 'Toggle theme';
        if (classes.includes('language-btn')) return 'Language selector';
        if (classes.includes('quick-actions-btn')) return 'Quick actions menu';
        if (classes.includes('telegram-web-app-login-btn')) return 'Login with Telegram';
        if (classes.includes('mobile-menu-btn')) return 'Toggle mobile menu';
        
        // Check for icons
        const icon = button.querySelector('svg');
        if (icon) {
            return this.getIconLabel(icon);
        }
        
        return 'Button';
    }

    /**
     * Get icon label from SVG
     */
    getIconLabel(svg) {
        const paths = svg.querySelectorAll('path');
        const pathData = Array.from(paths).map(p => p.getAttribute('d') || '').join('');
        
        // Common icon patterns
        if (pathData.includes('M12 2L13.09')) return 'Theme toggle';
        if (pathData.includes('M7 10L12')) return 'Language selector';
        if (pathData.includes('M3 12L21')) return 'Menu';
        if (pathData.includes('M11.944')) return 'Telegram';
        if (pathData.includes('M20 21V19')) return 'User profile';
        if (pathData.includes('M5 4V19')) return 'Admin panel';
        if (pathData.includes('M9 21H5')) return 'Logout';
        
        return 'Icon button';
    }

    /**
     * Setup role attributes
     */
    setupRoleAttributes() {
        // Add semantic roles where missing
        const navigation = document.querySelector('nav:not([role])');
        if (navigation) {
            navigation.setAttribute('role', 'navigation');
        }

        const main = document.querySelector('main:not([role])');
        if (main) {
            main.setAttribute('role', 'main');
        }

        const forms = document.querySelectorAll('form:not([role])');
        forms.forEach(form => {
            form.setAttribute('role', 'form');
        });

        // Add landmark roles
        this.setupLandmarks();
    }

    /**
     * Setup landmark regions
     */
    setupLandmarks() {
        const header = document.querySelector('header:not([role])');
        if (header) {
            header.setAttribute('role', 'banner');
        }

        const footer = document.querySelector('footer:not([role])');
        if (footer) {
            footer.setAttribute('role', 'contentinfo');
        }

        const aside = document.querySelector('aside:not([role])');
        if (aside) {
            aside.setAttribute('role', 'complementary');
        }
    }

    /**
     * Enhance keyboard navigation
     */
    enhanceKeyboardNavigation() {
        // Handle tab key trapping
        this.setupTabTrapping();
        
        // Add keyboard shortcuts
        this.setupKeyboardShortcuts();
        
        // Enhance focus indicators
        this.enhanceFocusIndicators();
    }

    /**
     * Setup tab key trapping in modals and dropdowns
     */
    setupTabTrapping() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                const modal = document.querySelector('.modal.show');
                if (modal) {
                    this.trapFocus(e, modal);
                }
                
                const dropdown = document.querySelector('.dropdown.show, .language-dropdown.show');
                if (dropdown) {
                    this.trapFocus(e, dropdown);
                }
            }
        });
    }

    /**
     * Trap focus within container
     */
    trapFocus(e, container) {
        const focusable = container.querySelectorAll(this.focusableElements.join(', '));
        const firstFocusable = focusable[0];
        const lastFocusable = focusable[focusable.length - 1];

        if (e.shiftKey) {
            if (document.activeElement === firstFocusable) {
                e.preventDefault();
                lastFocusable.focus();
            }
        } else {
            if (document.activeElement === lastFocusable) {
                e.preventDefault();
                firstFocusable.focus();
            }
        }
    }

    /**
     * Setup keyboard shortcuts
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Alt + T for theme toggle
            if (e.altKey && e.key === 't') {
                e.preventDefault();
                const themeToggle = document.getElementById('themeToggleBtn');
                if (themeToggle) {
                    themeToggle.click();
                    this.announce('Theme toggled');
                }
            }
            
            // Alt + L for language menu
            if (e.altKey && e.key === 'l') {
                e.preventDefault();
                const languageBtn = document.getElementById('languageBtn');
                if (languageBtn) {
                    languageBtn.click();
                    this.announce('Language menu opened');
                }
            }
            
            // Alt + M for main menu
            if (e.altKey && e.key === 'm') {
                e.preventDefault();
                const mainLink = document.querySelector('nav a[href="/"]');
                if (mainLink) {
                    mainLink.focus();
                    this.announce('Main navigation focused');
                }
            }
            
            // Escape to close modals/dropdowns
            if (e.key === 'Escape') {
                this.closeAllPopups();
            }
        });
    }

    /**
     * Close all open popups
     */
    closeAllPopups() {
        // Close modals
        document.querySelectorAll('.modal.show').forEach(modal => {
            const closeBtn = modal.querySelector('.modal-close');
            if (closeBtn) closeBtn.click();
        });
        
        // Close dropdowns
        document.querySelectorAll('.dropdown.show, .language-dropdown.show').forEach(dropdown => {
            const toggle = document.querySelector(`[aria-expanded="true"][aria-controls="${dropdown.id}"]`);
            if (toggle) toggle.click();
        });
    }

    /**
     * Enhance focus indicators
     */
    enhanceFocusIndicators() {
        // Add enhanced focus styles
        const style = document.createElement('style');
        style.textContent = `
            *:focus {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
                box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3);
            }
            
            button:focus,
            .btn:focus {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            
            /* Skip links focus */
            .skip-links:focus-within {
                top: 6px !important;
            }
        `;
        document.head.appendChild(style);
    }

    /**
     * Setup focus management
     */
    setupFocusManagement() {
        // Manage focus on page load
        this.manageInitialFocus();
        
        // Handle focus after navigation
        this.setupFocusAfterNavigation();
        
        // Focus management for dynamic content
        this.setupDynamicContentFocus();
    }

    /**
     * Manage initial focus on page load
     */
    manageInitialFocus() {
        // Focus main content if no other focusable element is targeted
        const main = document.querySelector('main');
        if (main && !document.activeElement.matches(this.focusableElements.join(', '))) {
            main.setAttribute('tabindex', '-1');
            main.focus();
        }
    }

    /**
     * Setup focus after navigation
     */
    setupFocusAfterNavigation() {
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[href^="/"]');
            if (link) {
                setTimeout(() => {
                    this.manageInitialFocus();
                }, 100);
            }
        });
    }

    /**
     * Setup focus management for dynamic content
     */
    setupDynamicContentFocus() {
        // Observe for new content
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            const focusable = node.querySelector(this.focusableElements.join(', '));
                            if (focusable) {
                                focusable.setAttribute('tabindex', '0');
                            }
                        }
                    });
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /**
     * Create announcement system
     */
    createAnnouncementSystem() {
        // Announcement function for screen readers
        window.announce = (message, priority = 'polite') => {
            if (this.announcementElement) {
                this.announcementElement.setAttribute('aria-live', priority);
                this.announcementElement.textContent = message;
                
                // Clear after announcement
                setTimeout(() => {
                    this.announcementElement.textContent = '';
                }, 1000);
            }
        };
    }

    /**
     * Announce message to screen readers
     */
    announce(message, priority = 'polite') {
        if (this.announcementElement) {
            this.announcementElement.setAttribute('aria-live', priority);
            this.announcementElement.textContent = message;
            
            setTimeout(() => {
                this.announcementElement.textContent = '';
            }, 1000);
        }
    }

    /**
     * Enhance form accessibility
     */
    enhanceFormAccessibility() {
        // Add labels to inputs without them
        const inputs = document.querySelectorAll('input:not([aria-label]):not([aria-labelledby]), textarea:not([aria-label]):not([aria-labelledby])');
        inputs.forEach(input => {
            if (!input.labels.length && !input.getAttribute('aria-label')) {
                const label = this.generateInputLabel(input);
                if (label) {
                    input.setAttribute('aria-label', label);
                }
            }
        });

        // Add error message associations
        this.associateErrorMessages();
        
        // Setup form validation announcements
        this.setupFormValidationAnnouncements();
    }

    /**
     * Generate label for input
     */
    generateInputLabel(input) {
        const name = input.getAttribute('name');
        const type = input.getAttribute('type');
        const placeholder = input.getAttribute('placeholder');
        
        if (name) return `${name} input`;
        if (placeholder) return placeholder;
        if (type) return `${type} input`;
        
        return 'Input field';
    }

    /**
     * Associate error messages with inputs
     */
    associateErrorMessages() {
        const errorElements = document.querySelectorAll('[class*="error"], .error-message');
        errorElements.forEach(error => {
            const input = error.previousElementSibling;
            if (input && input.matches('input, textarea, select')) {
                const errorId = `error-${Math.random().toString(36).substr(2, 9)}`;
                error.id = errorId;
                input.setAttribute('aria-describedby', errorId);
            }
        });
    }

    /**
     * Setup form validation announcements
     */
    setupFormValidationAnnouncements() {
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', (e) => {
                const errors = form.querySelectorAll('.error, [class*="error"]');
                if (errors.length > 0) {
                    this.announce(`Form contains ${errors.length} errors. Please review and correct them.`, 'assertive');
                    const firstError = errors[0];
                    if (firstError.scrollIntoView) {
                        firstError.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
                    }
                } else {
                    this.announce('Form submitted successfully', 'polite');
                }
            });
        });
    }

    /**
     * Setup reduced motion support
     */
    setupReducedMotion() {
        if (prefersReducedMotion()) {
            document.documentElement.classList.add('reduced-motion');
            
            // Disable smooth scrolling
            document.documentElement.style.scrollBehavior = 'auto';
            
            // Announce motion reduction
            this.announce('Reduced motion mode enabled for accessibility', 'polite');
        }
    }

    /**
     * Enhance color contrast
     */
    enhanceColorContrast() {
        // Check and fix contrast issues
        this.checkContrastIssues();
        
        // Add high contrast mode support
        this.setupHighContrastMode();
    }

    /**
     * Check for contrast issues
     */
    checkContrastIssues() {
        const elements = document.querySelectorAll('*');
        elements.forEach(element => {
            const color = getComputedStyle(element).color;
            const backgroundColor = getComputedStyle(element).backgroundColor;
            
            // Basic contrast check (simplified)
            if (this.isLowContrast(color, backgroundColor)) {
                element.classList.add('low-contrast');
            }
        });
    }

    /**
     * Simple contrast check
     */
    isLowContrast(foreground, background) {
        // This is a simplified check - in production, use a proper contrast checker
        return foreground === background;
    }

    /**
     * Setup high contrast mode
     */
    setupHighContrastMode() {
        const toggle = document.createElement('button');
        toggle.textContent = 'High Contrast';
        toggle.setAttribute('aria-label', 'Toggle high contrast mode');
        toggle.className = 'high-contrast-toggle';
        toggle.style.cssText = `
            position: fixed;
            bottom: 10px;
            left: 10px;
            z-index: 1000;
            padding: 8px 12px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        `;

        toggle.addEventListener('click', () => {
            document.documentElement.classList.toggle('high-contrast');
            const isActive = document.documentElement.classList.contains('high-contrast');
            this.announce(`High contrast mode ${isActive ? 'enabled' : 'disabled'}`, 'polite');
        });

        document.body.appendChild(toggle);
    }

    /**
     * Get accessibility status
     */
    getStatus() {
        return {
            isInitialized: this.isInitialized,
            announcementsSupported: !!this.announcementElement,
            keyboardNavigationEnabled: true,
            focusManagementEnabled: true,
            ariaSupportEnabled: true,
            motionPreferences: {
                reduced: prefersReducedMotion(),
                supported: window.matchMedia('(prefers-reduced-motion: reduce)').matches
            }
        };
    }
}

// Create global accessibility manager instance
export const accessibilityManager = new AccessibilityManager();

// Global functions for backward compatibility
window.announce = (message, priority = 'polite') => accessibilityManager.announce(message, priority);

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        accessibilityManager.init();
    });
} else {
    accessibilityManager.init();
}