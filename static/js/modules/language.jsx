// Language Manager Module for Black Diamond Web Application
// Handles language switching and localization

import { safeGetStorage, safeSetStorage, debounce } from './utils.js';

/**
 * Language management system
 */
class LanguageManager {
    constructor() {
        this.currentLanguage = 'en';
        this.supportedLanguages = ['en', 'ua'];
        this.isInitialized = false;
        this.isMenuOpen = false;
        this.menuElement = null;
        this.buttonElement = null;
    }

    /**
     * Initialize language system
     */
    init() {
        if (this.isInitialized) return;

        this.setupEventListeners();
        this.restoreLanguage();
        this.isInitialized = true;
    }

    /**
     * Setup event listeners for language selector
     */
    setupEventListeners() {
        // Get language selector elements
        this.menuElement = document.getElementById('languageDropdown');
        this.buttonElement = document.getElementById('languageBtn');

        if (!this.menuElement || !this.buttonElement) {
            console.warn('Language selector elements not found');
            return;
        }

        // Button click handler
        this.buttonElement.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.toggleMenu();
        });

        // Language option handlers
        document.addEventListener('click', (e) => {
            if (e.target.matches('.language-option[data-lang]') || 
                e.target.closest('.language-option[data-lang]')) {
                
                const option = e.target.matches('.language-option') 
                    ? e.target 
                    : e.target.closest('.language-option');
                
                const lang = option.getAttribute('data-lang');
                if (lang) {
                    this.changeLanguage(lang);
                }
            }
        });

        // Close menu on outside click
        document.addEventListener('click', (e) => {
            if (this.isMenuOpen && 
                !this.menuElement.contains(e.target) && 
                !this.buttonElement.contains(e.target)) {
                this.closeMenu();
            }
        });

        // Close menu on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isMenuOpen) {
                this.closeMenu();
                this.buttonElement.focus();
            }
        });

        // Keyboard navigation
        this.setupKeyboardNavigation();
    }

    /**
     * Setup keyboard navigation for menu
     */
    setupKeyboardNavigation() {
        if (!this.menuElement) return;

        this.menuElement.addEventListener('keydown', (e) => {
            const options = Array.from(this.menuElement.querySelectorAll('.language-option[data-lang]'));
            const currentIndex = options.indexOf(document.activeElement);

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    options[(currentIndex + 1) % options.length].focus();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    options[(currentIndex - 1 + options.length) % options.length].focus();
                    break;
                case 'Home':
                    e.preventDefault();
                    options[0].focus();
                    break;
                case 'End':
                    e.preventDefault();
                    options[options.length - 1].focus();
                    break;
            }
        });
    }

    /**
     * Toggle language menu
     */
    toggleMenu() {
        if (this.isMenuOpen) {
            this.closeMenu();
        } else {
            this.openMenu();
        }
    }

    /**
     * Open language menu
     */
    openMenu() {
        this.isMenuOpen = true;
        this.buttonElement.setAttribute('aria-expanded', 'true');
        this.menuElement.classList.add('show');
        
        // Position menu relative to button
        this.positionMenu();
        
        // Focus first option
        const firstOption = this.menuElement.querySelector('.language-option[data-lang]');
        if (firstOption) {
            firstOption.focus();
        }
    }

    /**
     * Close language menu
     */
    closeMenu() {
        this.isMenuOpen = false;
        this.buttonElement.setAttribute('aria-expanded', 'false');
        this.menuElement.classList.remove('show');
        
        // Return focus to button
        this.buttonElement.focus();
    }

    /**
     * Position menu relative to button
     */
    positionMenu() {
        if (!this.menuElement || !this.buttonElement) return;

        const rect = this.buttonElement.getBoundingClientRect();
        const dropdownRect = this.menuElement.getBoundingClientRect();
        
        // Reset any previous positioning
        this.menuElement.style.top = '';
        this.menuElement.style.left = '';
        this.menuElement.style.right = '';
        this.menuElement.style.zIndex = '';

        // Position below button
        this.menuElement.style.top = (rect.bottom + window.scrollY + 8) + 'px';
        this.menuElement.style.left = (rect.left + window.scrollX) + 'px';
        this.menuElement.style.zIndex = '10000';

        // Ensure menu stays within viewport
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;
        
        if (rect.bottom + dropdownRect.height + 16 > viewportHeight) {
            // Position above button if not enough space below
            this.menuElement.style.top = (rect.top + window.scrollY - dropdownRect.height - 8) + 'px';
        }

        if (rect.left + dropdownRect.width > viewportWidth) {
            // Adjust horizontal position if menu extends beyond viewport
            this.menuElement.style.left = (viewportWidth - dropdownRect.width - 16) + 'px';
        }
    }

    /**
     * Change language
     * @param {string} lang - Language code
     */
    async changeLanguage(lang) {
        if (!this.supportedLanguages.includes(lang)) {
            console.warn(`Unsupported language: ${lang}`);
            return;
        }

        if (lang === this.currentLanguage) {
            this.closeMenu();
            return;
        }

        // Close menu immediately
        this.closeMenu();

        try {
            // Show loading state
            this.setButtonLoading(true);

            // Make language change request
            const response = await fetch('/set-language', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ lang })
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok || !data.success) {
                throw new Error(data.message || 'Language change failed');
            }

            // Update current language
            this.currentLanguage = lang;
            safeSetStorage('lang', lang);

            // Update UI
            this.updateLanguageSelector();
            this.dispatchLanguageChange(lang);

            // Reload page to apply new language
            window.location.reload();

        } catch (error) {
            console.error('Error changing language:', error);
            this.showError('Failed to change language. Please try again.');
        } finally {
            this.setButtonLoading(false);
        }
    }

    /**
     * Set button loading state
     * @param {boolean} loading - Loading state
     */
    setButtonLoading(loading) {
        if (!this.buttonElement) return;

        if (loading) {
            this.buttonElement.disabled = true;
            this.buttonElement.classList.add('loading');
        } else {
            this.buttonElement.disabled = false;
            this.buttonElement.classList.remove('loading');
        }
    }

    /**
     * Show error message
     * @param {string} message - Error message
     */
    showError(message) {
        // Create toast notification or alert
        if (window.showToast) {
            window.showToast(message, 'error');
        } else {
            alert(message);
        }
    }

    /**
     * Restore language from storage or default
     */
    restoreLanguage() {
        const savedLanguage = safeGetStorage('lang', 'en');
        
        if (this.supportedLanguages.includes(savedLanguage)) {
            this.currentLanguage = savedLanguage;
        } else {
            // Default to browser language or English
            const browserLang = navigator.language.split('-')[0];
            this.currentLanguage = this.supportedLanguages.includes(browserLang) ? browserLang : 'en';
        }

        this.updateLanguageSelector();
    }

    /**
     * Update language selector UI
     */
    updateLanguageSelector() {
        // Update active option
        document.querySelectorAll('.language-option').forEach(option => {
            const isActive = option.getAttribute('data-lang') === this.currentLanguage;
            option.setAttribute('aria-current', isActive ? 'true' : 'false');
            
            if (isActive) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
            }
        });

        // Update current language display
        const currentDisplay = this.buttonElement?.querySelector('.current-lang-code');
        if (currentDisplay) {
            const languageNames = {
                'en': 'EN',
                'ua': 'UA'
            };
            currentDisplay.textContent = languageNames[this.currentLanguage] || this.currentLanguage.toUpperCase();
        }

        // Update mobile selector if exists
        const mobileSelect = document.getElementById('mobileLanguageSelect');
        if (mobileSelect) {
            mobileSelect.value = this.currentLanguage;
        }
    }

    /**
     * Dispatch language change event
     * @param {string} lang - New language
     */
    dispatchLanguageChange(lang) {
        const event = new CustomEvent('languagechange', {
            detail: { 
                language: lang, 
                previousLanguage: this.currentLanguage 
            }
        });
        document.dispatchEvent(event);
    }

    /**
     * Get current language
     * @returns {string} - Current language code
     */
    getCurrentLanguage() {
        return this.currentLanguage;
    }

    /**
     * Get supported languages
     * @returns {Array<string>} - Array of supported language codes
     */
    getSupportedLanguages() {
        return [...this.supportedLanguages];
    }

    /**
     * Get language display name
     * @param {string} lang - Language code
     * @returns {string} - Human readable name
     */
    getLanguageDisplayName(lang) {
        const names = {
            'en': 'English',
            'ua': 'Українська'
        };
        return names[lang] || lang;
    }

    /**
     * Check if language is supported
     * @param {string} lang - Language code to check
     * @returns {boolean} - True if supported
     */
    isLanguageSupported(lang) {
        return this.supportedLanguages.includes(lang);
    }

    /**
     * Clean up event listeners
     */
    destroy() {
        // Remove event listeners
        if (this.buttonElement) {
            this.buttonElement.removeEventListener('click', this.toggleMenu);
        }
        
        // Close menu
        if (this.isMenuOpen) {
            this.closeMenu();
        }
    }
}

