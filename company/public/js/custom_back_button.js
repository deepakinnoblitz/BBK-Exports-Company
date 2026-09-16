// === Universal "Back" Button (Left of Print, Persistent across navigation) ===

function add_global_back_button(frm) {
    if (!frm || !frm.page) return;

    // Prevent duplicates
    if (frm.page.wrapper.find('.btn-back-global').length) return;

    // Create Back button
    const backBtn = $(`
        <button class="btn btn-outline-secondary btn-sm btn-back-global" title="Go Back" style="margin-right: 8px; background-color: #f8f8f8 !important; border: 1px solid rgba(30, 47, 64, 0.3) !important; color: #1E293B !important; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);">
            ← Back
        </button>
    `);

    // Click action
    backBtn.on('click', function() {
        if (frappe.get_prev_route && frappe.get_prev_route()) {
            frappe.set_route(frappe.get_prev_route());
        } else {
            window.history.back();
        }
    });

    // Find Print button to insert before
    const $printBtn = frm.page.wrapper.find('.btn-print, .menu-btn-group .btn[data-original-title="Print"]');

    if ($printBtn.length) {
        $printBtn.closest('div').prepend(backBtn); // Insert left of Print
    } else {
        // Fallback: if Print not yet rendered, retry after small delay
        setTimeout(() => {
            const $retryPrintBtn = frm.page.wrapper.find('.btn-print');
            if ($retryPrintBtn.length) {
                $retryPrintBtn.closest('div').prepend(backBtn);
            } else {
                frm.page.wrapper.find('.page-actions').prepend(backBtn);
            }
        }, 300);
    }

    // For Quick Entry or Link dialogs
    if (frm.$wrapper && frm.$wrapper.closest('.modal-dialog').length) {
        const modalFooter = frm.$wrapper.closest('.modal-dialog').find('.modal-footer');
        if (!modalFooter.find('.btn-back-dialog').length) {
            const backDialog = $(`<button class="btn btn-secondary btn-back-dialog">← Back</button>`)
                .css({ marginRight: '8px' })
                .on('click', function() {
                    frm.$wrapper.closest('.modal-dialog').find('.btn-modal-close').trigger('click');
                });
            modalFooter.prepend(backDialog);
        }
    }

    frm.__back_button_added = true;
}

// --- Apply globally to all doctypes ---
frappe.ui.form.on('*', {
    refresh(frm) {
        frappe.after_ajax(() => {
            setTimeout(() => add_global_back_button(frm), 250);
        });
    }
});

// --- Re-add after route change ---
frappe.router.on('change', () => {
    setTimeout(() => {
        const cur_frm = frappe?.ui?.form?.get_cur_frm?.();
        if (cur_frm) add_global_back_button(cur_frm);
    }, 300);
});

// --- Re-add after browser back/forward navigation ---
window.addEventListener('popstate', () => {
    setTimeout(() => {
        const cur_frm = frappe?.ui?.form?.get_cur_frm?.();
        if (cur_frm) add_global_back_button(cur_frm);
    }, 400);
});
