// Service Worker for Black Diamond Web Application
// Provides offline functionality, caching, and PWA features

const CACHE_NAME = 'black-diamond-v2.0.0';
const STATIC_CACHE_NAME = 'black-diamond-static-v2.0.0';
const DYNAMIC_CACHE_NAME = 'black-diamond-dynamic-v2.0.0';

// Files to cache immediately
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/css/modern-language-selector.css',
    '/static/css/unified.css',
    '/static/js/main.jsx',
    '/static/js/modules/utils.jsx',
    '/static/js/modules/theme.jsx',
    '/static/js/modules/animations.jsx',
    '/static/js/modules/language.jsx',
    '/static/js/modules/accessibility.jsx',
    'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap',
    'https://telegram.org/js/telegram-web-app.js',
    'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js'
];

// API endpoints to cache
const API_CACHE_PATTERNS = [
    /^\/api\//,
    /^\/set-language/
];

// Routes to cache (HTML pages)
const ROUTE_CACHE_PATTERNS = [
    /^\/$/,
    /^\/profile/,
    /^\/create-deal/,
    /^\/join-deal/,
    /^\/admin/
];

// Installation event
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker: Installing...');
    
    event.waitUntil(
        Promise.all([
            // Cache static assets
            caches.open(STATIC_CACHE_NAME).then((cache) => {
                console.log('📦 Service Worker: Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            }),
            // Skip waiting to activate immediately
            self.skipWaiting()
        ])
    );
});

// Activation event
self.addEventListener('activate', (event) => {
    console.log('🚀 Service Worker: Activating...');
    
    event.waitUntil(
        Promise.all([
            // Clean up old caches
            cleanOldCaches(),
            // Take control of all clients immediately
            self.clients.claim(),
            // Initialize offline page
            initializeOfflinePage()
        ])
    );
});

// Fetch event - handle network requests
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') {
        return;
    }
    
    // Handle different types of requests
    if (isApiRequest(request)) {
        event.respondWith(handleApiRequest(request));
    } else if (isRouteRequest(request)) {
        event.respondWith(handleRouteRequest(request));
    } else if (isStaticAsset(request)) {
        event.respondWith(handleStaticAsset(request));
    } else {
        event.respondWith(handleGenericRequest(request));
    }
});

// Handle API requests with network-first strategy
async function handleApiRequest(request) {
    try {
        // Try network first
        const networkResponse = await fetch(request);
        
        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(DYNAMIC_CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.log('🌐 Service Worker: Network failed, trying cache for API request');
        
        // Try cache
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline response for API requests
        return new Response(
            JSON.stringify({
                error: 'Network unavailable',
                message: 'This request is not available offline',
                offline: true
            }),
            {
                status: 503,
                statusText: 'Service Unavailable',
                headers: {
                    'Content-Type': 'application/json',
                    'Cache-Control': 'no-cache'
                }
            }
        );
    }
}

// Handle route requests (HTML pages) with cache-first strategy
async function handleRouteRequest(request) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        // Try network
        const networkResponse = await fetch(request);
        
        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(DYNAMIC_CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.log('🌐 Service Worker: Network failed, returning offline page');
        
        // Return offline page
        return getOfflinePage();
    }
}

// Handle static assets with cache-first strategy
async function handleStaticAsset(request) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const networkResponse = await fetch(request);
        
        // Cache static assets for offline use
        const cache = await caches.open(STATIC_CACHE_NAME);
        cache.put(request, networkResponse.clone());
        
        return networkResponse;
    } catch (error) {
        console.log('🌐 Service Worker: Failed to fetch static asset:', request.url);
        
        // For CSS and JS files, return a minimal fallback
        if (request.destination === 'style') {
            return new Response(
                '/* Service Worker: Offline styles not available */',
                { 
                    headers: { 'Content-Type': 'text/css' },
                    status: 200
                }
            );
        }
        
        if (request.destination === 'script') {
            return new Response(
                '// Service Worker: Offline script not available',
                { 
                    headers: { 'Content-Type': 'application/javascript' },
                    status: 200
                }
            );
        }
        
        // For other assets, return 404
        return new Response('Asset not available offline', { 
            status: 404,
            statusText: 'Not Found'
        });
    }
}

