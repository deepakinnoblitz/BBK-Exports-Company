/******************************************************************
 * GLOBAL LISTVIEW OVERRIDE (WORKS FOR ALL DOCTYPES)
 ******************************************************************/

frappe.views.ListView = class CustomListView extends frappe.views.ListView {

    refresh() {
        super.refresh();

        // Run patch shortly after Frappe renders the list
        setTimeout(() => {
            add_global_action_buttons(this);
        }, 500);  // 50ms works best in Production
    }
};


/******************************************************************
 * INLINE CSS (Injected only once globally)
 ******************************************************************/
(function inject_global_css() {
    if (document.getElementById("global_list_css")) return;

    const css = `
        .custom-actions .delete-icon {
            color: #e03131 !important;
        }
        .custom-actions .edit-icon {
            color: #495057 !important;
        }
        .custom-actions a:hover svg {
            color: #1c7ed6 !important;
        }
    `;

    let styleTag = document.createElement("style");
    styleTag.id = "global_list_css";
    styleTag.innerHTML = css;
    document.head.appendChild(styleTag);
})();


/******************************************************************
 * MAIN GLOBAL ACTION BUTTON FUNCTION (PRODUCTION SAFE)
 ******************************************************************/
function add_global_action_buttons(listview) {

    const can_edit = frappe.model.can_write(listview.doctype);
    const can_delete = frappe.model.can_delete(listview.doctype);

    if (!can_edit && !can_delete) return;

    // Loop all rows
    listview.$result.find(".list-row-container").each(function () {

        let row_container = $(this);

        // ❗ ALWAYS REMOVE OLD CUSTOM ICONS — PRODUCTION SAFE
        row_container.find(".custom-actions").remove();

        // Identify row
        let row = row_container.find(".list-row");
        if (!row.length) row = row_container;

        let docname =
            row.attr("data-name") ||
            row.find("[data-name]").attr("data-name");

        if (!docname) return;

        // Right section exists?
        let right_section = row.find(".level-right");
        if (!right_section.length) return;

        // Build custom action HTML
        let action_html = `
            <span class="custom-actions"
                style="margin-left:10px; display:flex; gap:20px; align-items:center; margin-right:20px;">
                ${
                    can_edit
                        ? `
                <a class="edit-btn" data-name="${docname}" title="Edit" style="cursor:pointer;">
                    <svg class="icon icon-sm edit-icon" style="width:18px; height:25px; stroke:#2574b3;">
                        <use href="#icon-edit"></use>
                    </svg>
                </a>`
                        : ""
                }
                ${
                    can_delete
                        ? `
                <a class="delete-btn" data-name="${docname}" title="Delete" style="cursor:pointer;">
                    <svg class="icon icon-sm delete-icon" style="width:18px; height:25px; stroke:#ff0000;">
                        <use href="#icon-delete"></use>
                    </svg>
                </a>`
                        : ""
                }
            </span>
        `;

        // Add fresh icons every refresh (correct behavior)
        right_section.append(action_html);
    });

    /*****************************
     * CLICK HANDLERS (SAFE)
     *****************************/

    // Edit
    listview.$result.off("click", ".edit-btn");
    listview.$result.on("click", ".edit-btn", function (e) {
        e.stopPropagation();
        frappe.set_route("Form", listview.doctype, $(this).data("name"));
    });

    // Delete
    listview.$result.off("click", ".delete-btn");
    listview.$result.on("click", ".delete-btn", function (e) {
        e.stopPropagation();

        let name = $(this).data("name");
        frappe.confirm(`Delete ${listview.doctype} ${name}?`, () => {
            frappe.call({
                method: "frappe.client.delete",
                args: { doctype: listview.doctype, name },
                callback: () => {
                    frappe.show_alert(`${listview.doctype} deleted`);
                    listview.refresh();
                }
            });
        });
    });
}
