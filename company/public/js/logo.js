$(document).ready(() => {
    try {
        const logged_user = frappe.boot.user.email;
        const is_admin = ["admin@example.com"].includes(logged_user);

        if (is_admin) return;

        // Hide App Switcher for non-admin users
        if (!document.querySelector("#hide-app-switcher-css")) {
            $(`<style id="hide-app-switcher-css">
                .app-switcher-dropdown {
                    display: none !important;
                }
            </style>`).appendTo("head");
        }

        // Function to inject logo
        const injectLogo = () => {
            const sidebarTop = document.querySelector(".body-sidebar-top");
            if (sidebarTop && !document.querySelector("#company-sidebar-logo")) {
                let logo = document.createElement("div");
                logo.id = "company-sidebar-logo";
                logo.innerHTML = `
                    <img src="/assets/Innoblitz%20Logo%20Full.png"
                    style="width:165px; margin: -45px auto; margin-left: 22px; display:block;">

                `;
                sidebarTop.prepend(logo);
            }
        };

        // Run immediately
        injectLogo();

        // Watch for changes (sidebar appearing later)
        const observer = new MutationObserver(() => {
            injectLogo();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

    } catch (e) {
        console.error("Error in logo.js:", e);
    }
});
