importScripts("https://www.gstatic.com/firebasejs/10.8.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.8.1/firebase-messaging-compat.js");

// ===============================
// ✅ FIREBASE INITIALIZATION
// ===============================
const firebaseConfig = {
    apiKey: "AIzaSyAp3cIYT8C4gRD_vliPK0PODHzyyyFYu4Y",
    authDomain: "company-erp-ef845.firebaseapp.com",
    projectId: "company-erp-ef845",
    storageBucket: "company-erp-ef845.firebasestorage.app",
    messagingSenderId: "695314443067",
    appId: "1:695314443067:web:07f8f463a526660a7e251e",
    measurementId: "G-ZDGX26G2EW",
};

firebase.initializeApp(firebaseConfig);
const messaging = firebase.messaging();

console.log("🔥 [Service Worker] Firebase Initialized & Background Handler Ready");

// ✅ Handle Background Notifications
messaging.onBackgroundMessage((payload) => {
    console.log("🔥 [Service Worker] Received background message:", payload);

    const data = payload.data || {};
    const notification = payload.notification || {};

    const notificationTitle = notification.title || data.title || data.notification_title || "New Notification";
    const notificationBody = notification.body || data.body || data.notification_body || "";

    const notificationOptions = {
        body: notificationBody,
        icon: "https://erp.innoblitz.in/assets/Innoblitz%20Logo%20Full.png", // Customize this icon path
        badge: "https://erp.innoblitz.in/assets/Innoblitz%20Logo%20Full.png", // Customize this badge path
        data: data, // Pass data for click handling
    };

    self.registration.showNotification(notificationTitle, notificationOptions);
});

// ===============================
// 🌐 PWA CACHING LOGIC
// ===============================

const CACHE_NAME = "erpnext-cache-v4";

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll([
                "/",
            ]).catch(err => {
                console.warn("⚠️ Failed to cache some assets:", err);
            });
        })
    );
    self.skipWaiting(); // Force activation
});

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
            );
        })
    );
    self.clients.claim(); // Take control of all clients immediately
});

self.addEventListener("fetch", event => {
    const url = new URL(event.request.url);

    // ── 1. Static assets: cache-first (fast, versioned filenames never stale)
    if (url.pathname.startsWith("/assets/")) {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
        return;
    }

    // ── 2. API / socket / firebase calls: always go to network, never cache
    if (
        url.pathname.startsWith("/api/") ||
        url.pathname.startsWith("/socket.io") ||
        url.hostname.includes("firestore") ||
        url.hostname.includes("gstatic")
    ) {
        return; // Let browser handle normally
    }

    // ── 3. Navigation requests (HTML pages): network-first
    //    On a normal F5 refresh the browser fetches a fresh copy.
    //    Only fall back to cache when truly offline.
    if (event.request.mode === "navigate") {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Update cache with fresh response
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // ── 4. Everything else: network-first, cache fallback
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});


// ✅ Notification Click Handler (Optional but recommended)
self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl = event.notification.data?.url || "/app";

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true })
            .then((clientList) => {
                for (const client of clientList) {
                    // If the tab already exists, focus it and navigate
                    if ("focus" in client) {
                        client.focus();
                        client.navigate(targetUrl);
                        return;
                    }
                }
                // No open tab → open new one
                return clients.openWindow(targetUrl);
            })
    );
});

