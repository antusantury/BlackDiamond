// Frontend Test Suite for Black Diamond Web Application
// Tests components, modules, and functionality

// Test utilities
class TestRunner {
    constructor() {
        this.tests = [];
        this.passed = 0;
        this.failed = 0;
        this.results = [];
    }

    // Add test case
    addTest(name, testFunction) {
        this.tests.push({ name, testFunction });
    }

    // Run all tests
    async run() {
        console.log('🧪 Starting Black Diamond Frontend Tests...\n');

        for (const test of this.tests) {
            await this.runSingleTest(test);
        }

        this.printSummary();
        return {
            total: this.tests.length,
            passed: this.passed,
            failed: this.failed,
            results: this.results
        };
    }

    // Run single test
    async runSingleTest(test) {
        try {
            const startTime = performance.now();
            await test.testFunction();
            const duration = performance.now() - startTime;

            this.passed++;
            this.results.push({
                name: test.name,
                status: 'passed',
                duration: duration.toFixed(2)
            });

            console.log(`✅ ${test.name} (${duration.toFixed(2)}ms)`);
        } catch (error) {
            this.failed++;
            this.results.push({
                name: test.name,
                status: 'failed',
                error: error.message
            });

            console.log(`❌ ${test.name} - ${error.message}`);
        }
    }

    // Print test summary
    printSummary() {
        console.log(`\n📊 Test Summary:`);
        console.log(`   Total: ${this.tests.length}`);
        console.log(`   ✅ Passed: ${this.passed}`);
        console.log(`   ❌ Failed: ${this.failed}`);
        console.log(`   Success Rate: ${((this.passed / this.tests.length) * 100).toFixed(1)}%`);

        if (this.failed > 0) {
            console.log(`\n❌ Failed Tests:`);
            this.results
                .filter(r => r.status === 'failed')
                .forEach(r => console.log(`   • ${r.name}: ${r.error}`));
        }
    }
}

// Utility test functions
class TestUtils {
    // Check if element exists
    static assertElementExists(selector, message = 'Element should exist') {
        const element = document.querySelector(selector);
        if (!element) {
            throw new Error(`${message}: "${selector}" not found`);
        }
        return element;
    }

    // Check if element has class
    static assertElementHasClass(selector, className, message = 'Element should have class') {
        const element = this.assertElementExists(selector, message);
        if (!element.classList.contains(className)) {
            throw new Error(`${message}: "${className}" not found on ${selector}`);
        }
    }

    // Check if element has attribute
    static assertElementHasAttribute(selector, attribute, message = 'Element should have attribute') {
        const element = this.assertElementExists(selector, message);
        if (!element.hasAttribute(attribute)) {
            throw new Error(`${message}: "${attribute}" not found on ${selector}`);
        }
        return element.getAttribute(attribute);
    }

    // Check if function exists
    static assertFunctionExists(fn, message = 'Function should exist') {
        if (typeof fn !== 'function') {
            throw new Error(`${message}: ${fn} is not a function`);
        }
    }

    // Mock DOM elements for testing
    static mockDOM() {
        // Mock IntersectionObserver
        global.IntersectionObserver = class IntersectionObserver {
            constructor(callback) {
                this.callback = callback;
            }
            observe(element) {
                // Simulate element entering viewport
                setTimeout(() => {
                    this.callback([{ isIntersecting: true, target: element }], this);
                }, 10);
            }
            disconnect() {}
            unobserve() {}
        };

        // Mock localStorage
        const storage = {};
        global.localStorage = {
            getItem: (key) => storage[key] || null,
            setItem: (key, value) => { storage[key] = value; },
            removeItem: (key) => { delete storage[key]; },
            clear: () => { Object.keys(storage).forEach(key => delete storage[key]); }
        };

        // Mock fetch
        global.fetch = jest.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ success: true }),
                text: () => Promise.resolve('OK')
            })
        );
    }
}