// Handle generic requests with network-first strategy
async function handleGenericRequest(request) {
    try {
        const networkResponse = await fetch(request);
        return networkResponse;
    } catch (error) {
        const cachedResponse = await caches.match(request);
        return cachedResponse || new Response('Resource not available offline', { 
            status: 404 
        });
    }
}

// Clean up old caches
async function cleanOldCaches() {
    const cacheNames = await caches.keys();
    const validCacheNames = [CACHE_NAME, STATIC_CACHE_NAME, DYNAMIC_CACHE_NAME];
    
    const deletePromises = cacheNames
        .filter(cacheName => !validCacheNames.includes(cacheName))
        .map(cacheName => {
            console.log('🗑️ Service Worker: Deleting old cache:', cacheName);
            return caches.delete(cacheName);
        });
    
    return Promise.all(deletePromises);
}

// Check if request is for API
function isApiRequest(request) {
    const url = new URL(request.url);
    return API_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname));
}

// Check if request is for a route (HTML page)
function isRouteRequest(request) {
    const url = new URL(request.url);
    return ROUTE_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname));
}

// Check if request is for static asset
function isStaticAsset(request) {
    const url = new URL(request.url);
    return url.pathname.startsWith('/static/') || 
           url.pathname.startsWith('/icons/') ||
           url.pathname.startsWith('/qr_codes/') ||
           url.hostname.includes('googleapis.com') ||
           url.hostname.includes('telegram.org') ||
           url.hostname.includes('cdnjs.cloudflare.com');
}

// Get offline page HTML
function getOfflinePage() {
    return new Response(`
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Offline - Black Diamond</title>
            <style>
                body {
                    font-family: 'Inter', sans-serif;
                    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    text-align: center;
                    padding: 2rem;
                }
                
                .offline-container {
                    max-width: 400px;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 16px;
                    padding: 2rem;
                    backdrop-filter: blur(20px);
                }
                
                .offline-icon {
                    width: 64px;
                    height: 64px;
                    margin: 0 auto 1rem;
                    background: linear-gradient(135deg, #ef4444, #dc2626);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                }
                
                h1 {
                    margin: 0 0 1rem 0;
                    font-size: 1.5rem;
                    font-weight: 600;
                }
                
                p {
                    margin: 0 0 1.5rem 0;
                    opacity: 0.8;
                    line-height: 1.5;
                }
                
                .retry-btn {
                    background: linear-gradient(135deg, #3b82f6, #2563eb);
                    color: white;
                    border: none;
                    padding: 0.75rem 1.5rem;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: 500;
                    transition: transform 0.2s;
                }
                
                .retry-btn:hover {
                    transform: translateY(-2px);
                }
            </style>
        </head>
        <body>
            <div class="offline-container">
                <div class="offline-icon">📱</div>
                <h1>You're Offline</h1>
                <p>It looks like you're not connected to the internet. Some features may not be available.</p>
                <button class="retry-btn" onclick="window.location.reload()">Try Again</button>
            </div>
            
            <script>
                // Auto-retry connection
                setTimeout(() => {
                    if (navigator.onLine) {
                        window.location.reload();
                    }
                }, 5000);
                
                // Listen for online event
                window.addEventListener('online', () => {
                    window.location.reload();
                });
            </script>
        </body>
        </html>
    `, {
        headers: { 
            'Content-Type': 'text/html',
            'Cache-Control': 'no-cache'
        }
    });
}

// Initialize offline page in cache
async function initializeOfflinePage() {
    const cache = await caches.open(DYNAMIC_CACHE_NAME);
    const offlinePage = getOfflinePage();
    await cache.put('/offline', offlinePage);
}

