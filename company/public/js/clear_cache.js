frappe.after_ajax(() => {
    const checkMenu = setInterval(() => {
        let userMenu = document.querySelector("#toolbar-user");

        if (userMenu) {
            clearInterval(checkMenu);

            // Avoid duplicates
            if (!document.getElementById("clear-browser-cache-btn")) {

                // Create button HTML
                const btn = document.createElement("button");
                btn.className = "btn-reset dropdown-item";
                btn.id = "clear-browser-cache-btn";
                btn.textContent = "Clear Browser Cache";

                // Insert after Reload button
                let reloadBtn = userMenu.querySelector("button[onclick*='clear_cache']");
                if (reloadBtn) {
                    reloadBtn.insertAdjacentElement("afterend", btn);
                } else {
                    // fallback, append at top
                    userMenu.prepend(btn);
                }

                // Attach handler
                btn.addEventListener("click", clearSiteCache);
            }
        }
    }, 200);
});


async function clearSiteCache() {
    try {
        // Delete Cache Storage
        if ("caches" in window) {
            const names = await caches.keys();
            await Promise.all(names.map(name => caches.delete(name)));
        }

        // Remove service workers
        if ("serviceWorker" in navigator) {
            const regs = await navigator.serviceWorker.getRegistrations();
            for (let reg of regs) {
                await reg.unregister();
            }
        }

        // Clear browser storage
        localStorage.clear();
        sessionStorage.clear();

        console.log("🧹 Clearing all caches...");

    // 1️⃣ Clear Service Workers
    if ("serviceWorker" in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations();
        for (const reg of regs) {
            console.log("❌ Unregistering Service Worker:", reg);
            await reg.unregister();
        }
    }

    // 2️⃣ Clear all Cache Storage
    if ("caches" in window) {
        const cacheNames = await caches.keys();
        for (const name of cacheNames) {
            console.log("🗑️ Deleting cache:", name);
            await caches.delete(name);
        }
    }

    // 3️⃣ Clear LocalStorage
    console.log("🗑️ Clearing localStorage");
    localStorage.clear();

    // 4️⃣ Clear SessionStorage
    console.log("🗑️ Clearing sessionStorage");
    sessionStorage.clear();

    // 5️⃣ Clear IndexedDB
    if (window.indexedDB) {
        let dbs = await indexedDB.databases();
        for (const db of dbs) {
            console.log("🗑️ Deleting IndexedDB:", db.name);
            indexedDB.deleteDatabase(db.name);
        }
    }

    // 6️⃣ Clear Cookies (best effort)
    console.log("🍪 Clearing cookies");
    document.cookie.split(";").forEach(cookie => {
        const name = cookie.split("=")[0].trim();
        document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    });

    // 7️⃣ Reload fresh version of the site
    console.log("♻ Reloading page completely...");
    location.reload(true);

        frappe.msgprint("Browser Cache Cleared. Reloading…");

        setTimeout(() => {
            window.location.reload(true);
        }, 700);

    } catch (error) {
        console.error("Cache clear failed:", error);
    }
}