// Component tests
class ComponentTests {
    static addTests(testRunner) {
        testRunner.addTest('Header navigation exists', () => {
            const header = TestUtils.assertElementExists('header', 'Header should exist');
            const nav = TestUtils.assertElementExists('nav', 'Navigation should exist');
            TestUtils.assertElementHasClass('nav', 'nav', 'Navigation should have nav class');
        });

        testRunner.addTest('Theme toggle button works', () => {
            const themeToggle = document.getElementById('themeToggleBtn');
            TestUtils.assertElementExists('#themeToggleBtn', 'Theme toggle button should exist');
            
            if (themeToggle) {
                TestUtils.assertElementHasAttribute('#themeToggleBtn', 'aria-label', 'Theme toggle should have aria-label');
                const initialTheme = document.body.className;
                
                // Test theme switching if function exists
                if (window.themeManager) {
                    const newTheme = initialTheme.includes('theme-white') ? 'black' : 'white';
                    window.themeManager.switchToTheme(newTheme);
                    
                    const newClass = document.body.className;
                    if (newTheme === 'black') {
                        if (!newClass.includes('theme-black')) {
                            throw new Error('Theme switch to black failed');
                        }
                    }
                }
            }
        });

        testRunner.addTest('Language selector accessibility', () => {
            const languageBtn = TestUtils.assertElementExists('#languageBtn', 'Language button should exist');
            const languageDropdown = TestUtils.assertElementExists('#languageDropdown', 'Language dropdown should exist');
            
            // Check ARIA attributes
            TestUtils.assertElementHasAttribute('#languageBtn', 'aria-expanded', 'Language button should have aria-expanded');
            TestUtils.assertElementHasAttribute('#languageDropdown', 'role', 'Language dropdown should have role');
            
            // Check language options
            const languageOptions = document.querySelectorAll('.language-option');
            if (languageOptions.length === 0) {
                throw new Error('No language options found');
            }
        });

        testRunner.addTest('Skip links accessibility', () => {
            // Check if skip links are created
            const skipLinks = document.querySelector('.skip-links');
            if (skipLinks) {
                const skipToMain = skipLinks.querySelector('a[href="#main-content"]');
                const skipToNav = skipLinks.querySelector('a[href="#navigation"]');
                
                if (!skipToMain) throw new Error('Skip to main content link not found');
                if (!skipToNav) throw new Error('Skip to navigation link not found');
            }
        });

        testRunner.addTest('Responsive meta viewport', () => {
            const viewport = TestUtils.assertElementExists('meta[name="viewport"]', 'Viewport meta tag should exist');
            const content = viewport.getAttribute('content');
            
            if (!content.includes('width=device-width')) {
                throw new Error('Viewport should include width=device-width');
            }
        });

        testRunner.addTest('Focus management', () => {
            // Check if focus indicators are enhanced
            const styleElement = document.createElement('style');
            styleElement.textContent = '*:focus { outline: 2px solid var(--accent); }';
            document.head.appendChild(styleElement);
            
            const button = document.createElement('button');
            button.setAttribute('tabindex', '0');
            document.body.appendChild(button);
            
            // Simulate focus
            button.focus();
            
            if (document.activeElement !== button) {
                throw new Error('Focus management test failed');
            }
            
            document.body.removeChild(button);
        });
    }
}

// Module tests
class ModuleTests {
    static addTests(testRunner) {
        testRunner.addTest('Utils module functions', () => {
            // Test if utility functions are available
            if (!window.escapeHtml) throw new Error('escapeHtml function not found');
            if (!window.debounce) throw new Error('debounce function not found');
            if (!window.throttle) throw new Error('throttle function not found');
            if (!window.prefersReducedMotion) throw new Error('prefersReducedMotion function not found');
            
            // Test escapeHtml
            const escaped = window.escapeHtml('<script>alert("test")</script>');
            if (escaped.includes('<script>')) {
                throw new Error('escapeHtml should escape script tags');
            }
            
            // Test debounce
            let callCount = 0;
            const debouncedFn = window.debounce(() => { callCount++; }, 100);
            debouncedFn();
            debouncedFn();
            setTimeout(() => {
                if (callCount !== 1) {
                    throw new Error('debounce should only call function once');
                }
            }, 110);
        });

        testRunner.addTest('Theme manager initialization', () => {
            if (!window.themeManager) {
                throw new Error('Theme manager not found');
            }
            
            const status = window.themeManager.getStatus();
            if (!status.isInitialized) {
                throw new Error('Theme manager should be initialized');
            }
            
            const availableThemes = window.themeManager.getAvailableThemes();
            if (!Array.isArray(availableThemes) || availableThemes.length === 0) {
                throw new Error('Theme manager should have available themes');
            }
        });

        testRunner.addTest('Accessibility manager functionality', () => {
            if (!window.accessibilityManager) {
                throw new Error('Accessibility manager not found');
            }
            
            const status = window.accessibilityManager.getStatus();
            if (!status.announcementsSupported) {
                throw new Error('Accessibility manager should support announcements');
            }
            
            // Test announcement function
            if (typeof window.announce !== 'function') {
                throw new Error('Global announce function should exist');
            }
        });

        testRunner.addTest('Animation manager performance', () => {
            if (!window.animationManager) {
                throw new Error('Animation manager not found');
            }
            
            // Check if performance constraints are handled
            const header = document.querySelector('.header');
            if (header) {
                // Test scroll effects if enabled
                window.scrollTo(0, 100);
                setTimeout(() => {
                    const bgColor = header.style.backgroundColor;
                    if (window.scrollY > 50 && !bgColor) {
                        throw new Error('Scroll effects should update header background');
                    }
                }, 100);
            }
        });
    }
}

