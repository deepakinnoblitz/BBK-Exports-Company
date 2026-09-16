frappe.after_ajax(() => {

    const logo = document.querySelector(".navbar-brand");
    if (logo) {
        logo.style.pointerEvents = "none"; // disable default behavior
    }

    setTimeout(() => {

        const parent = logo?.parentElement;
        if (!parent) {
            console.log("Navbar parent not found");
            return;
        }

        // Create custom menu button
        const btn = document.createElement("button");
        btn.id = "custom-mobile-menu";

        btn.innerHTML = `
            <svg width="18" height="18" stroke="#4A4A4A" fill="none"
                stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 5h14M3 10h14M3 15h14" />
            </svg>
        `;

        // Insert BEFORE the logo → left side
        parent.insertBefore(btn, logo);

        // ⭐ Sidebar toggle
        btn.onclick = () => {

            const sidebarContainer = document.querySelector(".body-sidebar-container");
            const overlay = document.querySelector(".overlay");

            if (!sidebarContainer || !overlay) {
                console.log("Sidebar container OR overlay not found");
                return;
            }

            sidebarContainer.classList.toggle("expanded");
            overlay.classList.toggle("show");
        };

    }, 800);
});