// Background sync for offline actions
self.addEventListener('sync', (event) => {
    if (event.tag === 'background-sync') {
        event.waitUntil(doBackgroundSync());
    }
});

// Perform background sync
async function doBackgroundSync() {
    console.log('🔄 Service Worker: Performing background sync');
    
    // Get pending actions from IndexedDB or localStorage
    const pendingActions = await getPendingActions();
    
    for (const action of pendingActions) {
        try {
            await fetch(action.url, {
                method: action.method,
                headers: action.headers,
                body: action.body
            });
            
            // Remove successful action
            await removePendingAction(action.id);
        } catch (error) {
            console.log('❌ Service Worker: Background sync failed for action:', action.id);
        }
    }
}

// Get pending actions from storage
async function getPendingActions() {
    try {
        const actions = await self.clients.matchAll();
        if (actions.length > 0) {
            const client = actions[0];
            const response = await client.postMessage({ type: 'GET_PENDING_ACTIONS' });
            return response || [];
        }
    } catch (error) {
        console.log('❌ Service Worker: Failed to get pending actions');
    }
    return [];
}

// Remove pending action
async function removePendingAction(actionId) {
    try {
        const actions = await self.clients.matchAll();
        if (actions.length > 0) {
            const client = actions[0];
            await client.postMessage({ 
                type: 'REMOVE_PENDING_ACTION', 
                actionId 
            });
        }
    } catch (error) {
        console.log('❌ Service Worker: Failed to remove pending action');
    }
}

// Push notifications
self.addEventListener('push', (event) => {
    console.log('📧 Service Worker: Push notification received');
    
    const options = {
        body: event.data ? event.data.text() : 'New notification',
        icon: '/static/icons/notification-icon.png',
        badge: '/static/icons/badge-icon.png',
        tag: 'black-diamond-notification',
        requireInteraction: true,
        actions: [
            {
                action: 'view',
                title: 'View',
                icon: '/static/icons/view-action.png'
            },
            {
                action: 'dismiss',
                title: 'Dismiss',
                icon: '/static/icons/dismiss-action.png'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification('Black Diamond', options)
    );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
    console.log('👆 Service Worker: Notification clicked');
    
    event.notification.close();
    
    if (event.action === 'view') {
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});

// Message handling from main thread
self.addEventListener('message', (event) => {
    const { type, data } = event.data;
    
    switch (type) {
        case 'SKIP_WAITING':
            self.skipWaiting();
            break;
            
        case 'CACHE_URLS':
            cacheUrls(data.urls);
            break;
            
        case 'CLEAR_CACHE':
            clearCache(data.cacheName);
            break;
            
        case 'GET_VERSION':
            event.ports[0].postMessage({ version: CACHE_NAME });
            break;
            
        default:
            console.log('📨 Service Worker: Unknown message type:', type);
    }
});

// Cache specific URLs
async function cacheUrls(urls) {
    const cache = await caches.open(DYNAMIC_CACHE_NAME);
    await cache.addAll(urls);
}

// Clear specific cache
async function clearCache(cacheName) {
    await caches.delete(cacheName);
}

// Periodic background sync (experimental)
self.addEventListener('periodicsync', (event) => {
    if (event.tag === 'content-sync') {
        event.waitUntil(syncContent());
    }
});

// Sync content in background
async function syncContent() {
    console.log('🔄 Service Worker: Periodic content sync');
    
    // Update critical resources
    const cache = await caches.open(STATIC_CACHE_NAME);
    await cache.addAll(STATIC_ASSETS);
    
    // Notify clients of update
    const clients = await self.clients.matchAll();
    clients.forEach(client => {
        client.postMessage({
            type: 'CONTENT_UPDATED',
            timestamp: Date.now()
        });
    });
}

console.log('✅ Service Worker: Script loaded and ready');