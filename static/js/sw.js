/**
 * StandardGPT Service Worker
 * Provides offline functionality and caching for better performance
 */

const CACHE_NAME = 'standardgpt-v1.0.0';
const STATIC_CACHE_NAME = 'standardgpt-static-v1.0.0';
const DYNAMIC_CACHE_NAME = 'standardgpt-dynamic-v1.0.0';

// Files to cache immediately
const STATIC_FILES = [
    '/',
    '/static/css/main.css',
    '/static/js/app.js',
    '/health'
];

// API endpoints to cache with network-first strategy
const API_ENDPOINTS = [
    '/api/query'
];

// Install event - cache static files
self.addEventListener('install', event => {
    console.log('Service Worker installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE_NAME)
            .then(cache => {
                console.log('Caching static files');
                return cache.addAll(STATIC_FILES);
            })
            .then(() => {
                console.log('Static files cached successfully');
                return self.skipWaiting();
            })
            .catch(error => {
                console.error('Failed to cache static files:', error);
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    console.log('Service Worker activating...');
    
    event.waitUntil(
        caches.keys()
            .then(cacheNames => {
                return Promise.all(
                    cacheNames.map(cacheName => {
                        if (cacheName !== STATIC_CACHE_NAME && 
                            cacheName !== DYNAMIC_CACHE_NAME &&
                            cacheName !== CACHE_NAME) {
                            console.log('Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => {
                console.log('Service Worker activated');
                return self.clients.claim();
            })
    );
});

// Fetch event - handle requests with appropriate caching strategy
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') {
        // For POST requests (like API calls), use network-first with cache fallback
        if (isApiRequest(request)) {
            event.respondWith(handleApiRequest(request));
        }
        return;
    }
    
    // Handle different types of requests
    if (isStaticFile(request)) {
        event.respondWith(handleStaticFile(request));
    } else if (isApiRequest(request)) {
        event.respondWith(handleApiRequest(request));
    } else if (isPageRequest(request)) {
        event.respondWith(handlePageRequest(request));
    } else {
        event.respondWith(handleOtherRequest(request));
    }
});

// Check if request is for a static file
function isStaticFile(request) {
    const url = new URL(request.url);
    return url.pathname.startsWith('/static/') || 
           url.pathname.endsWith('.css') ||
           url.pathname.endsWith('.js') ||
           url.pathname.endsWith('.png') ||
           url.pathname.endsWith('.jpg') ||
           url.pathname.endsWith('.svg') ||
           url.pathname.endsWith('.ico');
}

// Check if request is for an API endpoint
function isApiRequest(request) {
    const url = new URL(request.url);
    return url.pathname.startsWith('/api/') || 
           url.pathname === '/health';
}

// Check if request is for a page
function isPageRequest(request) {
    const url = new URL(request.url);
    return request.headers.get('accept')?.includes('text/html');
}

// Handle static files with cache-first strategy
async function handleStaticFile(request) {
    try {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        const networkResponse = await fetch(request);
        
        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(STATIC_CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('Static file request failed:', error);
        
        // Return cached version if available
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline fallback
        return new Response('Offline - Static resource not available', {
            status: 503,
            statusText: 'Service Unavailable'
        });
    }
}

// Handle API requests with network-first strategy
async function handleApiRequest(request) {
    try {
        // Always try network first for API requests
        const networkResponse = await fetch(request);
        
        // Cache successful GET responses
        if (networkResponse.ok && request.method === 'GET') {
            const cache = await caches.open(DYNAMIC_CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('API request failed:', error);
        
        // For GET requests, try to return cached version
        if (request.method === 'GET') {
            const cachedResponse = await caches.match(request);
            if (cachedResponse) {
                return cachedResponse;
            }
        }
        
        // Return offline response for API requests
        return new Response(JSON.stringify({
            error: 'Offline - API not available',
            offline: true,
            timestamp: new Date().toISOString()
        }), {
            status: 503,
            statusText: 'Service Unavailable',
            headers: {
                'Content-Type': 'application/json'
            }
        });
    }
}

// Handle page requests with network-first, cache fallback
async function handlePageRequest(request) {
    try {
        const networkResponse = await fetch(request);
        
        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(DYNAMIC_CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('Page request failed:', error);
        
        // Try to return cached version
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return cached home page as fallback
        const homeCache = await caches.match('/');
        if (homeCache) {
            return homeCache;
        }
        
        // Return offline page
        return new Response(`
            <!DOCTYPE html>
            <html lang="no">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>StandardGPT - Offline</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        text-align: center;
                    }
                    .offline-container {
                        max-width: 400px;
                        padding: 2rem;
                    }
                    .offline-icon {
                        font-size: 4rem;
                        margin-bottom: 1rem;
                    }
                    .offline-title {
                        font-size: 2rem;
                        margin-bottom: 1rem;
                    }
                    .offline-message {
                        font-size: 1.1rem;
                        opacity: 0.9;
                        line-height: 1.6;
                    }
                    .retry-button {
                        background: rgba(255,255,255,0.2);
                        border: 2px solid rgba(255,255,255,0.3);
                        color: white;
                        padding: 0.75rem 1.5rem;
                        border-radius: 8px;
                        font-size: 1rem;
                        cursor: pointer;
                        margin-top: 1.5rem;
                        transition: all 0.3s ease;
                    }
                    .retry-button:hover {
                        background: rgba(255,255,255,0.3);
                        border-color: rgba(255,255,255,0.5);
                    }
                </style>
            </head>
            <body>
                <div class="offline-container">
                    <div class="offline-icon">📡</div>
                    <h1 class="offline-title">Du er offline</h1>
                    <p class="offline-message">
                        StandardGPT er ikke tilgjengelig uten internettforbindelse. 
                        Sjekk tilkoblingen din og prøv igjen.
                    </p>
                    <button class="retry-button" onclick="window.location.reload()">
                        🔄 Prøv igjen
                    </button>
                </div>
            </body>
            </html>
        `, {
            status: 503,
            statusText: 'Service Unavailable',
            headers: {
                'Content-Type': 'text/html'
            }
        });
    }
}

// Handle other requests with basic network-first strategy
async function handleOtherRequest(request) {
    try {
        return await fetch(request);
    } catch (error) {
        console.error('Other request failed:', error);
        
        // Try cache
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        return new Response('Offline', {
            status: 503,
            statusText: 'Service Unavailable'
        });
    }
}

// Background sync for failed requests
self.addEventListener('sync', event => {
    if (event.tag === 'background-sync') {
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    console.log('Performing background sync...');
    // Implement background sync logic here if needed
}

// Push notifications (for future use)
self.addEventListener('push', event => {
    if (event.data) {
        const data = event.data.json();
        const options = {
            body: data.body,
            icon: '/static/img/icon-192x192.png',
            badge: '/static/img/badge-72x72.png',
            vibrate: [100, 50, 100],
            data: {
                dateOfArrival: Date.now(),
                primaryKey: data.primaryKey
            },
            actions: [
                {
                    action: 'explore',
                    title: 'Åpne StandardGPT',
                    icon: '/static/img/checkmark.png'
                },
                {
                    action: 'close',
                    title: 'Lukk',
                    icon: '/static/img/xmark.png'
                }
            ]
        };
        
        event.waitUntil(
            self.registration.showNotification(data.title, options)
        );
    }
});

// Handle notification clicks
self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'explore') {
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});

// Message handling for communication with main app
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

console.log('StandardGPT Service Worker loaded'); 