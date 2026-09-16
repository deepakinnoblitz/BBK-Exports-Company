// ====================================================
// HR Leave + WFH + Request Tracker
// ====================================================

// --- Leave Application ListView ---
frappe.listview_settings["Leave Application"] = {
	onload(listview) {
		listview.$result.on("click", ".list-row", function () {
			const docname = $(this).attr("data-name");
			if (!docname) return;
			mark_hr_item_as_read("Leave Application", docname, listview);
		});
	}
};

// --- WFH Attendance ListView ---
frappe.listview_settings["WFH Attendance"] = {
	onload(listview) {
		listview.$result.on("click", ".list-row", function () {
			const docname = $(this).attr("data-name");
			if (!docname) return;
			mark_hr_item_as_read("WFH Attendance", docname, listview);
		});
	}
};

// --- Request ListView (NEW) ---
frappe.listview_settings["Request"] = {
	onload(listview) {
		listview.$result.on("click", ".list-row", function () {
			const docname = $(this).attr("data-name");
			if (!docname) return;
			mark_hr_item_as_read("Request", docname, listview);
		});
	}
};

// ====================================================
// Shared helper functions
// ====================================================

// Mark the record as read
function mark_hr_item_as_read(doctype, name, listview = null) {
	frappe.call({
		method: "company.company.api.mark_hr_item_as_read",
		args: { doctype, name },
		callback: () => {
			update_hr_badges();
			if (listview) listview.refresh();
		}
	});
}

// ====================================================
// Update HR Badges in Sidebar
// ====================================================
function update_hr_badges() {
	frappe.call({
		method: "company.company.api.get_unread_count",
		callback: function (r) {
			const data = r.message || {};
			const leaveBadge = document.querySelector("#leave-badge");
			const attBadge = document.querySelector("#attendance-badge");
			const reqBadge = document.querySelector("#request-badge");

			// --- Leave Application badge ---
			if (leaveBadge) {
				const count = data["Leave Application"] || 0;
				leaveBadge.textContent = count;
				leaveBadge.style.display = count > 0 ? "inline-block" : "none";
			}

			// --- WFH Attendance badge ---
			if (attBadge) {
				const count = data["WFH Attendance"] || 0;
				attBadge.textContent = count;
				attBadge.style.display = count > 0 ? "inline-block" : "none";
			}

			// --- Request badge (NEW) ---
			if (reqBadge) {
				const count = data["Request"] || 0;
				reqBadge.textContent = count;
				reqBadge.style.display = count > 0 ? "inline-block" : "none";
			}
		},
		error: (err) => {
			console.error("🔴 Failed to fetch unread counts:", err);
		}
	});
}

// ====================================================
// Dynamically add badge elements to the sidebar
// ====================================================
function inject_hr_sidebar_badges() {
	// Locate sidebar menu items by their links
	const leaveItem = document.querySelector('a[href="/app/leave-application"]');
	const attItem = document.querySelector('a[href="/app/wfh-attendance"]');
	const reqItem = document.querySelector('a[href="/app/request"]');

	// --- Leave Application Badge ---
	if (leaveItem && !document.querySelector("#leave-badge")) {
		const badge = createBadge("leave-badge");
		leaveItem.appendChild(badge);
	}

	// --- WFH Attendance Badge ---
	if (attItem && !document.querySelector("#attendance-badge")) {
		const badge = createBadge("attendance-badge");
		attItem.appendChild(badge);
	}

	// --- Request Badge (NEW) ---
	if (reqItem && !document.querySelector("#request-badge")) {
		const badge = createBadge("request-badge");
		reqItem.appendChild(badge);
	}
}

// Helper: Create badge element
function createBadge(id) {
	const badge = document.createElement("span");
	badge.id = id;
	badge.className = "count-badge";
	badge.style.cssText = `
		background: linear-gradient(145deg, #e63946, #c9184a); /* soft gradient red */
		color: #ffffff;
		padding: 2px 8px;
		border-radius: 12px;
		font-size: 11px;
		font-weight: 600;
		margin-left: 6px;
		display: none;
		box-shadow: 0 2px 5px rgba(230, 57, 70, 0.4), inset 0 1px 2px rgba(255, 255, 255, 0.15);
		border: 1px solid rgba(255, 255, 255, 0.1);
		text-shadow: 0 1px 1px rgba(0, 0, 0, 0.3);
		transition: all 0.2s ease-in-out;
	`;
	return badge;
}

// ====================================================
// Form-View Integration (auto mark as read)
// ====================================================

frappe.ui.form.on("Leave Application", {
	onload(frm) {
		if (frappe.user_roles.includes("HR") && frm.doc.name) {
			mark_hr_item_as_read(frm.doc.doctype, frm.doc.name);
		}
	}
});

frappe.ui.form.on("WFH Attendance", {
	onload(frm) {
		if (frappe.user_roles.includes("HR") && frm.doc.name) {
			mark_hr_item_as_read(frm.doc.doctype, frm.doc.name);
		}
	}
});

frappe.ui.form.on("Request", {
	onload(frm) {
		if (frappe.user_roles.includes("HR") && frm.doc.name) {
			mark_hr_item_as_read(frm.doc.doctype, frm.doc.name);
		}
	}
});

// ====================================================
// Initial load + periodic refresh (Desk-safe)
// ====================================================
frappe.after_ajax(() => {
	inject_hr_sidebar_badges();
	update_hr_badges();

	// Auto refresh every 30 seconds
	setInterval(update_hr_badges, 30000);
});
