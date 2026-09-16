// =====================================================================
// 0️⃣ SUPPRESS DEFAULT FRAPPE WARNING FOR MEETING + CALLS
// =====================================================================
let _original_msgprint = frappe.msgprint;

frappe.msgprint = function (opts) {
    let msg = "";

    if (typeof opts === "string") {
        msg = opts;
    } else if (opts && opts.message) {
        msg = opts.message;
    }

    // Suppress BOTH Meeting + Calls default delete warnings
    if (
        msg.includes("Cannot delete or cancel because Meeting") ||
        msg.includes("Cannot delete or cancel because Calls")
    ) {
        console.log("⚠️ Suppressed system delete warning");
        return false;
    }

    return _original_msgprint(opts);
};

// Register calendar behavior for Meeting
frappe.views.calendar["Meeting"] = {
    field_map: {
        start: "from",
        end: "to",
        id: "name",
        title: "title",
        color: "color"
    },
    get_events_method: "company.company.crm_api.get_meeting_events",

    options: {
        firstDay: 0,

        eventDidMount(info) {

            let deleteBtn = document.createElement("a");
            deleteBtn.classList.add("delete-btn");
            deleteBtn.setAttribute("title", "Delete");

            deleteBtn.style.cssText = `
                position: absolute;
                top: 2px;
                right: 4px;
                cursor: pointer;
                z-index: 10000;
                width: 20px;
                height: 20px;
                background: #ffffff;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                display: none;
            `;

            deleteBtn.innerHTML = `
                <svg class="icon icon-sm delete-icon"
                    style="width:12px; height:12px; stroke:#e03131; stroke-width:2;">
                    <use href="#icon-delete"></use>
                </svg>
            `;

            // ------------------------------
            // Hover → show popup
            // ------------------------------
            info.el.addEventListener("mouseenter", () => {

                if (window.__meet_dragging) return;

                deleteBtn.style.display = "flex";

                cleanup_meet_popup();   // 🔥 IMPORTANT

                fetch_meet_details(info.event.id, (meet) => {

                    const popup = create_meet_info_popup(meet);
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
                cleanup_meet_popup();   // 🔥 IMPORTANT
            });

            // ------------------------------
            // Delete click
            // ------------------------------
            deleteBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                cleanup_meet_popup();
                delete_meeting(info.event.id, info);
            };

            info.el.style.position = "relative";
            info.el.appendChild(deleteBtn);
        }
    }
};


// =============================================================
// 1️⃣ TRY DELETE MEETING FIRST
// =============================================================
function delete_meeting(meeting_id, info) {

    // First check if Meeting is linked with Event (Dynamic Link)
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Event",
            fields: ["name"],
            filters: {
                reference_doctype: "Meeting",
                reference_docname: meeting_id
            },
            limit: 1
        },

        callback: function (res) {

            // IF LINKED → Show delete both popup
            if (res.message && res.message.length > 0) {
                show_meeting_delete_options(meeting_id, info);
                return;
            }

            // NOT LINKED → ask confirmation to delete only Meeting
            confirm_delete_meeting_only(meeting_id, info);
        }
    });
}


// =============================================================
// 2️⃣ SHOW POPUP — MEETING LINKED WITH EVENT
// =============================================================
let meetingDeleteDialog = null;

function show_meeting_delete_options(meeting_id, info) {

    meetingDeleteDialog = new frappe.ui.Dialog({
        title: "Delete Options",
        indicator: "red",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "delete_html",
                options: `
                    <p>The Meeting <b>${meeting_id}</b> is linked with a Calendar Event.</p>
                    <p>Choose an action:</p>

                    <button class="btn btn-danger" id="delete_meeting_both_btn">
                        Delete Meeting + Event
                    </button>
                `
            }
        ]
    });

    meetingDeleteDialog.show();

    setTimeout(() => {
        meetingDeleteDialog.$wrapper.find('#delete_meeting_both_btn').on('click', () => {
            meetingDeleteDialog.hide();
            delete_meeting_and_event(meeting_id, info);
        });
    }, 50);
}



