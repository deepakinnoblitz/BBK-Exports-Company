frappe.listview_settings['Lead'] = {

    onload(listview) {

        // Save original refresh method
        const original_refresh = listview.refresh;

        // Override refresh safely
        listview.refresh = function () {

            // Call default refresh
            original_refresh.call(listview);

            // Delay to ensure DOM is fully rendered
            setTimeout(() => {
                add_action_buttons(listview);
            }, 200);
        };

        // Inject inline CSS styles for icons
        inject_inline_css();
    }
};

function inject_inline_css() {
    const css = `
        .custom-actions .delete-icon {
            color: #e03131 !important; /* Strong CRM red */
        }
        .custom-actions .edit-icon {
            color: #495057 !important; /* Muted gray */
        }
        .custom-actions a:hover svg {
            color: #1c7ed6 !important; /* Blue hover effect */
        }
    `;

    let styleTag = document.createElement("style");
    styleTag.innerHTML = css;
    document.head.appendChild(styleTag);
}

function add_action_buttons(listview) {

    const can_edit = frappe.model.can_write("Employee");
    const can_delete = frappe.model.can_delete("Employee");


    listview.$result.find(".list-row-container, .list-row").each(function () {

        let row = $(this);

        let docname =
            row.attr("data-name") ||
            row.find(".list-row-check").attr("data-name") ||
            row.find("[data-name]").attr("data-name");

        if (!docname) return;

        if (row.find(".custom-actions").length > 0) return;

        let right_section = row.find(".level-right");

        if (!right_section.length) {
            console.warn("❌ level-right not found:", docname);
            return;
        }

        // Build icons dynamically based on permission
        let edit_icon = can_edit ? `
            <a class="edit-btn" data-name="${docname}" title="Edit" style="cursor:pointer; display:flex;">
                <svg class="icon icon-sm edit-icon" style="width:18px; height:25px; stroke: #2574b3;">
                    <use href="#icon-edit"></use>
                </svg>
            </a>` : "";

        let delete_icon = can_delete ? `
            <a class="delete-btn" data-name="${docname}" title="Delete" style="cursor:pointer; display:flex;">
                <svg class="icon icon-sm delete-icon" style="width:18px; height:25px; stroke: #ff0000;">
                    <use href="#icon-delete"></use>
                </svg>
            </a>` : "";

        // If user has no permissions → don't show icon section at all
        if (!can_edit && !can_delete) return;

        right_section.append(`
            <span class="custom-actions" 
                  style="margin-left: 10px; display: flex; gap: 20px; align-items: center; margin-right: 20px;">
                ${edit_icon}
                ${delete_icon}
            </span>
        `);

    });

    // EDIT ACTION
    listview.$result.on("click", ".edit-btn", function (e) {
        e.stopPropagation();
        let name = $(this).data("name");
        frappe.set_route("Form", "Employee", name);
    });

    // DELETE ACTION
    listview.$result.off("click", ".delete-btn");
    listview.$result.on("click", ".delete-btn", function (e) {
        e.stopPropagation();
        let name = $(this).data("name");
        frappe.confirm("Are you sure you want to delete this Employee?", () => {
            frappe.call({
                method: "frappe.client.delete",
                args: { doctype: "Employee", name },
                callback: () => {
                    frappe.show_alert("Employee Deleted");
                    listview.refresh();
                }
            });
        });
    });
}
