// State Management System for Black Diamond Web Application
// Centralized state management with reactive updates

import { debounce, safeGetStorage } from './utils.js';

/**
 * Centralized store for application state
 */
class Store {
    constructor() {
        this.state = {
            // User state
            user: {
                isAuthenticated: false,
                profile: null,
                preferences: {
                    theme: 'current',
                    language: 'en',
                    notifications: true
                }
            },
            
            // UI state
            ui: {
                isLoading: false,
                currentPage: '/',
                modals: {
                    isLanguageOpen: false,
                    isThemeOpen: false,
                    isQuickActionsOpen: false
                },
                notifications: [],
                performance: {
                    animationsEnabled: true,
                    effectsEnabled: true,
                    reducedMotion: false
                }
            },
            
            // Application state
            app: {
                version: '2.0.0',
                isOnline: navigator.onLine,
                lastUpdate: Date.now(),
                features: {
                    pwa: false,
                    serviceWorker: false,
                    pushNotifications: false
                }
            }
        };
        
        this.subscribers = new Map();
        this.middleware = [];
        this.isDebugMode = this.checkDebugMode();
    }

    /**
     * Check if debug mode is enabled
     */
    checkDebugMode() {
        return window.location.hostname === 'localhost' || 
               window.location.hostname === '127.0.0.1' ||
               localStorage.getItem('bd-debug') === 'true';
    }

    /**
     * Get current state
     */
    getState() {
        return JSON.parse(JSON.stringify(this.state));
    }

    /**
     * Subscribe to state changes
     */
    subscribe(key, callback) {
        if (!this.subscribers.has(key)) {
            this.subscribers.set(key, new Set());
        }
        
        this.subscribers.get(key).add(callback);
        
        // Return unsubscribe function
        return () => {
            const subscribers = this.subscribers.get(key);
            if (subscribers) {
                subscribers.delete(callback);
                if (subscribers.size === 0) {
                    this.subscribers.delete(key);
                }
            }
        };
    }

    /**
     * Add middleware for state changes
     */
    use(middleware) {
        this.middleware.push(middleware);
    }

    /**
     * Update state
     */
    setState(updates, source = 'unknown') {
        const oldState = this.getState();
        const newState = { ...this.state };
        
        // Deep merge updates
        this.deepMerge(newState, updates);
        
        // Run middleware
        for (const middleware of this.middleware) {
            try {
                middleware(newState, oldState);
            } catch (error) {
                console.error('State middleware error:', error);
            }
        }
        
        this.state = newState;
        
        // Notify subscribers
        this.notifySubscribers(updates, oldState, newState);
        
        // Persist relevant state
        this.persistState(updates);
        
        // Debug logging
        if (this.isDebugMode) {
            console.log(`[Store] State updated from ${source}:`, {
                updates,
                changed: this.getChangedPaths(oldState, newState)
            });
        }
    }

    /**
     * Deep merge objects
     */
    deepMerge(target, source) {
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                if (!target[key] || typeof target[key] !== 'object') {
                    target[key] = {};
                }
                this.deepMerge(target[key], source[key]);
            } else {
                target[key] = source[key];
            }
        }
        return target;
    }

    /**
     * Notify subscribers of state changes
     */
    notifySubscribers(updates, oldState, newState) {
        for (const [key, subscribers] of this.subscribers) {
            if (this.hasStateChange(key, oldState, newState)) {
                subscribers.forEach(callback => {
                    try {
                        callback(this.getState()[key], oldState[key]);
                    } catch (error) {
                        console.error('Subscriber error:', error);
                    }
                });
            }
        }
    }

    /**
     * Check if specific state key changed
     */
    hasStateChange(key, oldState, newState) {
        return JSON.stringify(this.getPath(oldState, key)) !== JSON.stringify(this.getPath(newState, key));
    }

    /**
     * Get value by path
     */
    getPath(obj, path) {
        return path.split('.').reduce((current, key) => current?.[key], obj);
    }

    /**
     * Get changed paths between states
     */
    getChangedPaths(oldState, newState, prefix = '') {
        const changes = [];
        
        for (const key in newState) {
            const fullPath = prefix ? `${prefix}.${key}` : key;
            const oldValue = oldState[key];
            const newValue = newState[key];
            
            if (typeof newValue === 'object' && newValue !== null && !Array.isArray(newValue)) {
                if (typeof oldValue === 'object' && oldValue !== null && !Array.isArray(oldValue)) {
                    changes.push(...this.getChangedPaths(oldValue, newValue, fullPath));
                } else {
                    changes.push(fullPath);
                }
            } else if (JSON.stringify(oldValue) !== JSON.stringify(newValue)) {
                changes.push(fullPath);
            }
        }
        
        return changes;
    }

    /**
     * Persist state to localStorage
     */
    persistState(updates) {
        const persistKeys = ['user.preferences', 'ui.performance'];
        
        for (const key of persistKeys) {
            if (this.hasStateChange(key, this.state, { [key]: this.getPath(this.state, key) })) {
                try {
                    localStorage.setItem(`bd-${key.replace('.', '-')}`, JSON.stringify(this.getPath(this.state, key)));
                } catch (error) {
                    console.warn('Failed to persist state:', error);
                }
            }
        }
    }

    /**
     * Load persisted state
     */
    loadPersistedState() {
        const persistedKeys = ['user-preferences', 'ui-performance'];
        
        for (const key of persistedKeys) {
            try {
                const stored = safeGetStorage(`bd-${key}`);
                if (stored) {
                    const path = key.replace('-', '.');
                    this.setState({ [path]: JSON.parse(stored) }, 'persistence');
                }
            } catch (error) {
                console.warn(`Failed to load persisted state for ${key}:`, error);
            }
        }
    }

    /**
     * Reset state to initial values
     */
    resetState() {
        const persistedKeys = ['user.preferences', 'ui.performance'];
        const initialState = new Store().state;
        
        this.setState(initialState, 'reset');
        
        // Keep persisted user preferences
        for (const key of persistedKeys) {
            const persisted = safeGetStorage(`bd-${key.replace('.', '-')}`);
            if (persisted) {
                this.setState({ [key]: JSON.parse(persisted) }, 'persistence');
            }
        }
    }
}

