frappe.ui.form.on('*', {
    refresh(frm) {
        setTimeout(() => {
            (frm.fields || []).forEach(field => {
                if (field.df.fieldtype === "Phone") {
                    const $input = field.$input;
                    if (!$input || !$input.length) return;

                    // Wait for .selected-phone wrapper
                    const waitForFlag = setInterval(() => {
                        const $wrapper = field.$wrapper.find(".selected-phone");
                        if ($wrapper.length) {
                            clearInterval(waitForFlag);

                            const $isd = field.$wrapper.find(".country");
                            const icon = field.$wrapper.find("svg");

                            // ✅ Always reset existing flag before setting default
                            $wrapper.find("img").remove();

                            // ✅ Add India flag every time
                            const indiaFlag = frappe.utils.flag("in");
                            $wrapper.prepend(indiaFlag);

                            // ✅ Set +91 code
                            if ($isd.length) $isd.text("+91");

                            // ✅ Hide dropdown arrow
                            if (icon.length) icon.addClass("hide");

                            // ✅ Adjust padding
                            const len = $isd.text().length;
                            const diff = len - 2;
                            $input.css("padding-left", len > 2 ? 60 + diff * 7 : 60);

                            console.log(`📞 ${frm.doctype}.${field.df.fieldname} → 🇮🇳 +91 default set`);
                        }
                    }, 400);
                }
            });
        }, 600);
    }
});
