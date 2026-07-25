// State management
let rawData = [];
let filteredData = [];
let currentPage = 1;
let pageSize = 25;
let sortColumn = 'name';
let sortReverse = false;
let isSearching = false;
let pollTimer = null;

// Initialize app on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    setupTabNavigation();
    fetchStats();
    fetchResults();
    startStatusPolling();
});

// Tab Navigation logic
function setupTabNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn, .bottom-nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            switchToTab(targetTab);
        });
    });
}

function switchToTab(tabId) {
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.querySelectorAll('.nav-btn, .bottom-nav-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-tab') === tabId) {
            btn.classList.add('active');
        }
    });
    const target = document.getElementById(tabId);
    if (target) {
        target.classList.add('active');
    }
}

// Fetch stats for dashboard
async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('dash-val-total').innerText = data.total_businesses || 0;
            document.getElementById('dash-val-rating').innerText = (data.avg_rating || 0).toFixed(2);
            document.getElementById('dash-val-websites').innerText = data.with_website || 0;
            document.getElementById('dash-val-phones').innerText = data.with_phone || 0;
            if (data.export_folder) {
                document.getElementById('dash-export-folder').innerText = data.export_folder;
            }
        }
    } catch (e) {
        console.error('Failed to fetch stats:', e);
    }
}

// Fetch business search results
async function fetchResults() {
    try {
        const res = await fetch('/api/results');
        if (res.ok) {
            const data = await res.json();
            rawData = data.businesses || [];
            renderTable();
            fetchStats();
        }
    } catch (e) {
        console.error('Failed to fetch results:', e);
    }
}

// Toggle Light / Dark mode
function toggleTheme() {
    const body = document.body;
    const btn = document.getElementById('theme-toggle');
    if (body.classList.contains('light-theme')) {
        body.classList.remove('light-theme');
        body.classList.add('dark-theme');
        if (btn) btn.innerText = '🌙 Mode';
    } else {
        body.classList.remove('dark-theme');
        body.classList.add('light-theme');
        if (btn) btn.innerText = '☀️ Mode';
    }
}