// Performance tests
class PerformanceTests {
    static addTests(testRunner) {
        testRunner.addTest('Page load performance', () => {
            const navigation = performance.getEntriesByType('navigation')[0];
            if (!navigation) {
                throw new Error('Performance navigation timing not available');
            }
            
            const loadTime = navigation.loadEventEnd - navigation.loadEventStart;
            const domContentLoaded = navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart;
            
            console.log(`   DOM Content Loaded: ${domContentLoaded.toFixed(2)}ms`);
            console.log(`   Load Event: ${loadTime.toFixed(2)}ms`);
            
            // Performance should be reasonable (under 3 seconds load time)
            if (loadTime > 3000) {
                throw new Error(`Page load time too slow: ${loadTime.toFixed(2)}ms`);
            }
        });

        testRunner.addTest('Memory usage', () => {
            if (!performance.memory) {
                throw new Error('Memory usage API not available');
            }
            
            const memory = performance.memory;
            const usedMB = Math.round(memory.usedJSHeapSize / 1048576);
            
            console.log(`   Used Heap: ${usedMB}MB`);
            console.log(`   Total Heap: ${Math.round(memory.totalJSHeapSize / 1048576)}MB`);
            
            // Memory usage should be reasonable (under 100MB for this page)
            if (usedMB > 100) {
                throw new Error(`Memory usage too high: ${usedMB}MB`);
            }
        });

        testRunner.addTest('JavaScript execution performance', () => {
            const start = performance.now();
            
            // Simulate some DOM operations
            for (let i = 0; i < 1000; i++) {
                document.querySelectorAll('div');
            }
            
            const duration = performance.now() - start;
            console.log(`   1000 DOM queries: ${duration.toFixed(2)}ms`);
            
            // DOM queries should be reasonably fast
            if (duration > 100) {
                throw new Error(`DOM query performance too slow: ${duration.toFixed(2)}ms`);
            }
        });
    }
}

// Accessibility tests
class AccessibilityTests {
    static addTests(testRunner) {
        testRunner.addTest('ARIA labels and roles', () => {
            // Check for proper ARIA labels on interactive elements
            const interactiveElements = document.querySelectorAll('button, a, input, select, textarea');
            let unlabeledCount = 0;
            
            interactiveElements.forEach(element => {
                const hasLabel = element.getAttribute('aria-label') || 
                                element.getAttribute('aria-labelledby') ||
                                element.textContent.trim();
                
                if (!hasLabel) {
                    unlabeledCount++;
                }
            });
            
            // Allow some unlabeled elements but flag if too many
            if (unlabeledCount > interactiveElements.length * 0.2) {
                throw new Error(`Too many unlabeled interactive elements: ${unlabeledCount}/${interactiveElements.length}`);
            }
        });

        testRunner.addTest('Keyboard navigation', () => {
            const focusableElements = document.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            );
            
            if (focusableElements.length === 0) {
                throw new Error('No focusable elements found');
            }
            
            // Test tabbing through elements
            const firstElement = focusableElements[0];
            firstElement.focus();
            
            if (document.activeElement !== firstElement) {
                throw new Error('First focusable element not focusable');
            }
        });

        testRunner.addTest('Color contrast', () => {
            // Basic contrast check for main text elements
            const textElements = document.querySelectorAll('p, span, div, h1, h2, h3, h4, h5, h6');
            let contrastIssues = 0;
            
            textElements.forEach(element => {
                const style = getComputedStyle(element);
                const color = style.color;
                const backgroundColor = style.backgroundColor;
                
                // Very basic contrast check
                if (color === backgroundColor) {
                    contrastIssues++;
                }
            });
            
            // Flag significant contrast issues
            if (contrastIssues > textElements.length * 0.1) {
                throw new Error(`Potential contrast issues found in ${contrastIssues} elements`);
            }
        });
    }
}

// Main test execution
function runFrontendTests() {
    // Create test runner
    const testRunner = new TestRunner();
    
    // Add all test suites
    ComponentTests.addTests(testRunner);
    ModuleTests.addTests(testRunner);
    PerformanceTests.addTests(testRunner);
    AccessibilityTests.addTests(testRunner);
    
    // Mock DOM if needed
    if (typeof window !== 'undefined') {
        TestUtils.mockDOM();
    }
    
    return testRunner.run();
}

// Export for global access
export { runFrontendTests, TestRunner, TestUtils };

// Global functions for testing
if (typeof window !== 'undefined') {
    window.runFrontendTests = runFrontendTests;
    window.testUtils = TestUtils;
    
    // Auto-run tests in development mode
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        window.addEventListener('DOMContentLoaded', () => {
            setTimeout(() => {
                console.log('🚀 Auto-running frontend tests in development mode...');
                runFrontendTests().then(results => {
                    if (results.failed > 0) {
                        console.warn(`⚠️  ${results.failed} test(s) failed. Check console for details.`);
                    }
                });
            }, 1000);
        });
    }
}