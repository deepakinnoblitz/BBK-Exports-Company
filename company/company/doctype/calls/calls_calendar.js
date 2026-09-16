// ===========================================================
// Override ONLY Calls delete message
// ===========================================================
const _original_msgprint = frappe.msgprint;

frappe.msgprint = function (opts) {
    let msg = "";
    let final_opts = opts;

    if (typeof opts === "string") {
        msg = opts;
    } else if (opts?.message) {
        msg = opts.message;
    }

    // Convert HTML → plain text (important)
    const plain = $("<div>").html(msg).text();

    // 🔥 Intercept ONLY Calls delete error
    if (plain.includes("Cannot delete or cancel because Calls")) {

        // Show your OWN message
        _original_msgprint({
            title: __("Action Blocked"),
            indicator: "orange",
            message: __(
                "This Call cannot be deleted because it has active reminders. " +
                "Please remove the reminders first."
            )
        });

        // 🚫 Stop original message
        return;
    }

    // ✅ Everything else works as normal
    return _original_msgprint(final_opts);
};


// =====================================================================
// 2️⃣  CALENDAR SETUP — Add Delete Icon on Events
// =====================================================================
frappe.views.calendar["Calls"] = {
    field_map: {
        start: "call_start_time",
        end: "call_end_time",
        id: "name",
        title: "title",
        color: "color"
    },
    get_events_method: "company.company.crm_api.get_call_events",

    options: {
        firstDay: 0,

        eventDidMount(info) {

            // ------------------------------
            // Delete button
            // ------------------------------
            const deleteBtn = document.createElement("a");
            deleteBtn.className = "delete-btn";
            deleteBtn.title = "Delete";

            deleteBtn.style.cssText = `
                position: absolute;
                top: 2px;
                right: 4px;
                cursor: pointer;
                z-index: 10;
                width: 20px;
                height: 20px;
                background: #ffffff;
                border-radius: 50%;
                display: none;
                align-items: center;
                justify-content: center;
            `;

            deleteBtn.innerHTML = `
                <svg class="icon icon-sm"
                    style="width:12px; height:12px; stroke:#e03131; stroke-width:2;">
                    <use href="#icon-delete"></use>
                </svg>
            `;

            info.el.style.position = "relative";
            info.el.appendChild(deleteBtn);

            // ------------------------------
            // Hover → show popup
            // ------------------------------
            info.el.addEventListener("mouseenter", () => {

                if (window.__call_dragging) return;

                deleteBtn.style.display = "flex";

                cleanup_call_popup();   // 🔥 IMPORTANT

                fetch_call_details(info.event.id, (call) => {

                    const popup = create_call_info_popup(call);
                    document.body.appendChild(popup);

                    position_popup(info.el, popup);
                    popup.classList.add("show");
                });
            });

            // ------------------------------
            // Mouse leave → cleanup
            // ------------------------------
            info.el.addEventListener("mouseleave", () => {
                deleteBtn.style.display = "none";
                cleanup_call_popup();   // 🔥 IMPORTANT
            });

            // ------------------------------
            // Delete click
            // ------------------------------
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                cleanup_call_popup();
                delete_call(info.event.id, info);
            };
        }


    }
};



// =====================================================================
// 3️⃣ FIRST TRY: CHECK IF CALL IS LINKED WITH EVENT
// =====================================================================
function delete_call(call_id, info) {

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Event",
            fields: ["name"],
            filters: {
                reference_doctype: "Calls",
                reference_docname: call_id
            },
            limit: 1
        },

        callback: function (res) {

            // 👉 NOT linked → ask confirmation
            if (!res.message || res.message.length === 0) {
                confirm_delete_call_only(call_id, info);
                return;
            }

            // 👉 Linked → show delete options popup
            show_delete_options(call_id, info);
        }
    });
}




// =====================================================================
// 4️⃣ POPUP: CALL IS LINKED WITH EVENT
// =====================================================================
let deleteDialog = null;

function show_delete_options(call_id, info) {

    deleteDialog = new frappe.ui.Dialog({
        title: "Delete Options",
        indicator: "red",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "delete_html",
                options: `
                    <p>The Call <b>${call_id}</b> is linked with a Calendar Event.</p>
                    <p>Choose an action:</p>
                    <button class="btn btn-danger" id="delete_both_btn">
                        Delete Call + Event
                    </button>
                `
            }
        ]
    });

    deleteDialog.show();

    // Handle delete click
    setTimeout(() => {
        deleteDialog.$wrapper.find('#delete_both_btn').on('click', () => {
            deleteDialog.hide();
            delete_both_records(call_id, info);
        });
    }, 50);
}