// Create global language manager instance
export const languageManager = new LanguageManager();

// Global language functions (backward compatibility)
window.applyLanguage = (lang) => languageManager.changeLanguage(lang);

// Mobile language selector handler
function setupMobileLanguageSelector() {
    const mobileSelect = document.getElementById('mobileLanguageSelect');
    
    if (mobileSelect) {
        mobileSelect.addEventListener('change', (e) => {
            languageManager.changeLanguage(e.target.value);
        });
    }
}

// Listen for language changes
document.addEventListener('languagechange', (e) => {
    const { language } = e.detail;
    
    // Update any language-dependent elements
    updateLanguageDependentElements(language);
    
    // Dispatch event for other modules
    window.dispatchEvent(new CustomEvent('ui:languagechange', { detail: e.detail }));
});

/**
 * Update elements that depend on language
 * @param {string} lang - Current language
 */
function updateLanguageDependentElements(lang) {
    // Update direction for RTL languages if needed
    const rtlLanguages = ['ar', 'he', 'fa'];
    document.documentElement.dir = rtlLanguages.includes(lang) ? 'rtl' : 'ltr';
    document.documentElement.lang = lang;
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        languageManager.init();
        setupMobileLanguageSelector();
    });
} else {
    languageManager.init();
    setupMobileLanguageSelector();
}