/**
 * Reactive state hook for components
 */
function useState(path, initialValue = null) {
    const [state, setState] = useStateInternal(path, initialValue);
    
    // Return state and setter
    return [state, (newValue) => {
        store.setState({ [path]: newValue }, 'component');
    }];
}

/**
 * Internal useState implementation
 */
function useStateInternal(path, initialValue) {
    const [state, setState] = React.useState(() => {
        return store.getState() || initialValue;
    });
    
    React.useEffect(() => {
        return store.subscribe(path, setState);
    }, [path]);
    
    return [state, setState];
}

/**
 * Computed values derived from state
 */
function useComputed(computeFn, dependencies = []) {
    const [value, setValue] = React.useState(() => computeFn(store.getState()));
    
    React.useEffect(() => {
        const unsubscribe = store.subscribe('*', () => {
            const newValue = computeFn(store.getState());
            setValue(newValue);
        });
        
        return unsubscribe;
    }, dependencies);
    
    return value;
}

/**
 * Store actions creators
 */
const actions = {
    // User actions
    setUser(user) {
        store.setState({ user }, 'action');
    },
    
    updateUserPreferences(preferences) {
        store.setState({ 
            user: { 
                preferences: { ...store.getState().user.preferences, ...preferences }
            }
        }, 'action');
    },
    
    // UI actions
    setLoading(isLoading) {
        store.setState({ ui: { isLoading } }, 'action');
    },
    
    openModal(modalName) {
        store.setState({ 
            ui: { 
                modals: { 
                    [modalName]: true,
                    ...Object.fromEntries(
                        Object.entries(store.getState().ui.modals).map(([key]) => [key, key === modalName])
                    )
                }
            }
        }, 'action');
    },
    
    closeModal(modalName) {
        store.setState({ 
            ui: { 
                modals: { [modalName]: false }
            }
        }, 'action');
    },
    
    addNotification(notification) {
        const id = Date.now() + Math.random();
        const newNotification = { id, ...notification };
        
        store.setState({
            ui: {
                notifications: [...store.getState().ui.notifications, newNotification]
            }
        }, 'action');
        
        // Auto-remove after duration
        if (notification.duration > 0) {
            setTimeout(() => {
                actions.removeNotification(id);
            }, notification.duration);
        }
    },
    
    removeNotification(id) {
        store.setState({
            ui: {
                notifications: store.getState().ui.notifications.filter(n => n.id !== id)
            }
        }, 'action');
    },
    
    // Performance actions
    setPerformanceSetting(setting, value) {
        store.setState({
            ui: {
                performance: {
                    [setting]: value
                }
            }
        }, 'action');
    },
    
    togglePerformanceFeature(feature) {
        const currentValue = store.getState().ui.performance[feature];
        actions.setPerformanceSetting(feature, !currentValue);
    },
    
    // App actions
    setOnlineStatus(isOnline) {
        store.setState({ app: { isOnline } }, 'action');
    },
    
    enablePWA() {
        store.setState({ 
            app: { 
                features: { ...store.getState().app.features, pwa: true }
            }
        }, 'action');
    }
};

/**
 * Global store instance
 */
export const store = new Store();

// Load persisted state on initialization
store.loadPersistedState();

// Debug tools
if (store.isDebugMode) {
    window.BDStore = {
        store,
        actions,
        getState: () => store.getState(),
        subscribe: (key, callback) => store.subscribe(key, callback),
        reset: () => store.resetState()
    };
    
    console.log('🗂️ Store initialized with debug tools. Access via BDStore.*');
}

// Network status monitoring
window.addEventListener('online', () => {
    actions.setOnlineStatus(true);
    actions.addNotification({
        type: 'success',
        message: 'Connection restored',
        duration: 3000
    });
});

window.addEventListener('offline', () => {
    actions.setOnlineStatus(false);
    actions.addNotification({
        type: 'warning',
        message: 'You are offline. Some features may be limited.',
        duration: 5000
    });
});

// React hooks export
export { useState, useComputed, actions };
export default store;