// =============================================================
// 3️⃣ DELETE EVENT → THEN DELETE MEETING
// =============================================================
function delete_meeting_and_event(meeting_id, info) {

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Event",
            fields: ["name"],
            filters: {
                reference_doctype: "Meeting",
                reference_docname: meeting_id
            },
            limit: 1
        },

        callback: function (res) {

            // 👉 If NOT linked → Show confirmation
            if (!res.message || res.message.length === 0) {
                confirm_delete_meeting_only(meeting_id, info);
                return;
            }

            let event_id = res.message[0].name;

            // Step 1 — Delete Event
            frappe.call({
                method: "frappe.client.delete",
                args: {
                    doctype: "Event",
                    name: event_id
                },

                callback: function () {

                    // Step 2 — Delete Meeting
                    frappe.call({
                        method: "frappe.client.delete",
                        args: {
                            doctype: "Meeting",
                            name: meeting_id
                        },

                        callback: function () {
                            frappe.show_alert("Meeting & Event deleted successfully!");
                            info.event.remove();
                        }
                    });
                }
            });
        }
    });
}




// =============================================================
// 4️⃣ MEETING NOT LINKED → ASK CONFIRMATION
// =============================================================
function confirm_delete_meeting_only(meeting_id, info) {

    let dialog = new frappe.ui.Dialog({
        title: "Confirm Delete",
        indicator: "orange",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "confirm_html",
                options: `
                    <p>This Meeting is <b>not linked</b> with any Calendar Event.</p>
                    <p>Do you want to delete only the Meeting?</p>

                    <button class="btn btn-danger" id="delete_meeting_only_btn">Yes, Delete Meeting</button>
                    <button class="btn btn-secondary" id="cancel_delete_btn">Cancel</button>
                `
            }
        ]
    });

    dialog.show();

    setTimeout(() => {

        dialog.$wrapper.find("#delete_meeting_only_btn").on("click", function () {
            dialog.hide();

            frappe.call({
                method: "frappe.client.delete",
                args: { doctype: "Meeting", name: meeting_id },

                callback: function () {
                    frappe.show_alert("Meeting deleted");
                    info.event.remove();
                }
            });
        });

        dialog.$wrapper.find("#cancel_delete_btn").on("click", function () {
            dialog.hide();
        });

    }, 50);
}

function create_meet_info_popup(meet) {
    const box = document.createElement("div");

    const status = (meet.outgoing_call_status || "Unknown").toLowerCase();

    box.className = "meet-info-popup";
    box.innerHTML = `
        <div class="popup-header">
            <svg class="meet-svg" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 2v2H6a2 2 0 0 0-2 2v14
                        a2 2 0 0 0 2 2h12
                        a2 2 0 0 0 2-2V6
                        a2 2 0 0 0-2-2h-2V2
                        h-2v2h-4V2H8zm10 18H6V9h12v11zm-6-8
                        v4l3 1"/>
            </svg>

            <span class="meet-title">${meet.title || "Meeting"}</span>
        </div>

        <div class="popup-body">

            <div class="popup-row">
                <span class="label">Start</span>
                <span class="value">
                    ${frappe.datetime.str_to_user(meet.from)}
                </span>
            </div>

            <div class="popup-row">
                <span class="label">End</span>
                <span class="value">
                    ${meet.to
            ? frappe.datetime.str_to_user(meet.to)
            : "—"}
                </span>
            </div>

            <div class="popup-row">
                <span class="label">Status</span>
                <span class="status-badge status-${status}">
                    ${meet.outgoing_call_status || "Unknown"}
                </span>
            </div>

            <div class="popup-row">
                <span class="label">Host</span>
                <span class="value">${meet.host || "—"}</span>
            </div>

        </div>
    `;

    return box;
}



function fetch_meet_details(meet_id, callback) {
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Meeting",
            name: meet_id
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

function cleanup_meet_popup() {
    document
        .querySelectorAll(".meet-info-popup")
        .forEach(p => p.remove());
}
