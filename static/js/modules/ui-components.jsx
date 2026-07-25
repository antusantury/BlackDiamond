// UI Component Library for Black Diamond Web Application
// Modern, accessible, and performant UI components

import { debounce, prefersReducedMotion } from './utils.js';

/**
 * Toast notification component
 */
class ToastManager {
    constructor() {
        this.toasts = new Map();
        this.container = null;
        this.init();
    }

    init() {
        this.createContainer();
        this.setupKeyboardShortcuts();
    }

    createContainer() {
        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        this.container.className = 'toast-container';
        this.container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            pointer-events: none;
            max-width: 400px;
        `;
        document.body.appendChild(this.container);
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.clearAll();
            }
        });
    }

    show(message, options = {}) {
        const id = Date.now() + Math.random();
        const toast = {
            id,
            message,
            type: options.type || 'info',
            duration: options.duration || 5000,
            title: options.title,
            actions: options.actions || [],
            persistent: options.persistent || false,
            timestamp: Date.now()
        };

        this.createToastElement(toast);
        this.toasts.set(id, toast);

        if (!toast.persistent && toast.duration > 0) {
            setTimeout(() => this.remove(id), toast.duration);
        }

        this.updateARIA();
        return id;
    }

    createToastElement(toast) {
        const element = document.createElement('div');
        element.className = `toast toast-${toast.type}`;
        element.setAttribute('role', 'status');
        element.setAttribute('aria-live', 'polite');
        element.setAttribute('data-id', toast.id);

        const icon = this.getIcon(toast.type);
        const timestamp = new Date(toast.timestamp).toLocaleTimeString();

        element.innerHTML = `
            <div class="toast-content">
                <div class="toast-icon">${icon}</div>
                <div class="toast-message">
                    ${toast.title ? `<div class="toast-title">${toast.title}</div>` : ''}
                    <div class="toast-text">${toast.message}</div>
                </div>
                <button class="toast-close" aria-label="Close notification" onclick="BDUI.toasts.remove('${toast.id}')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6L18 18"/>
                    </svg>
                </button>
            </div>
            ${toast.actions.length > 0 ? `
                <div class="toast-actions">
                    ${toast.actions.map(action => `
                        <button class="toast-action toast-action-${action.type}" onclick="${action.onClick}">
                            ${action.label}
                        </button>
                    `).join('')}
                </div>
            ` : ''}
            <div class="toast-timestamp">${timestamp}</div>
        `;

        element.style.cssText = `
            background: var(--surface-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
            transform: translateX(100%);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            pointer-events: auto;
            backdrop-filter: blur(20px);
        `;

        // Add type-specific styles
        switch (toast.type) {
            case 'success':
                element.style.borderLeft = '4px solid #22c55e';
                break;
            case 'error':
                element.style.borderLeft = '4px solid #ef4444';
                break;
            case 'warning':
                element.style.borderLeft = '4px solid #f59e0b';
                break;
            case 'info':
            default:
                element.style.borderLeft = '4px solid #3b82f6';
                break;
        }

        this.container.appendChild(element);

        // Animate in
        requestAnimationFrame(() => {
            element.style.transform = 'translateX(0)';
            element.style.opacity = '1';
        });

        // Add progress bar for timed toasts
        if (!toast.persistent && toast.duration > 0) {
            this.addProgressBar(element, toast.duration);
        }
    }

    addProgressBar(element, duration) {
        const progressBar = document.createElement('div');
        progressBar.className = 'toast-progress';
        progressBar.style.cssText = `
            position: absolute;
            bottom: 0;
            left: 0;
            height: 3px;
            background: var(--accent);
            border-radius: 0 0 12px 12px;
            width: 100%;
            transform: scaleX(0);
            transform-origin: left;
            transition: transform ${duration}ms linear;
        `;
        
        element.appendChild(progressBar);
        
        requestAnimationFrame(() => {
            progressBar.style.transform = 'scaleX(1)';
        });
    }

    getIcon(type) {
        const icons = {
            success: `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 12l2 2 4-4M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
            `,
            error: `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
            `,
            warning: `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
            `,
            info: `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
            `
        };
        return icons[type] || icons.info;
    }

    remove(id) {
        const toast = this.toasts.get(id);
        if (!toast) return;

        const element = this.container.querySelector(`[data-id="${id}"]`);
        if (element) {
            element.style.transform = 'translateX(100%)';
            element.style.opacity = '0';
            setTimeout(() => {
                element.remove();
            }, 300);
        }

        this.toasts.delete(id);
        this.updateARIA();
    }

    clearAll() {
        for (const id of this.toasts.keys()) {
            this.remove(id);
        }
    }

    updateARIA() {
        const count = this.toasts.size;
        this.container.setAttribute('aria-label', `${count} notification${count !== 1 ? 's' : ''}`);
    }
}

/**
 * Modal component system
 */
class ModalManager {
    constructor() {
        this.modals = new Map();
        this.activeModal = null;
        this.trapFocus = this.trapFocus.bind(this);
        this.handleEscape = this.handleEscape.bind(this);
        this.init();
    }

    init() {
        this.createBackdrop();
    }

    createBackdrop() {
        this.backdrop = document.createElement('div');
        this.backdrop.className = 'modal-backdrop';
        this.backdrop.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(4px);
            z-index: 9999;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
        `;
    }

    open(id, content, options = {}) {
        // Close existing modal
        if (this.activeModal) {
            this.close(this.activeModal);
        }

        const modal = {
            id,
            content,
            options: {
                closable: options.closable !== false,
                trapFocus: options.trapFocus !== false,
                closeOnBackdrop: options.closeOnBackdrop !== false,
                ...options
            }
        };

        this.createModalElement(modal);
        this.modals.set(id, modal);
        this.activeModal = id;

        this.show();
    }

    createModalElement(modal) {
        const element = document.createElement('div');
        element.className = 'bd-modal';
        element.setAttribute('role', 'dialog');
        element.setAttribute('aria-modal', 'true');
        element.setAttribute('data-modal-id', modal.id);
        element.setAttribute('aria-labelledby', `modal-title-${modal.id}`);

        element.innerHTML = `
            <div class="bd-modal-content">
                ${modal.options.title ? `
                    <div class="bd-modal-header">
                        <h2 id="modal-title-${modal.id}" class="bd-modal-title">${modal.options.title}</h2>
                        ${modal.options.closable ? `
                            <button class="bd-modal-close" aria-label="Close modal" onclick="BDUI.modals.close('${modal.id}')">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M18 6L6 18M6 6L18 18"/>
                                </svg>
                            </button>
                        ` : ''}
                    </div>
                ` : ''}
                <div class="bd-modal-body">
                    ${modal.content}
                </div>
                ${modal.options.actions ? `
                    <div class="bd-modal-actions">
                        ${modal.options.actions.map(action => `
                            <button class="bd-modal-action bd-modal-action-${action.type || 'primary'}" onclick="${action.onClick}">
                                ${action.icon ? action.icon : ''}
                                ${action.label}
                            </button>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;

        element.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.9);
            background: var(--surface-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
            z-index: 10000;
            max-width: 90vw;
            max-height: 90vh;
            overflow-y: auto;
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            backdrop-filter: blur(20px);
        `;

        this.backdrop.appendChild(element);
        document.body.appendChild(this.backdrop);

        // Handle backdrop click
        if (modal.options.closeOnBackdrop) {
            this.backdrop.addEventListener('click', (e) => {
                if (e.target === this.backdrop) {
                    this.close(modal.id);
                }
            });
        }
    }

    show() {
        // Show backdrop
        this.backdrop.style.opacity = '1';
        this.backdrop.style.pointerEvents = 'auto';

        // Show modal with delay for backdrop
        setTimeout(() => {
            const modal = this.backdrop.querySelector('.bd-modal');
            if (modal) {
                modal.style.transform = 'translate(-50%, -50%) scale(1)';
                modal.style.opacity = '1';
            }
        }, 50);

        // Event listeners
        document.addEventListener('keydown', this.handleEscape);
        if (this.activeModal && this.modals.get(this.activeModal).options.trapFocus) {
            document.addEventListener('keydown', this.trapFocus);
        }

        // Focus management
        this.focusFirstElement();
    }

    close(id) {
        const modal = this.modals.get(id);
        if (!modal) return;

        const element = this.backdrop.querySelector(`[data-modal-id="${id}"]`);
        if (element) {
            element.style.transform = 'translate(-50%, -50%) scale(0.9)';
            element.style.opacity = '0';
        }

        this.backdrop.style.opacity = '0';
        this.backdrop.style.pointerEvents = 'none';

        setTimeout(() => {
            element.remove();
            this.modals.delete(id);
            
            if (this.modals.size === 0) {
                this.backdrop.remove();
                document.removeEventListener('keydown', this.handleEscape);
                document.removeEventListener('keydown', this.trapFocus);
                this.activeModal = null;
            }
        }, 300);
    }

    handleEscape(e) {
        if (e.key === 'Escape' && this.activeModal) {
            const modal = this.modals.get(this.activeModal);
            if (modal && modal.options.closable) {
                this.close(this.activeModal);
            }
        }
    }

    trapFocus(e) {
        if (e.key !== 'Tab' || !this.activeModal) return;

        const modal = this.modals.get(this.activeModal);
        if (!modal.options.trapFocus) return;

        const element = this.backdrop.querySelector(`[data-modal-id="${this.activeModal}"]`);
        const focusableElements = element.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            }
        } else {
            if (document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    }

    focusFirstElement() {
        const element = this.backdrop.querySelector('.bd-modal');
        if (element) {
            const focusableElement = element.querySelector(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            if (focusableElement) {
                focusableElement.focus();
            }
        }
    }
}

/**
 * Dropdown component
 */
class DropdownManager {
    constructor() {
        this.dropdowns = new Map();
        this.activeDropdown = null;
        this.clickHandler = this.handleClickOutside.bind(this);
        this.init();
    }

    init() {
        document.addEventListener('click', this.clickHandler);
    }

    toggle(trigger, dropdownId) {
        const isOpen = this.isOpen(dropdownId);
        
        if (isOpen) {
            this.close(dropdownId);
        } else {
            this.open(trigger, dropdownId);
        }
    }

    open(trigger, dropdownId) {
        this.close(this.activeDropdown);
        
        const dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;

        // Show dropdown
        dropdown.classList.add('show');
        trigger.setAttribute('aria-expanded', 'true');
        
        // Position dropdown
        this.positionDropdown(trigger, dropdown);
        
        this.dropdowns.set(dropdownId, {
            trigger,
            dropdown,
            timestamp: Date.now()
        });
        
        this.activeDropdown = dropdownId;

        // Keyboard navigation
        this.setupKeyboardNavigation(dropdown);

        // Close on outside click
        setTimeout(() => {
            document.addEventListener('click', this.clickHandler);
        }, 0);
    }

    close(dropdownId) {
        if (!dropdownId || !this.dropdowns.has(dropdownId)) return;

        const { trigger, dropdown } = this.dropdowns.get(dropdownId);
        
        dropdown.classList.remove('show');
        trigger.setAttribute('aria-expanded', 'false');
        
        this.dropdowns.delete(dropdownId);
        
        if (this.activeDropdown === dropdownId) {
            this.activeDropdown = null;
        }
    }

    positionDropdown(trigger, dropdown) {
        const triggerRect = trigger.getBoundingClientRect();
        const dropdownRect = dropdown.getBoundingClientRect();
        
        let top = triggerRect.bottom + 8;
        let left = triggerRect.left;
        
        // Adjust for viewport bounds
        if (left + dropdownRect.width > window.innerWidth) {
            left = window.innerWidth - dropdownRect.width - 16;
        }
        
        if (top + dropdownRect.height > window.innerHeight) {
            top = triggerRect.top - dropdownRect.height - 8;
        }
        
        dropdown.style.top = top + 'px';
        dropdown.style.left = left + 'px';
    }

    setupKeyboardNavigation(dropdown) {
        const items = dropdown.querySelectorAll('[role="menuitem"], .dropdown-item');
        const firstItem = items[0];
        const lastItem = items[items.length - 1];
        
        dropdown.addEventListener('keydown', (e) => {
            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    if (document.activeElement === lastItem) {
                        firstItem.focus();
                    } else {
                        const currentIndex = Array.from(items).indexOf(document.activeElement);
                        items[currentIndex + 1].focus();
                    }
                    break;
                    
                case 'ArrowUp':
                    e.preventDefault();
                    if (document.activeElement === firstItem) {
                        lastItem.focus();
                    } else {
                        const currentIndex = Array.from(items).indexOf(document.activeElement);
                        items[currentIndex - 1].focus();
                    }
                    break;
                    
                case 'Escape':
                    e.preventDefault();
                    this.close(this.activeDropdown);
                    break;
            }
        });
    }

    isOpen(dropdownId) {
        return this.dropdowns.has(dropdownId) && 
               this.dropdowns.get(dropdownId).dropdown.classList.contains('show');
    }

    handleClickOutside(e) {
        if (this.activeDropdown) {
            const { trigger, dropdown } = this.dropdowns.get(this.activeDropdown);
            
            if (!trigger.contains(e.target) && !dropdown.contains(e.target)) {
                this.close(this.activeDropdown);
            }
        }
    }

    destroy() {
        document.removeEventListener('click', this.clickHandler);
    }
}

/**
 * Global UI instance
 */
export const BDUI = {
    toasts: new ToastManager(),
    modals: new ModalManager(),
    dropdown s: new DropdownManager(),
    
    // Utility methods
    showToast(message, options) {
        return this.toasts.show(message, options);
    },
    
    showModal(id, content, options) {
        this.modals.open(id, content, options);
    },
    
    closeModal(id) {
        this.modals.close(id);
    },
    
    toggleDropdown(trigger, dropdownId) {
        this.dropdowns.toggle(trigger, dropdownId);
    }
};

// Add global styles for components
const componentStyles = document.createElement('style');
componentStyles.textContent = `
    .toast-container {
        font-family: 'Inter', sans-serif;
    }
    
    .toast-content {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
    }
    
    .toast-icon {
        color: var(--accent);
        flex-shrink: 0;
    }
    
    .toast-message {
        flex: 1;
    }
    
    .toast-title {
        font-weight: 600;
        color: var(--primary);
        margin-bottom: 0.25rem;
    }
    
    .toast-text {
        color: var(--secondary);
        font-size: 0.9rem;
    }
    
    .toast-close {
        background: none;
        border: none;
        color: var(--secondary);
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        transition: background 0.2s;
    }
    
    .toast-close:hover {
        background: rgba(0, 0, 0, 0.1);
    }
    
    .toast-actions {
        margin-top: 0.75rem;
        display: flex;
        gap: 0.5rem;
    }
    
    .toast-action {
        background: var(--accent);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        font-size: 0.8rem;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .toast-action:hover {
        transform: translateY(-1px);
    }
    
    .toast-timestamp {
        position: absolute;
        bottom: 8px;
        right: 12px;
        font-size: 0.7rem;
        color: var(--secondary);
        opacity: 0.6;
    }
    
    .bd-modal-content {
        min-width: 320px;
        max-width: 640px;
    }
    
    .bd-modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.5rem 1.5rem 0;
    }
    
    .bd-modal-title {
        margin: 0;
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--primary);
    }
    
    .bd-modal-close {
        background: none;
        border: none;
        color: var(--secondary);
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        transition: background 0.2s;
    }
    
    .bd-modal-close:hover {
        background: rgba(0, 0, 0, 0.1);
    }
    
    .bd-modal-body {
        padding: 1.5rem;
        color: var(--primary);
    }
    
    .bd-modal-actions {
        display: flex;
        justify-content: flex-end;
        gap: 0.75rem;
        padding: 0 1.5rem 1.5rem;
    }
    
    .bd-modal-action {
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .bd-modal-action-primary {
        background: var(--accent);
        color: white;
        border: none;
    }
    
    .bd-modal-action-secondary {
        background: transparent;
        color: var(--primary);
        border: 1px solid var(--border);
    }
    
    .bd-modal-action:hover {
        transform: translateY(-1px);
    }
    
    @media (max-width: 768px) {
        .toast-container {
            left: 16px;
            right: 16px;
            max-width: none;
        }
        
        .bd-modal-content {
            margin: 1rem;
            max-width: calc(100vw - 2rem);
        }
    }
`;

document.head.appendChild(componentStyles);

// Export for global use
window.BDUI = BDUI;