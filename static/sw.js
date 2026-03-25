// Service Worker for PWA 离线支持
const CACHE_NAME = 'video-center-v1';
const OFFLINE_PAGE = '/offline.html';

// 需要缓存的资源
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/style.css',
    '/static/css/mobile.css',
    '/static/js/app.js',
    '/offline.html',
    '/static/manifest.json'
];

// 安装事件 - 缓存资源
self.addEventListener('install', (event) => {
    console.log('[SW] 安装 Service Worker');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[SW] 缓存资源');
                return cache.addAll(ASSETS_TO_CACHE);
            })
            .then(() => {
                console.log('[SW] 安装完成，跳过等待');
                return self.skipWaiting();
            })
    );
});

// 激活事件 - 清理旧缓存
self.addEventListener('activate', (event) => {
    console.log('[SW] 激活 Service Worker');
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name !== CACHE_NAME)
                        .map((name) => {
                            console.log('[SW] 删除旧缓存:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => {
                console.log('[SW] 激活完成，接管所有页面');
                return self.clients.claim();
            })
    );
});

// 获取事件 - 网络优先，失败时返回缓存
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // 只处理同源请求
    if (url.origin !== location.origin) {
        return;
    }
    
    // API 请求 - 网络优先
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(request)
                .catch(() => {
                    // API 失败时返回离线提示
                    return new Response(JSON.stringify({
                        error: '离线状态',
                        message: '当前无法访问网络，请检查连接'
                    }), {
                        status: 503,
                        headers: { 'Content-Type': 'application/json' }
                    });
                })
        );
        return;
    }
    
    // 视频文件 - 流式传输，不缓存
    if (url.pathname.startsWith('/videos/')) {
        event.respondWith(
            fetch(request)
                .catch(() => {
                    return new Response('视频文件需要在线访问', {
                        status: 503,
                        headers: { 'Content-Type': 'text/plain' }
                    });
                })
        );
        return;
    }
    
    // 图片和静态资源 - 缓存优先
    if (url.pathname.startsWith('/thumbnails/') || 
        url.pathname.startsWith('/previews/') ||
        url.pathname.startsWith('/covers/') ||
        url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request)
                .then((cachedResponse) => {
                    if (cachedResponse) {
                        // 同时更新缓存（后台）
                        fetch(request).then((response) => {
                            if (response.ok) {
                                caches.open(CACHE_NAME).then((cache) => {
                                    cache.put(request, response);
                                });
                            }
                        }).catch(() => {});
                        return cachedResponse;
                    }
                    return fetch(request);
                })
                .catch(() => {
                    // 图片失败返回占位图
                    if (url.pathname.startsWith('/thumbnails/') || 
                        url.pathname.startsWith('/previews/') ||
                        url.pathname.startsWith('/covers/')) {
                        return new Response(
                            `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">
                                <rect fill="#333" width="320" height="180"/>
                                <text fill="#666" x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="40">🎬</text>
                            </svg>`,
                            { headers: { 'Content-Type': 'image/svg+xml' } }
                        );
                    }
                    return fetch(request);
                })
        );
        return;
    }
    
    // 页面请求 - 网络优先，失败返回离线页
    event.respondWith(
        fetch(request)
            .then((response) => {
                // 成功时缓存页面
                const responseClone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(request, responseClone);
                });
                return response;
            })
            .catch(() => {
                return caches.match(OFFLINE_PAGE)
                    .then((cachedPage) => {
                        return cachedPage || caches.match('/');
                    });
            })
    );
});

// 后台同步（上传队列）
self.addEventListener('sync', (event) => {
    console.log('[SW] 后台同步:', event.tag);
    if (event.tag === 'upload-videos') {
        event.waitUntil(syncUploads());
    }
});

async function syncUploads() {
    // 处理待上传的视频队列
    const queue = await getUploadQueue();
    for (const item of queue) {
        try {
            await uploadVideo(item);
            await removeFromQueue(item.id);
        } catch (e) {
            console.log('[SW] 上传失败:', e);
        }
    }
}

// 推送通知
self.addEventListener('push', (event) => {
    console.log('[SW] 收到推送:', event);
    const data = event.data ? event.data.json() : {};
    const title = data.title || '视频中心';
    const options = {
        body: data.body || '新消息',
        icon: '/static/icons/icon-192x192.png',
        badge: '/static/icons/icon-72x72.png',
        vibrate: [100, 50, 100],
        data: data.url ? { url: data.url } : undefined,
        actions: [
            { action: 'open', title: '打开' },
            { action: 'dismiss', title: '关闭' }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// 通知点击处理
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    if (event.action === 'dismiss') {
        return;
    }
    
    const urlToOpen = event.notification.data?.url || '/';
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((windowClients) => {
                // 检查是否有已打开的窗口
                for (const client of windowClients) {
                    if (client.url === urlToOpen && 'focus' in client) {
                        return client.focus();
                    }
                }
                // 打开新窗口
                if (clients.openWindow) {
                    return clients.openWindow(urlToOpen);
                }
            })
    );
});

// 消息处理
self.addEventListener('message', (event) => {
    console.log('[SW] 收到消息:', event.data);
    
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CLEAR_CACHE') {
        event.waitUntil(
            caches.keys().then((names) => {
                return Promise.all(names.map((name) => caches.delete(name)));
            })
        );
    }
});
