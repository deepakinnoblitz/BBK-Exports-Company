/**
 * Auto-refresh logic for Frappe/ERPNext
 * Detects 404 Asset errors and 400/403 CSRF/Session errors to trigger automatic reload.
 */

(function () {
    "use strict";

    // Optional: Only show alert if we haven't shown it in this session
    if (!sessionStorage.getItem("auto_refresh_alert_shown")) {
        sessionStorage.setItem("auto_refresh_alert_shown", "1");
    }

    // 1. Prevent infinite reload loops (max 1 reload every 30 seconds)
    const REFRESH_COOLDOWN = 30000;
    const lastReload = sessionStorage.getItem("last_auto_reload");
    const now = Date.now();

    if (lastReload && (now - parseInt(lastReload)) < REFRESH_COOLDOWN) {
        console.warn("[Auto-Refresh] Prevented infinite reload loop. Last reload was recently.");
        return;
    }

    function triggerReload(reason) {
        console.warn(`[Auto-Refresh] Triggering reload due to: ${reason}`);

        // Show a small notification to the user so they know WHY it's refreshing
        const msg = document.createElement("div");
        msg.style.cssText = "position:fixed; top:20px; left:50%; transform:translateX(-50%); background:rgba(0,0,0,0.8); color:white; padding:10px 20px; border-radius:5px; z-index:99999; font-family:sans-serif;";
        msg.innerText = "Error detected. Refreshing for you...";
        document.body.appendChild(msg);

        sessionStorage.setItem("last_auto_reload", Date.now().toString());

        setTimeout(() => {
            window.location.reload();
        }, 800);
    }

    // 2. Monitor Asset Loading Errors (404)
    window.addEventListener("error", function (e) {
        const target = e.target;
        if (target && (target.tagName === "SCRIPT" || target.tagName === "LINK")) {
            const url = target.src || target.href;
            if (url && (url.includes(".bundle.") || url.includes("/assets/"))) {
                triggerReload(`Asset load failure (404): ${url}`);
            }
        }
    }, true);

    // 3. Intercept XMLHttpRequest for API errors
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {
        this.addEventListener('load', function () {
            if (this.status === 400 || this.status === 403) {
                console.log(`[Auto-Refresh] Caught ${this.status} response from ${this.responseURL}`);
                const text = this.responseText || "";
                if (text.includes('CSRFTokenError') || text.includes('Invalid Request')) {
                    triggerReload(`Detected CSRF/Invalid Request in API response`);
                }
            }
        });
        return originalSend.apply(this, arguments);
    };

    // 4. MutationObserver to catch "Invalid Request" modals
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1) {
                    // Check for Frappe modal content
                    const text = node.innerText || "";
                    if (text.includes('Invalid Request') && (node.classList.contains('modal') || node.querySelector('.modal-content'))) {
                        triggerReload('Detected Invalid Request Modal in UI');
                    }
                }
            });
        });
    });

    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        window.addEventListener('DOMContentLoaded', () => {
            observer.observe(document.body, { childList: true, subtree: true });
        });
    }

    // 5. Check every 5 seconds for persistent "Invalid Request" on screen
    // Backup in case observer fails
    setInterval(() => {
        const modals = document.querySelectorAll('.modal.show, .modal.in');
        modals.forEach(m => {
            if (m.innerText.includes('Invalid Request')) {
                triggerReload('Persistent Invalid Request detected');
            }
        });
    }, 5000);

})();
