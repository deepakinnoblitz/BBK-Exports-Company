/**
 * Sidebar Active State Manager
 * Automatically highlights the correct sidebar item based on the current page URL
 */

// Run on initial page load
frappe.after_ajax(() => {
    setTimeout(() => {
        updateSidebarActiveState();
    }, 500);
});

// Listen to route changes for live updates
frappe.router.on('change', () => {
    setTimeout(() => {
        updateSidebarActiveState();
    }, 300);
});

// Also listen to frappe ready event
$(document).on('page-change', () => {
    setTimeout(() => {
        updateSidebarActiveState();
    }, 300);
});

function updateSidebarActiveState() {
    const currentUrl = window.location.href;
    const currentPath = window.location.pathname;

    // Remove active class from all sidebar items
    document.querySelectorAll('.standard-sidebar-item').forEach(item => {
        item.classList.remove('active-sidebar');
    });

    // Find all sidebar items and collect matches with scores
    const sidebarItems = document.querySelectorAll('.sidebar-item-container');
    const matches = [];

    sidebarItems.forEach(container => {
        const anchor = container.querySelector('.item-anchor');
        if (!anchor) return;

        const href = anchor.getAttribute('href');
        if (!href) return;

        const normalizedHref = normalizeUrl(href);
        const normalizedCurrent = normalizeUrl(currentUrl);
        const normalizedPath = normalizeUrl(currentPath);

        // Calculate match score (higher = better match)
        let matchScore = 0;

        // Exact match gets highest score
        if (normalizedHref === normalizedPath || normalizedHref === normalizedCurrent) {
            matchScore = 100;
        }
        // Path ends with href (for relative URLs)
        else if (normalizedPath.endsWith(normalizedHref) || normalizedCurrent.endsWith(normalizedHref)) {
            matchScore = 50;
        }
        // Contains match (lowest priority, must be exact segment)
        else if (isPathSegmentMatch(normalizedPath, normalizedHref)) {
            matchScore = 25;
        }

        if (matchScore > 0) {
            matches.push({
                container,
                score: matchScore,
                hrefLength: normalizedHref.length
            });
        }
    });

    // Sort by score (descending), then by href length (descending for specificity)
    matches.sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        return b.hrefLength - a.hrefLength;
    });

    // Apply active state only to the best match
    if (matches.length > 0) {
        const bestMatch = matches[0];
        const sidebarItem = bestMatch.container.querySelector('.standard-sidebar-item');
        if (sidebarItem) {
            sidebarItem.classList.add('active-sidebar');
        }

        // If this is a child item, expand its parent
        const parentContainer = bestMatch.container.closest('.sidebar-child-item');
        if (parentContainer) {
            expandParentContainer(parentContainer);
        }
        return;
    }

    // If no match found, try to match by page/report name
    matchByPageName();
}

function normalizeUrl(url) {
    // Remove protocol, domain, and query parameters for comparison
    try {
        const urlObj = new URL(url, window.location.origin);
        return decodeURIComponent(urlObj.pathname);
    } catch (e) {
        return url;
    }
}

function matchByPageName() {
    const currentPath = window.location.pathname;

    // Extract page/report name from URL
    const pathParts = currentPath.split('/');
    const pageName = pathParts[pathParts.length - 1];

    if (!pageName) return;

    // Try to find matching sidebar item by comparing item-name attribute
    const sidebarItems = document.querySelectorAll('.sidebar-item-container');

    sidebarItems.forEach(container => {
        const itemName = container.getAttribute('item-name');
        const itemTitle = container.getAttribute('item-title');

        // Check if item name matches (case-insensitive, handle spaces and encoding)
        if (itemName && normalizeString(itemName) === normalizeString(pageName)) {
            const sidebarItem = container.querySelector('.standard-sidebar-item');
            if (sidebarItem) {
                sidebarItem.classList.add('active-sidebar');

                // Expand parent if needed
                const parentContainer = container.closest('.sidebar-child-item');
                if (parentContainer) {
                    expandParentContainer(parentContainer);
                }
            }
        }
    });
}

function normalizeString(str) {
    return str.toLowerCase()
        .replace(/%20/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function isPathSegmentMatch(currentPath, hrefPath) {
    // Check if href path is an exact segment in the current path
    // e.g., /app/purchase should NOT match /app/purchase-collection
    const currentSegments = currentPath.split('/').filter(s => s);
    const hrefSegments = hrefPath.split('/').filter(s => s);

    // If href has fewer segments, check if all href segments match at the end of current
    if (hrefSegments.length <= currentSegments.length) {
        for (let i = 0; i < hrefSegments.length; i++) {
            if (currentSegments[i] !== hrefSegments[i]) {
                return false;
            }
        }
        return true;
    }
    return false;
}

function expandParentContainer(childContainer) {
    // Remove hidden class and set max-height
    if (childContainer.classList.contains('hidden')) {
        childContainer.classList.remove('hidden');
        childContainer.style.maxHeight = 'none';
    }

    // Find parent item and update arrow icon
    const parentSidebarContainer = childContainer.previousElementSibling;
    if (parentSidebarContainer && parentSidebarContainer.classList.contains('standard-sidebar-item')) {
        const arrow = parentSidebarContainer.querySelector('.drop-icon use');
        if (arrow) {
            arrow.setAttribute('href', '#es-line-up');
        }

        // Show the drop icon
        const dropIcon = parentSidebarContainer.querySelector('.drop-icon');
        if (dropIcon) {
            dropIcon.classList.remove('hidden');
            dropIcon.classList.add('show-in-edit-mode');
        }
    }
}