// Render data table with sorting, filtering, and pagination
function renderTable() {
    const searchVal = (document.getElementById('table-filter-search')?.value || '').toLowerCase().trim();
    const locationVal = (document.getElementById('filter-location')?.value || '').toLowerCase().trim();
    const statusVal = document.getElementById('filter-status')?.value || '';
    const hasPhoneOnly = document.getElementById('filter-has-phone')?.checked || false;
    const hasWebOnly = document.getElementById('filter-has-website')?.checked || false;

    // Filter rows
    filteredData = rawData.filter(biz => {
        if (searchVal) {
            const matchName = (biz.name || '').toLowerCase().includes(searchVal);
            const matchCity = (biz.city || '').toLowerCase().includes(searchVal);
            const matchType = (biz.type || '').toLowerCase().includes(searchVal);
            if (!matchName && !matchCity && !matchType) return false;
        }

        if (locationVal) {
            const cityStr = (biz.city || '').toLowerCase();
            const stateStr = (biz.state || '').toLowerCase();
            const addrStr = (biz.full_address || '').toLowerCase();
            if (!cityStr.includes(locationVal) && !stateStr.includes(locationVal) && !addrStr.includes(locationVal)) return false;
        }

        if (statusVal) {
            const bizStatus = (biz.status || 'Active').toLowerCase();
            if (!bizStatus.includes(statusVal.toLowerCase())) return false;
        }

        if (hasPhoneOnly && !biz.phone_number) return false;
        if (hasWebOnly && !biz.website) return false;

        return true;
    });

    // Sort rows
    filteredData.sort((a, b) => {
        let valA = a[sortColumn] || '';
        let valB = b[sortColumn] || '';
        if (typeof valA === 'string') valA = valA.toLowerCase();
        if (typeof valB === 'string') valB = valB.toLowerCase();

        if (valA < valB) return sortReverse ? 1 : -1;
        if (valA > valB) return sortReverse ? -1 : 1;
        return 0;
    });

    // Pagination calculations
    const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * pageSize;
    const pageRows = filteredData.slice(startIdx, startIdx + pageSize);

    const tbody = document.getElementById('table-body');
    if (!tbody) return;

    if (pageRows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No business records match criteria.</td></tr>';
    } else {
        tbody.innerHTML = pageRows.map((biz, idx) => {
            const rowNum = startIdx + idx + 1;
            const rating = biz.rating ? `<span class="rating-badge">★ ${biz.rating.toFixed(1)}</span>` : 'N/A';
            const phone = biz.phone_number ? `<a href="tel:${biz.phone_number}">${biz.phone_number}</a>` : '<span class="text-muted">N/A</span>';
            const web = biz.website ? `<a href="${biz.website}" target="_blank">Link ↗</a>` : '<span class="text-muted">N/A</span>';
            
            return `
                <tr>
                    <td>${rowNum}</td>
                    <td><strong>${escapeHtml(biz.name || 'Unknown')}</strong></td>
                    <td>${escapeHtml(biz.type || 'General')}</td>
                    <td><span class="status-badge">${escapeHtml(biz.status || 'Active')}</span></td>
                    <td>${phone}</td>
                    <td>${web}</td>
                    <td>${rating}</td>
                    <td>${biz.total_reviews || 0}</td>
                    <td>${escapeHtml(biz.city || biz.state || biz.full_address || 'N/A')}</td>
                </tr>
            `;
        }).join('');
    }

    // Update pagination controls
    document.getElementById('table-count-info').innerText = `Showing ${pageRows.length} of ${filteredData.length} businesses`;
    document.getElementById('page-num-display').innerText = `Page ${currentPage} of ${totalPages}`;
    document.getElementById('btn-prev-page').disabled = (currentPage <= 1);
    document.getElementById('btn-next-page').disabled = (currentPage >= totalPages);
}

function changePage(delta) {
    currentPage += delta;
    renderTable();
}

function sortTable(col) {
    if (sortColumn === col) {
        sortReverse = !sortReverse;
    } else {
        sortColumn = col;
        sortReverse = false;
    }
    renderTable();
}

// Start bulk search
async function handleStartSearch(e) {
    e.preventDefault();
    const keywordsStr = document.getElementById('input-keywords').value;
    const citiesStr = document.getElementById('input-cities').value;
    const radiusElem = document.getElementById('input-radius');
    const radius = radiusElem ? parseInt(radiusElem.value) : 2000;

    const keywords = keywordsStr.split(',').map(s => s.trim()).filter(Boolean);
    const cities = citiesStr.split(',').map(s => s.trim()).filter(Boolean);

    if (keywords.length === 0 || cities.length === 0) {
        showToast('Please enter at least one keyword and city.');
        return;
    }

    try {
        const res = await fetch('/api/search/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keywords, cities, radius })
        });

        if (res.ok) {
            showToast('Search started successfully!');
            document.getElementById('btn-start-search').classList.add('hidden');
            document.getElementById('btn-stop-search').classList.remove('hidden');
            document.getElementById('progress-card').classList.remove('hidden');
            isSearching = true;
        } else {
            const err = await res.json();
            showToast(err.error || 'Failed to start search');
        }
    } catch (err) {
        showToast('Server connection error.');
    }
}

// Stop search
async function handleStopSearch() {
    try {
        await fetch('/api/search/stop', { method: 'POST' });
        showToast('Search engine stopped.');
        document.getElementById('btn-start-search').classList.remove('hidden');
        document.getElementById('btn-stop-search').classList.add('hidden');
        isSearching = false;
    } catch (e) {
        console.error(e);
    }
}

