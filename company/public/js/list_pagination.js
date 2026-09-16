/******************************************************************
 * GLOBAL LISTVIEW PAGINATION OVERRIDE
 * - Custom Pagination: 10, 20, 50 rows per page
 * - Numerical Pagination: 1 2 3 ...
 ******************************************************************/

(function () {
    const BaseListView = frappe.views.ListView;

    frappe.views.ListView = class PaginationListView extends BaseListView {

        setup_defaults() {
            const promise = super.setup_defaults();
            this.page_length = 20;
            this.selected_page_count = 20;
            this.count_upper_bound = 10000;
            return promise;
        }

        setup_paging_area() {
            const me = this;
            const paging_values = [20, 50, 100];

            // Primary Paging Area (Sticky Bottom)
            this.$paging_area = $(
                `<div class="list-paging-area level" style="
                    padding: 14px 25px; 
                    border-top: 1px solid rgba(0,0,0,0.06); 
                    background: rgba(255, 255, 255, 0.85); 
                    backdrop-filter: blur(15px); 
                    -webkit-backdrop-filter: blur(15px); 
                    position: sticky; 
                    bottom: 0; 
                    z-index: 100; 
                    box-shadow: 0 -8px 24px rgba(0,0,0,0.05);
                ">
                    <div class="level-left">
                        <div class="rows-segmented-control" style="
                            display: flex;
                            background: rgb(83 83 83 / 8%);
                            padding: 4px;
                            border-radius: 30px;
                            gap: 2px;
                            border: 1px solid rgb(0 0 0 / 10%);
                        ">
                            <div class="rows-label" style="padding: 0 12px 0 8px; font-weight: 800; font-size: 10px; color: #2b3e51; display: flex; align-items: center; text-transform: uppercase; letter-spacing: 1px;">Rows</div>
                            ${paging_values.map(v => `
                                <div class="rows-segment-item ${v === this.page_length ? 'active' : ''}" data-value="${v}">
                                    ${v}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="level-right">
                        <div class="pagination-container" style="display:flex; gap: 8px; align-items:center;">
                        </div>
                    </div>
                </div>`
            );

            // Sticky Horizontal Proxy Scrollbar
            this.$proxy_scrollbar = $(
                `<div class="sticky-proxy-scrollbar" style="
                    position: sticky;
                    bottom: 60px; /* Just above paging area */
                    height: 12px;
                    width: 100%;
                    overflow-x: auto;
                    overflow-y: hidden;
                    z-index: 99;
                    background: transparent;
                    display: none;
                ">
                    <div class="proxy-scrollbar-content" style="height: 1px;"></div>
                </div>`
            );

            this.$frappe_list.append(this.$proxy_scrollbar);
            this.$frappe_list.append(this.$paging_area);

            // Sync Logic: Proxy -> Results
            this.$proxy_scrollbar.on('scroll', function () {
                if (me.is_syncing) return;
                me.is_syncing = true;
                me.$result.parent().scrollLeft($(this).scrollLeft());
                setTimeout(() => me.is_syncing = false, 10);
            });

            // Sync Logic: Results -> Proxy
            this.$result.parent().on('scroll', function () {
                if (me.is_syncing) return;
                me.is_syncing = true;
                me.$proxy_scrollbar.scrollLeft($(this).scrollLeft());
                setTimeout(() => me.is_syncing = false, 10);
            });

            this.$paging_area.on("click", ".rows-segment-item", function () {
                const val = parseInt($(this).data('value'));
                if (val === me.page_length) return;

                me.start = 0;
                me.page_length = val;
                me.selected_page_count = val;
                me.refresh();
            });

            // Function to update proxy scrollbar dimensions
            this.update_proxy_scrollbar = () => {
                const $container = me.$result.parent();
                const scrollWidth = $container[0].scrollWidth;
                const clientWidth = $container[0].clientWidth;

                if (scrollWidth > clientWidth) {
                    me.$proxy_scrollbar.show().find('.proxy-scrollbar-content').css('width', scrollWidth + 'px');
                } else {
                    me.$proxy_scrollbar.hide();
                }
            };
        }

        // Fix for double scrollbar and ensure table stretches to end of screen
        set_result_height() {
            const me = this;
            const $result = this.$result;
            const $container = $result.parent(".result-container");

            // Overriding completely to control the viewport filling
            const apply_min_height = () => {
                if (!$result.length) return;

                const offset = $result.offset().top;
                const window_height = $(window).height();
                // We want the result + paging area to fill the screen
                // Paging area height is fixed at roughly 60px in setup_paging_area
                const min_height = window_height - offset - 80; // 80px buffer for padding and paging-area

                if (min_height > 100) {
                    $container.css({
                        "overflow-y": "visible",
                        "height": "auto",
                        "min-height": min_height + "px"
                    });
                    $result.css({
                        "height": "auto",
                        "min-height": min_height + "px"
                    });
                }
            };

            // Apply immediately and also after a short delay to account for Frappe's late rendering
            apply_min_height();
            setTimeout(apply_min_height, 200);

            // Also re-apply on window resize
            $(window).off("resize.list_height").on("resize.list_height", apply_min_height);
        }

        toggle_result_area() {
            super.toggle_result_area();
            this.$paging_area.find(".btn-more").hide();

            if (this.data.length > 0) {
                this.$paging_area.show();
                this.render_pagination();
            }
        }

        prepare_data(r) {
            let data = r.message || {};
            if (data.user_info) {
                Object.assign(frappe.boot.user_info, data.user_info);
                delete data.user_info;
            }
            data = !Array.isArray(data) ? frappe.utils.dict(data.keys, data.values) : data;
            this.data = data.uniqBy((d) => d.name);
        }

        reset_defaults() {
            // Keep state
        }

        render_count() {
            const me = this;
            super.render_count();
            this.get_count_str().then(() => {
                me.render_pagination();
            });
        }

        render_pagination() {
            const me = this;
            const total_count = this.total_count || this.data.length || 0;
            const page_length = this.selected_page_count || 10;
            const total_pages = Math.ceil(total_count / page_length);
            const current_page = Math.floor(this.start / page_length) + 1;

            const $container = this.$paging_area.find(".pagination-container");
            $container.empty();

            if (total_count === 0) {
                this.$paging_area.hide();
                return;
            }

            this.$paging_area.show();

            // Update active segment
            this.$paging_area.find('.rows-segment-item').removeClass('active');
            this.$paging_area.find(`.rows-segment-item[data-value="${page_length}"]`).addClass('active');

            if (total_pages <= 1) return;

            // Previous
            const $prev = $(`
                <button class="btn-pagination prev" ${current_page === 1 ? 'disabled' : ''}>
                    <svg class="icon icon-xs"><use href="#icon-left"></use></svg>
                </button>
            `);
            $prev.on("click", () => {
                if (current_page > 1) {
                    me.start = (current_page - 2) * page_length;
                    me.page_length = page_length;
                    me.refresh();
                }
            });
            $container.append($prev);

            const add_page = (p) => {
                const is_active = (p === current_page);
                const $btn = $(`
                    <button class="btn-pagination page-num ${is_active ? 'active' : ''}">
                        ${p}
                    </button>
                `);
                if (!is_active) {
                    $btn.on("click", function () {
                        me.start = (p - 1) * page_length;
                        me.page_length = page_length;
                        me.refresh();
                    });
                }
                $container.append($btn);
            };

            const add_gap = () => {
                $container.append(`<span class="pagination-gap">...</span>`);
            };

            let start_page = Math.max(1, current_page - 2);
            let end_page = Math.min(total_pages, current_page + 2);

            if (start_page > 1) {
                add_page(1);
                if (start_page > 2) add_gap();
            }

            for (let i = start_page; i <= end_page; i++) {
                add_page(i);
            }

            if (end_page < total_pages) {
                if (end_page < total_pages - 1) add_gap();
                add_page(total_pages);
            }

            // Next
            const $next = $(`
                <button class="btn-pagination next" ${current_page === total_pages ? 'disabled' : ''}>
                    <svg class="icon icon-xs"><use href="#icon-right"></use></svg>
                </button>
            `);
            $next.on("click", () => {
                if (current_page < total_pages) {
                    me.start = current_page * page_length;
                    me.page_length = page_length;
                    me.refresh();
                }
            });
            $container.append($next);
        }
    };

    // Inject CSS
    const css = `
        .btn-pagination {
            border: 1px solid rgba(0,0,0,0.6);
            background: #fff;
            color: #444;
            min-width: 34px;
            height: 34px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            padding: 0 8px;
        }

        .btn-pagination:hover:not(:disabled) {
            background: #f8f9fa;
            border-color: rgba(0,0,0,0.12);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.06);
            color: #1e2f40;
        }

        .btn-pagination.active {
            background: linear-gradient(135deg, #1e2f40 0%, #34495e 100%) !important;
            color: #fff !important;
            border: none !important;
            box-shadow: 0 4px 12px rgba(30, 47, 64, 0.25) !important;
            transform: scale(1.05);
        }

        .btn-pagination:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            background: #fdfdfd;
        }

        .btn-pagination svg {
            width: 14px;
            height: 14px;
            stroke-width: 2.5;
        }

        .pagination-gap {
            color: #adb5bd;
            font-weight: 700;
            padding: 0 4px;
            font-size: 14px;
            letter-spacing: 1px;
        }

        .paging-dropdown:hover {
            border-color: rgba(0,0,0,0.1) !important;
            box-shadow: 0 4px 10px rgba(0,0,0,0.08) !important;
        }

        .list-row-head {
            border-top-right-radius: 8px !important;
            border-bottom-right-radius: 8px !important;
        }

        .rows-segment-item {
            padding: 6px 16px;
            font-size: 11px;
            font-weight: 700;
            color: #495057;
            cursor: pointer;
            border-radius: 20px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
            background: transparent;
        }

        .rows-segment-item:hover:not(.active) {
            color: #1e2f40;
            background: rgba(255, 255, 255, 0.45) !important;
        }

        .rows-segment-item.active {
            background: #ffffff !important;
            color: #1e2f40 !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
        }

        /* Sticky Proxy Scrollbar Styling */
        .sticky-proxy-scrollbar::-webkit-scrollbar {
            height: 8px;
        }
        .sticky-proxy-scrollbar::-webkit-scrollbar-track {
            background: rgba(0,0,0,0.02);
            border-radius: 10px;
        }
        .sticky-proxy-scrollbar::-webkit-scrollbar-thumb {
            background: rgba(0,0,0,0.15);
            border-radius: 10px;
            border: 2px solid transparent;
            background-clip: content-box;
        }
        .sticky-proxy-scrollbar::-webkit-scrollbar-thumb:hover {
            background: rgba(0,0,0,0.25);
            background-clip: content-box;
        }
    `;
    if (!document.getElementById("list_pagination_css")) {
        let styleTag = document.createElement("style");
        styleTag.id = "list_pagination_css";
        styleTag.innerHTML = css;
        document.head.appendChild(styleTag);
    }
})();
