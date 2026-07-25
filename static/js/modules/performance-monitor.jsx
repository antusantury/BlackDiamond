// Performance Monitoring System for Black Diamond Web Application
// Real-time performance metrics and optimization

import { debounce, throttle } from './utils.js';

/**
 * Performance Monitor class
 */
class PerformanceMonitor {
    constructor() {
        this.metrics = new Map();
        this.thresholds = {
            FCP: 1800,      // First Contentful Paint
            LCP: 2500,      // Largest Contentful Paint
            FID: 100,       // First Input Delay
            CLS: 0.1,       // Cumulative Layout Shift
            TTFB: 800,      // Time to First Byte
            bundleSize: 500, // Max bundle size in KB
            memoryUsage: 100 // Max memory usage in MB
        };
        
        this.observers = new Map();
        this.isInitialized = false;
        this.init();
    }

    init() {
        if (this.isInitialized) return;
        
        this.initializePerformanceObserver();
        this.setupMemoryMonitoring();
        this.startResourceTiming();
        this.monitorBundleSize();
        
        this.isInitialized = true;
        console.log('📊 Performance Monitor initialized');
    }

    /**
     * Initialize PerformanceObserver
     */
    initializePerformanceObserver() {
        if (!window.PerformanceObserver) return;

        // Largest Contentful Paint
        this.createObserver('largest-contentful-paint', (entries) => {
            const entry = entries[entries.length - 1];
            this.recordMetric('LCP', entry.startTime);
        });

        // First Input Delay
        this.createObserver('first-input', (entries) => {
            const entry = entries[0];
            this.recordMetric('FID', entry.processingStart - entry.startTime);
        });

        // Cumulative Layout Shift
        this.createObserver('layout-shift', (entries) => {
            let clsValue = 0;
            entries.forEach(entry => {
                if (!entry.hadRecentInput) {
                    clsValue += entry.value;
                }
            });
            this.recordMetric('CLS', clsValue);
        });

        // First Contentful Paint
        this.createObserver('paint', (entries) => {
            entries.forEach(entry => {
                if (entry.name === 'first-contentful-paint') {
                    this.recordMetric('FCP', entry.startTime);
                }
            });
        });

        // Navigation Timing
        if ('PerformanceNavigationTiming' in window) {
            window.addEventListener('load', () => {
                setTimeout(() => {
                    const navigation = performance.getEntriesByType('navigation')[0];
                    if (navigation) {
                        this.recordMetric('TTFB', navigation.responseStart - navigation.requestStart);
                        this.recordMetric('DOM_LOAD', navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart);
                        this.recordMetric('PAGE_LOAD', navigation.loadEventEnd - navigation.loadEventStart);
                    }
                }, 0);
            });
        }
    }

    /**
     * Create Performance Observer
     */
    createObserver(type, callback) {
        try {
            const observer = new PerformanceObserver((list) => {
                callback(list.getEntries());
            });
            observer.observe({ entryTypes: [type] });
            this.observers.set(type, observer);
        } catch (error) {
            console.warn(`Failed to create observer for ${type}:`, error);
        }
    }

    /**
     * Setup memory monitoring
     */
    setupMemoryMonitoring() {
        if (performance.memory) {
            // Monitor memory usage every 30 seconds
            setInterval(() => {
                const memory = performance.memory;
                const usedMB = Math.round(memory.usedJSHeapSize / 1048576);
                this.recordMetric('MEMORY_USAGE', usedMB);
            }, 30000);
        }
    }