// Poll status
function startStatusPolling() {
    setInterval(async () => {
        try {
            const res = await fetch('/api/search/status');
            if (res.ok) {
                const data = await res.json();
                
                // Update header status
                const globalText = document.getElementById('global-status-text');
                if (globalText) globalText.innerText = data.status || 'Ready';

                if (data.is_running) {
                    isSearching = true;
                    document.getElementById('btn-start-search').classList.add('hidden');
                    document.getElementById('btn-stop-search').classList.remove('hidden');
                    document.getElementById('progress-card').classList.remove('hidden');

                    const pct = Math.min(100, Math.round((data.progress || 0) * 100));
                    document.getElementById('progress-fill').style.width = pct + '%';
                    document.getElementById('progress-status-txt').innerText = `Status: ${data.message || 'Searching...'}`;
                    document.getElementById('progress-stats-txt').innerText = `Grid: ${data.grid_processed || 0}/${data.grid_total || 0} | Found: ${data.found || 0}`;

                    fetchResults();
                } else {
                    if (isSearching) {
                        isSearching = false;
                        document.getElementById('btn-start-search').classList.remove('hidden');
                        document.getElementById('btn-stop-search').classList.add('hidden');
                        showToast('Search completed!');
                    }
                    if (data.found > 0 || rawData.length > 0) {
                        fetchResults();
                    }
                }
            }
        } catch (e) {
            console.error('Polling error:', e);
        }
    }, 1500);
}

// Export ONLY filtered data (CSV and JSON)
function exportData(format) {
    if (!filteredData || filteredData.length === 0) {
        showToast('No matching filtered business records to export.');
        return;
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    
    if (format === 'csv') {
        const headers = ["S.No", "Business Name", "Type", "Status", "Phone", "Website", "Rating", "Reviews", "Address", "City", "State", "Country", "Latitude", "Longitude"];
        const rows = filteredData.map((b, idx) => [
            idx + 1,
            `"${(b.name || '').replace(/"/g, '""')}"`,
            `"${(b.type || '').replace(/"/g, '""')}"`,
            `"${(b.status || 'Active').replace(/"/g, '""')}"`,
            `"${(b.phone_number || '').replace(/"/g, '""')}"`,
            `"${(b.website || '').replace(/"/g, '""')}"`,
            b.rating || 0.0,
            b.total_reviews || 0,
            `"${(b.full_address || '').replace(/"/g, '""')}"`,
            `"${(b.city || '').replace(/"/g, '""')}"`,
            `"${(b.state || '').replace(/"/g, '""')}"`,
            `"${(b.country || '').replace(/"/g, '""')}"`,
            b.latitude || 0.0,
            b.longitude || 0.0
        ]);

        const csvContent = "\uFEFF" + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `Filtered_Businesses_${timestamp}.csv`;
        link.click();
        showToast(`Exported ${filteredData.length} filtered records to CSV!`);
    } else if (format === 'json') {
        const jsonContent = JSON.stringify(filteredData, null, 2);
        const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `Filtered_Businesses_${timestamp}.json`;
        link.click();
        showToast(`Exported ${filteredData.length} filtered records to JSON!`);
    }
}

// Save settings
async function saveSettings(e) {
    e.preventDefault();
    const apiKey = document.getElementById('set-api-key').value;
    const exportPath = document.getElementById('set-export-path').value;
    const radius = parseInt(document.getElementById('set-radius').value);
    const delay = parseFloat(document.getElementById('set-delay').value);
    const browserMode = document.getElementById('set-browser-mode').value;

    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: apiKey,
                export_folder: exportPath,
                search_radius: radius,
                request_delay: delay,
                headless: (browserMode === 'headless')
            })
        });

        if (res.ok) {
            showToast('Preferences updated successfully!');
            fetchStats();
        }
    } catch (err) {
        showToast('Error saving preferences.');
    }
}

// Clear results
async function clearResults() {
    if (confirm('Permanently clear all search results?')) {
        try {
            await fetch('/api/results/clear', { method: 'POST' });
            rawData = [];
            renderTable();
            fetchStats();
            showToast('Results cleared.');
        } catch (e) {
            console.error(e);
        }
    }
}

// Toast helper
function showToast(msg) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerText = msg;
    container.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