// =====================================================================
// 5️⃣ NOT LINKED → SHOW CONFIRM DELETE ONLY CALL
// =====================================================================
function confirm_delete_call_only(call_id, info) {

    let dialog = new frappe.ui.Dialog({
        title: "Confirm Delete",
        indicator: "orange",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "confirm_html",
                options: `
                    <p>This Call is <b>not linked</b> with any Calendar Event.</p>
                    <p>Do you want to delete only the Call?</p>

                    <button class="btn btn-danger" id="delete_call_only_btn">Yes, Delete Call</button>
                    <button class="btn btn-secondary" id="cancel_delete_btn">Cancel</button>
                `
            }
        ]
    });

    dialog.show();

    setTimeout(() => {

        dialog.$wrapper.find("#delete_call_only_btn").on("click", function () {
            dialog.hide();

            frappe.call({
                method: "frappe.client.delete",
                args: { doctype: "Calls", name: call_id },

                callback: function () {
                    frappe.show_alert("Call deleted");
                    info.event.remove();
                }
            });
        });

        dialog.$wrapper.find("#cancel_delete_btn").on("click", function () {
            dialog.hide();
        });

    }, 50);
}




// =====================================================================
// 6️⃣ DELETE EVENT → THEN DELETE CALL (LINKED CASE)
// =====================================================================
function delete_both_records(call_id, info) {

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Event",
            fields: ["name"],
            filters: {
                reference_doctype: "Calls",
                reference_docname: call_id
            },
            limit: 1
        },

        callback: function (res) {
            if (!res.message || res.message.length === 0) {
                frappe.msgprint("No linked Event found.");
                return;
            }

            let event_id = res.message[0].name;

            // Step 1 — Delete Event
            frappe.call({
                method: "frappe.client.delete",
                args: { doctype: "Event", name: event_id },

                callback: function () {

                    // Step 2 — Delete Call
                    frappe.call({
                        method: "frappe.client.delete",
                        args: { doctype: "Calls", name: call_id },

                        callback: function () {
                            frappe.show_alert("Call & Event deleted successfully!");
                            info.event.remove();
                        }
                    });
                }
            });
        }
    });
}

function create_call_info_popup(call) {
    const box = document.createElement("div");

    const status = (call.outgoing_call_status || "Unknown").toLowerCase();

    box.className = "call-info-popup";
    box.innerHTML = `
        <div class="popup-header">
            <svg class="call-svg" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2
                         19.79 19.79 0 0 1-8.63-3.07
                         19.5 19.5 0 0 1-6-6
                         19.79 19.79 0 0 1-3.07-8.67
                         A2 2 0 0 1 4.11 2h3
                         a2 2 0 0 1 2 1.72
                         12.44 12.44 0 0 0 .7 2.81
                         2 2 0 0 1-.45 2.11L8.09 9.91
                         a16 16 0 0 0 6 6l1.27-1.27
                         a2 2 0 0 1 2.11-.45
                         12.44 12.44 0 0 0 2.81.7
                         A2 2 0 0 1 22 16.92z" />
            </svg>

            <span class="call-title">${call.title || "Call"}</span>
        </div>

        <div class="popup-body">

            <div class="popup-row">
                <span class="label">Start</span>
                <span class="value">
                    ${frappe.datetime.str_to_user(call.call_start_time)}
                </span>
            </div>

            <div class="popup-row">
                <span class="label">End</span>
                <span class="value">
                    ${call.call_end_time
                        ? frappe.datetime.str_to_user(call.call_end_time)
                        : "—"}
                </span>
            </div>

            <div class="popup-row">
                <span class="label">Status</span>
                <span class="status-badge status-${status}">
                    ${call.outgoing_call_status || "Unknown"}
                </span>
            </div>

            <div class="popup-row">
                <span class="label">Owner</span>
                <span class="value">${call.owner || "—"}</span>
            </div>

        </div>
    `;

    return box;
}



function fetch_call_details(call_id, callback) {
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Calls",
            name: call_id
        },
        callback: function (res) {
            if (res.message) {
                callback(res.message);
            }
        }
    });
}

function position_popup(targetEl, popup) {

    const rect = targetEl.getBoundingClientRect();
    const popupRect = popup.getBoundingClientRect();
    const padding = 8;

    const space = {
        top: rect.top,
        bottom: window.innerHeight - rect.bottom,
        left: rect.left,
        right: window.innerWidth - rect.right
    };

    // Priority order
    let position = "right";

    if (space.right >= popupRect.width + padding) {
        position = "right";
    } else if (space.left >= popupRect.width + padding) {
        position = "left";
    } else if (space.bottom >= popupRect.height + padding) {
        position = "bottom";
    } else {
        position = "top";
    }

    let top, left;

    switch (position) {
        case "right":
            top = rect.top + rect.height / 2 - popupRect.height / 2;
            left = rect.right + padding;
            break;

        case "left":
            top = rect.top + rect.height / 2 - popupRect.height / 2;
            left = rect.left - popupRect.width - padding;
            break;

        case "bottom":
            top = rect.bottom + padding;
            left = rect.left + rect.width / 2 - popupRect.width / 2;
            break;

        case "top":
            top = rect.top - popupRect.height - padding;
            left = rect.left + rect.width / 2 - popupRect.width / 2;
            break;
    }

    // Clamp to viewport
    top = Math.max(8, Math.min(top, window.innerHeight - popupRect.height - 8));
    left = Math.max(8, Math.min(left, window.innerWidth - popupRect.width - 8));

    popup.style.top = `${top}px`;
    popup.style.left = `${left}px`;
}

function cleanup_call_popup() {
    document
        .querySelectorAll(".call-info-popup")
        .forEach(p => p.remove());
}