    /**
     * Start resource timing monitoring
     */
    startResourceTiming() {
        const observer = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
                if (entry.initiatorType === 'script' || entry.initiatorType === 'css') {
                    this.recordResourceMetric(entry);
                }
            });
        });

        observer.observe({ entryTypes: ['resource'] });
        this.observers.set('resource', observer);
    }

    /**
     * Record resource metrics
     */
    recordResourceMetric(entry) {
        const resourceName = entry.name;
        const loadTime = entry.responseEnd - entry.startTime;
        
        if (entry.initiatorType === 'script') {
            this.metrics.set(`script_${resourceName}`, {
                loadTime,
                size: entry.transferSize || 0,
                type: 'script'
            });
        } else if (entry.initiatorType === 'css') {
            this.metrics.set(`css_${resourceName}`, {
                loadTime,
                size: entry.transferSize || 0,
                type: 'css'
            });
        }
    }

    /**
     * Monitor bundle size
     */
    monitorBundleSize() {
        // This would be implemented with webpack bundle analyzer
        // For now, we'll estimate based on loaded resources
        const checkBundleSize = () => {
            const scripts = document.querySelectorAll('script[src]');
            let totalSize = 0;
            
            scripts.forEach(script => {
                // In a real implementation, you'd get the actual size
                // For now, we'll just count the number of scripts
                totalSize += 1;
            });
            
            this.recordMetric('BUNDLE_SIZE', totalSize * 50); // Rough estimate in KB
        };

        checkBundleSize();
        
        // Re-check periodically
        setInterval(checkBundleSize, 60000);
    }

    /**
     * Record metric
     */
    recordMetric(name, value, threshold = null) {
        const thresholdValue = threshold || this.thresholds[name] || Infinity;
        const status = value <= thresholdValue ? 'good' : 'warning';
        
        const metric = {
            name,
            value,
            threshold: thresholdValue,
            status,
            timestamp: Date.now(),
            unit: this.getUnit(name)
        };
        
        this.metrics.set(name, metric);
        
        // Log warnings
        if (status === 'warning') {
            console.warn(`⚠️ Performance warning: ${name} = ${value}${metric.unit} (threshold: ${thresholdValue}${metric.unit})`);
        }
        
        // Trigger custom event
        window.dispatchEvent(new CustomEvent('performanceMetric', {
            detail: metric
        }));
    }

    /**
     * Get unit for metric
     */
    getUnit(metricName) {
        const units = {
            FCP: 'ms',
            LCP: 'ms',
            FID: 'ms',
            CLS: '',
            TTFB: 'ms',
            DOM_LOAD: 'ms',
            PAGE_LOAD: 'ms',
            MEMORY_USAGE: 'MB',
            BUNDLE_SIZE: 'KB'
        };
        return units[metricName] || '';
    }

    /**
     * Get all metrics
     */
    getMetrics() {
        return Object.fromEntries(this.metrics);
    }

    /**
     * Get specific metric
     */
    getMetric(name) {
        return this.metrics.get(name);
    }

    /**
     * Generate performance report
     */
    generateReport() {
        const report = {
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            connection: navigator.connection ? {
                effectiveType: navigator.connection.effectiveType,
                downlink: navigator.connection.downlink
            } : null,
            metrics: {},
            summary: {
                totalMetrics: this.metrics.size,
                warnings: 0,
                goodMetrics: 0
            }
        };
        
        for (const [name, metric] of this.metrics) {
            report.metrics[name] = metric;
            
            if (metric.status === 'warning') {
                report.summary.warnings++;
            } else {
                report.summary.goodMetrics++;
            }
        }
        
        return report;
    }

    /**
     * Export metrics as JSON
     */
    exportMetrics() {
        const report = this.generateReport();
        const blob = new Blob([JSON.stringify(report, null, 2)], {
            type: 'application/json'
        });
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `performance-report-${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Performance optimization suggestions
     */
    getOptimizationSuggestions() {
        const suggestions = [];
        
        for (const [name, metric] of this.metrics) {
            if (metric.status === 'warning') {
                switch (name) {
                    case 'LCP':
                        suggestions.push({
                            type: 'critical',
                            title: 'Optimize Largest Contentful Paint',
                            description: 'Consider optimizing images, reducing server response time, or improving render blocking resources.',
                            actions: [
                                'Compress and resize images',
                                'Use WebP format',
                                'Optimize server response',
                                'Remove render-blocking resources'
                            ]
                        });
                        break;
                        
                    case 'FID':
                        suggestions.push({
                            type: 'high',
                            title: 'Reduce First Input Delay',
                            description: 'Minimize JavaScript execution time and break up long tasks.',
                            actions: [
                                'Code splitting',
                                'Reduce bundle size',
                                'Avoid long main thread tasks',
                                'Use web workers for heavy computation'
                            ]
                        });
                        break;
                        
                    case 'CLS':
                        suggestions.push({
                            type: 'medium',
                            title: 'Reduce Cumulative Layout Shift',
                            description: 'Reserve space for images and ads, avoid inserting content above existing content.',
                            actions: [
                                'Add width and height to images',
                                'Reserve space for dynamic content',
                                'Use transform for animations',
                                'Avoid inserting content above DOM'
                            ]
                        });
                        break;
                        
                    case 'MEMORY_USAGE':
                        suggestions.push({
                            type: 'medium',
                            title: 'Optimize Memory Usage',
                            description: 'High memory usage detected. Consider implementing memory cleanup strategies.',
                            actions: [
                                'Implement memory cleanup',
                                'Use object pooling',
                                'Remove event listeners when not needed',
                                'Optimize data structures'
                            ]
                        });
                        break;
                }
            }
        }
        
        return suggestions;
    }

    /**
     * Destroy observer and cleanup
     */
    destroy() {
        for (const observer of this.observers.values()) {
            observer.disconnect();
        }
        this.observers.clear();
        this.metrics.clear();
        this.isInitialized = false;
    }
}

/**
 * Bundle Analyzer
 */
class BundleAnalyzer {
    constructor() {
        this.bundles = new Map();
        this.loadedScripts = new Set();
        this.analyze();
    }

    analyze() {
        // Analyze loaded scripts
        document.querySelectorAll('script[src]').forEach(script => {
            this.analyzeScript(script);
        });

        // Monitor dynamically loaded scripts
        const originalCreateElement = document.createElement.bind(document);
        document.createElement = function(tagName) {
            const element = originalCreateElement(tagName);
            if (tagName.toLowerCase() === 'script') {
                const originalSrc = Object.getOwnPropertyDescriptor(element, 'src');
                Object.defineProperty(element, 'src', {
                    set: function(value) {
                        originalSrc.set.call(this, value);
                        // Analyze when script source is set
                        setTimeout(() => this.analyzeScript(this), 0);
                    }.bind(this),
                    get: originalSrc.get
                });
            }
            return element;
        };
    }

    analyzeScript(script) {
        if (script.src && !this.loadedScripts.has(script.src)) {
            this.loadedScripts.add(script.src);
            
            // In a real implementation, you would:
            // 1. Fetch the script content
            // 2. Analyze size and dependencies
            // 3. Check for optimization opportunities
            
            this.bundles.set(script.src, {
                size: 'Unknown', // Would be actual size
                type: 'script',
                async: script.async,
                defer: script.defer,
                loaded: true
            });
        }
    }

    getBundleInfo() {
        return Object.fromEntries(this.bundles);
    }

    getTotalSize() {
        let total = 0;
        for (const bundle of this.bundles.values()) {
            if (typeof bundle.size === 'number') {
                total += bundle.size;
            }
        }
        return total;
    }
}

/**
 * Real User Monitoring
 */
class RealUserMonitoring {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.pageViews = [];
        this.errors = [];
        this.performanceMarks = [];
        this.init();
    }

    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9);
    }

    init() {
        this.trackPageView();
        this.setupErrorTracking();
        this.setupUserInteractions();
    }

    trackPageView() {
        const pageView = {
            sessionId: this.sessionId,
            url: window.location.href,
            title: document.title,
            timestamp: Date.now(),
            referrer: document.referrer,
            userAgent: navigator.userAgent
        };
        
        this.pageViews.push(pageView);
        this.sendData('pageview', pageView);
    }

    setupErrorTracking() {
        window.addEventListener('error', (event) => {
            const error = {
                sessionId: this.sessionId,
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                stack: event.error ? event.error.stack : null,
                timestamp: Date.now()
            };
            
            this.errors.push(error);
            this.sendData('error', error);
        });

        window.addEventListener('unhandledrejection', (event) => {
            const error = {
                sessionId: this.sessionId,
                message: 'Unhandled Promise Rejection: ' + event.reason,
                timestamp: Date.now()
            };
            
            this.errors.push(error);
            this.sendData('error', error);
        });
    }

    setupUserInteractions() {
        // Track clicks
        document.addEventListener('click', (event) => {
            this.trackInteraction('click', {
                element: event.target.tagName,
                text: event.target.textContent,
                href: event.target.href
            });
        });

        // Track form submissions
        document.addEventListener('submit', (event) => {
            this.trackInteraction('form_submit', {
                formId: event.target.id,
                formName: event.target.name
            });
        });
    }

    trackInteraction(type, data) {
        const interaction = {
            sessionId: this.sessionId,
            type,
            data,
            timestamp: Date.now(),
            url: window.location.href
        };
        
        this.sendData('interaction', interaction);
    }

    markPerformance(name) {
        const mark = {
            sessionId: this.sessionId,
            name,
            timestamp: Date.now(),
            url: window.location.href
        };
        
        this.performanceMarks.push(mark);
        performance.mark(name);
        this.sendData('performance_mark', mark);
    }

    sendData(type, data) {
        // In a real implementation, you would send this to your analytics service
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.log(`[RUM] ${type}:`, data);
        }
        
        // Store locally for development
        const stored = JSON.parse(localStorage.getItem('bd_rum_data') || '[]');
        stored.push({ type, data, timestamp: Date.now() });
        localStorage.setItem('bd_rum_data', JSON.stringify(stored.slice(-100))); // Keep last 100 entries
    }
}

// Global performance monitoring instance
export const performanceMonitor = new PerformanceMonitor();
export const bundleAnalyzer = new BundleAnalyzer();
export const rum = new RealUserMonitoring();

// Export classes for custom usage
export { PerformanceMonitor, BundleAnalyzer, RealUserMonitoring };

// Auto-initialize in development
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.BDPerformance = {
        monitor: performanceMonitor,
        analyzer: bundleAnalyzer,
        rum: rum,
        getReport: () => performanceMonitor.generateReport(),
        getSuggestions: () => performanceMonitor.getOptimizationSuggestions(),
        exportMetrics: () => performanceMonitor.exportMetrics()
    };
    
    console.log('🚀 Performance monitoring available via BDPerformance.*');
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        rum.markPerformance('dom_ready');
    });
} else {
    rum.markPerformance('dom_ready');
}

window.addEventListener('load', () => {
    rum.markPerformance('window_load');
});