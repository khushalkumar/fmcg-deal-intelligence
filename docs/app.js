/**
 * FMCG Deal Intelligence Dashboard — Application Logic
 *
 * Loads newsletter_data.json and renders an interactive deal explorer
 * with filtering, sorting, and search capabilities.
 */

(function () {
    "use strict";

    let allDeals = [];
    let dashboardData = null;

    // ── Data Loading ────────────────────────────────────────

    async function loadData() {
        const paths = [
            "../output/newsletter_data.json",
            "./newsletter_data.json",
            "newsletter_data.json",
        ];

        for (const path of paths) {
            try {
                const resp = await fetch(path);
                if (resp.ok) {
                    dashboardData = await resp.json();
                    allDeals = dashboardData.deals || [];
                    console.log(`Loaded ${allDeals.length} deals from ${path}`);
                    return;
                }
            } catch (e) {
                continue;
            }
        }

        console.warn("Could not load newsletter_data.json from any path.");
        showEmptyState("No data found. Run the pipeline first: <code>python main.py</code>");
    }

    // ── Render Functions ────────────────────────────────────

    function renderAll() {
        renderHeader();
        renderStats();
        populateFilters();
        renderTopDeals();
        renderDealsList(allDeals);
        attachListeners();
    }

    function renderHeader() {
        if (!dashboardData) return;
        const titleEl = document.getElementById("newsletter-title");
        const subEl = document.getElementById("newsletter-subtitle");
        const dateEl = document.getElementById("report-date");

        if (dashboardData.title) titleEl.textContent = dashboardData.title;
        if (dashboardData.subtitle) subEl.textContent = dashboardData.subtitle;
        if (dashboardData.generated_at) {
            const d = new Date(dashboardData.generated_at);
            const dateStr = d.toLocaleDateString("en-US", {
                month: "short", day: "numeric", year: "numeric",
                hour: "2-digit", minute: "2-digit"
            });
            dateEl.textContent = `Last Fetched: ${dateStr}`;
        }
    }

    function renderStats() {
        if (!dashboardData || !dashboardData.stats) return;
        const s = dashboardData.stats;
        setText("stat-total", s.total_ingested || 0);
        setText("stat-dedup", (s.exact_duplicates_removed || 0) + (s.near_duplicates_removed || 0));
        setText("stat-filtered", s.irrelevant_filtered || 0);
        setText("stat-final", s.final_count || 0);
        setText("stat-time", (s.processing_time_seconds || 0).toFixed(2) + "s");
    }

    function populateFilters() {
        const types = new Set(allDeals.map(d => d.deal_type).filter(Boolean));
        const regions = new Set(allDeals.map(d => d.region).filter(Boolean));

        populateSelect("filter-type", types);
        populateSelect("filter-region", regions);
    }

    function renderTopDeals() {
        const grid = document.getElementById("top-deals-grid");
        const top = (dashboardData && dashboardData.top_deals) || allDeals.slice(0, 5);

        grid.innerHTML = top.map((deal, i) => `
            <div class="top-deal-card" style="animation-delay: ${(i + 1) * 0.08}s">
                <div class="top-deal-rank">#${i + 1} Top Deal</div>
                <div class="top-deal-title">${esc(deal.title)}</div>
                <div class="top-deal-meta">
                    ${deal.deal_type ? `<span class="meta-tag type">${esc(deal.deal_type)}</span>` : ""}
                    ${deal.deal_value ? `<span class="meta-tag value">${esc(deal.deal_value)}</span>` : ""}
                    ${deal.region ? `<span class="meta-tag region">${esc(deal.region)}</span>` : ""}
                </div>
                <div class="top-deal-score">
                    <span>Score: ${Math.round(deal.combined_score || 0)}</span>
                    <div class="score-bar">
                        <div class="score-fill" style="width: ${deal.combined_score || 0}%"></div>
                    </div>
                </div>
            </div>
        `).join("");
    }

    function renderDealsList(deals) {
        const list = document.getElementById("deals-list");
        const countEl = document.getElementById("deal-count");
        countEl.textContent = deals.length;

        if (deals.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="emoji">🔍</div>
                    <p>No deals match your filters.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = deals.map((deal, i) => {
            const score = Math.round(deal.combined_score || 0);
            const scoreClass = score >= 75 ? "score-high" : score >= 55 ? "score-medium" : "score-low";
            const isLowCred = deal.is_low_credibility;

            return `
                <div class="deal-card ${isLowCred ? 'low-cred' : ''}" style="animation-delay: ${i * 0.03}s">
                    <div class="deal-info">
                        <div class="deal-title">
                            <a href="${esc(deal.url)}" target="_blank" rel="noopener">${esc(deal.title)}</a>
                        </div>
                        <div class="deal-summary">${esc(truncate(deal.summary, 180))}</div>
                        <div class="deal-meta-row">
                            ${deal.deal_type ? `<span class="meta-tag type">${esc(deal.deal_type)}</span>` : ""}
                            ${deal.deal_value ? `<span class="meta-tag value">${esc(deal.deal_value)}</span>` : ""}
                            ${deal.region ? `<span class="meta-tag region">${esc(deal.region)}</span>` : ""}
                            ${isLowCred ? `<span class="low-cred-badge">⚠ Low Credibility</span>` : ""}
                            <span class="deal-source">${esc(deal.source)} · ${esc(deal.published_date)}</span>
                        </div>
                    </div>
                    <div class="deal-scores">
                        <div class="score-circle ${scoreClass}">${score}</div>
                        <div class="score-labels">
                            R:${Math.round(deal.relevance_score || 0)} C:${Math.round(deal.credibility_score || 0)}
                        </div>
                    </div>
                </div>
            `;
        }).join("");
    }

    // ── Filtering & Sorting ─────────────────────────────────

    function applyFilters() {
        let filtered = [...allDeals];

        const type = document.getElementById("filter-type").value;
        const region = document.getElementById("filter-region").value;
        const sortBy = document.getElementById("sort-by").value;
        const search = document.getElementById("search-input").value.toLowerCase().trim();

        if (type !== "all") {
            filtered = filtered.filter(d => d.deal_type === type);
        }
        if (region !== "all") {
            filtered = filtered.filter(d => d.region === region);
        }
        if (search) {
            filtered = filtered.filter(d =>
                (d.title || "").toLowerCase().includes(search) ||
                (d.summary || "").toLowerCase().includes(search) ||
                (d.buyer || "").toLowerCase().includes(search) ||
                (d.target || "").toLowerCase().includes(search) ||
                (d.source || "").toLowerCase().includes(search)
            );
        }

        filtered.sort((a, b) => {
            if (sortBy === "published_date") {
                return (b.published_date || "").localeCompare(a.published_date || "");
            }
            return (b[sortBy] || 0) - (a[sortBy] || 0);
        });

        renderDealsList(filtered);
    }

    function attachListeners() {
        document.getElementById("filter-type").addEventListener("change", applyFilters);
        document.getElementById("filter-region").addEventListener("change", applyFilters);
        document.getElementById("sort-by").addEventListener("change", applyFilters);

        let debounce;
        document.getElementById("search-input").addEventListener("input", () => {
            clearTimeout(debounce);
            debounce = setTimeout(applyFilters, 250);
        });
    }

    // ── Helpers ──────────────────────────────────────────────

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function populateSelect(id, items) {
        const sel = document.getElementById(id);
        items.forEach(item => {
            const opt = document.createElement("option");
            opt.value = item;
            opt.textContent = item;
            sel.appendChild(opt);
        });
    }

    function esc(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function truncate(str, len) {
        if (!str || str.length <= len) return str || "";
        return str.slice(0, len) + "…";
    }

    function showEmptyState(msg) {
        const list = document.getElementById("deals-list");
        list.innerHTML = `<div class="empty-state"><div class="emoji">📭</div><p>${msg}</p></div>`;
    }

    // ── Init ─────────────────────────────────────────────────

    async function init() {
        await loadData();
        if (dashboardData) {
            renderAll();
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
