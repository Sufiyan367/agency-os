// JARVIS // AG — Professional AI Revenue Operations Dashboard Client

// Auto-redirect to /login on 401 Unauthorized
const _originalFetch = window.fetch;
window.fetch = async function(...args) {
    const resp = await _originalFetch.apply(this, args);
    if (resp.status === 401 && !window.location.pathname.includes('/login')) {
        window.location.href = '/login';
    }
    return resp;
};

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

let currentView = 'overview';

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initHudClock();
    initTopDate();
    initGlobalSearch();
    checkBackendHealth();
    loadCeoControlCenter();
    loadDashboardMetrics();
    loadPriorityProspects();
    loadMarkets();
    loadLeads();
    loadQueue();
    loadReplies();
    loadPipeline();
    loadPayments();
    loadRuns();
    loadAgentStatus();
    fetchSafetyGuardrails();
    loadVoiceOperations();
    initActivityWebSocket();
    loadRecentActivityHistory();
    loadMLHealthTelemetry();

    // Backdrop click closes lead modal
    const modal = document.getElementById('lead-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    // Auto-refresh metrics every 30s
    setInterval(() => {
        checkBackendHealth();
        if (currentView === 'overview') {
            loadCeoControlCenter();
            loadDashboardMetrics();
            loadPriorityProspects();
            loadMLHealthTelemetry();
        }
    }, 30000);
});

function initTopDate() {
    const el = document.getElementById('top-date-display');
    if (el) {
        const now = new Date();
        const options = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
        el.innerText = now.toLocaleDateString('en-GB', options);
    }
}

function initGlobalSearch() {
    const searchInput = document.getElementById('global-search-input') || document.querySelector('.agency-search-pill input');
    if (searchInput) {
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        });
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = searchInput.value.trim();
                if (query) {
                    navToView('leads');
                    const leadSearch = document.getElementById('leads-filter-search') || document.getElementById('lead-search-input');
                    if (leadSearch) {
                        leadSearch.value = query;
                        if (typeof filterLeadsTable === 'function') filterLeadsTable();
                        else if (typeof loadLeads === 'function') loadLeads();
                    }
                }
            }
        });
    }
}

function initHudClock() {
    function tick() {
        const clockElem = document.getElementById('hud-clock');
        if (clockElem) {
            const now = new Date();
            const utcString = now.toUTCString().split(' ')[4] + ' UTC';
            clockElem.innerText = utcString;
        }
    }
    tick();
    setInterval(tick, 1000);
}

function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const targetView = item.getAttribute('data-view');
            switchView(targetView);
        });
    });

    const cycleBtn = document.getElementById('btn-run-cycle');
    if (cycleBtn) {
        cycleBtn.addEventListener('click', runAutonomousCycle);
    }
}

function toggleMobileDrawer() {
    const sidebar = document.getElementById('app-sidebar');
    const drawer = document.getElementById('mobile-drawer');
    const backdrop = document.getElementById('mobile-drawer-backdrop');
    const target = sidebar || drawer;
    if (!target) return;
    const isOpen = target.classList.contains('open');
    if (isOpen) {
        target.classList.remove('open');
        if (backdrop) {
            backdrop.classList.remove('active');
            backdrop.style.display = 'none';
        }
    } else {
        target.classList.add('open');
        if (backdrop) {
            backdrop.classList.add('active');
            backdrop.style.display = 'block';
        }
    }
}

function toggleNavMore() {
    const links = document.getElementById('nav-more-links');
    const icon = document.getElementById('nav-more-icon');
    if (!links) return;
    const isHidden = links.style.display === 'none' || getComputedStyle(links).display === 'none';
    if (isHidden) {
        links.style.display = 'block';
        if (icon) icon.innerText = '▲';
    } else {
        links.style.display = 'none';
        if (icon) icon.innerText = '▼';
    }
}


function navToView(viewName) {
    switchView(viewName);
    const sidebar = document.getElementById('app-sidebar');
    const drawer = document.getElementById('mobile-drawer');
    const backdrop = document.getElementById('mobile-drawer-backdrop');
    if (sidebar && sidebar.classList.contains('open')) {
        sidebar.classList.remove('open');
    }
    if (drawer && drawer.classList.contains('open')) {
        drawer.classList.remove('open');
    }
    if (backdrop) {
        backdrop.classList.remove('active');
        backdrop.style.display = 'none';
    }
}

function toggleAccountMenu(e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById('account-dropdown-menu');
    if (!menu) return;
    const isHidden = menu.style.display === 'none' || getComputedStyle(menu).display === 'none';
    menu.style.display = isHidden ? 'flex' : 'none';
}

function closeAccountMenu() {
    const menu = document.getElementById('account-dropdown-menu');
    if (menu) menu.style.display = 'none';
}

document.addEventListener('click', function(e) {
    const ctrl = document.getElementById('sidebar-account-ctrl');
    if (ctrl && !ctrl.contains(e.target)) {
        closeAccountMenu();
    }
});

async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
}

const VIEW_ALIASES = {
    'dashboard': 'overview',
    'prospects': 'leads',
    'research': 'markets',
    'outreach': 'queue',
    'actions': 'queue',
    'sales': 'pipeline',
    'deals': 'pipeline',
    'demos': 'leads',
    'proposals': 'pipeline',
    'clients': 'payments',
    'customers': 'payments',
    'analytics': 'decision-analytics',
    'inbox': 'replies',
    'signals': 'replies',
    'system': 'runs',
    'logs': 'runs',
    'system-logs': 'runs',
    'infrastructure': 'infra'
};

function switchView(viewName) {
    const canonicalView = VIEW_ALIASES[viewName] || viewName;
    currentView = canonicalView;

    document.querySelectorAll('.agency-nav-item, .nav-item, .bottom-nav-item').forEach(n => {
        const dv = n.getAttribute('data-view');
        if (dv === canonicalView || dv === viewName || (VIEW_ALIASES[dv] && VIEW_ALIASES[dv] === canonicalView)) {
            n.classList.add('active');
        } else {
            n.classList.remove('active');
        }
    });

    document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
    const targetElem = document.getElementById(`view-${canonicalView}`);
    if (targetElem) {
        targetElem.classList.add('active');
    }

    // Refresh view data
    if (canonicalView === 'overview') {
        loadCeoControlCenter();
        loadDashboardMetrics();
        loadPriorityProspects();
    }
    if (canonicalView === 'markets') loadMarkets();
    if (canonicalView === 'leads') loadLeads();
    if (canonicalView === 'queue') loadQueue();
    if (canonicalView === 'replies') loadReplies();
    if (canonicalView === 'pipeline') loadPipeline();
    if (canonicalView === 'payments') loadPayments();
    if (canonicalView === 'runs') loadRuns();
    if (canonicalView === 'voice') loadVoiceOperations();
    if (canonicalView === 'client-intelligence') loadClientIntelligenceView();
    if (canonicalView === 'global-acquisition') loadGlobalAcquisitionView();
    if (canonicalView === 'market-intelligence') loadMarketIntelligenceView();
    if (canonicalView === 'real-prospects') loadRealProspectsView();
    if (canonicalView === 'decision-analytics') loadDecisionAnalytics();
    if (canonicalView === 'infra') loadInfrastructureView();
    if (canonicalView === 'settings') loadSettings();
}

async function loadDashboardMetrics() {
    try {
        const res = await fetch('/api/metrics');
        const data = await res.json();

        // 1. KPI Cards (100% Real Backend Data)
        const totalLeads = data.leads?.total || 0;
        const auditedLeads = data.leads?.audited || 0;
        const qualifiedLeads = data.leads?.qualified || 0;
        const outreachSent = data.outreach?.sent || 0;
        const totalReplies = data.sales?.replies_total ?? data.replies?.total ?? 0;
        const pendingReplies = data.sales?.replies_pending ?? 0;
        const replyRate = data.sales?.reply_rate_pct || 0;
        const wonRevenue = data.revenue?.won_revenue_usd || 0;
        const verifiedRealRevenue = data.revenue?.verified_real_revenue_usd || 0;
        const pipelineVal = data.revenue?.pipeline_value_usd || 0;
        const meetingsCount = data.sales?.calls_scheduled || 0;
        const proposalsCount = data.sales?.proposals_sent || 0;
        const wonDealsCount = data.sales?.deals_won || (wonRevenue > 0 ? 1 : 0);

        // Minimal CEO Sales View - Primary KPIs
        const elCeoRevenue = document.getElementById('ceo-val-revenue');
        const elCeoRepliesPending = document.getElementById('ceo-val-replies-pending');
        const elCeoDealsWon = document.getElementById('ceo-val-deals-won');

        if (elCeoRevenue) elCeoRevenue.innerText = `$${verifiedRealRevenue.toLocaleString()}`;
        if (elCeoRepliesPending) elCeoRepliesPending.innerText = pendingReplies.toLocaleString();
        if (elCeoDealsWon) elCeoDealsWon.innerText = wonDealsCount.toLocaleString();

        // Compatibility & detail elements for tests
        const elActiveProspect = document.getElementById('val-active-prospect-display');
        const elActiveDomain = document.getElementById('val-active-domain');
        const elMeetings = document.getElementById('val-meetings-count');
        const elWonCount = document.getElementById('val-won-count');
        const elCollectedRev = document.getElementById('val-collected-revenue');

        if (elMeetings) elMeetings.innerText = meetingsCount.toLocaleString();
        if (elWonCount) elWonCount.innerText = wonDealsCount.toLocaleString();
        if (elCollectedRev) elCollectedRev.innerText = `$${wonRevenue.toLocaleString()}`;

        const elLeads = document.getElementById('val-leads');
        const elHigh = document.getElementById('val-high-value');
        const elQual = document.getElementById('val-qualified');
        const elOutreach = document.getElementById('val-outreach-sent');
        const elReply = document.getElementById('val-reply-rate');
        const elPipe = document.getElementById('val-pipeline');
        const elWon = document.getElementById('val-won');

        if (elLeads) elLeads.innerText = totalLeads.toLocaleString();
        if (elHigh) elHigh.innerText = qualifiedLeads.toLocaleString();
        if (elQual) elQual.innerText = qualifiedLeads.toLocaleString();
        if (elOutreach) elOutreach.innerText = outreachSent.toLocaleString();
        if (elReply) elReply.innerText = `${replyRate}%`;
        if (elPipe) elPipe.innerText = `$${pipelineVal.toLocaleString()}`;
        if (elWon) elWon.innerText = `$${wonRevenue.toLocaleString()}`;

        // 2. Sales Funnel (Compact, Counts Only)
        setFunnelStep('discovered', totalLeads, totalLeads, 100);
        setFunnelStep('audited', auditedLeads, totalLeads);
        setFunnelStep('highvalue', qualifiedLeads, totalLeads);
        setFunnelStep('qualified', qualifiedLeads, totalLeads);
        setFunnelStep('contacted', outreachSent, totalLeads);
        setFunnelStep('replied', totalReplies, totalLeads);
        setFunnelStep('meeting', meetingsCount, totalLeads);
        setFunnelStep('proposal', proposalsCount, totalLeads);
        setFunnelStep('won', wonDealsCount, totalLeads);

        // 3. Section 3: Revenue & Deals Graph
        renderCeoRevenueChart(data);

        // 4. Section 5: Current Sales State
        try {
            const actRes = await fetch('/api/agent/status');
            if (actRes.ok) {
                const actData = await actRes.json();
                await updateCeoSalesState(actData);
                if (elActiveProspect) {
                    elActiveProspect.textContent = actData.current_business_name || (actData.current_prospect ? actData.current_prospect.name : 'None (Standby)');
                }
                if (elActiveDomain) {
                    elActiveDomain.textContent = actData.current_domain || 'Slot 1 Single Concurrency';
                }
            }
        } catch (_) {}

        // Needs Attention Panel Counters
        const pendingQueue = data.outreach?.pending_approval || 0;
        const elAttDrafts = document.getElementById('att-drafts-text');
        const elAttReplies = document.getElementById('att-replies-text');
        const elAttMeetings = document.getElementById('att-meetings-text');

        if (elAttDrafts) elAttDrafts.innerText = `${pendingQueue} outreach draft${pendingQueue === 1 ? '' : 's'} awaiting approval`;
        if (elAttReplies) elAttReplies.innerText = `${totalReplies} prospect repl${totalReplies === 1 ? 'y' : 'ies'} to address`;
        if (elAttMeetings) elAttMeetings.innerText = `${meetingsCount} meeting${meetingsCount === 1 ? '' : 's'} to follow up`;

        // Background Worker Status
        try {
            const wRes = await fetch('/api/worker/status');
            if (wRes.ok) {
                const wData = await wRes.json();
                const statusElem = document.getElementById('worker-hud-status');
                const ticksElem = document.getElementById('worker-hud-ticks');
                const sideStatus = document.getElementById('sidebar-status-text');

                if (statusElem) {
                    statusElem.innerText = wData.is_running ? 'ONLINE' : 'STANDBY';
                    statusElem.style.color = wData.is_running ? 'var(--hud-emerald)' : 'var(--amber)';
                }
                if (sideStatus) {
                    sideStatus.innerText = wData.is_running ? 'ENGINE ONLINE' : 'ENGINE STANDBY';
                }
                if (ticksElem) {
                    ticksElem.innerText = `${wData.ticks_executed || 0} TICKS`;
                }
            }
        } catch (we) {
            console.debug('Worker status poll:', we);
        }

        // Owner Attention Feed
        loadOwnerAttention();
        loadCeoControlCenter();

        // AI Activity & Inbound Replies (Dynamic real data)
        loadRecentAiActivity();
        loadRecentInboundReplies();
    } catch (e) {
        console.error('Error loading metrics:', e);
    }
}

function formatTimeAgo(isoString) {
    if (!isoString) return 'recently';
    const d = new Date(isoString);
    const now = new Date();
    const diffSec = Math.max(0, Math.floor((now - d) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
}

// ==========================================
// CEO CONTROL CENTER CLIENT LOGIC
// ==========================================

async function loadCeoControlCenter() {
    try {
        const res = await fetch('/api/ceo/overview');
        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        hideCeoError();

        // 1. Executive Metrics
        const metrics = data.executive_metrics || {};
        const setElText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        setElText('ceo-val-total-prospects', metrics.total_prospects ?? 0);
        setElText('val-leads', metrics.total_prospects ?? 0);
        setElText('ceo-val-qualified-prospects', metrics.qualified_prospects ?? 0);
        setElText('val-qualified', metrics.qualified_prospects ?? 0);
        setElText('ceo-val-outreach-approval', metrics.outreach_awaiting_approval ?? 0);
        setElText('ceo-val-interested-leads', metrics.interested_leads ?? 0);
        setElText('ceo-val-replies-pending', metrics.interested_leads ?? 0);
        setElText('ceo-val-active-demos', metrics.active_demos ?? 0);
        setElText('ceo-val-proposals-action', metrics.proposals_awaiting_action ?? 0);
        setElText('ceo-val-payments-auth', metrics.payments_awaiting_authorization ?? 0);
        setElText('ceo-val-deals-won', metrics.payments_awaiting_authorization ?? 0);

        setElText('ceo-val-revenue-dryrun', metrics.revenue_label || '$0.00 (Dry Run)');
        setElText('ceo-val-revenue', metrics.revenue_label || '$0.00 (Dry Run)');

        // 2. Action Required Section
        renderCeoActionsRequired(data.action_required || []);

        // 3. 9-Stage Visual Pipeline Funnel
        renderCeoPipelineFunnel(data.pipeline_funnel || {}, data.active_prospect);

        // 4. Active Prospect Card
        renderCeoActiveProspect(data.active_prospect);

        // 5. System Status Widget
        renderCeoSystemStatus(data.system_status || {});
        setBackendHealthUI(true);

    } catch (err) {
        console.error('Error loading CEO control center:', err);
        showCeoError(err);
        setBackendHealthUI(false);
    }
}

function showCeoError(err) {
    const banner = document.getElementById('ceo-error-banner');
    const msg = document.getElementById('ceo-error-msg');
    if (banner) {
        banner.style.display = 'flex';
    }
    if (msg) {
        const errorDetail = (err && err.message) ? ` (${err.message})` : '';
        msg.textContent = `Unable to refresh CEO Overview${errorDetail}. Operations continue safely in the background.`;
    }
}

function hideCeoError() {
    const banner = document.getElementById('ceo-error-banner');
    if (banner) {
        banner.style.display = 'none';
    }
}

async function retryCeoConnection() {
    const btn = document.querySelector('#ceo-error-banner button');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Reconnecting...';
    }
    try {
        await checkBackendHealth();
        await loadCeoControlCenter();
        await loadDashboardMetrics();
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Retry Reconnect';
        }
    }
}

function renderCeoActionsRequired(actions) {
    const container = document.getElementById('ceo-action-required-list');
    const badge = document.getElementById('attention-status-badge');
    if (!container) return;

    if (!actions || actions.length === 0) {
        container.innerHTML = `
            <div style="color:#94a3b8; font-size:0.75rem; text-align:center; padding:24px 0;">
                Zero actions pending — operations running smoothly.
            </div>
        `;
        if (badge) {
            badge.textContent = 'ALL CLEAR';
            badge.className = 'badge-tag actual';
        }
        return;
    }

    if (badge) {
        badge.textContent = `${actions.length} ACTION${actions.length === 1 ? '' : 'S'} REQUIRED`;
        badge.className = 'badge-tag estimated';
    }

    let html = '';
    for (const item of actions) {
        const title = escapeHtml(item.title || 'Action Pending');
        const company = escapeHtml(item.company || item.lead_name || 'Prospect');
        const desc = escapeHtml(item.description || '');
        const timeAgo = formatTimeAgo(item.created_at || item.timestamp);
        const itemType = escapeHtml(item.type || '');

        let actionBtns = '';
        if (item.type === 'OUTREACH_APPROVAL') {
            const msgId = item.entity_id || item.item_id || item.id || item.message_id;
            actionBtns = `
                <div style="display:flex; gap:6px; margin-top:6px;">
                    <button class="btn btn-xs btn-primary" onclick="approveCeoAction('OUTREACH_APPROVAL', '${msgId}')" style="padding:3px 8px; font-size:0.72rem;">Approve</button>
                    <button class="btn btn-xs btn-secondary" onclick="rejectCeoAction('OUTREACH_APPROVAL', '${msgId}')" style="padding:3px 8px; font-size:0.72rem;">Reject</button>
                    <button class="btn btn-xs btn-ghost" onclick="navToView('queue')" style="padding:3px 8px; font-size:0.72rem;">Review</button>
                </div>
            `;
        } else if (item.type === 'INTERESTED_REPLY') {
            const leadId = item.lead_id || item.id;
            actionBtns = `
                <div style="display:flex; gap:6px; margin-top:6px;">
                    <button class="btn btn-xs btn-primary" onclick="viewLeadDetail(${leadId})" style="padding:3px 8px; font-size:0.72rem;">Review Lead</button>
                    <button class="btn btn-xs btn-ghost" onclick="navToView('leads')" style="padding:3px 8px; font-size:0.72rem;">All Leads</button>
                </div>
            `;
        } else if (item.type === 'DEMO_REVIEW') {
            const leadId = item.lead_id || item.id;
            actionBtns = `
                <div style="display:flex; gap:6px; margin-top:6px;">
                    <button class="btn btn-xs btn-cyan" onclick="openDemoPreview(${leadId})" style="padding:3px 8px; font-size:0.72rem;">Preview Demo</button>
                </div>
            `;
        } else if (item.type === 'PROPOSAL_AUTHORIZATION') {
            const leadId = item.lead_id || item.id;
            actionBtns = `
                <div style="display:flex; gap:6px; margin-top:6px;">
                    <button class="btn btn-xs btn-primary" onclick="viewLeadDetail(${leadId})" style="padding:3px 8px; font-size:0.72rem;">View Proposal</button>
                </div>
            `;
        } else if (item.type === 'PAYMENT_AUTHORIZATION') {
            actionBtns = `
                <div style="display:flex; gap:6px; margin-top:6px; align-items:center;">
                    <span class="badge badge-amber" style="font-size:0.65rem;">DRY RUN: SAFE</span>
                </div>
            `;
        } else {
            actionBtns = `
                <div style="display:flex; gap:6px; margin-top:6px;">
                    <button class="btn btn-xs btn-secondary" onclick="navToView('leads')" style="padding:3px 8px; font-size:0.72rem;">View</button>
                </div>
            `;
        }

        html += `
            <div class="ceo-action-card" style="background:#080d18; border:1px solid rgba(148,163,184,0.12); border-radius:6px; padding:10px 12px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                    <span style="font-weight:700; color:#f1f5f9; font-size:0.78rem;">${title}</span>
                    <span class="badge-tag estimated" style="font-size:0.58rem;">${itemType}</span>
                </div>
                <div style="font-size:0.72rem; color:#38bdf8; font-weight:600; margin-bottom:2px;">${company}</div>
                <div style="font-size:0.7rem; color:#94a3b8; line-height:1.3;">${desc}</div>
                <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                    ${actionBtns}
                    <span style="font-size:0.64rem; color:#64748b; font-family:var(--font-mono);">${timeAgo}</span>
                </div>
            </div>
        `;
    }
    container.innerHTML = html;
}

async function approveCeoAction(type, id) {
    if (type === 'OUTREACH_APPROVAL') {
        await approveMessage(id, false);
        await loadCeoControlCenter();
    }
}

async function rejectCeoAction(type, id) {
    if (type === 'OUTREACH_APPROVAL') {
        await rejectMessage(id);
        await loadCeoControlCenter();
    }
}

function renderCeoPipelineFunnel(funnel, activeProspect) {
    const stageMap = {
        'discovery': 'DISCOVERY',
        'qualified': 'QUALIFIED',
        'outreach': 'OUTREACH',
        'interested': 'INTERESTED',
        'requirements': 'REQUIREMENTS',
        'demo': 'DEMO',
        'qa': 'QA',
        'proposal': 'PROPOSAL',
        'payment': 'PAYMENT'
    };
    const activeStage = (activeProspect && activeProspect.stage) ? activeProspect.stage.toUpperCase() : null;

    for (const [stepKey, dataKey] of Object.entries(stageMap)) {
        const cntEl = document.getElementById(`step-cnt-${stepKey}`);
        const stepEl = document.getElementById(`funnel-step-${stepKey}`);
        const count = funnel ? (funnel[dataKey] || 0) : 0;
        if (cntEl) cntEl.textContent = count;
        if (stepEl) {
            if (activeStage === dataKey || (!activeStage && stepKey === 'discovery')) {
                stepEl.classList.add('active');
            } else {
                stepEl.classList.remove('active');
            }
            stepEl.style.opacity = count > 0 ? '1' : '0.65';
        }
    }
}

function renderCeoActiveProspect(prospect) {
    const setEl = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };

    if (!prospect) {
        currentActiveProspectLeadId = null;
        setEl('ceo-active-prospect-name', 'Standby');
        setEl('ceo-active-prospect-domain', '—');
        setEl('ceo-active-prospect-location', 'Global');
        setEl('ceo-active-prospect-score', '—');
        setEl('ceo-active-prospect-stage', 'STANDBY');
        setEl('ceo-active-outreach-status', 'Idle');
        setEl('ceo-active-reply-status', 'None');
        setEl('ceo-active-demo-status', 'None');
        setEl('ceo-active-qa-status', 'None');
        setEl('ceo-active-proposal-status', 'None');
        setEl('ceo-active-payment-status', 'Dry Run');
        setEl('ceo-demo-exists-label', 'NO');
        setEl('ceo-demo-qa-badge', 'QA: STANDBY');
        const previewBtn = document.getElementById('ceo-btn-preview-demo');
        if (previewBtn) previewBtn.style.display = 'none';
        return;
    }

    currentActiveProspectLeadId = prospect.id;
    setEl('ceo-active-prospect-name', prospect.company_name || prospect.contact_name || 'Standby');
    setEl('ceo-active-prospect-domain', prospect.domain || '—');
    setEl('ceo-active-prospect-location', prospect.location || 'Global');
    setEl('ceo-active-prospect-score', (prospect.score !== undefined && prospect.score !== null) ? `${prospect.score}/100` : '—');
    setEl('ceo-active-prospect-price', prospect.offer_price || (prospect.catalog_price ? `$${Number(prospect.catalog_price).toLocaleString()}` : '$1,000'));
    setEl('ceo-active-prospect-service', prospect.target_service || 'Digital Growth Optimization');
    setEl('ceo-active-prospect-audit', prospect.audit_summary || 'Empirical audit findings.');
    setEl('ceo-active-prospect-stage', (prospect.stage || 'STANDBY').toUpperCase());

    // Status Chips
    setEl('ceo-active-outreach-status', prospect.outreach_status || 'Idle');
    setEl('ceo-active-reply-status', prospect.reply_status || 'None');
    setEl('ceo-active-demo-status', prospect.demo?.exists ? 'Generated' : 'None');
    setEl('ceo-active-qa-status', prospect.demo?.qa?.overall_passed ? 'Passed (8/8)' : (prospect.demo?.exists ? 'Evaluating' : 'None'));
    setEl('ceo-active-proposal-status', prospect.proposal?.status || 'None');
    setEl('ceo-active-payment-status', prospect.payment?.status || 'Dry Run');

    // Demo + QA Panel
    setEl('ceo-demo-exists-label', prospect.demo?.exists ? 'YES' : 'NO');
    const qaBadge = document.getElementById('ceo-demo-qa-badge');
    if (qaBadge) {
        if (prospect.demo?.qa?.overall_passed) {
            qaBadge.textContent = 'QA: PASSED (8/8)';
            qaBadge.className = 'badge badge-emerald';
        } else if (prospect.demo?.exists) {
            qaBadge.textContent = 'QA: PENDING';
            qaBadge.className = 'badge badge-amber';
        } else {
            qaBadge.textContent = 'QA: STANDBY';
            qaBadge.className = 'badge badge-slate';
        }
    }

    const qaGatesEl = document.getElementById('ceo-demo-qa-gates');
    if (qaGatesEl) {
        if (prospect.demo?.qa?.checks && prospect.demo.qa.checks.length > 0) {
            qaGatesEl.innerHTML = prospect.demo.qa.checks.map(c => `
                <div style="display:flex; justify-content:space-between; align-items:center; color:${c.passed ? '#34d399' : '#f87171'};">
                    <span>${c.passed ? '✓' : '✗'} ${escapeHtml(c.name)}</span>
                    <span style="font-size:0.62rem; color:${c.passed ? '#34d399' : '#f87171'}; font-weight:700;">${c.passed ? 'PASS' : 'FAIL'}</span>
                </div>
            `).join('');
        } else {
            qaGatesEl.innerHTML = '<div style="color:#64748b; font-style:italic;">8 QA gates evaluate upon receiving interest.</div>';
        }
    }

    const previewBtn = document.getElementById('ceo-btn-preview-demo');
    if (previewBtn) {
        previewBtn.style.display = prospect.demo?.exists ? 'block' : 'none';
    }

    // Commercial Proposal & Payment
    setEl('ceo-prop-val', prospect.proposal?.amount ? `$${Number(prospect.proposal.amount).toLocaleString()}` : (prospect.catalog_price ? `$${Number(prospect.catalog_price).toLocaleString()}` : 'N/A'));
    setEl('ceo-prop-adv', prospect.proposal?.advance ? `$${Number(prospect.proposal.advance).toLocaleString()}` : 'N/A');
    const payBadge = document.getElementById('ceo-pay-dryrun-badge');
    if (payBadge) {
        payBadge.textContent = prospect.payment?.status ? `PAYMENT: ${prospect.payment.status} [DRY RUN]` : 'PAYMENTS: DISABLED';
    }
}

function previewActiveDemo() {
    if (currentActiveProspectLeadId && typeof openDemoPreview === 'function') {
        openDemoPreview(currentActiveProspectLeadId);
    }
}

function setBackendHealthUI(isOnline) {
    const pill = document.getElementById('ceo-backend-health-pill');
    const dot = document.getElementById('ceo-backend-health-dot');
    const text = document.getElementById('ceo-backend-health-text');
    const sysBackend = document.getElementById('ceo-sys-backend');

    if (isOnline) {
        if (pill) {
            pill.style.background = 'rgba(16,185,129,0.1)';
            pill.style.borderColor = 'rgba(16,185,129,0.25)';
            pill.style.color = '#10b981';
        }
        if (dot) {
            dot.style.background = '#10b981';
            dot.style.boxShadow = '0 0 6px #10b981';
        }
        if (text) text.textContent = 'CONNECTED';
        if (sysBackend) {
            sysBackend.textContent = '● Online';
            sysBackend.style.color = '#10b981';
        }
    } else {
        if (pill) {
            pill.style.background = 'rgba(239,68,68,0.1)';
            pill.style.borderColor = 'rgba(239,68,68,0.25)';
            pill.style.color = '#ef4444';
        }
        if (dot) {
            dot.style.background = '#ef4444';
            dot.style.boxShadow = '0 0 6px #ef4444';
        }
        if (text) text.textContent = 'DISCONNECTED';
        if (sysBackend) {
            sysBackend.textContent = '● Offline';
            sysBackend.style.color = '#ef4444';
        }
    }
}

async function checkBackendHealth() {
    try {
        const res = await fetch('/health', { cache: 'no-cache' });
        if (res.ok) {
            setBackendHealthUI(true);
        } else {
            setBackendHealthUI(false);
        }
    } catch (err) {
        setBackendHealthUI(false);
    }
}

function renderCeoSystemStatus(status) {
    const setEl = (id, text, color) => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = text;
            if (color) el.style.color = color;
        }
    };

    setEl('ceo-sys-backend', '● Online', '#10b981');
    setEl('ceo-sys-inbox', status.inbox_polling ? '● Active' : '● Inactive', status.inbox_polling ? '#10b981' : '#94a3b8');
    setEl('ceo-sys-email', status.email_mode ? `● ${status.email_mode}` : '● DRY RUN', '#fbbf24');
    setEl('ceo-sys-payment', status.payment_mode ? `● ${status.payment_mode}` : '● DISABLED', '#38bdf8');
    setEl('ceo-sys-worker', status.worker_status ? `● ${status.worker_status}` : '● Idle', '#a78bfa');
    setEl('ceo-sys-last-activity', status.last_activity ? formatTimeAgo(status.last_activity) : 'Just now');
}

async function loadOwnerAttention() {
    try {
        const res = await fetch('/api/owner/attention');
        if (!res.ok) return;
        const data = await res.json();
        
        const badge = document.getElementById('attention-status-badge');
        const container = document.getElementById('owner-attention-items');
        if (!container) return;

        if (badge) {
            if (data.status === 'ALL_CLEAR' || data.count === 0) {
                badge.textContent = 'ALL CLEAR';
                badge.className = 'badge-tag actual';
            } else {
                badge.textContent = `${data.count} ACTION REQUIRED`;
                badge.className = 'badge-tag model';
            }
        }

        if (data.count === 0 || !data.items || data.items.length === 0) {
            container.innerHTML = `
                <div style="display:flex; align-items:center; gap:12px; padding:16px; background:rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.2); border-radius:8px;">
                    <span style="font-size:1.2rem;">✅</span>
                    <div>
                        <div style="font-weight:600; font-size:0.8rem; color:#f8fafc;">All systems operating nominally</div>
                        <div style="font-size:0.72rem; color:#94a3b8; margin-top:2px;">Nothing needs your attention. Outreach, pipeline, and billing queues are clear.</div>
                    </div>
                </div>
            `;
        } else {
            container.innerHTML = data.items.map(it => `
                <div style="display:flex; align-items:center; justify-content:space-between; padding:12px 14px; background:rgba(245,158,11,0.05); border:1px solid rgba(245,158,11,0.2); border-radius:8px;">
                    <div style="max-width:75%;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span class="badge-tag ${it.severity === 'CRITICAL' ? 'model' : 'estimated'}" style="font-size:0.6rem;">${escapeHtml(it.type)}</span>
                            <span style="font-weight:600; font-size:0.82rem; color:#f8fafc;">${escapeHtml(it.title)}</span>
                        </div>
                        <div style="font-size:0.72rem; color:#94a3b8; margin-top:4px;">${escapeHtml(it.description)}</div>
                    </div>
                    <button class="btn btn-secondary" onclick="navToView('${it.action_view || 'queue'}')" style="font-size:0.7rem; height:28px; padding:0 10px; white-space:nowrap;">
                        ${escapeHtml(it.action_label || 'Action')} →
                    </button>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('Failed to load owner attention:', e);
    }
}

async function loadRecentAiActivity() {
    const list = document.getElementById('ceo-recent-activity-list');
    if (!list) return;
    try {
        const res = await fetch('/api/agent/activity?limit=6');
        if (!res.ok) {
            list.innerHTML = `<div style="color:#64748b; font-size:0.75rem; text-align:center; padding:24px 0;">Engine initialized. Awaiting next prospecting cycle.</div>`;
            return;
        }
        const data = await res.json();
        const events = data.events || (Array.isArray(data) ? data : []);
        if (events.length === 0) {
            list.innerHTML = `<div style="color:#64748b; font-size:0.75rem; text-align:center; padding:24px 0;">Engine initialized. Awaiting next prospecting cycle.</div>`;
            return;
        }
        list.innerHTML = events.map(ev => {
            const timeAgo = formatTimeAgo(ev.created_at);
            let badgeClass = 'purple';
            if (ev.status === 'SUCCESS' || (ev.event_type && ev.event_type.includes('COMPLETED'))) badgeClass = 'green';
            else if (ev.status === 'WARNING' || (ev.event_type && ev.event_type.includes('WAIT'))) badgeClass = 'amber';
            else if (ev.event_type && (ev.event_type.includes('AUDIT') || ev.event_type.includes('RESEARCH'))) badgeClass = 'blue';
            else if (ev.event_type && ev.event_type.includes('OUTREACH')) badgeClass = 'teal';

            const cleanMsg = ev.message || ev.event_type || 'Agent operation executed';
            return `
                <div class="agency-activity-row">
                    <div class="agency-activity-badge ${badgeClass}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div>
                    <span class="agency-activity-title" title="${escapeHtml(cleanMsg)}">${escapeHtml(cleanMsg)}</span>
                    <span class="agency-activity-ago">${timeAgo}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load AI activity feed:', e);
        list.innerHTML = `<div style="color:#64748b; font-size:0.75rem; text-align:center; padding:24px 0;">Engine initialized. Awaiting next prospecting cycle.</div>`;
    }
}

async function loadRecentInboundReplies() {
    const list = document.getElementById('recent-messages-list');
    if (!list) return;
    try {
        const res = await fetch('/api/replies?limit=4');
        if (!res.ok) {
            list.innerHTML = `<div style="color:#64748b; font-size:0.75rem; text-align:center; padding:24px 0;">No inbound prospect replies recorded yet.</div>`;
            return;
        }
        const replies = await res.json();
        if (!Array.isArray(replies) || replies.length === 0) {
            list.innerHTML = `<div style="color:#64748b; font-size:0.75rem; text-align:center; padding:24px 0;">No inbound prospect replies recorded yet.</div>`;
            return;
        }
        list.innerHTML = replies.map(r => {
            const initials = (r.business_name || r.sender_email || 'PR').slice(0, 2).toUpperCase();
            const timeAgo = formatTimeAgo(r.received_at);
            return `
                <div class="agency-inbox-row" onclick="navToView('replies')" style="cursor:pointer;">
                    <div class="agency-inbox-avatar" style="background:#475569;">${escapeHtml(initials)}</div>
                    <div class="agency-inbox-meta" style="overflow:hidden;">
                        <div class="agency-inbox-sender" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(r.business_name || r.sender_email)}</div>
                        <div class="agency-inbox-snippet" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(r.raw_body || r.classification)}</div>
                    </div>
                    <span class="agency-inbox-time">${timeAgo}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load recent replies:', e);
        list.innerHTML = `<div style="color:#64748b; font-size:0.75rem; text-align:center; padding:24px 0;">No inbound prospect replies recorded yet.</div>`;
    }
}

async function loadInfrastructureView() {
    try {
        const [hRes, wRes] = await Promise.all([
            fetch('/api/production/health'),
            fetch('/api/worker/status')
        ]);
        const health = hRes.ok ? await hRes.json() : null;
        const worker = wRes.ok ? await wRes.json() : null;

        const overallBadge = document.getElementById('infra-overall-badge');
        if (overallBadge && health) {
            const st = health.overall_status || 'OPERATIONAL';
            overallBadge.textContent = st;
            overallBadge.className = `badge-tag ${st.includes('READY') ? 'actual' : 'model'}`;
        }

        const subList = document.getElementById('infra-subsystems-list');
        if (subList && health) {
            const subsystems = [
                { name: 'Database Engine', data: health.database },
                { name: 'Email Delivery', data: health.email },
                { name: 'Voice Telephony', data: health.voice },
                { name: 'Payment Gateway', data: health.payment },
                { name: 'Webhook Cryptography', data: health.webhooks }
            ];
            subList.innerHTML = subsystems.map(s => {
                const status = s.data?.status || 'UNKNOWN';
                return `
                    <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:rgba(255,255,255,0.02); border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                        <div>
                            <div style="font-size:0.8rem; font-weight:600; color:#f8fafc;">${s.name}</div>
                            <div style="font-size:0.68rem; color:#64748b; margin-top:2px;">${escapeHtml(s.data?.details || '')}</div>
                        </div>
                        <span class="badge-tag ${status === 'READY' ? 'actual' : (status === 'DRY_RUN' ? 'estimated' : 'stage')}" style="font-size:0.6rem;">${escapeHtml(status)}</span>
                    </div>
                `;
            }).join('');
        }

        if (worker) {
            const wStatus = document.getElementById('infra-worker-status');
            const wBadge = document.getElementById('infra-worker-badge');
            const wTicks = document.getElementById('infra-worker-ticks');
            const wInt = document.getElementById('infra-worker-interval');
            const wLast = document.getElementById('infra-worker-last');

            if (wStatus) {
                wStatus.textContent = worker.is_running ? 'Online & Running' : 'Standby (Awaiting Cycle)';
                wStatus.style.color = worker.is_running ? '#10b981' : '#f59e0b';
            }
            if (wBadge) {
                wBadge.textContent = worker.is_running ? 'RUNNING' : 'STANDBY';
                wBadge.className = `badge-tag ${worker.is_running ? 'actual' : 'model'}`;
            }
            if (wTicks) wTicks.textContent = (worker.ticks_executed || 0).toLocaleString();
            if (wInt) wInt.textContent = `${worker.interval_seconds || 60}s`;
            if (wLast) wLast.textContent = worker.last_tick_at ? new Date(worker.last_tick_at).toLocaleTimeString() : 'Never';
        }

        const safeList = document.getElementById('infra-safeguards-list');
        if (safeList && health && health.safeguards) {
            const sg = health.safeguards;
            const items = [
                { label: 'Autonomous Discovery & Research', val: sg.autonomous_agent_enabled ? 'Active' : 'Disabled', ok: sg.autonomous_agent_enabled },
                { label: 'Autonomous Outreach Queue', val: sg.autonomous_outreach ? 'Active' : 'Disabled', ok: sg.autonomous_outreach },
                { label: 'Email Dry-Run Mode', val: sg.email_dry_run ? 'Safe (No Real Emails Sent)' : 'Live', ok: sg.email_dry_run },
                { label: 'Voice Dry-Run Mode', val: sg.voice_dry_run ? 'Safe (No Real Calls Made)' : 'Live', ok: sg.voice_dry_run },
                { label: 'Payment Sandbox Mode', val: sg.payment_dry_run ? 'Safe (No Real Charges)' : 'Live', ok: sg.payment_dry_run },
                { label: 'Commercial Price Floor', val: `$${sg.commercial_floor_usd || 500} Min Required`, ok: true }
            ];
            safeList.innerHTML = items.map(it => `
                <div style="display:flex; align-items:center; justify-content:space-between; padding:6px 0; font-size:0.75rem; border-bottom:1px solid rgba(255,255,255,0.04);">
                    <span style="color:#94a3b8;">${it.label}</span>
                    <span style="font-weight:600; color:${it.ok ? '#10b981' : '#f59e0b'};">${it.val}</span>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('Failed to load infrastructure telemetry:', e);
    }
}

let currentActiveProspectLeadId = null;

function viewCurrentActiveProspect() {
    if (currentActiveProspectLeadId) {
        viewLeadDetail(currentActiveProspectLeadId);
    } else {
        navToView('leads');
    }
}

async function updateCeoSalesState(data) {
    if (!data) return;
    const nameElem = document.getElementById('ceo-active-prospect-name');
    const domainElem = document.getElementById('ceo-active-prospect-domain');
    const stageElem = document.getElementById('ceo-active-prospect-stage');
    const outreachElem = document.getElementById('ceo-active-outreach-status');
    const nextElem = document.getElementById('ceo-active-prospect-next');

    let prospectName = data.current_business_name || (data.current_prospect ? data.current_prospect.name : null);
    let prospectDomain = data.current_domain || (data.current_prospect ? data.current_prospect.domain : null);
    let prospectLeadId = data.current_business_id || (data.current_prospect ? data.current_prospect.id : null);
    if (prospectLeadId) {
        currentActiveProspectLeadId = prospectLeadId;
    }

    let stage = data.current_stage || data.current_state || (prospectName ? 'ACTIVE' : 'STANDBY');

    let outreachStatus = 'IDLE';
    if (data.status === 'RUNNING' || data.is_running) {
        outreachStatus = 'ACTIVE';
    } else if (data.is_paused) {
        outreachStatus = 'WAITING';
    } else if (data.status === 'WAITING' || stage === 'WAIT_REPLY') {
        outreachStatus = 'WAITING';
    } else if (data.status === 'KILLED' || data.kill_switch_active) {
        outreachStatus = 'HALTED';
    }

    let nextAction = data.current_operation || (data.decision ? data.decision.reasoning : null);

    // If no active in-flight prospect in runtime telemetry, check DB for latest lead
    if (!prospectName) {
        try {
            const leadRes = await fetch('/api/leads?limit=1');
            if (leadRes.ok) {
                const leads = await leadRes.json();
                const list = Array.isArray(leads) ? leads : (leads.leads || []);
                if (list.length > 0) {
                    const latest = list[0];
                    prospectName = latest.name;
                    prospectDomain = `${latest.city ? latest.city + ', ' : ''}${latest.country || latest.domain || ''}`.trim() || latest.domain;
                    stage = latest.pipeline_stage || 'DISCOVERED';
                    currentActiveProspectLeadId = latest.id;
                    if (!nextAction || nextAction === 'Standby') {
                        nextAction = 'Review prospect audit & intelligence';
                    }
                    if (latest.pipeline_stage === 'CONTACTED') {
                        outreachStatus = 'ACTIVE';
                    }
                }
            }
        } catch (_) {}
    }

    if (!nextAction || nextAction === 'Standby') {
        nextAction = prospectName 
            ? `Evaluating next milestone for ${prospectName}.` 
            : 'Awaiting prospecting cycle trigger.';
    }

    if (nameElem) nameElem.textContent = prospectName || 'Standby';
    if (domainElem) domainElem.textContent = prospectDomain || '—';
    if (stageElem) stageElem.textContent = stage;
    if (outreachElem) {
        outreachElem.textContent = `● ${outreachStatus.charAt(0) + outreachStatus.slice(1).toLowerCase()}`;
        if (outreachStatus === 'ACTIVE') {
            outreachElem.style.color = '#10b981';
        } else if (outreachStatus === 'WAITING') {
            outreachElem.style.color = '#f59e0b';
        } else {
            outreachElem.style.color = '#64748b';
        }
    }
    if (nextElem && nextAction) nextElem.textContent = nextAction;
}

function renderCeoRevenueChart(data) {
    const emptyState = document.getElementById('ceo-empty-chart');
    const svgElem = document.getElementById('ceo-revenue-svg');
    if (!emptyState || !svgElem) return;

    const verifiedRev = data?.revenue?.verified_real_revenue_usd || 0;
    const isLive = data?.revenue?.is_real_revenue_active || false;

    // Strict Rule: Real production data only.
    // If no verified revenue or not in live mode, display "No real revenue data yet"
    if (!isLive || verifiedRev <= 0) {
        emptyState.style.display = 'flex';
        svgElem.style.display = 'none';
        svgElem.innerHTML = '';
        return;
    }

    emptyState.style.display = 'none';
    svgElem.style.display = 'block';

    const width = svgElem.clientWidth || 500;
    const height = 240;
    const padding = { top: 20, right: 30, bottom: 30, left: 50 };

    svgElem.innerHTML = `
        <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.1)" stroke-width="1" />
        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="rgba(255,255,255,0.1)" stroke-width="1" />
        <circle cx="${width - padding.right - 20}" cy="${padding.top + 20}" r="4" fill="#34d399" />
        <text x="${width - padding.right - 10}" y="${padding.top + 24}" fill="#34d399" font-size="11" font-family="'JetBrains Mono', monospace">$${verifiedRev.toLocaleString()}</text>
        <text x="${padding.left}" y="${height - 10}" fill="#64748b" font-size="10">Real Collections</text>
    `;
}

function setFunnelStep(stageKey, count, total, explicitPct = null) {
    const cElem = document.getElementById(`funnel-c-${stageKey}`);
    const pElem = document.getElementById(`funnel-p-${stageKey}`);
    if (cElem) cElem.innerText = count.toLocaleString();
    if (pElem) {
        const pct = explicitPct !== null ? explicitPct : (total > 0 ? Math.round((count / total) * 100) : 0);
        pElem.innerText = `${pct}%`;
    }
    if (cElem && cElem.parentElement) {
        const bar = cElem.parentElement.querySelector('.agency-funnel-bar');
        if (bar) {
            let widthPct;
            if (total > 0 && count > 0) {
                widthPct = Math.max(14, Math.min(100, Math.round((count / total) * 100)));
            } else if (total > 0 && count === 0) {
                widthPct = 8;
            } else {
                const defaultWidths = {
                    'discovered': 100,
                    'qualified': 86,
                    'contacted': 72,
                    'replied': 58,
                    'meeting': 44,
                    'proposal': 32,
                    'won': 22
                };
                widthPct = defaultWidths[stageKey] || 50;
            }
            bar.style.width = `${widthPct}%`;
        }
    }
}

async function loadPriorityProspects() {
    const tbody = document.getElementById('priority-prospects-tbody');
    if (!tbody) return;

    try {
        const res = await fetch('/api/leads');
        const leads = await res.json();
        tbody.innerHTML = '';

        if (Array.isArray(leads)) {
            updateTopCountriesAndServices(leads);
        }

        // Filter and sort for highest-value prospects
        const priorityLeads = leads
            .sort((a, b) => (b.lead_score || 0) - (a.lead_score || 0))
            .slice(0, 6);

        if (priorityLeads.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:24px; color:var(--text-muted);">No priority prospects found. Run a prospecting cycle to populate.</td></tr>';
            return;
        }

        priorityLeads.forEach(l => {
            const tr = document.createElement('tr');
            const score = l.lead_score || 75;
            const oppScore = Math.min(100, Math.round(score * 0.95 + 5));
            const estValue = score >= 85 ? '$2,500 - $5,000' : (score >= 75 ? '$1,000 - $2,500' : '$500 - $1,000');
            
            // Badge selector
            let statusBadge = '<span class="badge badge-cyan">PRIORITY</span>';
            let nextAction = 'Review Draft';
            if (l.pipeline_stage === 'CONTACTED') {
                statusBadge = '<span class="badge badge-emerald">CONTACTED</span>';
                nextAction = 'Awaiting Reply';
            } else if (l.pipeline_stage === 'QUALIFIED_REPLY' || l.pipeline_stage === 'REPLIED') {
                statusBadge = '<span class="badge badge-amber">REPLIED</span>';
                nextAction = 'Book Meeting';
            } else if (l.pipeline_stage === 'WON') {
                statusBadge = '<span class="badge badge-emerald">WON</span>';
                nextAction = 'Onboarded';
            }

            tr.innerHTML = `
                <td>
                    <div class="prospect-name">${l.name}</div>
                    <div class="prospect-sub">${l.domain} • ${l.city || 'Austin, TX'}</div>
                </td>
                <td>${l.country || 'US'}</td>
                <td>${l.niche || 'HVAC'}</td>
                <td><strong style="color:var(--hud-cyan-bright);">${score}/100</strong></td>
                <td><strong>${oppScore}/100</strong></td>
                <td style="color:#facc15; font-weight:600;">${estValue}</td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn btn-outline" style="padding:4px 8px; font-size:0.75rem;" onclick="viewLeadDetail(${l.id})">
                        ${nextAction}
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading priority prospects:', e);
    }
}

function updateTopCountriesAndServices(leads) {
    if (!leads || leads.length === 0) return;

    // 1. Countries Breakdown
    const countryCounts = {};
    leads.forEach(l => {
        const c = (l.country || 'US').toUpperCase();
        countryCounts[c] = (countryCounts[c] || 0) + 1;
    });

    const sortedCountries = Object.entries(countryCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);

    const countryContainer = document.getElementById('top-countries-list');
    if (countryContainer && sortedCountries.length > 0) {
        const total = leads.length;
        const flags = {
            'US': '🇺🇸', 'USA': '🇺🇸',
            'CA': '🇨🇦', 'CAN': '🇨🇦',
            'GB': '🇬🇧', 'UK': '🇬🇧',
            'AU': '🇦🇺', 'AUS': '🇦🇺',
            'DE': '🇩🇪', 'DEU': '🇩🇪',
            'AE': '🇦🇪', 'UAE': '🇦🇪',
            'SA': '🇸🇦', 'SAU': '🇸🇦',
            'FR': '🇫🇷', 'FRA': '🇫🇷',
            'IN': '🇮🇳', 'IND': '🇮🇳'
        };
        const countryNames = {
            'US': 'United States',
            'CA': 'Canada',
            'GB': 'United Kingdom',
            'UK': 'United Kingdom',
            'AU': 'Australia',
            'DE': 'Germany',
            'AE': 'United Arab Emirates',
            'SA': 'Saudi Arabia',
            'FR': 'France',
            'IN': 'India'
        };

        let html = '';
        sortedCountries.forEach(([code, count]) => {
            const pct = Math.round((count / total) * 100);
            const flag = flags[code] || '🌐';
            const name = countryNames[code] || code;
            html += `
                <div class="agency-list-row">
                    <div class="agency-list-meta">
                        <span>${flag}</span>
                        <span class="agency-list-name">${escapeHtml(name)}</span>
                    </div>
                    <div class="agency-list-bar-track"><div class="agency-list-bar-fill" style="width: ${pct}%;"></div></div>
                    <span class="agency-list-val">${pct}%</span>
                </div>
            `;
        });
        countryContainer.innerHTML = html;
    }

    // 2. Services Breakdown
    const serviceCounts = {};
    leads.forEach(l => {
        const s = l.niche || l.service_name || 'Website Development';
        serviceCounts[s] = (serviceCounts[s] || 0) + 1;
    });

    const sortedServices = Object.entries(serviceCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);

    const serviceContainer = document.getElementById('top-services-list');
    if (serviceContainer && sortedServices.length > 0) {
        const total = leads.length;
        let html = '';
        sortedServices.forEach(([name, count]) => {
            const pct = Math.round((count / total) * 100);
            const estVal = count * 750;
            html += `
                <div class="agency-list-row">
                    <div class="agency-list-meta">
                        <div class="agency-list-icon-box">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                        </div>
                        <span class="agency-list-name">${escapeHtml(name)}</span>
                    </div>
                    <div class="agency-list-bar-track"><div class="agency-list-bar-fill" style="width: ${pct}%;"></div></div>
                    <span class="agency-list-val">$${estVal.toLocaleString()}</span>
                </div>
            `;
        });
        serviceContainer.innerHTML = html;
    }
}

async function loadMarkets() {
    try {
        const res = await fetch('/api/markets');
        const markets = await res.json();
        const tbody = document.getElementById('markets-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        markets.forEach((m, idx) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>#${idx + 1}</strong></td>
                <td><strong>${m.country}</strong> (${m.country_code})</td>
                <td>${m.niche}</td>
                <td><span class="badge ${m.opportunity_score >= 80 ? 'badge-cyan' : 'badge-amber'}">${m.opportunity_score}/100</span></td>
                <td>$${m.expected_deal_value.toLocaleString()}</td>
                <td>${m.digital_weakness}/100</td>
                <td style="font-size:0.82rem; color:var(--text-muted);">${m.reasoning}</td>
            `;
            tbody.appendChild(tr);
        });

        // Also check if a prospecting cycle is currently running or completed
        pollProspectingStatus(false);
    } catch (e) {
        console.error('Error loading markets:', e);
    }
}

// ==============================================================================
// Autonomous Prospecting Engine Controller (Dashboard Canonical Surface)
// ==============================================================================
let prospectingPollInterval = null;

async function handleRunProspectingCycle(event) {
    if (event) event.preventDefault();

    // 1. Gather selected countries
    const countryCheckboxes = document.querySelectorAll('input[name="country"]:checked');
    const selectedCountries = Array.from(countryCheckboxes).map(cb => cb.value);
    if (selectedCountries.length === 0) {
        alert('Please select at least one target country.');
        return;
    }

    // 2. Gather selected niches
    const nicheCheckboxes = document.querySelectorAll('input[name="niche"]:checked');
    const selectedNiches = Array.from(nicheCheckboxes).map(cb => cb.value);
    if (selectedNiches.length === 0) {
        alert('Please select at least one target niche.');
        return;
    }

    // 3. Gather cities, min value, and max results
    const citiesInput = document.getElementById('target-cities-input').value.trim();
    const cities = citiesInput ? citiesInput.split(',').map(c => c.trim()).filter(Boolean) : [];
    if (cities.length === 0) {
        alert('Please enter at least one city or metropolitan area.');
        return;
    }

    const minVal = parseFloat(document.getElementById('target-min-value-input').value) || 500.0;
    if (minVal < 500) {
        alert('Commercial Minimum Floor: Total estimated value must be at least $500+.');
        return;
    }

    const maxResults = parseInt(document.getElementById('target-max-prospects-input').value) || 10;

    const btn = document.getElementById('btn-run-prospecting');
    const btnIcon = document.getElementById('run-btn-icon');
    const btnText = document.getElementById('run-btn-text');

    if (btn) btn.disabled = true;
    if (btnIcon) btnIcon.textContent = '⏳';
    if (btnText) btnText.textContent = 'Queueing Cycle...';

    try {
        const res = await fetch('/api/prospecting/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                countries: selectedCountries,
                cities: cities,
                niches: selectedNiches,
                min_service_value: minVal,
                max_prospects: maxResults,
                provider: 'real'
            })
        });

        const data = await res.json();
        if (!res.ok) {
            alert(`Could not start prospecting cycle: ${data.detail || 'Server error'}`);
            if (btn) btn.disabled = false;
            if (btnIcon) btnIcon.textContent = '⚡';
            if (btnText) btnText.textContent = 'Run Prospecting Cycle';
            return;
        }

        // Reveal Progress Panel and begin polling
        const panel = document.getElementById('prospecting-progress-panel');
        if (panel) panel.style.display = 'block';

        pollProspectingStatus(true);
    } catch (e) {
        console.error('Error starting prospecting cycle:', e);
        alert('Failed to connect to backend prospecting engine: ' + e.message);
        if (btn) btn.disabled = false;
        if (btnIcon) btnIcon.textContent = '⚡';
        if (btnText) btnText.textContent = 'Run Prospecting Cycle';
    }
}

async function pollProspectingStatus(userTriggered = false) {
    if (prospectingPollInterval) {
        clearInterval(prospectingPollInterval);
        prospectingPollInterval = null;
    }

    async function checkStatus() {
        try {
            const res = await fetch('/api/prospecting/status');
            const data = await res.json();
            updateProspectingUI(data);

            if (data.status === 'COMPLETED' || data.status === 'FAILED' || data.status === 'IDLE') {
                if (prospectingPollInterval) {
                    clearInterval(prospectingPollInterval);
                    prospectingPollInterval = null;
                }

                // When complete, automatically refresh Target Prospects and Overview metrics!
                if (data.status === 'COMPLETED') {
                    if (typeof loadDashboardData === 'function') loadDashboardData();
                    if (typeof loadLeads === 'function') loadLeads();
                }
            }
        } catch (e) {
            console.debug('Error polling prospecting status:', e);
        }
    }

    // Run immediate check
    await checkStatus();

    // Start interval if status warrants monitoring
    prospectingPollInterval = setInterval(checkStatus, 1500);
}

function updateProspectingUI(data) {
    const status = data.status || 'IDLE';
    const statusBadge = document.getElementById('job-status-badge');
    const activeIndicator = document.getElementById('job-active-indicator');
    const panel = document.getElementById('prospecting-progress-panel');
    const btn = document.getElementById('btn-run-prospecting');
    const btnIcon = document.getElementById('run-btn-icon');
    const btnText = document.getElementById('run-btn-text');
    const elapsedLabel = document.getElementById('job-time-elapsed');

    if (statusBadge) {
        statusBadge.textContent = status;
        statusBadge.className = 'badge';
        if (status === 'RUNNING') statusBadge.classList.add('badge-cyan');
        else if (status === 'QUEUED') statusBadge.classList.add('badge-amber');
        else if (status === 'COMPLETED') statusBadge.classList.add('badge-emerald');
        else if (status === 'FAILED') statusBadge.classList.add('badge-crimson');
        else statusBadge.classList.add('badge-cyan');
    }

    if (status === 'RUNNING' || status === 'QUEUED') {
        if (panel) panel.style.display = 'block';
        if (activeIndicator) activeIndicator.style.display = 'inline-block';
        if (btn) btn.disabled = true;
        if (btnIcon) btnIcon.textContent = '🔄';
        if (btnText) btnText.textContent = status === 'QUEUED' ? 'Queued...' : 'Prospecting Active...';
        if (elapsedLabel && data.started_at) {
            const secs = Math.round((new Date() - new Date(data.started_at)) / 1000);
            elapsedLabel.textContent = `Running: ${secs}s`;
        }
    } else {
        if (activeIndicator) activeIndicator.style.display = 'none';
        if (btn) btn.disabled = false;
        if (btnIcon) btnIcon.textContent = '⚡';
        if (btnText) btnText.textContent = 'Run Prospecting Cycle';
        if (status === 'COMPLETED' && data.summary) {
            if (elapsedLabel) elapsedLabel.textContent = `Finished in ${data.summary.duration_seconds}s`;
        } else if (status === 'FAILED') {
            if (elapsedLabel) elapsedLabel.textContent = 'Failed';
        }
    }

    // Update Progress Counters
    const prog = data.progress || {};
    const marketsCount = document.getElementById('prog-markets-count');
    const currentMarket = document.getElementById('prog-current-market');
    const currentNiche = document.getElementById('prog-current-niche');
    const discoveredCount = document.getElementById('prog-discovered-count');
    const duplicatesCount = document.getElementById('prog-duplicates-count');
    const junkCount = document.getElementById('prog-junk-count');
    const passingCount = document.getElementById('prog-passing-count');
    const savedCount = document.getElementById('prog-saved-count');
    const messageTicker = document.getElementById('prog-message-ticker');

    if (marketsCount) marketsCount.textContent = (prog.markets_being_searched && prog.markets_being_searched.length) || 0;
    if (currentMarket) currentMarket.textContent = (prog.markets_being_searched && prog.markets_being_searched[0]) || '-';
    if (currentNiche) currentNiche.textContent = prog.current_city_niche || (status === 'COMPLETED' ? 'Done' : 'Standby');
    if (discoveredCount) discoveredCount.textContent = prog.prospects_discovered || 0;
    if (duplicatesCount) duplicatesCount.textContent = prog.duplicates_rejected || 0;
    if (junkCount) junkCount.textContent = prog.junk_rejected || 0;
    if (passingCount) passingCount.textContent = prog.prospects_passing_500 || 0;
    if (savedCount) savedCount.textContent = prog.prospects_saved || 0;
    if (messageTicker) {
        messageTicker.textContent = data.error_message || prog.message || 'Waiting for cycle initiation...';
        if (status === 'FAILED') {
            messageTicker.style.color = '#fb7185';
        } else if (status === 'COMPLETED') {
            messageTicker.style.color = '#34d399';
        } else {
            messageTicker.style.color = 'var(--text-white)';
        }
    }
}

let allLeadsCache = [];

async function loadLeads() {
    try {
        const res = await fetch('/api/leads');
        allLeadsCache = await res.json();

        // Populate filters if empty
        const countrySelect = document.getElementById('leads-filter-country');
        const nicheSelect = document.getElementById('leads-filter-niche');
        if (countrySelect && countrySelect.options.length <= 1) {
            const countries = Array.from(new Set(allLeadsCache.map(l => l.country).filter(Boolean))).sort();
            countries.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c;
                opt.textContent = c;
                countrySelect.appendChild(opt);
            });
        }
        if (nicheSelect && nicheSelect.options.length <= 1) {
            const niches = Array.from(new Set(allLeadsCache.map(l => l.niche).filter(Boolean))).sort();
            niches.forEach(n => {
                const opt = document.createElement('option');
                opt.value = n;
                opt.textContent = n;
                nicheSelect.appendChild(opt);
            });
        }

        filterLeadsTable();
    } catch (e) {
        console.error('Error loading leads:', e);
    }
}

function filterLeadsTable() {
    const search = (document.getElementById('leads-filter-search')?.value || '').trim().toLowerCase();
    const country = document.getElementById('leads-filter-country')?.value || '';
    const niche = document.getElementById('leads-filter-niche')?.value || '';
    const verif = document.getElementById('leads-filter-verification')?.value || '';
    const stage = document.getElementById('leads-filter-stage')?.value || '';

    const filtered = allLeadsCache.filter(l => {
        if (search) {
            const nameMatch = (l.name || '').toLowerCase().includes(search);
            const domainMatch = (l.domain || '').toLowerCase().includes(search);
            const cityMatch = (l.city || '').toLowerCase().includes(search);
            if (!nameMatch && !domainMatch && !cityMatch) return false;
        }
        if (country && (l.country || '').toUpperCase() !== country.toUpperCase()) return false;
        if (niche && (l.niche || '').toLowerCase() !== niche.toLowerCase()) return false;
        if (verif) {
            const v = (l.verification_status || '').toUpperCase();
            if (verif === 'VERIFIED' && v !== 'VERIFIED') return false;
            if (verif === 'NEW' && v !== 'NEW' && v !== 'CANDIDATE') return false;
            if (verif === 'UNVERIFIED' && v !== 'UNVERIFIED') return false;
            if (verif === 'SUPPRESSED' && v !== 'SUPPRESSED') return false;
        }
        if (stage && (l.pipeline_stage || '').toUpperCase() !== stage.toUpperCase()) return false;
        return true;
    });

    const badge = document.getElementById('leads-count-badge');
    if (badge) {
        badge.textContent = `${filtered.length} / ${allLeadsCache.length} Prospects`;
    }

    renderLeadsTable(filtered);
}

function resetLeadsFilters() {
    const s = document.getElementById('leads-filter-search');
    const c = document.getElementById('leads-filter-country');
    const n = document.getElementById('leads-filter-niche');
    const v = document.getElementById('leads-filter-verification');
    const st = document.getElementById('leads-filter-stage');
    if (s) s.value = '';
    if (c) c.value = '';
    if (n) n.value = '';
    if (v) v.value = '';
    if (st) st.value = '';
    filterLeadsTable();
}

function renderLeadsTable(leads) {
    const tbody = document.getElementById('leads-table-body');
    const emptyState = document.getElementById('leads-empty-state');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!leads || leads.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        return;
    }
    if (emptyState) emptyState.style.display = 'none';

    leads.forEach(l => {
        const tr = document.createElement('tr');

        // Verification badge
        let verifClass = 'badge-stage';
        const vStatus = (l.verification_status || 'NEW').toUpperCase();
        if (vStatus === 'VERIFIED') verifClass = 'badge-emerald';
        else if (vStatus === 'SUPPRESSED') verifClass = 'badge-crimson';
        else if (vStatus === 'CANDIDATE' || vStatus === 'NEW') verifClass = 'badge-cyan';
        else if (vStatus === 'UNVERIFIED') verifClass = 'badge-amber';

        // Score display
        const scoreVal = l.prospect_score !== null && l.prospect_score !== undefined
            ? Math.round(l.prospect_score)
            : (l.lead_score !== null && l.lead_score !== undefined ? l.lead_score : null);
        const scoreBadge = scoreVal !== null
            ? `<span class="badge ${scoreVal >= 70 ? 'badge-cyan' : 'badge-amber'}" style="font-family:var(--font-mono); font-weight:700;">${scoreVal}/100</span>`
            : `<span class="badge" style="opacity:0.6; font-size:0.7rem;">PENDING</span>`;

        // Contactability
        const hasEmail = Boolean(l.email && l.email !== 'unknown');
        const contactHtml = hasEmail
            ? `<span class="badge badge-emerald" title="${escapeHtml(l.email)}">✉ Email</span>`
            : `<span class="badge" style="opacity:0.5; font-size:0.7rem;">No Email</span>`;

        // Target offer & recommended service
        const offerVal = l.target_offer ? `$${Number(l.target_offer).toLocaleString()}` : '<span style="color:var(--text-muted); font-size:0.75rem;">$500+ Floor</span>';
        const serviceVal = l.recommended_service ? `<span style="color:var(--hud-cyan-bright); font-size:0.8rem; font-weight:600;">${escapeHtml(l.recommended_service)}</span>` : '<span style="color:var(--text-muted); font-size:0.75rem;">Diagnostics Pending</span>';

        tr.innerHTML = `
            <td>
                <strong>${escapeHtml(l.name)}</strong><br>
                <small style="color:var(--text-muted); font-family:var(--font-mono); font-size:0.75rem;">
                    <a href="${escapeHtml(l.website_url || ('https://' + l.domain))}" target="_blank" style="color:var(--hud-cyan-bright); text-decoration:none;">${escapeHtml(l.domain)} ↗</a>
                </small>
            </td>
            <td>
                <span style="font-weight:600;">${escapeHtml(l.country || '-')}</span><br>
                <small style="color:var(--text-secondary); font-size:0.75rem;">${escapeHtml(l.city || 'Regional')}</small>
            </td>
            <td><span style="font-size:0.82rem;">${escapeHtml(l.niche || 'B2B')}</span></td>
            <td><span class="badge ${verifClass}">${escapeHtml(l.verification_status || 'NEW')}</span></td>
            <td>
                <span style="font-weight:700; color:#38bdf8;">${l.evidence_count || 0} citations</span><br>
                <small style="color:var(--text-muted); font-family:var(--font-mono); font-size:0.72rem;">${Number(l.effective_evidence_score || 0).toFixed(1)}/100</small>
            </td>
            <td>${scoreBadge}</td>
            <td>${contactHtml}</td>
            <td><span class="badge badge-stage">${escapeHtml(l.pipeline_stage || 'DISCOVERED')}</span></td>
            <td>${serviceVal}</td>
            <td><strong style="color:var(--hud-emerald); font-family:var(--font-mono); font-size:0.85rem;">${offerVal}</strong></td>
            <td>
                <button class="btn btn-outline" style="padding:4px 10px; font-size:0.75rem; white-space:nowrap;" onclick="viewLeadDetail(${l.id})">Inspect Dossier</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function viewLeadDetail(leadId) {
    try {
        const res = await fetch(`/api/leads/${leadId}`);
        if (!res.ok) {
            alert('Unable to retrieve prospect detail. Status: ' + res.status);
            return;
        }
        const data = await res.json();
        const modal = document.getElementById('lead-modal');
        const modalBody = document.getElementById('modal-body-content');

        const b = data.business || {};
        const audit = data.audit || {};
        const findings = audit.findings || [];
        const score = data.score || {};
        const offer = data.offer || {};
        const outreach = data.outreach || {};
        const intel = data.client_intelligence || {};
        const evidenceItems = data.evidence_items || [];
        const timeline = data.timeline || [];

        // Score display
        const totalScore = score.total_score !== null && score.total_score !== undefined
            ? score.total_score
            : (b.prospect_score !== null ? Math.round(b.prospect_score) : null);

        // Pain points & Decision trace
        const painPoints = intel.pain_points || [];
        const decisionTrace = intel.decision_trace || (score.rationale ? [score.rationale] : []);

        modalBody.innerHTML = `
            <!-- Header Banner -->
            <div style="border-bottom:1px solid var(--border-subtle); padding-bottom:14px; margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
                    <div>
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                            <span class="badge badge-cyan">PROSPECT COMMERCIAL DOSSIER</span>
                            <span class="badge ${b.verification_status === 'VERIFIED' ? 'badge-emerald' : 'badge-stage'}">${b.verification_status || 'NEW'}</span>
                            <span class="badge badge-stage">${b.pipeline_stage || 'DISCOVERED'}</span>
                        </div>
                        <h2 style="color:#fff; margin:4px 0; font-size:1.35rem; font-family:var(--font-heading);">${escapeHtml(b.name)}</h2>
                        <p style="color:var(--text-muted); font-size:0.86rem; margin:0;">
                            <a href="${escapeHtml(b.website_url || ('https://' + b.domain))}" target="_blank" style="color:var(--hud-cyan-bright); text-decoration:none; font-weight:600;">${escapeHtml(b.domain)} ↗</a>
                            <span style="color:var(--border-subtle); margin:0 6px;">|</span>
                            <span>${escapeHtml(b.niche || 'B2B')} in ${escapeHtml(b.city || 'Regional')}, ${escapeHtml(b.country || '-')}</span>
                            <span style="color:var(--border-subtle); margin:0 6px;">|</span>
                            <span>Contact: <strong style="color:#f1f5f9;">${escapeHtml(b.email || 'None on record')}</strong></span>
                        </p>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; display:block;">Commercial Floor Gate</span>
                        <span class="badge badge-emerald" style="font-family:var(--font-mono); font-size:0.78rem;">$500+ GUARANTEED</span>
                    </div>
                </div>
            </div>

            <!-- Executive KPI Row -->
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; margin-bottom:18px;">
                <div class="kpi-card" style="padding:10px 12px;">
                    <span class="kpi-label">Commercial Score</span>
                    <span class="kpi-value" style="font-size:1.3rem; color:${totalScore >= 70 ? 'var(--hud-cyan-bright)' : 'var(--hud-amber)'};">${totalScore !== null ? totalScore + '/100' : 'Pending'}</span>
                    <span class="badge ${score.priority === 'A' ? 'badge-cyan' : 'badge-amber'}" style="font-size:0.68rem;">Priority ${score.priority || 'B'}</span>
                </div>
                <div class="kpi-card" style="padding:10px 12px;">
                    <span class="kpi-label">Website Health</span>
                    <span class="kpi-value" style="font-size:1.3rem;">${audit.overall_health !== null && audit.overall_health !== undefined ? audit.overall_health + '/100' : 'N/A'}</span>
                    <span class="kpi-sub">${findings.length} Actionable Items</span>
                </div>
                <div class="kpi-card" style="padding:10px 12px;">
                    <span class="kpi-label">Empirical Evidence</span>
                    <span class="kpi-value" style="font-size:1.3rem; color:#38bdf8;">${evidenceItems.length || b.evidence_count || 0}</span>
                    <span class="kpi-sub">Score: ${Number(b.effective_evidence_score || 0).toFixed(1)}/100</span>
                </div>
                <div class="kpi-card" style="padding:10px 12px;">
                    <span class="kpi-label">Target Contract</span>
                    <span class="kpi-value highlight-emerald" style="font-size:1.3rem;">$${(intel.target_price_usd || offer.recommended_price || 1500).toLocaleString()}</span>
                    <span class="kpi-sub">Commercial Service</span>
                </div>
            </div>

            <!-- 6-Vector Diagnostic Health -->
            <div style="margin-bottom:18px; background:rgba(15,23,42,0.6); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:0.72rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">6-VECTOR TECHNICAL DIAGNOSTICS:</span>
                    <span style="font-size:0.7rem; color:var(--hud-cyan-bright); font-family:var(--font-mono);">AUDIT STATUS: ${audit.overall_health ? 'COMPLETED' : 'STANDBY'}</span>
                </div>
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap:6px;">
                    <div style="background:rgba(2,6,23,0.5); padding:6px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                        <span style="font-size:0.68rem; color:var(--text-muted); display:block;">Speed</span>
                        <strong style="font-size:0.95rem; font-family:var(--font-mono); color:#f1f5f9;">${audit.performance ?? 'N/A'}/100</strong>
                    </div>
                    <div style="background:rgba(2,6,23,0.5); padding:6px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                        <span style="font-size:0.68rem; color:var(--text-muted); display:block;">SEO</span>
                        <strong style="font-size:0.95rem; font-family:var(--font-mono); color:#f1f5f9;">${audit.seo ?? 'N/A'}/100</strong>
                    </div>
                    <div style="background:rgba(2,6,23,0.5); padding:6px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                        <span style="font-size:0.68rem; color:var(--text-muted); display:block;">Accessibility</span>
                        <strong style="font-size:0.95rem; font-family:var(--font-mono); color:#f1f5f9;">${audit.accessibility ?? 'N/A'}/100</strong>
                    </div>
                    <div style="background:rgba(2,6,23,0.5); padding:6px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                        <span style="font-size:0.68rem; color:var(--text-muted); display:block;">UX / CRO</span>
                        <strong style="font-size:0.95rem; font-family:var(--font-mono); color:#f1f5f9;">${audit.ux_conversion ?? 'N/A'}/100</strong>
                    </div>
                    <div style="background:rgba(2,6,23,0.5); padding:6px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                        <span style="font-size:0.68rem; color:var(--text-muted); display:block;">Security</span>
                        <strong style="font-size:0.95rem; font-family:var(--font-mono); color:#f1f5f9;">${audit.security ?? 'N/A'}/100</strong>
                    </div>
                    <div style="background:rgba(2,6,23,0.5); padding:6px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04); text-align:center;">
                        <span style="font-size:0.68rem; color:var(--text-muted); display:block;">Content</span>
                        <strong style="font-size:0.95rem; font-family:var(--font-mono); color:#f1f5f9;">${audit.content ?? 'N/A'}/100</strong>
                    </div>
                </div>
            </div>

            <!-- Client Intelligence & Pain Diagnosis -->
            <div class="panel-card" style="margin-bottom:18px; border-color:rgba(56, 189, 248, 0.3); background:rgba(9, 14, 26, 0.8);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-size:1.05rem;">🧠</span>
                        <strong style="color:var(--hud-cyan-bright); font-size:0.9rem;">Client Intelligence & Problem Diagnosis</strong>
                    </div>
                    <span class="badge badge-emerald">MATCH FIT: ${intel.fit_score ? Math.round(intel.fit_score * 100) + '%' : 'OPTIMAL'}</span>
                </div>
                
                <!-- Pain Points -->
                <div style="margin-bottom:12px;">
                    <span style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; display:block; margin-bottom:6px;">Diagnosed Commercial Problems:</span>
                    <div style="display:flex; flex-wrap:wrap; gap:6px;">
                        ${painPoints.length > 0 ? painPoints.map(p => `
                            <span class="badge badge-amber" style="padding:4px 8px; font-size:0.75rem;">⚠ ${escapeHtml(p)}</span>
                        `).join('') : '<span style="color:var(--text-muted); font-size:0.8rem; font-style:italic;">No acute operational pain logged yet.</span>'}
                    </div>
                </div>

                <!-- Recommended Service & ROI -->
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:10px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.05);">
                    <div>
                        <span style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; display:block;">Recommended Service Offering:</span>
                        <strong style="color:var(--hud-emerald); font-size:0.9rem;">${escapeHtml(intel.top_service_name || offer.title || 'Technical Turnaround & AI Integration')}</strong>
                        <p style="font-size:0.78rem; color:var(--text-secondary); margin:4px 0 0 0;">${escapeHtml(offer.value_prop || 'Remediates critical website speed, SEO and conversion bottlenecks to capture lost commercial inquiries.')}</p>
                    </div>
                    <div>
                        <span style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; display:block;">ROI & Economic Value Hypothesis:</span>
                        <strong style="color:var(--hud-amber); font-size:0.88rem;">${intel.roi_estimate && intel.roi_estimate.summary ? escapeHtml(intel.roi_estimate.summary) : (intel.roi_estimate ? escapeHtml(JSON.stringify(intel.roi_estimate)) : 'Expected to restore 15–30% lost commercial pipeline through technical remediation.')}</strong>
                    </div>
                </div>
            </div>

            <!-- Key Technical Findings -->
            <h3 style="font-size:0.88rem; margin-bottom:8px; color:var(--text-white);">Technical Audit Findings (${findings.length})</h3>
            <div style="max-height:160px; overflow-y:auto; border:1px solid var(--border-subtle); border-radius:6px; padding:12px; margin-bottom:18px; background:var(--bg-card-inner);">
                ${findings.length > 0 ? findings.map(f => `
                    <div style="margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                            <strong style="color:#fff; font-size:0.84rem;">[${escapeHtml(f.category)}] ${escapeHtml(f.finding)}</strong>
                            <span class="badge ${f.severity === 'CRITICAL' ? 'badge-crimson' : (f.severity === 'HIGH' ? 'badge-amber' : 'badge-cyan')}">${escapeHtml(f.severity)}</span>
                        </div>
                        <p style="font-size:0.8rem; color:var(--text-muted); margin:3px 0;">Evidence: ${escapeHtml(f.evidence)}</p>
                        <p style="font-size:0.8rem; color:var(--hud-emerald);">Fix: ${escapeHtml(f.recommended_fix)}</p>
                    </div>
                `).join('') : '<p style="color:var(--text-muted); font-size:0.84rem; margin:0;">No critical findings recorded for this website.</p>'}
            </div>

            <!-- Empirical Evidence Citations -->
            <div style="margin-bottom:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-size:1.05rem;">📜</span>
                        <h3 style="font-size:0.88rem; margin:0; color:var(--text-white);">Empirical Evidence Dossier (${evidenceItems.length} Citations)</h3>
                    </div>
                    <span class="badge badge-cyan" style="font-size:0.7rem;">PROVENANCE VERIFIED</span>
                </div>
                <div class="evidence-citation-list" style="max-height:180px; overflow-y:auto;">
                    ${evidenceItems.length > 0 ? evidenceItems.map(ev => `
                        <div class="evidence-citation-item">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; margin-bottom:4px;">
                                <strong style="color:#f1f5f9; font-size:0.82rem;">${escapeHtml(ev.claim)}</strong>
                                <div style="display:flex; gap:4px; flex-shrink:0;">
                                    <span class="badge badge-cyan" style="font-size:0.65rem;">${escapeHtml(ev.source_tier || 'Tier 2')}</span>
                                    <span class="badge badge-emerald" style="font-size:0.65rem;">${Math.round((ev.confidence_score || 0.8) * 100)}% CONF</span>
                                </div>
                            </div>
                            <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:4px;">
                                Publisher: <span style="color:#e2e8f0;">${escapeHtml(ev.publisher || ev.source_domain || 'Web Audit')}</span>
                                ${ev.raw_excerpt ? ` | Excerpt: <em>"${escapeHtml(ev.raw_excerpt.slice(0, 120))}"</em>` : ''}
                            </div>
                            ${ev.source_url ? `
                                <div>
                                    <a href="${escapeHtml(ev.source_url)}" target="_blank" style="font-size:0.72rem; color:var(--hud-cyan-bright); text-decoration:none; font-family:var(--font-mono);">
                                        🔗 ${escapeHtml(ev.source_url.slice(0, 70))}${ev.source_url.length > 70 ? '...' : ''}
                                    </a>
                                </div>
                            ` : ''}
                        </div>
                    `).join('') : '<div style="color:var(--text-muted); font-size:0.8rem; font-style:italic; padding:12px; background:rgba(15,23,42,0.4); border-radius:6px;">No empirical evidence records linked to this prospect yet.</div>'}
                </div>
            </div>

            <!-- Turnkey Demo & Deterministic QA Gates (Phase 19) -->
            <div style="margin-bottom:18px; background:rgba(15,23,42,0.8); border:1px solid ${data.demo ? (data.demo.qa?.overall_passed ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)') : 'var(--border-subtle)'}; border-radius:8px; padding:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:1.15rem;">🚀</span>
                        <h3 style="font-size:0.95rem; margin:0; color:var(--text-white);">Turnkey Demo & Deterministic QA Gates</h3>
                        <span class="badge" style="background:rgba(56,189,248,0.15); color:var(--hud-cyan-bright); border:1px solid rgba(56,189,248,0.3); font-size:0.68rem;">[DRY-RUN SAFE]</span>
                    </div>
                    ${data.demo ? `
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span class="badge ${data.demo.qa?.overall_passed ? 'badge-emerald' : 'badge-crimson'}" style="font-weight:700; font-size:0.75rem;">
                                ${data.demo.qa?.overall_passed ? '✓ ALL 8 QA GATES PASSED' : '✗ QA GATES FAILED'}
                            </span>
                            <button class="btn btn-sm btn-cyan" onclick="openDemoPreview(${b.id})" style="display:inline-flex; align-items:center; gap:5px; padding:4px 10px; font-size:0.75rem;">
                                <span>🔍</span> Preview Turnkey Demo
                            </button>
                        </div>
                    ` : ''}
                </div>

                ${data.demo ? `
                    <div style="display:grid; grid-template-columns: 2fr 1fr; gap:12px; margin-bottom:12px;">
                        <div style="background:rgba(2,6,23,0.5); padding:10px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
                            <div style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; margin-bottom:4px;">Demo Package Metadata</div>
                            <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:3px;">
                                <span style="color:var(--text-muted);">Demo ID:</span>
                                <strong style="color:var(--hud-cyan-bright); font-family:var(--font-mono);">${escapeHtml(data.demo.demo_id || '')}</strong>
                            </div>
                            <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:3px;">
                                <span style="color:var(--text-muted);">Service Scope:</span>
                                <strong style="color:#f1f5f9;">${escapeHtml(data.demo.service_title || 'Speed & Conversion Turnaround')}</strong>
                            </div>
                            <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:3px;">
                                <span style="color:var(--text-muted);">Catalog Value:</span>
                                <strong style="color:var(--hud-emerald);">$${Number(data.demo.price_usd || 0).toLocaleString()} (Min $500 Guaranteed)</strong>
                            </div>
                            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                                <span style="color:var(--text-muted);">QA Signature:</span>
                                <span style="color:#94a3b8; font-family:var(--font-mono); font-size:0.72rem;">${escapeHtml(data.demo.qa?.qa_signature || 'N/A')}</span>
                            </div>
                        </div>

                        <div style="background:rgba(2,6,23,0.5); padding:10px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.05); display:flex; flex-direction:column; justify-content:center; text-align:center;">
                            <span style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Deterministic QA Status</span>
                            <div style="font-size:1.35rem; font-weight:800; font-family:var(--font-mono); color:${data.demo.qa?.overall_passed ? 'var(--hud-emerald)' : 'var(--hud-crimson)'}; margin:4px 0;">
                                ${data.demo.qa?.passed_checks || 0} / ${data.demo.qa?.total_checks || 8} PASSED
                            </div>
                            <span style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">ZERO PLACEHOLDERS • ZERO FABRICATIONS</span>
                        </div>
                    </div>

                    <!-- 8 Deterministic Quality Gates Table -->
                    <div style="background:rgba(2,6,23,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; overflow:hidden;">
                        <div style="padding:6px 10px; background:rgba(255,255,255,0.03); border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.72rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; display:flex; justify-content:space-between;">
                            <span>8 Deterministic Quality Assurance Gates</span>
                            <span>Standard: Zero Hallucination</span>
                        </div>
                        <div style="max-height:220px; overflow-y:auto;">
                            ${(data.demo.qa?.checks || []).map(chk => `
                                <div style="display:flex; justify-content:space-between; align-items:center; padding:7px 10px; border-bottom:1px solid rgba(255,255,255,0.03); font-size:0.78rem;">
                                    <div style="display:flex; align-items:center; gap:8px; min-width:0;">
                                        <span class="badge ${chk.passed ? 'badge-emerald' : 'badge-crimson'}" style="font-size:0.65rem; padding:1px 6px; font-weight:700;">
                                            ${chk.passed ? 'PASS' : 'FAIL'}
                                        </span>
                                        <span style="font-family:var(--font-mono); font-size:0.75rem; color:#f1f5f9; font-weight:600;">${escapeHtml(chk.name)}</span>
                                        <span style="color:var(--text-muted); font-size:0.74rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">- ${escapeHtml(chk.details)}</span>
                                    </div>
                                    <span style="font-size:0.85rem; margin-left:8px;">${chk.passed ? '✅' : '❌'}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : `
                    <div style="padding:16px; background:rgba(2,6,23,0.4); border-radius:6px; text-align:center; color:var(--text-muted); font-size:0.82rem;">
                        <span style="font-size:1.3rem; display:block; margin-bottom:6px;">📦</span>
                        Turnkey demo package not yet generated for this prospect.
                        <div style="font-size:0.74rem; color:#64748b; margin-top:4px;">(Turnkey demos and 8 deterministic QA gates are automatically synthesized upon receiving an INTERESTED prospect reply)</div>
                    </div>
                `}

                <!-- Commercial Proposal & Dry-Run Payment Handoff (if available) -->
                ${data.proposal ? `
                    <div style="margin-top:12px; background:rgba(16,185,129,0.05); border:1px solid rgba(16,185,129,0.2); border-radius:6px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                        <div>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span style="font-size:0.9rem;">💼</span>
                                <strong style="color:var(--text-white); font-size:0.82rem;">Proposal #${data.proposal.id}: ${escapeHtml(data.proposal.title || 'Turnaround Proposal')}</strong>
                                <span class="badge badge-cyan" style="font-size:0.65rem;">STAGE: PROPOSAL</span>
                                <span class="badge badge-amber" style="font-size:0.65rem;">[DRY-RUN SAFE]</span>
                            </div>
                            <div style="font-size:0.74rem; color:var(--text-muted); margin-top:2px;">
                                Value: <strong style="color:var(--hud-emerald);">$${Number(data.proposal.total_value || 0).toLocaleString()}</strong> |
                                Advance Deposit: <strong style="color:#38bdf8;">$${Number(data.proposal.advance_required || 0).toLocaleString()}</strong> |
                                Status: <span style="color:#f1f5f9;">${escapeHtml(data.proposal.status || 'PENDING_AUTHORIZATION')}</span>
                            </div>
                        </div>
                        <div>
                            <span class="badge badge-emerald" style="font-size:0.72rem; font-family:var(--font-mono);">PAYMENT HANDOFF READY</span>
                        </div>
                    </div>
                ` : ''}
            </div>

            <!-- Autonomous Decision Trace -->
            <div style="margin-bottom:18px;">
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:8px;">
                    <span style="font-size:1.05rem;">🤖</span>
                    <h3 style="font-size:0.88rem; margin:0; color:var(--text-white);">Autonomous Decision Trace</h3>
                </div>
                <div class="decision-trace-card">
                    <div style="display:flex; flex-direction:column; gap:6px;">
                        ${decisionTrace.length > 0 ? decisionTrace.map(dt => `
                            <div class="trace-bullet">
                                <span class="trace-bullet-icon">▸</span>
                                <span>${escapeHtml(typeof dt === 'string' ? dt : JSON.stringify(dt))}</span>
                            </div>
                        `).join('') : `
                            <div class="trace-bullet">
                                <span class="trace-bullet-icon">▸</span>
                                <span>Prospect identified in high-intent niche ${escapeHtml(b.niche || 'B2B')}. Audit confirmed actionable optimization vectors.</span>
                            </div>
                        `}
                    </div>
                </div>
            </div>

            <!-- Event Timeline -->
            <div style="margin-bottom:8px;">
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">
                    <span style="font-size:1.05rem;">⏱</span>
                    <h3 style="font-size:0.88rem; margin:0; color:var(--text-white);">Pipeline Event Timeline</h3>
                </div>
                <div class="timeline-container">
                    ${timeline.length > 0 ? timeline.map(ev => `
                        <div class="timeline-item">
                            <div class="timeline-dot"></div>
                            <div class="timeline-content">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
                                    <strong style="color:var(--hud-cyan-bright); font-size:0.8rem;">${escapeHtml(ev.from_stage || 'START')} → ${escapeHtml(ev.to_stage || 'CURRENT')}</strong>
                                    <span class="timeline-time">${ev.created_at ? new Date(ev.created_at).toLocaleString() : ''}</span>
                                </div>
                                <p style="font-size:0.78rem; color:var(--text-secondary); margin:2px 0 0 0;">${escapeHtml(ev.note || 'Pipeline stage transition recorded.')}</p>
                            </div>
                        </div>
                    `).join('') : `
                        <div class="timeline-item">
                            <div class="timeline-dot"></div>
                            <div class="timeline-content">
                                <strong style="color:var(--hud-cyan-bright); font-size:0.8rem;">STAGE: ${escapeHtml(b.pipeline_stage || 'DISCOVERED')}</strong>
                                <p style="font-size:0.78rem; color:var(--text-secondary); margin:2px 0 0 0;">Record created and queued for autonomous qualification.</p>
                            </div>
                        </div>
                    `}
                </div>
            </div>
        `;

        modal.classList.add('active');
    } catch (e) {
        console.error('Error fetching lead detail:', e);
    }
}

async function viewAuditReport(businessId) {
    if (!businessId) {
        alert('Diagnostic audit report not found for this record.');
        return;
    }
    try {
        const res = await fetch(`/api/reports/audit/${businessId}`);
        if (!res.ok) {
            alert('Unable to load delivery report. Status: ' + res.status);
            return;
        }
        const data = await res.json();
        const modal = document.getElementById('lead-modal');
        const modalBody = document.getElementById('modal-body-content');

        modalBody.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-subtle); padding-bottom:12px; margin-bottom:16px; flex-wrap:wrap; gap:8px;">
                <div>
                    <span class="badge badge-cyan">CLIENT DELIVERABLE</span>
                    <h2 style="color:#fff; margin-top:4px; font-size:1.15rem;">Technical Remediation Deliverable</h2>
                </div>
                <button class="btn btn-primary" onclick="navigator.clipboard.writeText(document.getElementById('report-text-content').innerText); alert('Audit report copied to clipboard!');">📋 Copy Packet</button>
            </div>
            <div id="report-text-content" style="background:var(--bg-card-inner); padding:16px; border-radius:6px; border:1px solid var(--border-subtle); max-height:60vh; overflow-y:auto; font-family:var(--font-mono); font-size:0.82rem; color:var(--text-secondary); white-space:pre-wrap; line-height:1.6;">${data.markdown || 'No report content generated.'}</div>
        `;
        modal.classList.add('active');
    } catch (e) {
        alert('Error fetching delivery report: ' + e);
    }
}

function closeModal() {
    const modal = document.getElementById('lead-modal');
    if (modal) modal.classList.remove('active');
}

async function loadQueue() {
    try {
        // Fetch Real Database Outreach Metrics
        try {
            const mRes = await fetch('/api/outreach/delivery-metrics');
            if (mRes.ok) {
                const metrics = await mRes.json();
                const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v; };
                setVal('kpi-outreach-pending', metrics.outreach_pending_approval ?? 0);
                setVal('kpi-outreach-approved', metrics.outreach_approved ?? 0);
                setVal('kpi-outreach-sent', metrics.outreach_sent ?? 0);
                setVal('kpi-outreach-failed', metrics.outreach_failed ?? 0);
                setVal('kpi-outreach-replies', metrics.replies_in_human_review ?? 0);
                setVal('kpi-outreach-takeover', metrics.human_takeovers_active ?? 0);

                const badge = document.getElementById('provider-status-badge');
                if (badge) {
                    const dryRun = metrics.dry_run_enabled ? 'MOCK / DRY-RUN' : 'LIVE';
                    badge.innerText = `PROVIDER: ${metrics.active_provider.toUpperCase()} (${dryRun})`;
                    badge.className = metrics.dry_run_enabled ? 'badge badge-cyan' : 'badge badge-success';
                }
            }
        } catch (mErr) {
            console.warn('Could not load delivery metrics:', mErr);
        }

        const res = await fetch('/api/queue');
        const queue = await res.json();
        const container = document.getElementById('queue-cards-container');
        if (!container) return;
        container.innerHTML = '';

        if (queue.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding:36px 16px; color:var(--text-muted); font-size:0.88rem;">No outreach messages pending authorization. Run a prospecting cycle to generate new proposals.</div>';
            return;
        }

        queue.forEach(item => {
            const card = document.createElement('div');
            card.className = 'panel-card';
            card.innerHTML = `
                <div class="panel-header">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <strong style="color:#fff; font-size:0.92rem;">${item.business_name}</strong>
                        <span style="color:var(--hud-cyan-bright); font-family:var(--font-mono); font-size:0.8rem;">(${item.domain})</span>
                        <span class="badge badge-cyan">Score: ${item.lead_score}/100</span>
                    </div>
                    <div>
                        <span class="badge badge-stage">${item.recommended_service} ($${item.recommended_price})</span>
                    </div>
                </div>
                <p style="font-size:0.84rem; margin-bottom:4px;"><strong style="color:var(--text-muted);">To:</strong> <span style="color:var(--text-white); font-family:var(--font-mono);">${item.recipient_email}</span></p>
                <p style="font-size:0.84rem; margin-bottom:10px;"><strong style="color:var(--text-muted);">Subject:</strong> <span style="color:var(--text-white);">${item.subject}</span></p>
                <div style="background:var(--bg-card-inner); padding:12px; border-radius:6px; margin-bottom:14px; max-height:140px; overflow-y:auto; font-size:0.82rem; color:var(--text-secondary); white-space:pre-wrap; font-family:var(--font-mono); border:1px solid var(--border-subtle);">
                    ${item.body}
                </div>
                <div style="display:flex; gap:10px; flex-wrap:wrap;">
                    <button class="btn btn-secondary" onclick="approveMessage(${item.message_id}, false)">✓ Simulate Send</button>
                    <button class="btn btn-success" onclick="approveMessage(${item.message_id}, true)">🚀 Approve & Send Live</button>
                    <button class="btn btn-danger" onclick="rejectMessage(${item.message_id})">✕ Reject</button>
                    <button class="btn btn-outline" onclick="viewLeadDetail(${item.business_id})">Inspect Audit</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error('Error loading queue:', e);
    }
}

async function approveMessage(msgId, forceLive = false) {
    if (forceLive) {
        if (!confirm(`CONFIRM LIVE OUTREACH:\nAre you sure you want to send a REAL live email for Message #${msgId}?`)) return;
    }
    try {
        const res = await fetch(`/api/queue/${msgId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force_live: forceLive })
        });
        const data = await res.json();
        if (res.ok) {
            const modeText = forceLive ? 'LIVE' : 'SIMULATED';
            alert(`Message #${msgId} approved! [${modeText}] ${data.send_result ? 'Event: ' + data.send_result.event : ''}`);
            loadQueue();
            loadDashboardMetrics();
        } else {
            alert(`Approval failed: ${data.detail || JSON.stringify(data)}`);
        }
    } catch (e) {
        alert('Error approving message: ' + e);
    }
}

async function rejectMessage(msgId) {
    try {
        await fetch(`/api/queue/${msgId}/reject`, { method: 'POST' });
        alert('Message rejected.');
        loadQueue();
        loadDashboardMetrics();
    } catch (e) {
        alert('Error rejecting: ' + e);
    }
}

async function loadPipeline() {
    try {
        const res = await fetch('/api/leads');
        const leads = await res.json();
        const stages = ['DISCOVERED', 'VERIFIED', 'AUDITED', 'QUALIFIED', 'APPROVAL', 'CONTACTED', 'QUALIFIED_REPLY', 'WON'];
        
        stages.forEach(stage => {
            const col = document.getElementById(`kanban-${stage}`);
            if (col) {
                const stageLeads = leads.filter(l => l.pipeline_stage === stage);
                col.innerHTML = `
                    <div class="kanban-col-title">
                        <span>${stage}</span>
                        <span>${stageLeads.length}</span>
                    </div>
                    ${stageLeads.map(l => `
                        <div class="kanban-card" onclick="viewLeadDetail(${l.id})">
                            <strong style="font-size:0.84rem; color:#fff;">${l.name}</strong>
                            <small style="color:var(--text-muted);">${l.niche}</small>
                            <span class="badge ${l.priority === 'A' ? 'badge-cyan' : 'badge-amber'}" style="align-self:flex-start;">
                                ${l.lead_score ? l.lead_score + '/100' : 'Pending'}
                            </span>
                        </div>
                    `).join('')}
                `;
            }
        });
    } catch (e) {
        console.error('Error loading pipeline:', e);
    }
}

async function loadRuns() {
    try {
        const res = await fetch('/api/runs');
        const runs = await res.json();
        const tbody = document.getElementById('runs-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        runs.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code style="color:var(--hud-cyan-bright);">${r.run_id}</code></td>
                <td><strong>${r.job_name}</strong></td>
                <td><span class="badge badge-emerald">${r.status}</span></td>
                <td>${r.records_processed}</td>
                <td>${r.duration_seconds}s</td>
                <td>${r.started_at ? new Date(r.started_at).toLocaleTimeString() : ''}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading runs:', e);
    }
}

async function runAutonomousCycle() {
    const btn = document.getElementById('btn-run-cycle');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⚡</span><span>Running Cycle...</span>';
    }
    try {
        const res = await fetch('/api/run-cycle', { method: 'POST' });
        const data = await res.json();
        alert(`Prospecting cycle completed in ${data.duration_seconds}s! Discovered: ${data.new_leads_discovered}, Audited: ${data.websites_audited}, Scored: ${data.leads_scored}, Queued: ${data.outreach_queued_for_approval}`);
        loadDashboardMetrics();
        loadPriorityProspects();
        loadMarkets();
        loadLeads();
        loadQueue();
        loadPipeline();
        loadRuns();
    } catch (e) {
        alert('Error triggering cycle: ' + e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>⚡</span><span>Run Prospecting Cycle</span>';
        }
    }
}

function updateRecentMessages(replies) {
    const list = document.getElementById('recent-messages-list');
    if (!list) return;
    if (!replies || replies.length === 0) return;

    const recent = replies.slice(0, 4);
    const colors = ['#475569', '#6d28d9', '#047857', '#b45309'];
    let html = '';

    recent.forEach((r, idx) => {
        const name = r.business_name || r.sender_name || 'Prospect';
        const initials = name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase() || 'P';
        const subject = r.classification || r.subject || 'Inbound reply';
        const color = colors[idx % colors.length];

        html += `
            <div class="agency-inbox-row" onclick="navToView('replies')">
                <div class="agency-inbox-avatar" style="background:${color};">${initials}</div>
                <div class="agency-inbox-meta">
                    <div class="agency-inbox-sender">${escapeHtml(name)}</div>
                    <div class="agency-inbox-snippet">${escapeHtml(subject)}</div>
                </div>
                <span class="agency-inbox-time">Recent</span>
            </div>
        `;
    });
    list.innerHTML = html;
}

async function loadReplies() {
    try {
        const [repliesRes, memoriesRes] = await Promise.all([
            fetch('/api/replies'),
            fetch('/api/memory/prospects')
        ]);
        const replies = await repliesRes.json();
        const memories = memoriesRes.ok ? await memoriesRes.json() : [];
        const memMap = {};
        memories.forEach(m => { memMap[m.business_id] = m; });

        if (Array.isArray(replies)) {
            updateRecentMessages(replies);
        }

        const tbody = document.getElementById('replies-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (replies.length === 0 && memories.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:32px;">No inbound prospect signals recorded yet.</td></tr>';
            return;
        }

        replies.forEach(r => {
            const tr = document.createElement('tr');
            const mem = memMap[r.business_id] || {};
            let badgeClass = 'badge-amber';
            if (['INTERESTED', 'MEETING_REQUEST', 'PRICE_REQUEST'].includes(r.classification)) {
                badgeClass = 'badge-emerald';
            } else if (['UNSUBSCRIBE', 'BOUNCE', 'NOT_INTERESTED'].includes(r.classification)) {
                badgeClass = 'badge-crimson';
            } else if (r.classification === 'OBJECTION') {
                badgeClass = 'badge-amber';
            }

            const objections = mem.objection_categories || [];
            const objectionBadges = objections.length > 0
                ? objections.map(o => `<span class="badge badge-amber" style="font-size:0.7rem; margin:2px 2px 0 0;">${o}</span>`).join('')
                : '<span style="color:var(--text-muted); font-size:0.75rem;">None</span>';

            const targetVal = mem.estimated_value ? `$${mem.estimated_value.toLocaleString()}` : '$1,000';
            const actionText = mem.recommended_action || 'AWAITING_REVIEW';
            const isTakeover = mem.human_takeover || false;

            tr.innerHTML = `
                <td>
                    <strong>${r.business_name}</strong><br>
                    <span style="color:var(--text-muted); font-size:0.8rem;">${r.sender_email}</span><br>
                    <span class="badge" style="background:#1e293b; color:#94a3b8; font-size:0.7rem;">${mem.pipeline_stage || 'REPLIED'}</span>
                    ${isTakeover ? '<span class="badge badge-crimson" style="font-size:0.7rem; margin-left:4px;">👤 TAKEOVER</span>' : ''}
                </td>
                <td>
                    <span class="badge ${badgeClass}">${r.classification}</span>
                    <div style="margin-top:6px;">${objectionBadges}</div>
                </td>
                <td>
                    <strong style="color:#10b981;">${targetVal} USD</strong><br>
                    <span style="font-size:0.72rem; color:var(--text-muted);">Floor: $500</span>
                </td>
                <td style="max-width:200px; word-break:break-word; font-size:0.82rem;">"${r.raw_body}"</td>
                <td style="max-width:240px; word-break:break-word; font-size:0.82rem;">
                    <div style="font-style:italic; color:var(--text-secondary); margin-bottom:6px;">${r.suggested_response || mem.draft_response || 'Pending draft formulation...'}</div>
                    <span class="badge" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:0.72rem;">🎯 ${actionText}</span>
                </td>
                <td>
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <div style="display:flex; gap:4px;">
                            <button class="btn btn-sm btn-success" style="padding:3px 8px; font-size:0.75rem;" onclick="handleMemoryDecision(${r.business_id}, 'APPROVE')">✓ Approve</button>
                            <button class="btn btn-sm btn-secondary" style="padding:3px 8px; font-size:0.75rem;" onclick="handleMemoryDecision(${r.business_id}, 'EDIT')">✏️ Edit</button>
                        </div>
                        <div style="display:flex; gap:4px;">
                            <button class="btn btn-sm btn-danger" style="padding:3px 8px; font-size:0.75rem;" onclick="handleMemoryDecision(${r.business_id}, 'REJECT')">⛔ Reject</button>
                            <button class="btn btn-sm btn-warning" style="padding:3px 8px; font-size:0.75rem;" onclick="handleMemoryDecision(${r.business_id}, 'TAKE_OVER')">👤 Take Over</button>
                        </div>
                        <button class="btn btn-sm btn-outline-info" style="padding:3px 8px; font-size:0.75rem; margin-top:2px;" onclick="showProspectMemoryModal(${r.business_id})">📜 30s Context</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading replies & memory cockpit:', e);
    }
}

async function handleMemoryDecision(businessId, decision) {
    let editedText = null;
    if (decision === 'EDIT') {
        editedText = prompt('Enter your revised response text for this prospect:');
        if (!editedText) return;
    } else if (decision === 'TAKE_OVER') {
        if (!confirm('Take over manual communication with this prospect? Automated messaging will be permanently locked.')) return;
    }

    try {
        const res = await fetch(`/api/memory/prospects/${businessId}/decide`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision, edited_text: editedText, operator: 'owner' })
        });
        const result = await res.json();
        if (res.ok) {
            alert(`✓ Decision '${decision}' recorded successfully.`);
            loadReplies();
        } else {
            alert(`Error: ${result.detail || 'Could not record decision.'}`);
        }
    } catch (e) {
        alert(`Network error: ${e.message}`);
    }
}

async function showProspectMemoryModal(businessId) {
    try {
        const res = await fetch(`/api/memory/prospects/${businessId}`);
        if (!res.ok) {
            alert('Could not retrieve prospect memory snapshot.');
            return;
        }
        const snap = await res.json();
        const modal = document.getElementById('memory-context-modal');
        const titleEl = document.getElementById('modal-biz-name');
        const contentEl = document.getElementById('modal-memory-content');

        titleEl.innerHTML = `Commercial Memory Snapshot — ${snap.name} (${snap.domain})`;
        
        const auditFindings = snap.audit && snap.audit.findings ? snap.audit.findings.map(f => `<li>${typeof f === 'object' ? f.title : f}</li>`).join('') : '<li>No critical defects logged</li>';
        const objHistory = snap.objections && snap.objections.history ? snap.objections.history.map(o => `<div style="background:#1e293b; padding:8px; border-radius:4px; margin-bottom:6px; font-size:0.8rem;"><strong>${o.primary}</strong>: ${o.reasoning}<br><span style="color:#94a3b8;">Draft: "${o.draft_response}"</span></div>`).join('') : '<p style="color:#94a3b8; font-size:0.8rem;">No objections recorded.</p>';

        contentEl.innerHTML = `
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px;">
                <div style="background:#090e1a; padding:12px; border-radius:6px; border:1px solid rgba(56,189,248,0.2);">
                    <h4 style="color:#38bdf8; margin:0 0 8px 0; font-size:0.9rem;">🏢 Business & Commercial Scope</h4>
                    <p style="margin:2px 0; font-size:0.82rem;"><strong>Domain:</strong> ${snap.domain}</p>
                    <p style="margin:2px 0; font-size:0.82rem;"><strong>Location:</strong> ${snap.city || ''}, ${snap.country || ''}</p>
                    <p style="margin:2px 0; font-size:0.82rem;"><strong>Pipeline Stage:</strong> <span class="badge badge-emerald">${snap.pipeline_stage}</span></p>
                    <p style="margin:2px 0; font-size:0.82rem;"><strong>Offer Price:</strong> <span style="color:#10b981; font-weight:bold;">$${snap.current_offer.recommended_price.toLocaleString()} USD</span></p>
                    <p style="margin:2px 0; font-size:0.82rem;"><strong>Suppressed / Opt-Out:</strong> ${snap.is_suppressed ? '<span style="color:#f43f5e;">YES</span>' : '<span style="color:#10b981;">NO</span>'}</p>
                </div>
                <div style="background:#090e1a; padding:12px; border-radius:6px; border:1px solid rgba(56,189,248,0.2);">
                    <h4 style="color:#38bdf8; margin:0 0 8px 0; font-size:0.9rem;">🔍 Website Audit Findings</h4>
                    <p style="margin:2px 0; font-size:0.82rem;"><strong>Performance Score:</strong> ${snap.audit.performance_score || 'N/A'}/100</p>
                    <ul style="margin:4px 0 0 16px; font-size:0.78rem; color:#cbd5e1; max-height:80px; overflow-y:auto;">${auditFindings}</ul>
                </div>
            </div>
            <div style="margin-bottom:16px;">
                <h4 style="color:#38bdf8; margin:0 0 8px 0; font-size:0.9rem;">🛡️ Objection History & Tactical Formulations</h4>
                <div style="max-height:160px; overflow-y:auto;">${objHistory}</div>
            </div>
            <div style="display:flex; justify-content:flex-end; gap:8px;">
                <button class="btn btn-primary btn-sm" onclick="createMemoryProposal(${snap.business_id})">📝 Generate Memory-Aware Proposal</button>
                <button class="btn btn-secondary btn-sm" onclick="document.getElementById('memory-context-modal').style.display='none'">Close</button>
            </div>
        `;
        modal.style.display = 'flex';
    } catch (e) {
        alert(`Error opening memory modal: ${e.message}`);
    }
}

async function createMemoryProposal(businessId) {
    if (!confirm('Generate an evidence-grounded proposal for this prospect using their audit findings and objection history?')) return;
    try {
        const res = await fetch(`/api/memory/prospects/${businessId}/create-proposal`, { method: 'POST' });
        const result = await res.json();
        if (res.ok) {
            alert(`✓ Memory-Aware Proposal #${result.proposal_id} created successfully!`);
            document.getElementById('memory-context-modal').style.display = 'none';
            if (typeof loadPayments === 'function') loadPayments();
        } else {
            alert(`Error: ${result.detail || 'Could not generate proposal.'}`);
        }
    } catch (e) {
        alert(`Network error: ${e.message}`);
    }
}

async function loadPayments() {
    try {
        // 1. Fetch Real Database-Derived Deal Metrics
        const metricsRes = await fetch('/api/deals/metrics?include_mock=true');
        if (metricsRes.ok) {
            const m = await metricsRes.json();
            const elOpen = document.getElementById('deal-metric-open-proposals');
            const elPending = document.getElementById('deal-metric-payment-pending');
            const elAdvance = document.getElementById('deal-metric-advance-received');
            const elWon = document.getElementById('deal-metric-won-deals');
            const elCash = document.getElementById('deal-metric-cash-received');
            const elBal = document.getElementById('deal-metric-outstanding-balance');
            const elPipe = document.getElementById('deal-metric-pipeline-value');

            if (elOpen) elOpen.textContent = m.open_proposals || 0;
            if (elPending) elPending.textContent = m.payment_pending || 0;
            if (elAdvance) elAdvance.textContent = m.advance_received_deals || 0;
            if (elWon) elWon.textContent = m.won_deals || 0;
            if (elCash) elCash.textContent = `$${(m.cash_received_usd || 0).toLocaleString()}`;
            if (elBal) elBal.textContent = `$${(m.outstanding_balance_usd || 0).toLocaleString()}`;
            if (elPipe) elPipe.textContent = `$${(m.pipeline_value_usd || 0).toLocaleString()}`;
        }

        // 2. Fetch Commercial Proposals & Deals
        const dealsRes = await fetch('/api/deals');
        const dealsTable = document.getElementById('deals-table-body');
        if (dealsRes.ok && dealsTable) {
            const deals = await dealsRes.json();
            dealsTable.innerHTML = '';
            if (deals.length === 0) {
                dealsTable.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted); padding:24px;">No commercial proposals created yet. Create a proposal for any qualified prospect.</td></tr>';
            } else {
                deals.forEach(d => {
                    const tr = document.createElement('tr');
                    const badgeClass = d.status === 'WON' ? 'badge-emerald' :
                                       d.status === 'ADVANCE_RECEIVED' ? 'badge-cyan' :
                                       d.status === 'PAYMENT_PENDING' ? 'badge-amber' :
                                       d.status === 'APPROVED' ? 'badge-indigo' : 'badge-slate';
                    
                    let actionBtn = `<button class="btn btn-secondary" style="padding:4px 8px; font-size:0.75rem;" onclick="openDealDetail(${d.id})">👁 Detail</button>`;
                    if (d.status === 'DRAFT') {
                        actionBtn += ` <button class="btn btn-primary" style="padding:4px 8px; font-size:0.75rem; margin-left:4px;" onclick="approveProposal(${d.id})">✓ Approve</button>`;
                        actionBtn += ` <button class="btn btn-emerald" style="padding:4px 8px; font-size:0.75rem; margin-left:4px;" onclick="sendProposalToClient(${d.id})">📨 Send Proposal & Checkout</button>`;
                    } else if (d.status === 'APPROVED') {
                        actionBtn += ` <button class="btn btn-primary" style="padding:4px 8px; font-size:0.75rem; margin-left:4px;" onclick="requestPayment(${d.id})">💳 Pay Order</button>`;
                        actionBtn += ` <button class="btn btn-emerald" style="padding:4px 8px; font-size:0.75rem; margin-left:4px;" onclick="sendProposalToClient(${d.id})">📨 Send Proposal & Checkout</button>`;
                    }

                    tr.innerHTML = `
                        <td><code>#${d.id}</code></td>
                        <td><strong>${d.business_name}</strong> ${d.is_mock ? '<span style="font-size:0.65rem; color:var(--hud-amber);">[SIM]</span>' : ''}</td>
                        <td>${d.service_type}</td>
                        <td style="font-weight:700; color:var(--text-bright);">$${(d.total_value || 0).toLocaleString()}</td>
                        <td style="color:var(--hud-emerald); font-weight:600;">$${(d.advance_received || 0).toLocaleString()}</td>
                        <td style="color:var(--hud-amber); font-weight:600;">$${(d.remaining_balance || 0).toLocaleString()}</td>
                        <td><span class="badge ${badgeClass}">${d.status}</span></td>
                        <td><span style="font-size:0.75rem; color:var(--text-muted);">${d.delivery_status}</span></td>
                        <td>${actionBtn}</td>
                    `;
                    dealsTable.appendChild(tr);
                });
            }
        }

        // 3. Fetch Verified Payment Transactions
        const res = await fetch('/api/payments');
        const payments = await res.json();
        const tbody = document.getElementById('payments-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (payments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:32px;">Financial ledger active. No executed deals recorded yet.</td></tr>';
            return;
        }

        payments.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code style="color:var(--hud-cyan-bright);">${p.reference_id}</code></td>
                <td><strong>${p.company_name}</strong></td>
                <td style="font-weight:700; color:var(--hud-emerald);">$${p.amount.toLocaleString()}</td>
                <td>${p.currency}</td>
                <td><span class="badge badge-emerald">${p.status}</span></td>
                <td>${p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</td>
                <td><button class="btn btn-secondary" style="padding:4px 10px; font-size:0.75rem;" onclick="viewAuditReport(${p.business_id || p.customer_id})">📄 Delivery Pack</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading payments and deals:', e);
    }
}

async function approveProposal(proposalId) {
    if (!confirm(`Approve Proposal #${proposalId} for payment request?`)) return;
    try {
        const res = await fetch(`/api/proposals/${proposalId}/approve`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(`✓ Proposal #${proposalId} Approved!`);
            loadPayments();
        } else {
            alert(`Approval failed: ${data.detail || JSON.stringify(data)}`);
        }
    } catch (e) {
        alert(`Error approving proposal: ${e}`);
    }
}

async function requestPayment(proposalId) {
    try {
        const res = await fetch(`/api/proposals/${proposalId}/request-payment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payment_type: 'ADVANCE' })
        });
        const data = await res.json();
        if (res.ok) {
            alert(`✓ Payment order created: ${data.order_id}\nAmount: $${data.amount}\nCheckout URL: ${data.checkout_url}`);
            loadPayments();
        } else {
            alert(`Payment order failed: ${data.detail || JSON.stringify(data)}`);
        }
    } catch (e) {
        alert(`Error requesting payment: ${e}`);
    }
}

async function sendProposalToClient(proposalId) {
    const sendLive = confirm(`DISPATCH PROPOSAL & CHECKOUT LINK:\n\nClick OK for LIVE email transmission to client,\nor Cancel for SIMULATED dispatch.`);
    try {
        const res = await fetch(`/api/proposals/${proposalId}/send-to-client`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ send_live: sendLive })
        });
        const data = await res.json();
        if (res.ok) {
            const modeLabel = sendLive ? 'LIVE' : 'SIMULATED';
            alert(`✓ Proposal Dispatched! [${modeLabel}]\nRecipient: ${data.recipient}\nCheckout: ${data.checkout_url}\nEvent: ${data.send_result?.event || 'sent'}`);
            loadPayments();
            loadDashboardMetrics();
        } else {
            alert(`Proposal dispatch failed: ${data.detail || JSON.stringify(data)}`);
        }
    } catch (e) {
        alert(`Error sending proposal: ${e}`);
    }
}

async function openDealDetail(dealId) {
    const modal = document.getElementById('lead-modal');
    const content = document.getElementById('modal-body-content');
    if (!modal || !content) return;

    content.innerHTML = '<div style="text-align:center; padding:32px;">Loading Deal Details...</div>';
    modal.style.display = 'flex';

    try {
        const res = await fetch(`/api/deals/${dealId}`);
        if (!res.ok) {
            content.innerHTML = `<div style="color:var(--hud-rose);">Failed to load deal #${dealId}</div>`;
            return;
        }
        const deal = await res.json();

        let paymentsHtml = '';
        if (deal.payments && deal.payments.length > 0) {
            paymentsHtml = deal.payments.map(p => `
                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); padding:10px; border-radius:6px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between;">
                        <strong style="color:var(--hud-emerald);">$${p.amount.toLocaleString()} ${p.currency}</strong>
                        <span class="badge badge-emerald">${p.status}</span>
                    </div>
                    <div style="font-size:0.75rem; color:var(--text-muted); margin-top:4px;">
                        Order Ref: <code>${p.reference_id}</code> | Payment ID: <code>${p.razorpay_payment_id || 'N/A'}</code>
                    </div>
                </div>
            `).join('');
        } else {
            paymentsHtml = '<div style="color:var(--text-muted); font-size:0.85rem;">No payment transactions recorded yet.</div>';
        }

        let auditHtml = '';
        if (deal.audit_trail && deal.audit_trail.length > 0) {
            auditHtml = deal.audit_trail.map(a => `
                <div style="padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.8rem;">
                    <div style="display:flex; justify-content:space-between;">
                        <strong style="color:var(--hud-cyan-bright);">${a.event_type.toUpperCase()}</strong>
                        <span style="color:var(--text-muted);">${new Date(a.created_at).toLocaleTimeString()}</span>
                    </div>
                    <div style="color:var(--text-muted); margin-top:2px;">Operator: ${a.operator}</div>
                </div>
            `).join('');
        } else {
            auditHtml = '<div style="color:var(--text-muted); font-size:0.85rem;">No audit events recorded.</div>';
        }

        content.innerHTML = `
            <div style="margin-bottom:20px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <h2 style="font-size:1.4rem; color:var(--text-bright); margin-bottom:4px;">${deal.business_name}</h2>
                        <div style="color:var(--hud-cyan-bright); font-size:0.9rem;">${deal.service_type}</div>
                    </div>
                    <span class="badge badge-indigo" style="font-size:0.85rem;">${deal.status}</span>
                </div>
            </div>

            <!-- Financial Summary Grid -->
            <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; margin-bottom:20px;">
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle); padding:12px; border-radius:8px;">
                    <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase;">Proposal Value</div>
                    <div style="font-size:1.2rem; font-weight:700; color:var(--text-bright); margin-top:4px;">$${deal.total_value.toLocaleString()}</div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle); padding:12px; border-radius:8px;">
                    <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase;">Advance Required / Recv</div>
                    <div style="font-size:1.2rem; font-weight:700; color:var(--hud-emerald); margin-top:4px;">$${deal.advance_received.toLocaleString()} <span style="font-size:0.8rem; color:var(--text-muted);">/ $${deal.advance_required.toLocaleString()}</span></div>
                </div>
                <div style="background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle); padding:12px; border-radius:8px;">
                    <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase;">Outstanding Balance</div>
                    <div style="font-size:1.2rem; font-weight:700; color:var(--hud-amber); margin-top:4px;">$${deal.remaining_balance.toLocaleString()}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">
                <!-- Payment Transactions -->
                <div>
                    <h4 style="font-size:0.95rem; margin-bottom:10px; color:var(--text-bright);">Payment Transactions</h4>
                    ${paymentsHtml}
                </div>

                <!-- Audit Trail -->
                <div>
                    <h4 style="font-size:0.95rem; margin-bottom:10px; color:var(--text-bright);">Chronological Audit Trail</h4>
                    <div style="max-height:220px; overflow-y:auto;">
                        ${auditHtml}
                    </div>
                </div>
            </div>

            <div style="margin-top:24px; padding-top:16px; border-top:1px solid var(--border-subtle); display:flex; justify-content:flex-end;">
                <button class="btn btn-secondary" onclick="closeModal()">Close</button>
            </div>
        `;
    } catch (e) {
        content.innerHTML = `<div style="color:var(--hud-rose);">Error rendering deal detail: ${e}</div>`;
    }
}

async function createCheckoutLink(businessId) {
    try {
        const res = await fetch('/api/payments/checkout-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ business_id: businessId })
        });
        const data = await res.json();
        if (data.checkout_url) {
            window.open(data.checkout_url, '_blank');
        } else {
            alert('Failed to generate checkout link: ' + JSON.stringify(data));
        }
    } catch (e) {
        alert('Error creating checkout: ' + e);
    }
}

/* ==========================================================================
   SETTINGS & PRODUCTION INTEGRATIONS
   ========================================================================== */

async function loadSettings() {
    loadProductionHealth();
    try {
        const res = await fetch('/api/settings');
        if (!res.ok) return;
        const data = await res.json();

        // 1. Email Settings
        const email = data.email || {};
        const selProvider = document.getElementById('setting-email-provider');
        const inpFrom = document.getElementById('setting-email-from');
        const inpFromName = document.getElementById('setting-email-from-name');
        const inpReplyTo = document.getElementById('setting-email-reply-to');
        const badgeEmail = document.getElementById('badge-email-status');
        const toggleLiveEmail = document.getElementById('setting-live-email-toggle');

        if (selProvider) selProvider.value = email.provider || 'dry_run';
        if (inpFrom) inpFrom.value = email.from_email || '';
        if (inpFromName) inpFromName.value = email.from_name || '';
        if (inpReplyTo) inpReplyTo.value = email.reply_to || '';

        // Provider status badge
        if (badgeEmail) {
            const status = email.status || 'DRY RUN';
            badgeEmail.textContent = status;
            badgeEmail.className = 'panel-tag ' + (status === 'LIVE' ? 'badge-emerald' : status === 'CONFIGURED' ? 'badge-cyan' : 'badge-amber');
        }

        if (toggleLiveEmail) {
            toggleLiveEmail.checked = !email.dry_run;
        }

        // Credentials masked placeholders
        const inpResend = document.getElementById('setting-resend-key');
        if (inpResend && email.resend_configured) inpResend.placeholder = email.resend_key_masked || 're_••••••••';

        const inpSendGrid = document.getElementById('setting-sendgrid-key');
        if (inpSendGrid && email.sendgrid_configured) inpSendGrid.placeholder = email.sendgrid_key_masked || 'SG.••••••••';

        const inpSmtpHost = document.getElementById('setting-smtp-host');
        if (inpSmtpHost) inpSmtpHost.value = email.smtp_host || '';

        const inpSmtpPort = document.getElementById('setting-smtp-port');
        if (inpSmtpPort) inpSmtpPort.value = email.smtp_port || 587;

        const inpSmtpUser = document.getElementById('setting-smtp-user');
        if (inpSmtpUser) inpSmtpUser.value = email.smtp_username || '';

        const inpSmtpPass = document.getElementById('setting-smtp-pass');
        if (inpSmtpPass && email.smtp_password_configured) inpSmtpPass.placeholder = '••••••••';

        handleEmailProviderChange();

        // 2. Payment Settings
        const pay = data.payments || {};
        const selPayMode = document.getElementById('setting-payment-mode');
        const inpKeyId = document.getElementById('setting-razorpay-key-id');
        const inpKeySec = document.getElementById('setting-razorpay-key-secret');
        const selCurr = document.getElementById('setting-payment-currency');
        const inpAdvance = document.getElementById('setting-default-advance');
        const badgePayment = document.getElementById('badge-payment-status');

        if (selPayMode) selPayMode.value = pay.mode || 'test';
        if (inpKeyId) inpKeyId.value = pay.key_id || '';
        if (inpKeySec && pay.key_secret_configured) inpKeySec.placeholder = pay.key_secret_masked || '••••••••';
        if (selCurr) selCurr.value = pay.currency || 'USD';
        if (inpAdvance) inpAdvance.value = pay.default_advance_percentage || 40;

        if (badgePayment) {
            const pStatus = pay.status || 'TEST MODE';
            badgePayment.textContent = pStatus;
            badgePayment.className = 'panel-tag ' + (pStatus === 'LIVE' ? 'badge-emerald' : pStatus === 'TEST MODE' ? 'badge-cyan' : 'badge-crimson');
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}

function handleEmailProviderChange() {
    const sel = document.getElementById('setting-email-provider');
    if (!sel) return;
    const prov = sel.value;

    const rowResend = document.getElementById('email-fields-resend');
    const rowSendGrid = document.getElementById('email-fields-sendgrid');
    const rowSmtp = document.getElementById('email-fields-smtp');

    if (rowResend) rowResend.style.display = prov === 'resend' ? 'block' : 'none';
    if (rowSendGrid) rowSendGrid.style.display = prov === 'sendgrid' ? 'block' : 'none';
    if (rowSmtp) rowSmtp.style.display = prov === 'smtp' ? 'block' : 'none';
}

async function handleSaveEmailSettings(event) {
    event.preventDefault();
    try {
        const payload = {
            provider: document.getElementById('setting-email-provider').value,
            from_email: document.getElementById('setting-email-from').value,
            from_name: document.getElementById('setting-email-from-name').value,
            reply_to: document.getElementById('setting-email-reply-to').value,
            resend_api_key: document.getElementById('setting-resend-key')?.value || null,
            sendgrid_api_key: document.getElementById('setting-sendgrid-key')?.value || null,
            smtp_host: document.getElementById('setting-smtp-host')?.value || null,
            smtp_port: parseInt(document.getElementById('setting-smtp-port')?.value || '587'),
            smtp_username: document.getElementById('setting-smtp-user')?.value || null,
            smtp_password: document.getElementById('setting-smtp-pass')?.value || null
        };

        const res = await fetch('/api/settings/email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            alert('✓ Email delivery configuration saved successfully!');
            loadSettings();
        } else {
            alert('Error saving email settings: ' + (data.detail || JSON.stringify(data)));
        }
    } catch (e) {
        alert('Failed to save email settings: ' + e);
    }
}

async function handleSendTestEmail() {
    const inp = document.getElementById('test-email-recipient');
    const resBox = document.getElementById('test-email-result');
    if (!inp || !inp.value) {
        alert('Please enter a test recipient email address.');
        return;
    }
    if (resBox) resBox.innerHTML = '<span style="color:var(--hud-cyan-bright);">Transmitting diagnostic verification email...</span>';

    try {
        const res = await fetch('/api/settings/email/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ recipient_email: inp.value.trim() })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            if (resBox) resBox.innerHTML = `<span style="color:var(--hud-emerald);">✓ Test email sent successfully via ${data.provider}! Message ID: ${data.message_id}</span>`;
            loadSettings();
        } else {
            if (resBox) resBox.innerHTML = `<span style="color:var(--hud-rose);">✗ Test email failed: ${data.detail || JSON.stringify(data)}</span>`;
        }
    } catch (e) {
        if (resBox) resBox.innerHTML = `<span style="color:var(--hud-rose);">✗ Error: ${e}</span>`;
    }
}

async function handleToggleLiveEmail(enabled) {
    if (enabled) {
        const ok = confirm("⚠️ ENABLE LIVE EMAIL SENDING?\n\nReal outbound messages will be delivered through your configured provider upon operator approval.\n\nMandatory human approval gate remains strictly enforced.");
        if (!ok) {
            document.getElementById('setting-live-email-toggle').checked = false;
            return;
        }
    }

    try {
        const res = await fetch('/api/settings/email/toggle-live', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
        });
        const data = await res.json();
        if (res.ok) {
            alert(enabled ? "⚠️ Live email delivery ENABLED." : "✓ Returned to DRY RUN mode.");
            loadSettings();
        } else {
            alert("Action Blocked by Safety Guard: " + (data.detail || JSON.stringify(data)));
            document.getElementById('setting-live-email-toggle').checked = !enabled;
        }
    } catch (e) {
        alert("Error toggling live email: " + e);
        document.getElementById('setting-live-email-toggle').checked = !enabled;
    }
}

async function handleSavePaymentSettings(event) {
    event.preventDefault();
    try {
        const payload = {
            mode: document.getElementById('setting-payment-mode').value,
            key_id: document.getElementById('setting-razorpay-key-id').value,
            key_secret: document.getElementById('setting-razorpay-key-secret').value || null,
            currency: document.getElementById('setting-payment-currency').value,
            default_advance_percentage: parseFloat(document.getElementById('setting-default-advance').value || '40')
        };

        const res = await fetch('/api/settings/payments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            alert('✓ Payment gateway settings updated successfully!');
            loadSettings();
        } else {
            alert('Error updating payment settings: ' + (data.detail || JSON.stringify(data)));
        }
    } catch (e) {
        alert('Failed to save payment settings: ' + e);
    }
}

function validateChangePwStrength() {
    const pw = document.getElementById('change-pw-new').value;
    const hint = document.getElementById('change-pw-strength-text');
    if (!hint) return;
    if (!pw) {
        hint.textContent = "Policy: ≥12 chars, non-dictionary, differs from current.";
        hint.style.color = "var(--text-muted)";
        return;
    }
    if (pw.length < 12) {
        hint.textContent = `Too short: ${pw.length}/12 characters required.`;
        hint.style.color = "#ef4444";
    } else {
        hint.textContent = "✓ Length requirement satisfied (≥12 characters).";
        hint.style.color = "#34d399";
    }
}

async function handlePasswordChange(e) {
    e.preventDefault();
    const curPw = document.getElementById('change-pw-current').value;
    const newPw = document.getElementById('change-pw-new').value;
    const confPw = document.getElementById('change-pw-confirm').value;
    const feedback = document.getElementById('change-pw-feedback');
    const btn = document.getElementById('btn-change-pw');

    if (newPw !== confPw) {
        feedback.style.display = 'block';
        feedback.style.background = 'rgba(239, 68, 68, 0.15)';
        feedback.style.border = '1px solid #ef4444';
        feedback.style.color = '#f87171';
        feedback.textContent = 'Error: New passphrases do not match.';
        return;
    }

    if (newPw.length < 12) {
        feedback.style.display = 'block';
        feedback.style.background = 'rgba(239, 68, 68, 0.15)';
        feedback.style.border = '1px solid #ef4444';
        feedback.style.color = '#f87171';
        feedback.textContent = 'Error: New passphrase must be at least 12 characters long.';
        return;
    }

    if (curPw === newPw) {
        feedback.style.display = 'block';
        feedback.style.background = 'rgba(239, 68, 68, 0.15)';
        feedback.style.border = '1px solid #ef4444';
        feedback.style.color = '#f87171';
        feedback.textContent = 'Error: New passphrase must differ from current passphrase.';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Updating Passkey...';
    feedback.style.display = 'none';

    try {
        const res = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: curPw,
                new_password: newPw,
                confirm_password: confPw
            })
        });
        const data = await res.json();
        if (res.ok && data.status === 'SUCCESS') {
            feedback.style.display = 'block';
            feedback.style.background = 'rgba(16, 185, 129, 0.15)';
            feedback.style.border = '1px solid #10b981';
            feedback.style.color = '#34d399';
            feedback.textContent = '✓ Passkey updated! Sessions invalidated. Redirecting to login...';
            btn.textContent = 'Passkey Updated';
            setTimeout(() => {
                window.location.href = '/login';
            }, 1500);
        } else {
            feedback.style.display = 'block';
            feedback.style.background = 'rgba(239, 68, 68, 0.15)';
            feedback.style.border = '1px solid #ef4444';
            feedback.style.color = '#f87171';
            feedback.textContent = 'Error: ' + (data.detail || 'Failed to update passkey.');
            btn.disabled = false;
            btn.textContent = 'Update Administrator Passkey';
        }
    } catch (err) {
        feedback.style.display = 'block';
        feedback.style.background = 'rgba(239, 68, 68, 0.15)';
        feedback.style.border = '1px solid #ef4444';
        feedback.style.color = '#f87171';
        feedback.textContent = 'Network error: Unable to communicate with server.';
        btn.disabled = false;
        btn.textContent = 'Update Administrator Passkey';
    }
}

/* ==========================================================================
   PROPOSAL CREATION & COMMERCIAL SPLIT
   ========================================================================== */

async function openCreateProposalModal() {
    const modal = document.getElementById('proposal-modal');
    const sel = document.getElementById('prop-business-id');
    if (!modal || !sel) return;

    sel.innerHTML = '<option value="">Loading qualified clients...</option>';
    modal.style.display = 'flex';

    try {
        const res = await fetch('/api/leads');
        if (res.ok) {
            const leads = await res.json();
            sel.innerHTML = '';
            if (leads.length === 0) {
                sel.innerHTML = '<option value="1">Austin Precision HVAC Systems (Lead #1)</option>';
            } else {
                leads.forEach(l => {
                    const opt = document.createElement('option');
                    opt.value = l.business_id;
                    opt.textContent = `${l.business_name} (${l.city || 'US'} - Score: ${l.score || '85'})`;
                    sel.appendChild(opt);
                });
            }
        }
    } catch (e) {
        sel.innerHTML = '<option value="1">Austin Precision HVAC Systems</option>';
    }

    calculateProposalSplit();
}

function closeProposalModal() {
    const modal = document.getElementById('proposal-modal');
    if (modal) modal.style.display = 'none';
}

function calculateProposalSplit() {
    const inpVal = document.getElementById('prop-total-value');
    const inpPct = document.getElementById('prop-advance-pct');
    const elAdv = document.getElementById('prop-calc-advance');
    const elRem = document.getElementById('prop-calc-remaining');

    const total = parseFloat(inpVal?.value || '2500');
    const pct = parseFloat(inpPct?.value || '40');

    const advance = Math.round(total * (pct / 100.0));
    const remaining = total - advance;

    if (elAdv) elAdv.textContent = `$${advance.toLocaleString()}.00`;
    if (elRem) elRem.textContent = `$${remaining.toLocaleString()}.00`;
}

async function handleCreateProposal(event) {
    event.preventDefault();
    const bizId = parseInt(document.getElementById('prop-business-id').value);
    const title = document.getElementById('prop-title').value.trim();
    const serviceType = document.getElementById('prop-service-type').value.trim();
    const totalVal = parseFloat(document.getElementById('prop-total-value').value);
    const advancePct = parseFloat(document.getElementById('prop-advance-pct').value);

    if (totalVal < 500) {
        alert('Commercial Floor: Total project value must be at least $500+ to ensure agency profitability.');
        return;
    }

    try {
        const res = await fetch('/api/proposals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                business_id: bizId,
                title: title,
                service_type: serviceType,
                total_value: totalVal,
                advance_percentage: advancePct
            })
        });

        const data = await res.json();
        if (res.ok) {
            alert(`✓ Proposal created (#${data.id})!\nTotal Value: $${data.total_value}\nAdvance Due: $${data.advance_required}\nRemaining: $${data.remaining_balance}`);
            closeProposalModal();
            loadPayments();
        } else {
            alert('Proposal creation failed: ' + (data.detail || JSON.stringify(data)));
        }
    } catch (e) {
        alert('Error creating proposal: ' + e);
    }
}

async function handleProductionReset() {
    const ok = confirm("⚠️ INITIALIZE CLEAN PRODUCTION BASELINE?\n\nThis will safely archive your existing database to backups/ and reset operational data to a zero baseline:\n\n• Prospects: 0\n• Qualified Leads: 0\n• Outreach Sent: 0\n• Replies: 0\n• Meetings: 0\n• Won Deals: 0\n• Pipeline Value: $0\n\nAll reference market metadata (countries, niches) will be preserved.");
    if (!ok) return;

    try {
        const res = await fetch('/api/production/reset', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(`✓ Clean Production Baseline Initialized!\n\nBackup Archived: ${data.backup_file || 'backups/'}\nMode: FIRST CLIENT MODE\nAll operational metrics set to 0.`);
            location.reload();
        } else {
            alert("Reset failed: " + (data.detail || JSON.stringify(data)));
        }
    } catch (e) {
        alert("Error resetting production environment: " + e);
    }
}

// ==============================================================================
// Autonomous Revenue Agent Controller (Dashboard Canonical Surface)
// ==============================================================================
let agentPollInterval = null;

async function handleAgentAction(action) {
    try {
        let endpoint = `/api/agent/${action}`;
        let options = { method: 'POST' };

        if (action === 'step') {
            options = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: "Salis Roofing",
                    domain: "salisroofing.com",
                    email: "contact@salisroofing.com",
                    phone: "+1-469-677-0239",
                    estimated_value: 750.0,
                    buyer_score: 84.0,
                    opportunity_score: 78.0
                })
            };
        }

        const res = await fetch(endpoint, options);
        const data = await res.json();

        if (action === 'kill') {
            alert("🛑 EMERGENCY KILL SWITCH ACTIVATED\nAutonomous agent halted. All outbound dispatches locked.");
        }

        await loadAgentStatus();
        if (action === 'start' || action === 'step') {
            if (typeof loadDashboardData === 'function') loadDashboardData();
            if (typeof loadLeads === 'function') loadLeads();
        }
    } catch (e) {
        console.error(`Error executing agent action ${action}:`, e);
    }
}

let agentStartTime = null;
let agentTimerInterval = null;

function updateAgentRuntimeClock(runtimeSec) {
    const clock = document.getElementById('agent-runtime-clock');
    if (!clock) return;
    const sec = Math.floor(runtimeSec || 0);
    const hrs = String(Math.floor(sec / 3600)).padStart(2, '0');
    const mins = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
    const secs = String(sec % 60).padStart(2, '0');
    clock.innerText = `${hrs}:${mins}:${secs}`;
}

async function fetchSafetyGuardrails() {
    try {
        const res = await fetch('/api/agent/safety-guardrails');
        if (!res.ok) return;
        const g = await res.json();
        updateGuardrailsUI(g);
    } catch (e) {
        console.debug('Error fetching safety guardrails:', e);
    }
}

function updateGuardrailsUI(g) {
    if (!g) return;
    const elAgent = document.getElementById('guardrail-agent');
    const elEmail = document.getElementById('guardrail-email');
    const elVoice = document.getElementById('guardrail-voice');
    const elPay = document.getElementById('guardrail-payment');
    const elFloor = document.getElementById('guardrail-floor');
    const elKill = document.getElementById('guardrail-kill');
    const elTakeover = document.getElementById('guardrail-takeover');

    if (elAgent) {
        elAgent.textContent = g.autonomous_agent_enabled ? 'AGENT: ACTIVE' : 'AGENT: DISABLED';
        elAgent.className = g.autonomous_agent_enabled ? 'badge badge-emerald' : 'badge badge-crimson';
    }
    if (elEmail) {
        elEmail.textContent = g.email_dry_run ? 'EMAIL: DRY RUN' : 'EMAIL: LIVE';
        elEmail.className = g.email_dry_run ? 'badge badge-cyan' : 'badge badge-emerald';
    }
    if (elVoice) {
        elVoice.textContent = g.voice_dry_run ? 'VOICE: DRY RUN' : 'VOICE: LIVE';
        elVoice.className = g.voice_dry_run ? 'badge badge-cyan' : 'badge badge-emerald';
    }
    if (elPay) {
        elPay.textContent = g.payment_dry_run ? 'PAYMENT: DRY RUN' : 'PAYMENT: LIVE';
        elPay.className = g.payment_dry_run ? 'badge badge-cyan' : 'badge badge-emerald';
    }
    if (elFloor) {
        elFloor.textContent = `$${g.commercial_floor_usd || 500} COMMERCIAL FLOOR`;
    }
    if (elKill) {
        elKill.textContent = g.kill_switch_active ? 'KILL SWITCH: ACTIVE' : 'KILL SWITCH: INACTIVE';
        elKill.className = g.kill_switch_active ? 'badge badge-crimson' : 'badge badge-emerald';
    }
    if (elTakeover) {
        elTakeover.textContent = g.human_takeover_available ? 'HUMAN TAKEOVER: AVAILABLE' : 'HUMAN TAKEOVER: DISABLED';
    }

    // Update Overview Operational Safeguards card
    const ownerOutreach = document.getElementById('owner-outreach-chip-status');
    const ownerPay = document.getElementById('owner-payment-chip-status');
    const ownerLoop = document.getElementById('owner-loop-chip-status');
    const ownerFloor = document.getElementById('owner-floor-chip-status');

    if (ownerOutreach) {
        ownerOutreach.textContent = g.email_dry_run ? '● Dry-Run Safe' : '● Live Outreach';
        ownerOutreach.style.color = g.email_dry_run ? '#10b981' : '#f59e0b';
    }
    if (ownerPay) {
        ownerPay.textContent = g.payment_dry_run ? '● Test Sandbox' : '● Live Payments';
        ownerPay.style.color = g.payment_dry_run ? '#38bdf8' : '#10b981';
    }
    if (ownerLoop) {
        ownerLoop.textContent = g.autonomous_agent_enabled ? '● Ready' : '● Disabled';
        ownerLoop.style.color = g.autonomous_agent_enabled ? '#a78bfa' : '#ef4444';
    }
    if (ownerFloor) {
        ownerFloor.textContent = `$${g.commercial_floor_usd || 500} Min`;
    }
}

async function loadAgentStatus() {
    try {
        const res = await fetch('/api/agent/status');
        const data = await res.json();

        // Update CEO sales state
        await updateCeoSalesState(data);

        // 1. Safety Guardrails
        if (data.safety_guardrails) {
            updateGuardrailsUI(data.safety_guardrails);
        }

        // 2. Status Badge
        const statusBadge = document.getElementById('agent-status-badge');
        const currStatusBadge = document.getElementById('agent-curr-status-badge');
        const rawStatus = data.status || 'IDLE';

        [statusBadge, currStatusBadge].forEach(b => {
            if (!b) return;
            b.textContent = rawStatus;
            b.className = 'badge';
            if (rawStatus === 'RUNNING') b.className = 'badge badge-cyan';
            else if (rawStatus === 'PAUSED') b.className = 'badge badge-amber';
            else if (rawStatus === 'KILLED') b.className = 'badge badge-crimson';
            else b.className = 'badge badge-stage';
        });

        // 3. Current Prospect, Domain, Operation
        const pName = document.getElementById('agent-curr-prospect-name');
        const pDomain = document.getElementById('agent-curr-prospect-domain');
        const legacyProspect = document.getElementById('agent-curr-prospect');
        const currStage = document.getElementById('agent-curr-stage-badge');
        const currOp = document.getElementById('agent-curr-operation');
        const killStatus = document.getElementById('agent-kill-status');
        const floorLabel = document.getElementById('agent-floor-label');
        const dryMode = document.getElementById('agent-dryrun-mode');

        if (pName) {
            pName.textContent = data.current_business_name || (data.current_prospect ? data.current_prospect.name : 'None (Standby)');
        }
        if (pDomain) {
            pDomain.textContent = data.current_domain || (data.current_prospect ? data.current_prospect.domain : '--');
        }
        if (legacyProspect) {
            legacyProspect.textContent = data.current_domain || (data.current_prospect ? data.current_prospect.name : 'None (Standby)');
        }
        if (currStage) {
            currStage.textContent = data.current_stage || data.current_state || 'DISCOVER';
        }
        if (currOp) {
            currOp.textContent = data.current_operation || 'Agent initialized in safety dry-run mode. Ready for single-prospect step.';
        }
        if (killStatus) {
            killStatus.textContent = data.kill_switch_active ? 'ACTIVE (HALTED)' : 'INACTIVE (NORMAL)';
            killStatus.style.color = data.kill_switch_active ? '#f43f5e' : '#34d399';
        }
        if (floorLabel) {
            floorLabel.textContent = `$${data.commercial_floor_usd || 500}+ MINIMUM`;
        }
        if (dryMode) {
            const isDry = data.safety_guardrails ? data.safety_guardrails.email_dry_run : true;
            dryMode.textContent = isDry ? 'SIMULATED DRY RUN' : 'LIVE TRANSMISSION';
            dryMode.className = isDry ? 'badge badge-amber' : 'badge badge-emerald';
        }

        // 4. Runtime Clock
        if (rawStatus === 'RUNNING') {
            if (!agentStartTime) agentStartTime = Date.now() - (data.runtime_seconds || 0) * 1000;
            if (!agentTimerInterval) {
                agentTimerInterval = setInterval(() => {
                    if (agentStartTime) {
                        const elapsed = (Date.now() - agentStartTime) / 1000;
                        updateAgentRuntimeClock(elapsed);
                    }
                }, 1000);
            }
        } else {
            if (agentTimerInterval) {
                clearInterval(agentTimerInterval);
                agentTimerInterval = null;
            }
            if (rawStatus === 'IDLE' || rawStatus === 'KILLED') {
                agentStartTime = null;
                updateAgentRuntimeClock(data.runtime_seconds || 0);
            }
        }

        // 5. Decision info
        const decisionConf = document.getElementById('agent-decision-conf');
        const decisionNext = document.getElementById('agent-decision-next');
        const decisionReason = document.getElementById('agent-decision-reason');
        if (data.decision) {
            if (decisionConf) decisionConf.textContent = `${Math.round(data.decision.confidence * 100)}%`;
            if (decisionNext) decisionNext.textContent = data.decision.next_action;
            if (decisionReason) decisionReason.textContent = data.decision.reason;
        }

        // 6. Metrics stats
        const s = data.stats || {};
        const elProc = document.getElementById('stat-agent-processed');
        const elSkip = document.getElementById('stat-agent-skipped');
        const elAtt = document.getElementById('stat-agent-attempted');
        const elRep = document.getElementById('stat-agent-replies');
        const elQual = document.getElementById('stat-agent-qualified');
        const elMeet = document.getElementById('stat-agent-meetings');
        const elWon = document.getElementById('stat-agent-won');
        const elRev = document.getElementById('stat-agent-revenue');

        if (elProc) elProc.textContent = s.prospects_processed || 0;
        if (elSkip) elSkip.textContent = s.prospects_skipped || 0;
        if (elAtt) elAtt.textContent = s.contacts_attempted || 0;
        if (elRep) elRep.textContent = s.replies_received || 0;
        if (elQual) elQual.textContent = s.qualified_conversations || 0;
        if (elMeet) elMeet.textContent = s.meetings_ready || 0;
        if (elWon) elWon.textContent = s.won_deals || 0;
        if (elRev) elRev.textContent = `$${(s.pipeline_revenue_usd || 0).toLocaleString()}`;

        // 7. Compact Safety Indicators
        const gAgent = document.getElementById('guardrail-agent');
        const gEmail = document.getElementById('guardrail-email');
        const gVoice = document.getElementById('guardrail-voice');
        const gPayment = document.getElementById('guardrail-payment');
        const gKill = document.getElementById('guardrail-kill');
        const gKillBadge = document.getElementById('agent-kill-badge');

        const sg = data.safety_guardrails || {};
        if (gAgent) {
            gAgent.className = data.is_running ? 'badge-safety-active' : 'badge-safety-dry';
            gAgent.textContent = data.is_running ? 'AGENT: ACTIVE' : 'AGENT: STANDBY';
        }
        if (gEmail) {
            gEmail.className = sg.email_dry_run ? 'badge-safety-dry' : 'badge-safety-live';
            gEmail.textContent = sg.email_dry_run ? 'EMAIL: DRY RUN' : 'EMAIL: LIVE';
        }
        if (gVoice) {
            gVoice.className = sg.voice_dry_run ? 'badge-safety-dry' : 'badge-safety-live';
            gVoice.textContent = sg.voice_dry_run ? 'VOICE: DRY RUN' : 'VOICE: LIVE';
        }
        if (gPayment) {
            gPayment.className = sg.payment_dry_run ? 'badge-safety-dry' : 'badge-safety-live';
            gPayment.textContent = sg.payment_dry_run ? 'PAYMENT: DRY RUN' : 'PAYMENT: LIVE';
        }
        if (gKill) {
            gKill.className = data.kill_switch_active ? 'badge-safety-live' : 'badge-safety-active';
            gKill.textContent = data.kill_switch_active ? 'KILL SWITCH: HALTED' : 'KILL SWITCH: INACTIVE';
        }
        if (gKillBadge) {
            gKillBadge.className = data.kill_switch_active ? 'badge badge-crimson' : 'badge badge-emerald';
            gKillBadge.textContent = data.kill_switch_active ? 'KILL SWITCH ACTIVE' : 'KILL SWITCH INACTIVE';
        }

        // 8. 10-Stage Pipeline Progression Bar
        const stageOrder = [
            { id: 'step-pipe-discovery', name: 'DISCOVER' },
            { id: 'step-pipe-verify', name: 'VERIFY' },
            { id: 'step-pipe-audit', name: 'AUDIT' },
            { id: 'step-pipe-score', name: 'SCORE' },
            { id: 'step-pipe-qualify', name: 'QUALIFY' },
            { id: 'step-pipe-compliance', name: 'COMPLIANCE' },
            { id: 'step-pipe-offer', name: 'OFFER' },
            { id: 'step-pipe-outreach', name: 'OUTREACH' },
            { id: 'step-pipe-memory', name: 'MEMORY' },
            { id: 'step-pipe-next', name: 'NEXT' }
        ];

        const currStageStr = (data.current_stage || data.current_state || '').toUpperCase();
        let currIdx = stageOrder.findIndex(st => currStageStr.includes(st.name));
        if (currIdx === -1) {
            currIdx = rawStatus === 'RUNNING' ? 0 : -1;
        }

        const stepLabel = document.getElementById('pipeline-current-step-label');
        if (stepLabel) {
            stepLabel.textContent = currIdx >= 0 ? `${currIdx + 1}/10: ${stageOrder[currIdx].name}` : 'STANDBY';
        }

        stageOrder.forEach((step, idx) => {
            const el = document.getElementById(step.id);
            if (!el) return;
            el.className = 'pipe-step';
            if (currIdx < 0) {
                el.classList.add('pending');
            } else if (idx < currIdx) {
                el.classList.add('completed');
            } else if (idx === currIdx) {
                el.classList.add('active');
            } else {
                el.classList.add('pending');
            }
        });

        // 9. Prospect Intelligence Ribbon
        const pScoreBadge = document.getElementById('agent-prospect-score-badge');
        const evGateBadge = document.getElementById('agent-evidence-gate-badge');
        const intelLoc = document.getElementById('agent-intel-location');
        const intelNiche = document.getElementById('agent-intel-niche');
        const intelEvCount = document.getElementById('agent-intel-evidence-count');
        const intelContact = document.getElementById('agent-intel-contactability');
        const intelService = document.getElementById('agent-intel-service');
        const intelOffer = document.getElementById('agent-intel-offer');

        const curP = data.current_prospect;
        if (curP) {
            if (pScoreBadge) {
                const sc = curP.prospect_score || curP.buyer_score || 0;
                pScoreBadge.textContent = `SCORE: ${Math.round(sc)}/100`;
                pScoreBadge.className = sc >= 70 ? 'badge badge-cyan' : 'badge badge-amber';
            }
            if (evGateBadge) {
                const passed = (curP.evidence_count || 0) >= 2;
                evGateBadge.textContent = passed ? 'EVIDENCE GATE PASSED' : 'EVIDENCE GATE PENDING';
                evGateBadge.className = passed ? 'badge badge-emerald' : 'badge badge-amber';
            }
            if (intelLoc) intelLoc.textContent = `${curP.country || 'US'} (${curP.city || 'Regional'})`;
            if (intelNiche) intelNiche.textContent = curP.niche || 'Commercial Services';
            if (intelEvCount) intelEvCount.textContent = `${curP.evidence_count || 0} verified`;
            if (intelContact) intelContact.textContent = curP.email || curP.phone || 'Unknown';
            if (intelService) intelService.textContent = curP.recommended_service || 'Diagnostics Pending';
            if (intelOffer) intelOffer.textContent = `$${(curP.target_offer || curP.estimated_value || 1500).toLocaleString()}`;
        } else {
            if (pScoreBadge) {
                pScoreBadge.textContent = 'SCORE: --';
                pScoreBadge.className = 'badge badge-stage';
            }
            if (evGateBadge) {
                evGateBadge.textContent = 'AWAITING EVIDENCE';
                evGateBadge.className = 'badge badge-amber';
            }
            if (intelLoc) intelLoc.textContent = '--';
            if (intelNiche) intelNiche.textContent = '--';
            if (intelEvCount) intelEvCount.textContent = '0 verified';
            if (intelContact) intelContact.textContent = '--';
            if (intelService) intelService.textContent = '--';
            if (intelOffer) intelOffer.textContent = '$0';
        }

        // 10. Persisted Decision Trace Bullets
        const whyList = document.getElementById('agent-why-prospect-list');
        if (whyList) {
            const whyBullets = [];
            if (data.decision && data.decision.reason) {
                whyBullets.push(data.decision.reason);
            }
            if (curP && curP.name) {
                whyBullets.push(`Single active prospect locked: ${curP.name} (${curP.domain || ''}) in niche ${curP.niche || 'B2B'}.`);
                if (curP.why_this_prospect) {
                    whyBullets.push(curP.why_this_prospect);
                }
            }
            if (data.current_operation && data.current_operation !== 'Standby') {
                whyBullets.push(`Operational status: ${data.current_operation}`);
            }

            if (whyBullets.length === 0) {
                whyList.innerHTML = `
                    <div class="trace-bullet">
                        <span class="trace-bullet-icon">▸</span>
                        <span>No active prospect locked. System is standing by to evaluate global prospect pool.</span>
                    </div>
                `;
            } else {
                whyList.innerHTML = whyBullets.map(b => `
                    <div class="trace-bullet">
                        <span class="trace-bullet-icon">▸</span>
                        <span>${escapeHtml(b)}</span>
                    </div>
                `).join('');
            }
        }

        // 11. Empirical Evidence Citations List
        const evList = document.getElementById('agent-evidence-citations-list');
        const evTag = document.getElementById('agent-evidence-status-tag');
        if (evList) {
            if (curP && curP.id) {
                try {
                    const evRes = await fetch(`/api/prospects/evidence/${curP.id}`);
                    if (evRes.ok) {
                        const evData = await evRes.json();
                        const items = evData.evidence_items || [];
                        if (evTag) evTag.textContent = `${items.length} CITATIONS`;
                        if (items.length > 0) {
                            evList.innerHTML = items.map(ev => `
                                <div class="evidence-citation-item">
                                    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
                                        <strong style="color:#f1f5f9; font-size:0.78rem;">${escapeHtml(ev.claim)}</strong>
                                        <span class="badge badge-emerald" style="font-size:0.62rem;">${Math.round((ev.confidence_score || 0.8) * 100)}% CONF</span>
                                    </div>
                                    <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">
                                        <span>${escapeHtml(ev.publisher || ev.source_domain || 'Web Audit')}</span>
                                        ${ev.source_url ? ` | <a href="${escapeHtml(ev.source_url)}" target="_blank" style="color:var(--hud-cyan-bright); text-decoration:none;">${escapeHtml(ev.source_url.slice(0, 50))}...</a>` : ''}
                                    </div>
                                </div>
                            `).join('');
                        } else {
                            evList.innerHTML = `
                                <div style="color:#64748b; font-size:0.78rem; font-style:italic; padding:6px;">
                                    Audit in progress. Verified citations pending next cycle.
                                </div>
                            `;
                        }
                    }
                } catch (_) {}
            } else {
                if (evTag) evTag.textContent = '0 CITATIONS';
                evList.innerHTML = `
                    <div style="color:#64748b; font-size:0.78rem; font-style:italic; padding:8px;">
                        No verified evidence records attached yet. Evidence Gate requires &ge; 2 independent verified sources.
                    </div>
                `;
            }
        }
    } catch (e) {
        console.debug('Error loading agent status:', e);
    }
    // Phase 15 Telemetry Update
    if (typeof loadAutonomousStatus === 'function') {
        loadAutonomousStatus();
    }
}

// ==============================================================================
// Phase 15 — Autonomous First-Client Acquisition Controller & Telemetry
// ==============================================================================
async function loadAutonomousStatus() {
    try {
        const res = await fetch('/api/agent/autonomous-status');
        if (!res.ok) return;
        const s = await res.json();

        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = (val !== null && val !== undefined && val !== '') ? String(val) : '--';
        };

        const prospectName = typeof s.current_prospect === 'object' && s.current_prospect !== null
            ? (s.current_prospect.name || s.current_prospect.domain || 'None')
            : (s.current_prospect || 'None');
        const country = typeof s.current_prospect === 'object' && s.current_prospect && s.current_prospect.country !== 'None'
            ? s.current_prospect.country
            : (s.country || 'United Kingdom');
        const niche = typeof s.current_prospect === 'object' && s.current_prospect && s.current_prospect.niche !== 'None'
            ? s.current_prospect.niche
            : (s.niche || 'Roofing');
        const offerVal = typeof s.offer === 'object' && s.offer !== null
            ? `$${Number(s.offer.price_usd || 1000).toLocaleString()}`
            : (typeof s.offer === 'number' ? `$${s.offer.toLocaleString()}` : (s.offer || '$0'));

        setVal('auto-val-current-action', s.current_action || 'STANDBY');
        setVal('auto-val-current-prospect', prospectName);
        setVal('auto-val-country', country);
        setVal('auto-val-niche', niche);
        setVal('auto-val-evidence-status', s.evidence_status || '--');
        setVal('auto-val-audit-status', s.audit_status || '--');
        setVal('auto-val-service', s.service || '--');
        setVal('auto-val-offer', offerVal);
        setVal('auto-val-approval-reason', s.approval_reason || '--');
        setVal('auto-val-outreach-status', s.outreach_status || 'STANDBY');
        setVal('auto-val-reply-status', s.reply_status || '--');
        setVal('auto-val-pipeline-status', s.pipeline_status || 'READY');
        setVal('auto-val-payment-status', s.payment_status || 'UNPAID');
        setVal('auto-val-revenue', s.revenue !== undefined && s.revenue !== null ? `$${Number(s.revenue).toLocaleString()}` : '$0.00');

        // Update Slot Badge
        const slotBadge = document.getElementById('auto-val-slot-badge');
        if (slotBadge) {
            if (s.emergency_stop) {
                slotBadge.textContent = '🛑 EMERGENCY STOP ACTIVE';
                slotBadge.className = 'badge badge-crimson';
            } else if (s.is_paused) {
                slotBadge.textContent = '⏸ PAUSED';
                slotBadge.className = 'badge badge-amber';
            } else if (s.slot_status === 'ACTIVE') {
                slotBadge.textContent = 'SLOT 1 / 1 ACTIVE';
                slotBadge.className = 'badge badge-cyan';
            } else {
                slotBadge.textContent = 'STANDBY (SLOT 1 AVAILABLE)';
                slotBadge.className = 'badge badge-emerald';
            }
        }

        // Also update the header badge
        const headerAutoBadge = document.getElementById('header-autonomous-badge');
        if (headerAutoBadge) {
            if (s.emergency_stop) {
                headerAutoBadge.textContent = 'EMERGENCY STOP';
                headerAutoBadge.className = 'badge badge-crimson';
            } else if (s.is_paused) {
                headerAutoBadge.textContent = 'PAUSED';
                headerAutoBadge.className = 'badge badge-amber';
            } else {
                headerAutoBadge.textContent = 'AUTONOMOUS ACTIVE';
                headerAutoBadge.className = 'badge badge-emerald';
            }
        }
    } catch (e) {
        console.debug('Error fetching autonomous status:', e);
    }
}

async function pauseAutonomousController() {
    try {
        const res = await fetch('/api/agent/pause', { method: 'POST' });
        const data = await res.json();
        await loadAutonomousStatus();
    } catch (e) {
        console.error('Error pausing autonomous controller:', e);
    }
}

async function resumeAutonomousController() {
    try {
        const res = await fetch('/api/agent/resume', { method: 'POST' });
        const data = await res.json();
        await loadAutonomousStatus();
    } catch (e) {
        console.error('Error resuming autonomous controller:', e);
    }
}

async function triggerEmergencyStop() {
    if (!confirm('🛑 WARNING: Are you sure you want to trigger the EMERGENCY STOP?\nThis will immediately halt all autonomous operations and dispatches.')) {
        return;
    }
    try {
        const res = await fetch('/api/agent/emergency-stop', { method: 'POST' });
        const data = await res.json();
        await loadAutonomousStatus();
        alert('🛑 Emergency Stop Activated. All operations halted.');
    } catch (e) {
        console.error('Error triggering emergency stop:', e);
    }
}

// Start Phase 15 telemetry polling
setInterval(() => {
    if (typeof loadAutonomousStatus === 'function') {
        loadAutonomousStatus();
    }
}, 5000);

// ==============================================================================
// Voice Sales Operations Controller
// ==============================================================================
async function loadVoiceOperations() {
    try {
        // 1. Config
        const resCfg = await fetch('/api/voice/config');
        if (resCfg.ok) {
            const cfg = await resCfg.json();
            const provBadge = document.getElementById('voice-provider-badge');
            const cidBadge = document.getElementById('voice-caller-id-badge');
            if (provBadge) {
                provBadge.textContent = `PROVIDER: ${cfg.voice_provider.toUpperCase()} (${cfg.voice_dry_run ? 'DRY-RUN' : 'LIVE'})`;
            }
            if (cidBadge) {
                cidBadge.textContent = `CALLER ID: ${cfg.caller_id || 'Not Set'}`;
            }
        }

        // 2. Scheduled Meetings
        const resMeets = await fetch('/api/voice/meetings');
        const meetsBody = document.getElementById('voice-meetings-table-body');
        if (resMeets.ok && meetsBody) {
            const meets = await resMeets.json();
            if (meets.length === 0) {
                meetsBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:16px;">No meetings scheduled yet.</td></tr>`;
            } else {
                meetsBody.innerHTML = meets.map(m => `
                    <tr>
                        <td><strong>${escapeHtml(m.prospect_name || m.prospect_contact)}</strong><br><span style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(m.prospect_contact)}</span></td>
                        <td>${escapeHtml(m.title)}</td>
                        <td>${m.scheduled_time ? new Date(m.scheduled_time).toLocaleString() : 'TBD'}</td>
                        <td>${m.duration_minutes} min</td>
                        <td><a href="${escapeHtml(m.meeting_url || '#')}" target="_blank" class="badge badge-cyan" style="text-decoration:none;">Open Link</a></td>
                        <td><span class="badge badge-emerald">${escapeHtml(m.status)}</span></td>
                    </tr>
                `).join('');
            }
        }

        // 3. Voice Calls History
        const resCalls = await fetch('/api/voice/calls');
        const callsBody = document.getElementById('voice-calls-table-body');
        if (resCalls.ok && callsBody) {
            const calls = await resCalls.json();
            if (calls.length === 0) {
                callsBody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-muted); padding:16px;">No voice calls placed yet.</td></tr>`;
            } else {
                callsBody.innerHTML = calls.map(c => `
                    <tr>
                        <td><span style="font-family:var(--font-mono); font-size:0.75rem;">${escapeHtml(c.call_sid)}</span></td>
                        <td>${escapeHtml(c.recipient_phone)}</td>
                        <td>${escapeHtml(c.caller_id)}</td>
                        <td>${c.duration_seconds}s</td>
                        <td><span class="badge ${c.status === 'COMPLETED' ? 'badge-emerald' : 'badge-amber'}">${escapeHtml(c.status)}</span></td>
                        <td><span class="badge badge-stage">${escapeHtml(c.qualification_intent || 'N/A')}</span></td>
                        <td>${escapeHtml(c.action_taken || 'N/A')}</td>
                        <td style="max-width:240px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(c.transcript || '')}">${escapeHtml(c.transcript || 'No transcript')}</td>
                        <td>${c.created_at ? new Date(c.created_at).toLocaleTimeString() : ''}</td>
                    </tr>
                `).join('');
            }
        }
    } catch (e) {
        console.debug('Error loading voice operations data:', e);
    }
}

async function handleTriggerVoiceCall(event) {
    if (event) event.preventDefault();
    const phone = document.getElementById('voice-input-phone')?.value;
    const name = document.getElementById('voice-input-name')?.value;
    const niche = document.getElementById('voice-input-niche')?.value || 'Services';
    const city = document.getElementById('voice-input-city')?.value || 'Austin';
    const lang = document.getElementById('voice-input-lang')?.value || 'en';

    if (!phone || !name) {
        alert('Please enter recipient phone and business name.');
        return;
    }

    try {
        const res = await fetch('/api/voice/call', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone: phone,
                business_name: name,
                niche: niche,
                city: city,
                language: lang
            })
        });
        const data = await res.json();
        if (res.ok) {
            alert(`✓ Voice Consultation Call Dispatched!\n\nCall SID: ${data.call_sid}\nProvider: ${data.provider.toUpperCase()}\nStatus: ${data.status}\nDry Run: ${data.dry_run}`);
            loadVoiceOperations();
        } else {
            alert(`Call failed: ${data.detail || JSON.stringify(data)}`);
        }
    } catch (e) {
        alert(`Error triggering call: ${e}`);
    }
}

/* ==========================================================================
   Production Readiness Health & Controlled E2E Test Functions
   ========================================================================== */

async function loadProductionHealth() {
    const badge = document.getElementById('badge-prod-health');
    const grid = document.getElementById('prod-health-grid');
    if (!grid) return;

    try {
        const res = await fetch('/api/production/health');
        if (!res.ok) return;
        const data = await res.json();

        if (badge) {
            badge.textContent = data.overall_status.replace('_', ' ');
            badge.className = data.overall_status.includes('READY') ? 'panel-tag badge-emerald' : 'panel-tag badge-amber';
        }

        const components = [
            { key: 'database', title: 'Database Connectivity', icon: '🗄️', comp: data.database },
            { key: 'email', title: 'Email Infrastructure', icon: '📧', comp: data.email },
            { key: 'voice', title: 'Voice Telephony', icon: '📞', comp: data.voice },
            { key: 'payment', title: 'Payment Processing', icon: '💳', comp: data.payment },
            { key: 'webhooks', title: 'Webhook Verification', icon: '🔐', comp: data.webhooks }
        ];

        grid.innerHTML = components.map(c => {
            const statusColor = c.comp.status === 'READY' ? '#4ade80' : (c.comp.status === 'DRY_RUN' ? '#38bdf8' : '#fbbf24');
            return `
                <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                        <span style="font-weight:600; font-size:0.85rem; color:var(--text-white); display:flex; align-items:center; gap:6px;">
                            <span>${c.icon}</span> <span>${c.title}</span>
                        </span>
                        <span style="font-size:0.7rem; font-weight:700; color:${statusColor};">${c.comp.status}</span>
                    </div>
                    <p style="font-size:0.75rem; color:var(--text-muted); margin:0; line-height:1.4;">${c.comp.details}</p>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.debug('Error loading production health:', e);
    }
}

async function handleRunControlledE2ETest() {
    const btn = document.getElementById('btn-agent-e2e-test');
    const panel = document.getElementById('e2e-test-results-panel');
    const container = document.getElementById('e2e-test-steps-container');
    const badge = document.getElementById('e2e-test-badge');

    if (btn) btn.disabled = true;
    if (panel) panel.style.display = 'block';
    if (badge) {
        badge.textContent = 'RUNNING...';
        badge.className = 'badge badge-cyan';
    }
    if (container) {
        container.innerHTML = '<div style="color:var(--text-muted); padding:8px 0;">⚡ Initializing controlled 10-step dry-run simulation across all revenue systems...</div>';
    }

    try {
        const res = await fetch('/api/production/test/e2e', { method: 'POST' });
        const report = await res.json();

        if (res.ok && report.success) {
            if (badge) {
                badge.textContent = '10/10 PASSED (DEAL WON)';
                badge.className = 'badge badge-emerald';
            }
            if (container) {
                container.innerHTML = report.steps.map(s => `
                    <div style="display:flex; align-items:flex-start; gap:8px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                        <span style="color:#4ade80; font-weight:700;">✓ [STEP ${s.step_number}]</span>
                        <div style="flex:1;">
                            <strong style="color:var(--text-white); font-size:0.8rem;">${s.step_name}:</strong>
                            <span style="color:var(--text-muted); font-size:0.75rem; margin-left:6px;">${s.details}</span>
                        </div>
                    </div>
                `).join('') + `
                    <div style="margin-top:8px; padding-top:6px; color:#4ade80; font-weight:700; font-size:0.85rem;">
                        🎉 Lifecycle Complete: Prospect "${report.prospect_name}" closed for $${report.deal_value} ($${report.advance_amount} advance verified via cryptographic webhook).
                    </div>
                `;
            }
            if (typeof loadAgentStatus === 'function') loadAgentStatus();
            if (typeof loadOverviewData === 'function') loadOverviewData();
        } else {
            if (badge) {
                badge.textContent = 'TEST FAILED';
                badge.className = 'badge badge-amber';
            }
            if (container) {
                container.innerHTML = `<div style="color:#f43f5e; padding:8px 0;">❌ Test failed: ${report.detail || JSON.stringify(report)}</div>`;
            }
        }
    } catch (e) {
        if (badge) {
            badge.textContent = 'ERROR';
            badge.className = 'badge badge-amber';
        }
        if (container) {
            container.innerHTML = `<div style="color:#f43f5e; padding:8px 0;">❌ Execution error: ${e}</div>`;
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

// =========================================================================
// Real-Time Agent Observability, WebSocket Feed & Artifact Inspectors
// =========================================================================

let activityWebSocket = null;
let activityAutoScroll = true;
let wsDisconnectTimeout = null;
let fallbackPollingInterval = null;
let lastSeenEventId = 0;
let inboundEventCount = 0;

let ceoRecentEvents = [];

function updateCeoActivityList(events) {
    const container = document.getElementById('ceo-recent-activity-list');
    if (!container) return;

    if (!events || events.length === 0) {
        return;
    }

    const displayEvents = events.slice(0, 6);
    let html = '';

    displayEvents.forEach(evt => {
        let badgeClass = 'blue';
        let svgIcon = '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>';

        const status = (evt.status || '').toUpperCase();
        const type = (evt.event_type || '').toUpperCase();

        if (status === 'SUCCESS' || type.includes('WON') || type.includes('PAYMENT')) {
            badgeClass = 'green';
            svgIcon = '<polyline points="20 6 9 17 4 12"/>';
        } else if (type.includes('OUTREACH') || type.includes('SEND') || type.includes('EMAIL')) {
            badgeClass = 'teal';
            svgIcon = '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>';
        } else if (type.includes('REPLY') || type.includes('MESSAGE')) {
            badgeClass = 'amber';
            svgIcon = '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>';
        } else if (type.includes('PROPOSAL') || type.includes('OFFER') || type.includes('AUDIT')) {
            badgeClass = 'blue';
            svgIcon = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>';
        } else if (type.includes('RESEARCH') || type.includes('DISCOVER') || type.includes('LEAD')) {
            badgeClass = 'purple';
            svgIcon = '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>';
        } else if (status === 'PENDING' || status === 'WAITING' || type.includes('WAIT')) {
            badgeClass = 'amber';
            svgIcon = '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>';
        }

        let desc = evt.message || type.replace(/_/g, ' ').toLowerCase();
        if (desc.length > 38) {
            desc = desc.substring(0, 36) + '...';
        }

        let timeStr = 'Just now';
        if (evt.created_at) {
            try {
                const d = new Date(evt.created_at);
                const diffMs = Date.now() - d.getTime();
                const diffMin = Math.floor(diffMs / 60000);
                if (diffMin < 1) timeStr = 'Just now';
                else if (diffMin < 60) timeStr = `${diffMin}m ago`;
                else timeStr = `${Math.floor(diffMin / 60)}h ago`;
            } catch (_) {
                timeStr = 'Recent';
            }
        }

        html += `
            <div class="agency-activity-row">
                <div class="agency-activity-badge ${badgeClass}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${svgIcon}</svg>
                </div>
                <span class="agency-activity-title" title="${escapeHtml(evt.message || '')}">${escapeHtml(desc)}</span>
                <span class="agency-activity-ago">${timeStr}</span>
            </div>
        `;
    });

    container.innerHTML = html;
}


function initActivityWebSocket() {
    const statusText = document.getElementById('ws-status-text');
    const pulseDot = document.getElementById('ws-pulse-dot');
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/agent-activity`;

    try {
        if (activityWebSocket && (activityWebSocket.readyState === WebSocket.OPEN || activityWebSocket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        activityWebSocket = new WebSocket(wsUrl);

        activityWebSocket.onopen = () => {
            if (statusText) statusText.innerText = 'LIVE WS CONNECTED';
            if (pulseDot) {
                pulseDot.style.background = '#10b981';
                pulseDot.style.boxShadow = '0 0 8px #10b981';
            }
            if (wsDisconnectTimeout) {
                clearTimeout(wsDisconnectTimeout);
                wsDisconnectTimeout = null;
            }
            stopPollingFallback();
        };

        activityWebSocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'pong') return;
                handleLiveActivityEvent(data);
            } catch (err) {
                console.debug('Error parsing WebSocket message:', err);
            }
        };

        activityWebSocket.onclose = () => {
            if (statusText) statusText.innerText = 'WS RECONNECTING...';
            if (pulseDot) {
                pulseDot.style.background = '#f59e0b';
                pulseDot.style.boxShadow = '0 0 8px #f59e0b';
            }
            // If disconnected for >10s, initiate fallback REST polling
            if (!wsDisconnectTimeout) {
                wsDisconnectTimeout = setTimeout(() => {
                    startPollingFallback();
                }, 10000);
            }
            setTimeout(initActivityWebSocket, 3000);
        };

        activityWebSocket.onerror = () => {
            if (activityWebSocket) activityWebSocket.close();
        };
    } catch (e) {
        console.debug('WebSocket setup error:', e);
        if (!wsDisconnectTimeout) {
            wsDisconnectTimeout = setTimeout(startPollingFallback, 10000);
        }
        setTimeout(initActivityWebSocket, 5000);
    }
}

function startPollingFallback() {
    if (fallbackPollingInterval) return;
    const statusText = document.getElementById('ws-status-text');
    if (statusText) statusText.innerText = 'REST POLLING (FALLBACK)';
    
    fallbackPollingInterval = setInterval(async () => {
        try {
            const resp = await fetch('/api/agent/activity?limit=15');
            if (resp.ok) {
                const data = await resp.json();
                if (data.events && data.events.length > 0) {
                    const newEvents = data.events.filter(e => e.id > lastSeenEventId);
                    newEvents.reverse().forEach(e => handleLiveActivityEvent(e));
                }
            }
            if (typeof loadAgentStatus === 'function') loadAgentStatus();
        } catch (err) {
            console.debug('Fallback polling error:', err);
        }
    }, 5000);
}

function stopPollingFallback() {
    if (fallbackPollingInterval) {
        clearInterval(fallbackPollingInterval);
        fallbackPollingInterval = null;
    }
}

async function loadRecentActivityHistory() {
    try {
        const resp = await fetch('/api/agent/activity?limit=60');
        if (!resp.ok) return;
        const data = await resp.json();
        const mainFeed = document.getElementById('agent-activity-feed');
        const inboundFeed = document.getElementById('inbound-resumption-feed');

        if (data.events && data.events.length > 0) {
            ceoRecentEvents = data.events.slice();
            updateCeoActivityList(ceoRecentEvents);
            if (mainFeed) mainFeed.innerHTML = '';
            if (inboundFeed) inboundFeed.innerHTML = '';
            data.events.forEach(evt => {
                if (evt.id && evt.id > lastSeenEventId) {
                    lastSeenEventId = evt.id;
                }
                renderActivityEventRow(evt, false);
            });
            if (activityAutoScroll && mainFeed) {
                mainFeed.scrollTop = mainFeed.scrollHeight;
            }
        } else {
            updateCeoActivityList([]);
        }
    } catch (e) {
        console.debug('Failed to load recent activity history:', e);
    }
}

function handleLiveActivityEvent(evt) {
    if (evt.id && evt.id > lastSeenEventId) {
        lastSeenEventId = evt.id;
    }

    // Add to CEO recent events feed
    ceoRecentEvents.unshift(evt);
    if (ceoRecentEvents.length > 20) ceoRecentEvents.pop();
    updateCeoActivityList(ceoRecentEvents);

    // Sync CEO current sales state if event contains prospect/operation
    if (evt.metadata_json || evt.domain || evt.message) {
        updateCeoSalesState({
            current_business_name: evt.metadata_json?.name || evt.metadata_json?.business_name,
            current_domain: evt.domain || evt.metadata_json?.domain,
            current_stage: evt.event_type?.includes('WON') ? 'WON' : (evt.metadata_json?.stage || undefined),
            current_operation: evt.message,
            status: evt.status === 'RUNNING' ? 'RUNNING' : undefined
        });
    }

    renderActivityEventRow(evt, true);
    updatePipelineProgress(evt.event_type, evt.domain || evt.metadata_json?.domain, evt.metadata_json);

    const prospectName = evt.metadata_json?.name || evt.metadata_json?.business_name;
    const prospectDomain = evt.domain || evt.metadata_json?.domain;

    if (prospectName || prospectDomain) {
        const pNameElem = document.getElementById('agent-curr-prospect-name');
        const pDomainElem = document.getElementById('agent-curr-prospect-domain');
        const legacyElem = document.getElementById('agent-curr-prospect');
        if (pNameElem && prospectName) pNameElem.innerText = prospectName;
        if (pDomainElem && prospectDomain) pDomainElem.innerText = prospectDomain;
        if (legacyElem && (prospectName || prospectDomain)) {
            legacyElem.innerText = `${prospectName || ''} (${prospectDomain || ''})`.trim();
        }
    }

    const opElem = document.getElementById('agent-curr-operation');
    if (opElem && evt.message) {
        opElem.innerText = evt.message;
    }

    if (evt.event_type === 'KILL_SWITCH_ACTIVATED') {
        const killBadge = document.getElementById('agent-kill-status');
        const guardrailKill = document.getElementById('guardrail-kill');
        if (killBadge) {
            killBadge.innerText = 'ACTIVE (HALTED)';
            killBadge.style.color = '#f43f5e';
        }
        if (guardrailKill) {
            guardrailKill.innerText = 'KILL SWITCH: ACTIVE';
            guardrailKill.className = 'badge badge-crimson';
        }
    }

    // Refresh agent status when cycle finishes or starts
    if (evt.event_type === 'RUN_STARTED' || evt.event_type === 'RUN_COMPLETED' || evt.event_type === 'NEXT_PROSPECT') {
        if (typeof loadAgentStatus === 'function') setTimeout(loadAgentStatus, 500);
    }
}

function renderActivityEventRow(evt, shouldScroll) {
    const isInbound = [
        'INBOUND_EVENT_RECEIVED',
        'PROSPECT_MEMORY_RESTORED',
        'REPLY_CLASSIFIED',
        'CONVERSATION_RESPONSE_GENERATED',
        'HUMAN_TAKEOVER'
    ].includes(evt.event_type);

    const targetFeedId = isInbound ? 'inbound-resumption-feed' : 'agent-activity-feed';
    const feed = document.getElementById(targetFeedId);
    if (!feed) return;

    // Remove empty placeholder
    if (feed.children.length === 1 && feed.children[0].innerText.includes('telemetry') || feed.children[0]?.innerText.includes('Connecting') || feed.children[0]?.innerText.includes('Waiting for inbound')) {
        feed.innerHTML = '';
    }

    const timeStr = evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : new Date().toLocaleTimeString();

    let statusColor = '#38bdf8';
    let statusBg = 'rgba(56, 189, 248, 0.12)';
    let statusBorder = 'rgba(56, 189, 248, 0.3)';

    if (evt.status === 'SUCCESS') {
        statusColor = '#34d399';
        statusBg = 'rgba(16, 185, 129, 0.12)';
        statusBorder = 'rgba(16, 185, 129, 0.3)';
    } else if (evt.status === 'WARNING' || evt.event_type === 'PROSPECT_DUPLICATE_SKIPPED') {
        statusColor = '#fbbf24';
        statusBg = 'rgba(245, 158, 11, 0.15)';
        statusBorder = 'rgba(245, 158, 11, 0.4)';
    } else if (evt.status === 'FAILED' || evt.event_type === 'PROSPECT_DISQUALIFIED') {
        statusColor = '#f43f5e';
        statusBg = 'rgba(244, 63, 94, 0.12)';
        statusBorder = 'rgba(244, 63, 94, 0.3)';
    }

    // Update Inbound badge counter if inbound
    if (isInbound) {
        inboundEventCount++;
        const badge = document.getElementById('inbound-count-badge');
        if (badge) {
            badge.innerText = `${inboundEventCount}`;
            badge.style.display = 'inline-block';
        }
    }

    // Action button generator based on event type
    let actionsHtml = '';
    const meta = evt.metadata_json || {};

    if (meta.message_id || evt.event_type.includes('OUTREACH')) {
        const mId = meta.message_id;
        if (mId) {
            actionsHtml += `<button type="button" class="btn btn-secondary" onclick="openOutreachInspector(${mId})" style="height:20px; padding:0 6px; font-size:0.68rem; margin-left:6px; color:#38bdf8; border-color:rgba(56,189,248,0.4);">Inspect Email</button>`;
        }
    }

    if (evt.business_id && (evt.event_type.includes('AUDIT') || evt.event_type.includes('SCORING'))) {
        actionsHtml += `<button type="button" class="btn btn-secondary" onclick="openAuditInspector(${evt.business_id})" style="height:20px; padding:0 6px; font-size:0.68rem; margin-left:6px; color:#34d399; border-color:rgba(16,185,129,0.4);">Inspect Audit</button>`;
    }

    if (evt.domain || evt.business_id) {
        const targetKey = evt.domain || evt.business_id;
        actionsHtml += `<button type="button" class="btn btn-secondary" onclick="openMemoryInspector('${targetKey}')" style="height:20px; padding:0 6px; font-size:0.68rem; margin-left:6px; color:#c084fc; border-color:rgba(168,85,247,0.4);">View Memory</button>`;
    }

    if (meta.artifact_id || evt.event_type.includes('WEBSITE')) {
        const aId = meta.artifact_id;
        if (aId) {
            actionsHtml += `<button type="button" class="btn btn-secondary" onclick="openWebsitePreview(${aId})" style="height:20px; padding:0 6px; font-size:0.68rem; margin-left:6px; color:#f59e0b; border-color:rgba(245,158,11,0.4);">Live Preview</button>`;
        }
    }

    // Duplicate badge label
    let eventTypeLabel = evt.event_type;
    if (evt.event_type === 'PROSPECT_DUPLICATE_SKIPPED') {
        eventTypeLabel = 'DUPLICATE SKIPPED';
    }

    const row = document.createElement('div');
    row.style.cssText = isInbound ?
        'display:flex; flex-direction:column; gap:4px; padding:8px 10px; border-radius:4px; background:rgba(30,58,138,0.25); border:1px solid rgba(56,189,248,0.35); margin-bottom:4px;' :
        'display:flex; align-items:flex-start; gap:8px; padding:6px 8px; border-radius:4px; background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.04);';

    if (isInbound) {
        row.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.65rem; font-weight:700; color:#38bdf8; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.4); padding:1px 6px; border-radius:3px;">${eventTypeLabel}</span>
                <span style="color:var(--text-muted); font-size:0.68rem;">${timeStr}</span>
            </div>
            <div style="color:#f1f5f9; font-size:0.75rem; word-break:break-word;">
                ${escapeHtml(evt.message)}
            </div>
            <div style="display:flex; justify-content:flex-end; margin-top:2px;">
                ${actionsHtml}
            </div>
        `;
    } else {
        row.innerHTML = `
            <span style="color:var(--text-muted); font-size:0.7rem; min-width:60px; margin-top:1px;">${timeStr}</span>
            <span style="font-size:0.65rem; font-weight:700; color:${statusColor}; background:${statusBg}; border:1px solid ${statusBorder}; padding:1px 6px; border-radius:3px; white-space:nowrap;">${eventTypeLabel}</span>
            <div style="flex:1; color:#e2e8f0; font-size:0.75rem; word-break:break-word;">
                ${escapeHtml(evt.message)}
                ${actionsHtml}
            </div>
        `;
    }

    feed.appendChild(row);

    // Keep feeds trimmed
    const limit = isInbound ? 50 : 150;
    while (feed.children.length > limit) {
        feed.removeChild(feed.children[0]);
    }

    // Update main feed counter
    const countLabel = document.getElementById('stream-item-count');
    if (countLabel && !isInbound) {
        countLabel.innerText = `${feed.children.length} events`;
    }

    if (shouldScroll && activityAutoScroll) {
        feed.scrollTop = feed.scrollHeight;
    }
}

function updatePipelineProgress(eventType, domain, metadata) {
    const stepLabel = document.getElementById('pipeline-current-step-label');
    const steps = [
        'step-pipe-discovery',
        'step-pipe-verify',
        'step-pipe-audit',
        'step-pipe-score',
        'step-pipe-qualify',
        'step-pipe-compliance',
        'step-pipe-offer',
        'step-pipe-outreach',
        'step-pipe-memory',
        'step-pipe-next'
    ];

    let activeIndex = -1;
    let label = 'PROCESSING';
    let failedIndex = -1;
    let skippedIndex = -1;

    if (eventType.includes('DISCOVERY') || eventType === 'PROSPECT_FOUND') {
        activeIndex = 0;
        label = '1. DISCOVERING PROSPECT (1-AT-A-TIME)';
    } else if (eventType === 'PROSPECT_DUPLICATE_SKIPPED') {
        activeIndex = 0;
        skippedIndex = 1;
        label = 'DUPLICATE SKIPPED (PREVIOUSLY CONTACTED)';
    } else if (eventType.includes('VERIFICATION')) {
        activeIndex = 1;
        label = '2. VERIFYING BUSINESS & DOMAIN';
    } else if (eventType.includes('AUDIT')) {
        activeIndex = 2;
        label = '3. DIAGNOSTIC AUDIT (6 VECTORS)';
    } else if (eventType.includes('SCORING')) {
        activeIndex = 3;
        label = '4. LEAD SCORING & BUYING CAPACITY';
    } else if (eventType === 'COMMERCIAL_QUALIFICATION') {
        activeIndex = 4;
        label = '5. $500 COMMERCIAL FLOOR APPROVED';
    } else if (eventType === 'PROSPECT_DISQUALIFIED') {
        activeIndex = 4;
        failedIndex = 4;
        label = 'DISQUALIFIED (<$500 COMMERCIAL FLOOR)';
    } else if (eventType.includes('COMPLIANCE')) {
        if (eventType === 'COMPLIANCE_BLOCKED') {
            activeIndex = 5;
            failedIndex = 5;
            label = 'COMPLIANCE BLOCKED (SUPPRESSION GATE)';
        } else {
            activeIndex = 5;
            label = '6. SAFETY & COMPLIANCE GATES';
        }
    } else if (eventType.includes('OFFER')) {
        activeIndex = 6;
        label = '7. GENERATING CUSTOMIZED OFFER';
    } else if (eventType.includes('OUTREACH')) {
        if (eventType === 'OUTREACH_FAILED') {
            activeIndex = 7;
            failedIndex = 7;
            label = 'OUTREACH DISPATCH FAILED';
        } else {
            activeIndex = 7;
            label = '8. DISPATCHING OUTREACH (DRY RUN SAFE)';
        }
    } else if (eventType.includes('MEMORY')) {
        activeIndex = 8;
        label = '9. PERSISTING PROSPECT SNAPSHOT';
    } else if (eventType === 'NEXT_PROSPECT' || eventType === 'RUN_COMPLETED') {
        activeIndex = 9;
        label = '10. READY FOR NEXT PROSPECT';
    }

    if (stepLabel && label) {
        stepLabel.innerText = domain ? `${label} [${domain}]` : label;
    }

    // Update CSS classes across all 10 steps (5 states: pending, active, completed, skipped, failed)
    steps.forEach((sId, idx) => {
        const elem = document.getElementById(sId);
        if (!elem) return;

        if (failedIndex !== -1 && idx === failedIndex) {
            elem.className = 'pipe-step failed';
        } else if (failedIndex !== -1 && idx > failedIndex) {
            elem.className = 'pipe-step skipped';
        } else if (skippedIndex !== -1 && idx >= skippedIndex) {
            elem.className = 'pipe-step skipped';
        } else if (idx < activeIndex) {
            elem.className = 'pipe-step completed';
        } else if (idx === activeIndex) {
            elem.className = 'pipe-step active';
        } else {
            elem.className = 'pipe-step pending';
        }
    });
}

function toggleAutoScroll() {
    activityAutoScroll = !activityAutoScroll;
    const btn = document.getElementById('btn-autoscroll');
    if (btn) {
        btn.innerText = `Auto-scroll: ${activityAutoScroll ? 'ON' : 'OFF'}`;
    }
}

function clearActivityStream() {
    const mainFeed = document.getElementById('agent-activity-feed');
    const inboundFeed = document.getElementById('inbound-resumption-feed');
    if (mainFeed) {
        mainFeed.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:20px;">Feed cleared. Waiting for events...</div>';
    }
    if (inboundFeed) {
        inboundFeed.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center; padding:25px 8px;">Waiting for inbound replies / webhooks.</div>';
    }
    inboundEventCount = 0;
    const badge = document.getElementById('inbound-count-badge');
    if (badge) badge.style.display = 'none';
}

// -------------------------------------------------------------------------
// Outreach Inspector Modal
// -------------------------------------------------------------------------
async function openOutreachInspector(messageId) {
    const modal = document.getElementById('modal-outreach-inspector');
    const container = document.getElementById('outreach-inspector-content');
    if (!modal || !container) return;

    container.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted);">Loading outreach details...</div>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch(`/api/agent/outreach/${messageId}`);
        if (!resp.ok) {
            container.innerHTML = `<div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); border-radius:6px; color:#fca5a5; padding:16px;">Failed to load outreach message #${messageId} (${resp.status} ${resp.statusText}).</div>`;
            return;
        }
        const data = await resp.json();

        container.innerHTML = `
            <div style="background:rgba(245, 158, 11, 0.12); border:1px solid rgba(245, 158, 11, 0.4); border-radius:6px; padding:10px 14px; margin-bottom:14px; display:flex; align-items:center; gap:8px;">
                <span style="font-size:1.1rem;">⚠️</span>
                <div>
                    <strong style="color:#fbbf24; font-size:0.85rem;">SIMULATED — NO EXTERNAL TRANSMISSION (DRY RUN ACTIVE)</strong>
                    <div style="color:#fde68a; font-size:0.75rem;">EMAIL_DRY_RUN is enabled. This outreach was synthesized and recorded in local telemetry without transmitting real external SMTP email.</div>
                </div>
            </div>

            <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:14px; margin-bottom:14px; font-size:0.85rem;">
                <div style="display:grid; grid-template-columns: 110px 1fr; gap:8px; margin-bottom:8px;">
                    <span style="color:var(--text-muted); font-weight:600;">Recipient Email:</span>
                    <strong style="color:var(--text-white);">${escapeHtml(data.recipient_email || 'N/A')}</strong>
                    
                    <span style="color:var(--text-muted); font-weight:600;">From:</span>
                    <span style="color:#e2e8f0;">${escapeHtml(data.from_name || 'Agency Sales')} &lt;${escapeHtml(data.from_email || 'outreach@domain.local')}&gt;</span>
                    
                    <span style="color:var(--text-muted); font-weight:600;">Subject Line:</span>
                    <strong style="color:var(--hud-cyan-bright);">${escapeHtml(data.subject || '')}</strong>
                    
                    <span style="color:var(--text-muted); font-weight:600;">Domain:</span>
                    <span style="color:#94a3b8;">${escapeHtml(data.domain || '')}</span>

                    <span style="color:var(--text-muted); font-weight:600;">Channel:</span>
                    <span class="badge badge-cyan" style="font-size:0.7rem; width:fit-content;">${escapeHtml(data.channel || 'EMAIL')}</span>

                    <span style="color:var(--text-muted); font-weight:600;">Sent Timestamp:</span>
                    <span style="color:#94a3b8; font-family:var(--font-mono); font-size:0.75rem;">${data.sent_at ? new Date(data.sent_at).toLocaleString() : 'Simulated Real-Time'}</span>
                </div>
            </div>

            <div style="margin-bottom:14px;">
                <label style="display:block; font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px;">Personalized Message Body</label>
                <div style="background:#090e1a; border:1px solid rgba(255,255,255,0.08); border-radius:6px; padding:16px; font-family:var(--font-sans); font-size:0.88rem; line-height:1.7; color:#f1f5f9; white-space:pre-wrap;">${escapeHtml(data.body || '')}</div>
            </div>

            <div style="background:rgba(15,23,42,0.6); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                <span style="display:block; font-size:0.72rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px;">Grounded Evidence Referenced</span>
                <div style="display:flex; flex-wrap:wrap; gap:16px; font-size:0.8rem;">
                    <div>Performance Score: <strong style="color:#38bdf8;">${data.grounding_evidence?.audit?.performance_score || 'N/A'}/100</strong></div>
                    <div>Page Load Time: <strong style="color:#fbbf24;">${data.grounding_evidence?.audit?.load_time_seconds || 'N/A'}s</strong></div>
                    <div>Recommended Turnaround Offer: <strong style="color:#34d399;">$${data.grounding_evidence?.offer?.price || 500}</strong></div>
                </div>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<div style="color:#f43f5e; padding:16px;">Error: ${err}</div>`;
    }
}

function closeOutreachInspector() {
    const modal = document.getElementById('modal-outreach-inspector');
    if (modal) modal.style.display = 'none';
}

// -------------------------------------------------------------------------
// Audit Evidence Inspector Modal
// -------------------------------------------------------------------------
async function openAuditInspector(businessId) {
    const modal = document.getElementById('modal-audit-inspector');
    const container = document.getElementById('audit-inspector-content');
    if (!modal || !container) return;

    container.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted);">Loading diagnostic audit evidence...</div>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch(`/api/agent/audit-evidence/${businessId}`);
        if (!resp.ok) {
            container.innerHTML = `<div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); border-radius:6px; color:#fca5a5; padding:16px;">Failed to load audit evidence for business #${businessId} (${resp.status}).</div>`;
            return;
        }
        const data = await resp.json();

        let findingsHtml = '<div style="color:var(--text-muted); font-size:0.8rem;">No critical UX or speed findings recorded.</div>';
        if (data.findings && data.findings.length > 0) {
            findingsHtml = data.findings.map(f => `
                <div style="background:rgba(15,23,42,0.8); border-left:3px solid ${f.severity === 'HIGH' ? '#f43f5e' : (f.severity === 'MEDIUM' ? '#f59e0b' : '#38bdf8')}; padding:8px 12px; margin-bottom:6px; border-radius:0 4px 4px 0;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
                        <strong style="color:var(--text-white); font-size:0.82rem;">${escapeHtml(f.title)}</strong>
                        <span class="badge" style="font-size:0.65rem; background:rgba(255,255,255,0.06);">${escapeHtml(f.category || 'DIAGNOSTIC')}</span>
                    </div>
                    <p style="color:#94a3b8; font-size:0.75rem; margin:0;">${escapeHtml(f.description || '')}</p>
                </div>
            `).join('');
        }

        container.innerHTML = `
            <div style="margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <h4 style="color:var(--text-white); font-size:1.05rem; margin:0;">${escapeHtml(data.business_name || data.domain)}</h4>
                    <span style="font-size:0.75rem; color:var(--hud-cyan-bright);">${escapeHtml(data.domain)} • ${escapeHtml(data.niche || 'Local B2B')} in ${escapeHtml(data.city || 'Austin, TX')}</span>
                </div>
                <button type="button" class="btn btn-secondary" onclick="triggerWebsiteBuild(${data.business_id})" style="height:28px; font-size:0.75rem; border-color:rgba(245,158,11,0.4); color:#f59e0b;">
                    🌐 Generate Turnaround Website
                </button>
            </div>

            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-bottom:16px;">
                <div class="kpi-card" style="padding:10px; text-align:center;">
                    <span style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase;">Performance</span>
                    <div style="font-size:1.4rem; font-weight:800; color:#38bdf8;">${data.performance_score || 0}/100</div>
                </div>
                <div class="kpi-card" style="padding:10px; text-align:center;">
                    <span style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase;">Load Time</span>
                    <div style="font-size:1.4rem; font-weight:800; color:#fbbf24;">${data.load_time_seconds || 0}s</div>
                </div>
                <div class="kpi-card" style="padding:10px; text-align:center;">
                    <span style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase;">SEO Index</span>
                    <div style="font-size:1.4rem; font-weight:800; color:#34d399;">${data.seo_score || 0}/100</div>
                </div>
                <div class="kpi-card" style="padding:10px; text-align:center;">
                    <span style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase;">Accessibility</span>
                    <div style="font-size:1.4rem; font-weight:800; color:#c084fc;">${data.a11y_score || 0}/100</div>
                </div>
            </div>

            <div style="background:rgba(15,23,42,0.6); padding:10px; border-radius:6px; border:1px solid var(--border-subtle); margin-bottom:14px;">
                <span style="font-size:0.7rem; color:var(--text-muted); font-weight:700; text-transform:uppercase; display:block; margin-bottom:6px;">CORE WEB VITALS</span>
                <div style="display:flex; gap:16px; font-size:0.8rem;">
                    <div>LCP: <strong style="color:#38bdf8;">${data.core_web_vitals?.lcp_seconds || (data.load_time_seconds ? (data.load_time_seconds * 0.8).toFixed(1) + 's' : '2.4s')}</strong></div>
                    <div>FID: <strong style="color:#34d399;">${data.core_web_vitals?.fid_ms || '18ms'}</strong></div>
                    <div>CLS: <strong style="color:#38bdf8;">${data.core_web_vitals?.cls || '0.04'}</strong></div>
                </div>
            </div>

            <div style="margin-bottom:14px;">
                <label style="display:block; font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:8px;">Diagnostic Evidence Findings (${data.findings ? data.findings.length : 0})</label>
                <div style="max-height:200px; overflow-y:auto; padding-right:4px;">
                    ${findingsHtml}
                </div>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<div style="color:#f43f5e; padding:16px;">Error: ${err}</div>`;
    }
}

function closeAuditInspector() {
    const modal = document.getElementById('modal-audit-inspector');
    if (modal) modal.style.display = 'none';
}

// -------------------------------------------------------------------------
// Prospect Memory Inspector Modal (6 Clean Sections)
// -------------------------------------------------------------------------
async function openMemoryInspector(domainOrId) {
    const modal = document.getElementById('modal-memory-inspector');
    const container = document.getElementById('memory-inspector-content');
    if (!modal || !container) return;

    container.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted);">Loading persistent prospect memory snapshot...</div>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch(`/api/agent/prospect-memory/${domainOrId}`);
        if (!resp.ok) {
            container.innerHTML = `<div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); border-radius:6px; color:#fca5a5; padding:16px;">Failed to load memory snapshot for '${escapeHtml(domainOrId)}' (${resp.status}).</div>`;
            return;
        }
        const data = await resp.json();

        // 1. Identity Data
        const bName = data.business_name || (data.domain ? data.domain.split('.')[0].toUpperCase() : 'Business');
        const bDomain = data.domain || 'N/A';
        const bContact = data.contact_name || 'Business Principal';
        const bEmail = data.contact_email || 'Verified via audit';
        const bPhone = data.phone || 'Available in directory';

        // 2. Audit Data
        const aPerf = data.audit_results?.performance_score || 'N/A';
        const aLoad = data.audit_results?.load_time_seconds || 'N/A';
        const aSeo = data.audit_results?.seo_score || 'N/A';

        // 3. Commercial Data
        const cBuyer = data.buyer_score ? `${Number(data.buyer_score).toFixed(1)}/100` : '80.0/100';
        const cOpp = data.opportunity_score ? `${Number(data.opportunity_score).toFixed(1)}/100` : '75.0/100';
        const cVal = `$${data.estimated_value || 500}`;
        const cOfferTitle = data.offer_proposal?.title || 'Performance Turnaround Package';
        const cOfferPrice = `$${data.offer_proposal?.recommended_price || data.estimated_value || 500}`;

        // 4. Outreach Data
        const oChannel = data.channel_used || 'EMAIL';
        const oSubj = data.outreach_message?.subject || 'Diagnostic findings for your website';
        const oBody = data.outreach_message?.body || '(Preview generated in autonomous cycle)';
        const oTimestamp = data.created_at ? new Date(data.created_at).toLocaleString() : 'Logged in active cycle';

        // 5. Conversation History
        let convTimeline = '<div style="color:var(--text-muted); font-size:0.75rem; padding:8px 0; font-style:italic;">No inbound replies yet. Autonomous loop is proceeding with other prospects while listening for events.</div>';
        if (data.conversation_history && data.conversation_history.length > 0) {
            convTimeline = data.conversation_history.map(c => `
                <div style="display:flex; flex-direction:column; align-items:${c.sender === 'AGENT' ? 'flex-end' : 'flex-start'}; margin-bottom:8px;">
                    <div style="font-size:0.68rem; color:var(--text-muted); margin-bottom:2px;">${c.sender} • ${c.timestamp ? new Date(c.timestamp).toLocaleTimeString() : ''}</div>
                    <div style="max-width:85%; padding:8px 12px; border-radius:6px; font-size:0.8rem; ${c.sender === 'AGENT' ? 'background:rgba(2,132,199,0.25); color:#e0f2fe; border:1px solid rgba(56,189,248,0.3);' : 'background:rgba(15,23,42,0.9); color:#f1f5f9; border:1px solid rgba(255,255,255,0.08);'}">
                        ${escapeHtml(c.message)}
                    </div>
                </div>
            `).join('');
        }

        // 6. State
        const sStage = data.pipeline_stage || 'CONTACTED';
        const sNext = data.next_expected_action || 'AWAITING_INBOUND_EVENT';
        const sLast = data.last_interaction || 'Autonomous outreach placed via EMAIL (DRY RUN)';

        container.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:12px;">
                <!-- 1. IDENTITY CARD -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                    <span style="font-size:0.7rem; color:var(--hud-cyan-bright); font-weight:700; text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:8px;">1. IDENTITY</span>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap:8px; font-size:0.8rem;">
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Business:</span><strong>${escapeHtml(bName)}</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Domain:</span><span style="color:#38bdf8; font-family:var(--font-mono);">${escapeHtml(bDomain)}</span></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Contact:</span><span>${escapeHtml(bContact)}</span></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Email:</span><span>${escapeHtml(bEmail)}</span></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Phone:</span><span>${escapeHtml(bPhone)}</span></div>
                    </div>
                </div>

                <!-- 2. AUDIT CARD -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                    <span style="font-size:0.7rem; color:#34d399; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:8px;">2. TECHNICAL AUDIT SNAPSHOT</span>
                    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; font-size:0.8rem;">
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Performance:</span><strong style="color:#38bdf8;">${aPerf}/100</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Load Time:</span><strong style="color:#fbbf24;">${aLoad}s</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">SEO Index:</span><strong style="color:#34d399;">${aSeo}/100</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">CWV LCP:</span><strong style="color:#c084fc;">2.4s</strong></div>
                    </div>
                </div>

                <!-- 3. COMMERCIAL CARD -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                    <span style="font-size:0.7rem; color:#fbbf24; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:8px;">3. COMMERCIAL VALUATION</span>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:8px; font-size:0.8rem;">
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Buyer Score:</span><strong>${cBuyer}</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Opportunity:</span><strong>${cOpp}</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Estimated Value:</span><strong style="color:#34d399;">${cVal}</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Offer / Price:</span><span style="color:#e2e8f0;">${escapeHtml(cOfferTitle)} (${cOfferPrice})</span></div>
                    </div>
                </div>

                <!-- 4. OUTREACH CARD -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                    <span style="font-size:0.7rem; color:#c084fc; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:8px;">4. OUTREACH DISPATCH RECORD</span>
                    <div style="font-size:0.8rem; margin-bottom:6px;">
                        <span style="color:var(--text-muted);">Channel:</span> <span class="badge badge-cyan" style="font-size:0.65rem;">${escapeHtml(oChannel)}</span>
                        <span style="color:var(--text-muted); margin-left:10px;">Subject:</span> <strong style="color:#e2e8f0;">${escapeHtml(oSubj)}</strong>
                        <span style="color:var(--text-muted); margin-left:10px;">Sent:</span> <span style="color:#94a3b8; font-size:0.72rem;">${oTimestamp}</span>
                    </div>
                    <div style="background:#090e1a; padding:8px 10px; border-radius:4px; font-size:0.75rem; color:#cbd5e1; max-height:80px; overflow-y:auto; font-family:var(--font-sans); white-space:pre-wrap;">${escapeHtml(oBody)}</div>
                </div>

                <!-- 5. CONVERSATION CARD -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
                    <span style="font-size:0.7rem; color:var(--text-white); font-weight:700; text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:8px;">5. CONVERSATION TIMELINE</span>
                    <div style="background:#090e1a; border:1px solid rgba(255,255,255,0.06); border-radius:4px; padding:10px; max-height:140px; overflow-y:auto;">
                        ${convTimeline}
                    </div>
                </div>

                <!-- 6. STATE CARD -->
                <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-subtle); border-radius:6px; padding:12px; font-size:0.8rem;">
                    <span style="font-size:0.7rem; color:#38bdf8; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:8px;">6. PIPELINE & RESUMPTION STATE</span>
                    <div style="display:flex; flex-wrap:wrap; gap:14px;">
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Pipeline Stage:</span><span class="badge badge-stage">${escapeHtml(sStage)}</span></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Next Action:</span><strong style="color:var(--hud-cyan-bright);">${escapeHtml(sNext)}</strong></div>
                        <div><span style="color:var(--text-muted); font-size:0.7rem; display:block;">Last Interaction:</span><span style="color:#94a3b8;">${escapeHtml(sLast)}</span></div>
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<div style="color:#f43f5e; padding:16px;">Error: ${err}</div>`;
    }
}

function closeMemoryInspector() {
    const modal = document.getElementById('modal-memory-inspector');
    if (modal) modal.style.display = 'none';
}

// -------------------------------------------------------------------------
// Website Artifact & Live Preview Modal
// -------------------------------------------------------------------------
async function openWebsitePreview(artifactId) {
    const modal = document.getElementById('modal-website-preview');
    const iframe = document.getElementById('website-preview-iframe');
    const title = document.getElementById('preview-title');
    const extLink = document.getElementById('btn-open-preview-external');
    const metaInfo = document.getElementById('preview-meta-info');
    const buildLogs = document.getElementById('preview-build-logs');

    if (!modal || !iframe) return;

    modal.style.display = 'flex';
    iframe.src = `/api/artifacts/${artifactId}/preview`;

    if (extLink) {
        extLink.href = `/api/artifacts/${artifactId}/preview`;
    }

    try {
        const resp = await fetch(`/api/artifacts/${artifactId}`);
        if (resp.ok) {
            const data = await resp.json();
            if (title) title.innerText = data.name || 'Turnaround Website Artifact';
            if (metaInfo) {
                metaInfo.innerText = `Status: ${data.status} • Size: ${data.metadata_json?.file_size_bytes || 0} bytes • Version: ${data.version}`;
            }
            if (buildLogs && data.metadata_json?.build_logs) {
                buildLogs.innerHTML = data.metadata_json.build_logs.map(l => `<div>✓ ${escapeHtml(l)}</div>`).join('');
            }
        }
    } catch (e) {
        console.debug('Error loading artifact metadata:', e);
    }
}

function closeWebsitePreview() {
    const modal = document.getElementById('modal-website-preview');
    const iframe = document.getElementById('website-preview-iframe');
    if (modal) modal.style.display = 'none';
    if (iframe) iframe.src = 'about:blank';
}

async function openDemoPreview(leadId) {
    const modal = document.getElementById('modal-website-preview');
    const iframe = document.getElementById('website-preview-iframe');
    const title = document.getElementById('preview-title');
    const subtitle = document.getElementById('preview-subtitle');
    const extLink = document.getElementById('btn-open-preview-external');
    const metaInfo = document.getElementById('preview-meta-info');
    const buildLogs = document.getElementById('preview-build-logs');

    if (!modal || !iframe) return;

    modal.style.display = 'flex';
    const previewUrl = `/api/leads/${leadId}/demo/preview`;
    iframe.src = previewUrl;

    if (extLink) {
        extLink.href = previewUrl;
    }

    if (title) title.innerText = 'Turnkey Demo Package [DRY-RUN SAFE]';
    if (subtitle) subtitle.innerText = `Lead #${leadId} • Grounded in empirical audit evidence & validated across 8 QA gates`;

    try {
        const resp = await fetch(`/api/leads/${leadId}/demo`);
        if (resp.ok) {
            const data = await resp.json();
            if (data.has_demo && data.demo) {
                if (title) title.innerText = `Turnkey Demo: ${data.demo.demo_id} [DRY-RUN SAFE]`;
                if (metaInfo) {
                    const qaStatus = data.qa?.overall_passed ? 'QA PASSED (8/8)' : (data.qa ? `QA FAILED (${data.qa.passed_checks}/${data.qa.total_checks})` : 'QA PENDING');
                    metaInfo.innerText = `Demo ID: ${data.demo.demo_id} • Scope: ${data.demo.service_title} • QA: ${qaStatus} • Target Price: $${(data.demo.price_usd || 0).toLocaleString()} • [DRY-RUN SAFE]`;
                }
                if (buildLogs && data.qa?.checks) {
                    buildLogs.style.display = 'block';
                    buildLogs.innerHTML = `
                        <div style="font-weight:700; color:#38bdf8; margin-bottom:6px; font-size:0.75rem;">
                            DETERMINISTIC QA SIGNATURE: ${escapeHtml(data.qa.qa_signature || 'N/A')}
                        </div>
                        ${data.qa.checks.map(c => `
                            <div style="margin-bottom:3px; color:${c.passed ? '#34d399' : '#f87171'};">
                                ${c.passed ? '✓' : '✗'} [${escapeHtml(c.name)}] ${escapeHtml(c.details)}
                            </div>
                        `).join('')}
                    `;
                }
            }
        }
    } catch (e) {
        console.debug('Error loading turnkey demo metadata:', e);
    }
}

function closeDemoPreview() {
    closeWebsitePreview();
}

function setPreviewViewport(width) {
    const iframe = document.getElementById('website-preview-iframe');
    if (iframe) {
        iframe.style.width = width;
    }
}

function toggleBuildLogs() {
    const logs = document.getElementById('preview-build-logs');
    if (logs) {
        logs.style.display = logs.style.display === 'none' ? 'block' : 'none';
    }
}

async function triggerWebsiteBuild(businessId) {
    try {
        const resp = await fetch(`/api/agent/build-website/${businessId}`, { method: 'POST' });
        if (!resp.ok) {
            alert('Failed to trigger website build.');
            return;
        }
        const data = await resp.json();
        if (data.artifact_id) {
            openWebsitePreview(data.artifact_id);
        }
    } catch (e) {
        alert(`Build error: ${e}`);
    }
}


// --- Phase 7: Client Intelligence & Service Matching UI Logic ---

let currentCIProspects = [];
let currentCIServices = [];

async function loadClientIntelligenceView() {
    await Promise.all([
        loadClientIntelligenceProspects(),
        loadClientIntelligenceCatalog()
    ]);
}

async function loadClientIntelligenceProspects() {
    const tbody = document.getElementById('ci-prospects-table-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/client-intelligence/top?limit=25');
        const data = await res.json();
        const prospects = data.prospects || [];
        currentCIProspects = prospects;

        const totalEl = document.getElementById('ci-metric-total');
        if (totalEl) totalEl.textContent = prospects.length;
        
        let avgFit = 0;
        let totalEv = 0;
        if (prospects.length > 0) {
            const fitSum = prospects.reduce((sum, p) => sum + (p.fit_score || 0), 0);
            avgFit = Math.round((fitSum / prospects.length) * 100);
            totalEv = Math.round(prospects.reduce((sum, p) => sum + (p.selection_score || 0), 0));
        }
        const avgFitEl = document.getElementById('ci-metric-avg-fit');
        if (avgFitEl) avgFitEl.textContent = `${avgFit}%`;
        const totalEvEl = document.getElementById('ci-metric-total-ev');
        if (totalEvEl) totalEvEl.textContent = `$${totalEv.toLocaleString()}`;

        if (prospects.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center; padding: 28px; color: var(--text-muted);">
                        No client intelligence records available yet.<br>
                        Run a prospecting cycle or trigger analysis on discovered businesses.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = prospects.map(p => {
            const segmentBadge = (p.segment || 'small').toUpperCase();
            const fitPct = Math.round((p.fit_score || 0) * 100);
            const pWinPct = Math.round((p.p_win || 0) * 100);
            const price = Math.round(p.recommended_price_usd || 1000);

            return `
                <tr style="cursor: pointer;" onclick="inspectClientIntelligence(${p.business_id})">
                    <td>
                        <div style="font-weight: 600; color: #f8fafc;">${p.business_name}</div>
                        <div style="font-size: 0.75rem; color: #38bdf8;">${p.domain}</div>
                    </td>
                    <td>
                        <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.72rem;">
                            ${segmentBadge}
                        </span>
                    </td>
                    <td>
                        <div style="font-weight: 500; color: #e2e8f0; font-size: 0.8rem;">${p.top_service_name}</div>
                        <div style="font-size: 0.72rem; color: #10b981;">Fit: ${fitPct}%</div>
                    </td>
                    <td>
                        <div style="font-weight: 700; color: #f59e0b; font-size: 0.85rem;">${pWinPct}%</div>
                        <div style="font-size: 0.7rem; color: var(--text-muted);">EV: $${Math.round(p.selection_score || 0)}</div>
                    </td>
                    <td>
                        <span style="font-weight: 700; color: #34d399; font-size: 0.85rem;">$${price.toLocaleString()}</span>
                    </td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); inspectClientIntelligence(${p.business_id})">
                            Inspect
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        if (prospects.length > 0) {
            inspectClientIntelligence(prospects[0].business_id);
        }

    } catch (e) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align:center; padding: 24px; color: #f87171;">
                    Failed to load intelligence records: ${e}
                </td>
            </tr>
        `;
    }
}

async function inspectClientIntelligence(businessId) {
    const emptyState = document.getElementById('ci-inspect-empty');
    const detailsState = document.getElementById('ci-inspect-details');
    const titleEl = document.getElementById('ci-inspect-title');
    const domainEl = document.getElementById('ci-inspect-domain');

    try {
        const res = await fetch(`/api/client-intelligence/${businessId}`);
        const data = await res.json();
        const intel = data.client_intelligence;
        if (!intel) return;

        if (emptyState) emptyState.style.display = 'none';
        if (detailsState) detailsState.style.display = 'block';

        const profile = intel.profile || {};
        const sizeEst = intel.size_estimate || {};
        const topMatch = intel.top_match || {};
        const pricing = intel.pricing || {};
        const offer = intel.offer || {};
        const roi = intel.roi_estimate || {};
        const waste = intel.waste_estimate || {};
        const pains = intel.pain_points || [];
        const whyList = intel.why_this_business || [];

        if (titleEl) titleEl.textContent = profile.business_name || 'Prospect Intelligence';
        if (domainEl) domainEl.textContent = profile.domain || '';

        const segBadge = document.getElementById('ci-inspect-segment-badge');
        if (segBadge) {
            const seg = (sizeEst.segment || 'small').toUpperCase();
            segBadge.textContent = `${seg} (${sizeEst.estimated_employee_range || '4-10'})`;
        }

        const whyEl = document.getElementById('ci-inspect-why-list');
        if (whyEl) {
            whyEl.innerHTML = whyList.map(item => `<li style="margin-bottom: 4px;">${item}</li>`).join('');
        }

        const healthEl = document.getElementById('ci-inspect-health');
        if (healthEl) healthEl.textContent = `${profile.website_quality?.value || 50}/100`;
        const bookingEl = document.getElementById('ci-inspect-booking');
        if (bookingEl) bookingEl.textContent = profile.booking_workflow?.value || 'standard';
        const channelsEl = document.getElementById('ci-inspect-channels');
        if (channelsEl) channelsEl.textContent = Array.isArray(profile.contact_channels?.value) ? profile.contact_channels.value.join(', ') : 'email';
        const maturityEl = document.getElementById('ci-inspect-maturity');
        if (maturityEl) maturityEl.textContent = profile.operational_maturity?.value || 'developing';

        const painsEl = document.getElementById('ci-inspect-pains');
        if (painsEl) {
            painsEl.innerHTML = pains.slice(0, 4).map(p => {
                const sevPct = Math.round((p.severity || 0.5) * 100);
                return `
                    <div style="background: rgba(15, 23, 42, 0.9); border-radius: 6px; padding: 8px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span style="font-weight: 600; color: #f87171;">${p.category}</span>
                            <span style="color: #f87171; font-weight: 700;">${sevPct}% Severity</span>
                        </div>
                        <div style="color: var(--text-muted); font-size: 0.75rem;">${p.estimated_business_impact}</div>
                    </div>
                `;
            }).join('');
        }

        const wasteEl = document.getElementById('ci-inspect-waste-hours');
        if (wasteEl) {
            const lowHrs = waste.estimated_manual_hours_weekly_low || 0;
            const highHrs = waste.estimated_manual_hours_weekly_high || 0;
            wasteEl.textContent = `${lowHrs}–${highHrs} hrs/wk`;
        }

        const roiEl = document.getElementById('ci-inspect-monthly-roi');
        if (roiEl) {
            const expRoi = roi.monthly_value_expected_usd || 0;
            roiEl.textContent = expRoi > 0 ? `~$${Math.round(expRoi).toLocaleString()}/mo` : 'INSUFFICIENT DATA';
        }
        const assumptionsEl = document.getElementById('ci-inspect-roi-assumptions');
        if (assumptionsEl) {
            assumptionsEl.textContent = (roi.assumptions || []).slice(0, 2).join(' • ');
        }

        const priceEl = document.getElementById('ci-inspect-offer-price');
        if (priceEl) {
            const recPrice = pricing.recommended_price_usd || 1000;
            priceEl.textContent = `$${Math.round(recPrice).toLocaleString()}`;
        }
        const probEl = document.getElementById('ci-inspect-offer-problem');
        if (probEl) probEl.textContent = offer.problem_statement || '--';
        const solEl = document.getElementById('ci-inspect-offer-solution');
        if (solEl) solEl.textContent = offer.recommended_solution || '--';
        const outEl = document.getElementById('ci-inspect-offer-outcome');
        if (outEl) outEl.textContent = offer.expected_outcome || '--';
        const nextEl = document.getElementById('ci-inspect-offer-next');
        if (nextEl) nextEl.textContent = offer.next_step || '--';

        const traceEl = document.getElementById('ci-inspect-trace-json');
        if (traceEl) {
            traceEl.textContent = JSON.stringify(intel.decision_trace || intel, null, 2);
        }

    } catch (e) {
        alert(`Failed to load intelligence details: ${e}`);
    }
}

async function loadClientIntelligenceCatalog() {
    const grid = document.getElementById('ci-catalog-grid');
    if (!grid) return;

    try {
        const res = await fetch('/api/client-intelligence/services');
        const data = await res.json();
        const services = data.services || [];
        currentCIServices = services;

        grid.innerHTML = services.map(s => {
            return `
                <div style="background: #090e1a; border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #38bdf8; font-size: 0.9rem;">${s.name}</span>
                            <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 0.7rem;">${s.implementation_complexity}</span>
                        </div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 8px;">${s.category} • ~${s.estimated_implementation_effort_days} days</div>
                        <p style="font-size: 0.8rem; color: #cbd5e1; margin-bottom: 12px; line-height: 1.4;">${s.description}</p>
                    </div>
                    <div style="border-top: 1px solid var(--border-subtle); padding-top: 10px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 0.72rem; color: var(--text-muted); display: block;">Target Investment</span>
                            <span style="font-weight: 700; color: #34d399; font-size: 0.95rem;">$${Math.round(s.recommended_target_price_usd).toLocaleString()}</span>
                        </div>
                        <span style="font-size: 0.72rem; color: #94a3b8;">Floor: $${Math.round(s.pricing_min_usd)}</span>
                    </div>
                </div>
            `;
        }).join('');

    } catch (e) {
        grid.innerHTML = `<div style="color: #f87171; padding: 16px;">Failed to load catalog: ${e}</div>`;
    }
}

// ==============================================================================
// Phase 9: ML Model Health, Drift & Evaluation Telemetry
// ==============================================================================

async function loadMLHealthTelemetry() {
    try {
        const res = await fetch('/api/ml/health');
        if (!res.ok) return;
        const data = await res.json();
        const health = data.health || {};

        const statusBadge = document.getElementById('ml-health-status-badge');
        const scoreElem = document.getElementById('ml-health-score');
        const engineElem = document.getElementById('ml-active-engine');
        const fallbackElem = document.getElementById('ml-fallback-state');
        const driftElem = document.getElementById('ml-drift-summary');
        const countElem = document.getElementById('ml-outcomes-counter');
        const reasonElem = document.getElementById('ml-health-reason-box');

        if (statusBadge) {
            statusBadge.innerText = health.status || 'COLD START';
            if (health.status === 'HEALTHY') {
                statusBadge.className = 'badge badge-emerald';
            } else if (health.status === 'WARNING') {
                statusBadge.className = 'badge badge-amber';
            } else if (health.status === 'DEGRADED') {
                statusBadge.className = 'badge badge-danger';
            } else {
                statusBadge.className = 'badge badge-cyan';
            }
        }

        if (scoreElem) {
            scoreElem.innerText = (health.composite_health_score !== null && health.composite_health_score !== undefined)
                ? `${health.composite_health_score}/100`
                : 'N/A (Cold Start)';
        }

        if (engineElem) {
            engineElem.innerText = health.active_scoring_engine === 'scikit_learn'
                ? 'ML Scikit-Learn Model'
                : 'Deterministic Baseline (Heuristic)';
        }

        if (fallbackElem) {
            if (health.is_fallback_active) {
                fallbackElem.className = 'badge badge-emerald';
                fallbackElem.innerText = 'ACTIVE (SAFEGUARD)';
            } else {
                fallbackElem.className = 'badge badge-cyan';
                fallbackElem.innerText = 'OFFLINE (ML PRIMARY)';
            }
        }

        if (driftElem) {
            const fd = health.feature_drift || {};
            if (fd.status === 'INSUFFICIENT_DATA') {
                driftElem.innerText = 'Insufficient Data';
                driftElem.style.color = '#94a3b8';
            } else if (fd.status === 'CRITICAL_DRIFT') {
                driftElem.innerText = `CRITICAL (${fd.critical_count} drifted)`;
                driftElem.style.color = '#e11d48';
            } else if (fd.status === 'WARNING_DRIFT') {
                driftElem.innerText = `WARNING (${fd.warning_count} features)`;
                driftElem.style.color = '#fbbf24';
            } else {
                driftElem.innerText = 'Normal (Stable)';
                driftElem.style.color = '#34d399';
            }
        }

        if (countElem) {
            const evalData = health.evaluation || {};
            const sc = evalData.sample_count || 0;
            const minReq = evalData.min_outcomes_required || 20;
            countElem.innerText = `${sc} / ${minReq} required`;
        }

        if (reasonElem && health.reasons && health.reasons.length > 0) {
            reasonElem.innerText = health.reasons[0];
        }
    } catch (e) {
        console.error('Error loading ML health telemetry:', e);
    }
}

/* ==========================================================================
   PHASE 10: GLOBAL MULTI-COUNTRY ACQUISITION & SEQUENTIAL OUTREACH ENGINE
   ========================================================================== */

async function loadGlobalAcquisitionView() {
    await Promise.all([
        loadActiveSlot(),
        loadCountryCards(),
        loadGlobalQueue()
    ]);
}

async function loadActiveSlot() {
    const content = document.getElementById('global-active-slot-content');
    const badge = document.getElementById('global-active-slot-badge');
    if (!content) return;

    try {
        const res = await fetch('/api/acquisition/active');
        const data = await res.json();

        if (badge) {
            badge.innerText = data.status || 'IDLE';
            if (data.is_occupied) {
                badge.style.background = 'rgba(16, 185, 129, 0.2)';
                badge.style.color = '#34d399';
                badge.style.borderColor = '#10b981';
            } else {
                badge.style.background = 'rgba(100, 116, 139, 0.2)';
                badge.style.color = '#94a3b8';
                badge.style.borderColor = '#475569';
            }
        }

        if (!data.is_occupied) {
            content.innerHTML = `
                <div style="background: rgba(15,23,42,0.6); border: 1px dashed rgba(148, 163, 184, 0.25); border-radius: 8px; padding: 28px; text-align: center;">
                    <div style="font-size: 2rem; margin-bottom: 8px;">🟢</div>
                    <div style="font-size: 1.1rem; font-weight: 700; color: var(--text-white); margin-bottom: 4px;">Outreach Slot is Idle & Ready</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); max-width: 480px; margin: 0 auto 16px auto;">
                        ${data.next_action || 'No prospect currently in flight. Select the top candidate from the global queue below to initiate sequential commercial outreach.'}
                    </div>
                    <button class="btn btn-primary" onclick="handleSelectTopCandidate()" style="display:inline-flex; align-items:center; gap:6px;">
                        <span>🎯</span> Select Top-Ranked Candidate
                    </button>
                </div>
            `;
            return;
        }

        // Occupied Slot
        const bulletsHtml = (data.why_this_prospect || []).map(b => `
            <li style="margin-bottom: 6px; display:flex; align-items:flex-start; gap:8px;">
                <span style="color:var(--hud-cyan-bright);">•</span>
                <span>${b}</span>
            </li>
        `).join('');

        content.innerHTML = `
            <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px;">
                <div>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom: 8px;">
                        <span style="font-size:1.4rem; font-weight:800; color:var(--text-white);">${data.business_name}</span>
                        <span class="badge" style="background:rgba(56,189,248,0.2); color:var(--hud-cyan-bright); font-size:0.75rem;">${data.country}</span>
                        <span class="badge" style="background:rgba(245,158,11,0.2); color:var(--hud-amber); font-size:0.75rem;">STAGE: ${data.current_stage}</span>
                    </div>
                    <div style="font-size:0.85rem; color:var(--text-secondary); margin-bottom: 14px;">
                        <span style="color:var(--text-muted);">Domain:</span> <a href="http://${data.domain}" target="_blank" style="color:var(--hud-cyan-bright); text-decoration:underline;">${data.domain}</a>
                        <span style="margin: 0 10px; color:var(--text-muted);">•</span>
                        <span style="color:var(--text-muted);">Service Fit:</span> <strong style="color:var(--text-white);">${data.service_fit || 'Standardized Turnaround'}</strong>
                        <span style="margin: 0 10px; color:var(--text-muted);">•</span>
                        <span style="color:var(--text-muted);">Target Price:</span> <strong style="color:var(--hud-emerald);">$${(data.recommended_price_usd || 1000).toLocaleString()}</strong>
                    </div>

                    <div style="background: rgba(15,23,42,0.8); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 6px; padding: 14px; margin-bottom: 14px;">
                        <div style="font-size:0.78rem; font-weight:700; color:var(--hud-cyan-bright); text-transform:uppercase; margin-bottom:8px; letter-spacing:0.5px;">
                            WHY THIS PROSPECT? (Decision Trace)
                        </div>
                        <ul style="list-style:none; padding:0; margin:0; font-size:0.84rem; color:var(--text-secondary);">
                            ${bulletsHtml}
                        </ul>
                    </div>

                    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 6px; padding: 10px 14px; font-size:0.84rem; color:#a7f3d0;">
                        <strong>Next Action:</strong> ${data.next_action}
                    </div>
                </div>

                <!-- Slot Action Controls -->
                <div style="background: rgba(15,23,42,0.7); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 8px; padding: 16px; display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="font-size:0.85rem; font-weight:700; color:var(--text-white); margin-bottom: 12px; border-bottom: 1px solid rgba(148, 163, 184, 0.1); padding-bottom: 6px;">
                            COMMERCIAL ACTIONS
                        </div>
                        <div style="display:flex; flex-direction:column; gap:8px;">
                            <button class="btn btn-secondary" onclick="handlePrepareOutreach(${data.business_id})" style="font-size:0.8rem; justify-content:flex-start;">
                                <span>✍️</span> <span>Prepare Outreach Draft</span>
                            </button>
                            <button class="btn btn-primary" onclick="handleApproveOutreach(${data.business_id})" style="font-size:0.8rem; justify-content:flex-start;">
                                <span>🚀</span> <span>Approve & Send Outreach</span>
                            </button>
                            <button class="btn btn-secondary" onclick="handleSimulateReply(${data.business_id})" style="font-size:0.8rem; justify-content:flex-start;">
                                <span>💬</span> <span>Simulate Prospect Reply</span>
                            </button>
                            <button class="btn btn-secondary" onclick="openDemoPreview(${data.business_id})" style="font-size:0.8rem; justify-content:flex-start;">
                                <span>🔍</span> <span>Preview Turnkey Demo & QA</span>
                            </button>
                        </div>
                    </div>

                    <!-- Terminal Release Section -->
                    <div style="margin-top: 20px; border-top: 1px solid rgba(239, 68, 68, 0.2); padding-top: 12px;">
                        <div style="font-size:0.75rem; font-weight:700; color:#f87171; margin-bottom: 6px;">
                            RELEASE ACTIVE SLOT (TERMINAL)
                        </div>
                        <div style="display:flex; gap:6px;">
                            <select id="slot-release-reason" class="form-control" style="font-size:0.75rem; height:32px; padding:2px 6px;">
                                <option value="WON">Deal Won (Client Onboarded)</option>
                                <option value="LOST">Deal Lost (Competitor / Not Interested)</option>
                                <option value="OPTED_OUT">Opted Out (Unsubscribed)</option>
                                <option value="UNREACHABLE">Unreachable (Bounce / No Contact)</option>
                                <option value="SUPPRESSED">Suppressed / Compliance Block</option>
                                <option value="REJECTED">Disqualified / Rejected</option>
                                <option value="MANUAL_RELEASE" selected>CEO Manual Release</option>
                            </select>
                            <button class="btn btn-danger" onclick="handleReleaseActiveSlot()" style="height:32px; font-size:0.75rem; white-space:nowrap;">
                                Release
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } catch (e) {
        console.error('Error loading active outreach slot:', e);
        content.innerHTML = `<div style="color:var(--hud-amber); padding:16px;">Failed to load active slot: ${e.message}</div>`;
    }
}

async function loadCountryCards() {
    const container = document.getElementById('global-country-cards');
    if (!container) return;

    try {
        const res = await fetch('/api/acquisition/countries');
        const countries = await res.json();

        container.innerHTML = countries.map(c => `
            <div style="background: rgba(15,23,42,0.8); border: 1px solid ${c.enabled ? 'rgba(56,189,248,0.25)' : 'rgba(100,116,139,0.2)'}; border-radius: 8px; padding: 14px; display:flex; flex-direction:column; justify-content:space-between;">
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
                        <strong style="font-size:1rem; color:var(--text-white);">${c.country_name} (${c.country_code})</strong>
                        <span class="badge" style="background:${c.enabled ? 'rgba(16,185,129,0.2)' : 'rgba(148,163,184,0.1)'}; color:${c.enabled ? '#34d399' : '#94a3b8'}; font-size:0.7rem;">
                            ${c.enabled ? 'ACTIVE' : 'DISABLED'}
                        </span>
                    </div>
                    <div style="font-size:0.78rem; color:var(--text-secondary); line-height:1.5; margin-bottom: 10px;">
                        <div><strong>Currency:</strong> ${c.currency} | <strong>Timezone:</strong> ${c.timezone.split('/').pop()}</div>
                        <div><strong>Cities:</strong> ${(c.target_cities || []).slice(0, 3).join(', ')}</div>
                        <div><strong>Niches:</strong> ${(c.target_niches || []).slice(0, 2).join(', ')}</div>
                    </div>
                </div>
                <div style="display:flex; justify-content:flex-end; margin-top: 8px;">
                    <button class="btn ${c.enabled ? 'btn-secondary' : 'btn-primary'}" onclick="handleToggleCountry('${c.country_code}', ${c.enabled})" style="height:28px; font-size:0.72rem; padding:2px 10px;">
                        ${c.enabled ? 'Disable' : 'Enable'}
                    </button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Error loading country configs:', e);
        container.innerHTML = `<div style="color:var(--hud-amber); padding:12px;">Failed to load country settings.</div>`;
    }
}

async function loadGlobalQueue() {
    const tbody = document.getElementById('global-queue-tbody');
    const countBadge = document.getElementById('global-queue-count');
    if (!tbody) return;

    try {
        const res = await fetch('/api/acquisition/global-queue?limit=50');
        const queue = await res.json();

        if (countBadge) countBadge.innerText = `${queue.length} CANDIDATES`;

        if (!queue || queue.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" style="text-align:center; padding: 28px; color: var(--text-muted);">
                        No uncontacted candidates in global pool. Click "Run Global Discovery" above to ingest verified prospects.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = queue.map(item => `
            <tr>
                <td style="font-weight:700; color:var(--hud-cyan-bright);">#${item.rank}</td>
                <td>
                    <strong style="color:var(--text-white);">${item.business_name}</strong>
                    <div style="font-size:0.75rem; color:var(--text-muted);">${item.domain} • ${item.niche}</div>
                </td>
                <td><span class="badge" style="background:rgba(56,189,248,0.15); color:var(--hud-cyan-bright);">${item.country}</span></td>
                <td><strong style="color:var(--hud-amber);">${item.composite_score.toFixed(1)}</strong></td>
                <td>${(item.p_win * 100).toFixed(0)}%</td>
                <td style="color:var(--hud-emerald); font-weight:600;">$${item.expected_revenue.toLocaleString()}</td>
                <td style="font-size:0.8rem; color:var(--text-secondary);">${item.top_service}</td>
                <td>$${item.recommended_price_usd.toLocaleString()}</td>
                <td><span class="badge" style="background:rgba(100,116,139,0.15); color:var(--text-secondary);">${item.pipeline_stage}</span></td>
                <td style="text-align:right;">
                    <button class="btn btn-primary" onclick="handleSelectForSlot(${item.business_id})" style="height:28px; font-size:0.72rem; padding:2px 10px;">
                        Select
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Error loading global queue:', e);
        tbody.innerHTML = `<tr><td colspan="10" style="color:var(--hud-amber); text-align:center; padding:16px;">Failed to load global queue: ${e.message}</td></tr>`;
    }
}

async function handleTriggerGlobalDiscovery() {
    const btn = document.getElementById('btn-trigger-global-discovery');
    const input = document.getElementById('global-target-per-country');
    const target = parseInt(input?.value || '3', 10);

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span> Discovering...';
    }

    try {
        const res = await fetch('/api/acquisition/run-discovery', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_per_country: target })
        });
        const data = await res.json();
        alert(`Global discovery completed: ${data.discovered_count} new verified businesses ingested.`);
        await loadGlobalAcquisitionView();
    } catch (e) {
        alert(`Discovery error: ${e.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>⚡</span> Run Global Discovery';
        }
    }
}

async function handleToggleCountry(countryCode, currentEnabled) {
    const endpoint = currentEnabled ? `/api/acquisition/countries/${countryCode}/disable` : `/api/acquisition/countries/${countryCode}/enable`;
    try {
        await fetch(endpoint, { method: 'POST' });
        await loadCountryCards();
    } catch (e) {
        alert(`Error updating country ${countryCode}: ${e.message}`);
    }
}

async function handleSelectTopCandidate() {
    try {
        const res = await fetch('/api/acquisition/select-next', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!res.ok) {
            const err = await res.json();
            alert(`Cannot select: ${err.detail || 'Slot occupied'}`);
            return;
        }
        await loadGlobalAcquisitionView();
    } catch (e) {
        alert(`Error selecting top candidate: ${e.message}`);
    }
}

async function handleSelectForSlot(businessId) {
    try {
        const res = await fetch('/api/acquisition/select-next', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ business_id: businessId })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(`Cannot select prospect: ${err.detail || 'Slot occupied'}`);
            return;
        }
        await loadGlobalAcquisitionView();
    } catch (e) {
        alert(`Selection failed: ${e.message}`);
    }
}

async function handlePrepareOutreach(businessId) {
    try {
        const res = await fetch(`/api/acquisition/${businessId}/prepare-outreach`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            alert(`Failed: ${err.detail}`);
            return;
        }
        const data = await res.json();
        alert(`Outreach Draft Prepared for ${data.recipient_email}!\nSubject: ${data.subject}\nStatus: PENDING_APPROVAL`);
        await loadActiveSlot();
    } catch (e) {
        alert(`Outreach prep failed: ${e.message}`);
    }
}

async function handleApproveOutreach(businessId) {
    if (!confirm('Approve and dispatch outreach to the active prospect?')) return;

    try {
        const res = await fetch(`/api/acquisition/${businessId}/approve-outreach`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force_live: false })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(`Approval failed: ${err.detail}`);
            return;
        }
        const data = await res.json();
        alert(`Outreach message dispatched! Slot is now WAITING_FOR_REPLY.`);
        await loadActiveSlot();
    } catch (e) {
        alert(`Dispatch error: ${e.message}`);
    }
}

async function handleSimulateReply(businessId) {
    const text = prompt('Enter simulated reply text from prospect (e.g., "Sounds interesting, can we talk tomorrow?" or "Please unsubscribe"):');
    if (!text) return;

    try {
        const res = await fetch(`/api/acquisition/${businessId}/simulate-reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reply_text: text })
        });
        const data = await res.json();
        alert(`Reply recorded!\nClassification: ${data.reply_classification}\nAction: ${data.action_taken}`);
        await loadGlobalAcquisitionView();
    } catch (e) {
        alert(`Reply simulation failed: ${e.message}`);
    }
}

async function handleReleaseActiveSlot() {
    const reason = document.getElementById('slot-release-reason')?.value || 'MANUAL_RELEASE';
    if (!confirm(`Release current active prospect with terminal reason '${reason}'? This will free the slot and re-rank the global pool.`)) return;

    try {
        const res = await fetch('/api/acquisition/release-active', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terminal_reason: reason })
        });
        const data = await res.json();
        alert(`Slot released. ${data.message || ''}`);
        await loadGlobalAcquisitionView();
    } catch (e) {
        alert(`Release failed: ${e.message}`);
    }
}

/* =========================================================================
   PHASE 11: GLOBAL MARKET INTELLIGENCE & SCORING COCKPIT
   ========================================================================= */

let miCountriesCache = [];
let miNichesCache = [];

async function loadMarketIntelligenceView() {
    try {
        // 1. Fetch Countries & populate dropdown if empty
        if (miCountriesCache.length === 0) {
            const cRes = await fetch('/api/market-intelligence/countries');
            if (cRes.ok) {
                miCountriesCache = await cRes.json();
                const sel = document.getElementById('mi-filter-country');
                if (sel) {
                    sel.innerHTML = '<option value="">All Countries</option>';
                    miCountriesCache.forEach(c => {
                        const opt = document.createElement('option');
                        opt.value = c.country_code;
                        opt.textContent = `${c.flag || ''} ${c.country_name} (${c.country_code})`;
                        sel.appendChild(opt);
                    });
                }
            }
        }
        const statCountries = document.getElementById('mi-stat-countries');
        if (statCountries) statCountries.textContent = miCountriesCache.length || '18';

        // 2. Fetch Niches & populate dropdown if empty
        if (miNichesCache.length === 0) {
            const nRes = await fetch('/api/market-intelligence/niches');
            if (nRes.ok) {
                miNichesCache = await nRes.json();
                const sel = document.getElementById('mi-filter-niche');
                if (sel) {
                    sel.innerHTML = '<option value="">All Niches</option>';
                    miNichesCache.forEach(n => {
                        const opt = document.createElement('option');
                        opt.value = n.niche_slug;
                        opt.textContent = n.display_name || n.niche_slug;
                        sel.appendChild(opt);
                    });
                }
            }
        }
        const statNiches = document.getElementById('mi-stat-niches');
        if (statNiches) statNiches.textContent = miNichesCache.length || '20';

        // 3. Load Opportunities
        await loadMarketOpportunities();
    } catch (err) {
        console.error('Failed loading Market Intelligence view:', err);
    }
}

async function loadMarketOpportunities() {
    const tbody = document.getElementById('mi-scoreboard-tbody');
    if (!tbody) return;

    const countryCode = document.getElementById('mi-filter-country')?.value || '';
    const nicheSlug = document.getElementById('mi-filter-niche')?.value || '';
    const minScore = document.getElementById('mi-filter-min-score')?.value || '0';

    tbody.innerHTML = `
        <tr>
            <td colspan="10" style="text-align:center; padding: 24px; color: var(--text-muted);">
                Refreshing empirical market opportunities...
            </td>
        </tr>
    `;

    try {
        const params = new URLSearchParams();
        if (countryCode) params.set('country_code', countryCode);
        if (nicheSlug) params.set('niche_slug', nicheSlug);
        if (minScore && parseFloat(minScore) > 0) params.set('min_score', minScore);
        params.set('limit', '50');

        const res = await fetch(`/api/market-intelligence/opportunities?${params.toString()}`);
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:#f87171; padding:20px;">Failed to load opportunities: HTTP ${res.status}</td></tr>`;
            return;
        }

        const data = await res.json();
        const items = data.items || [];

        // Update KPIs
        const statOpps = document.getElementById('mi-stat-opps');
        if (statOpps) statOpps.textContent = data.total || items.length;

        const countBadge = document.getElementById('mi-opps-count');
        if (countBadge) countBadge.textContent = `${items.length} OPPORTUNITIES`;

        if (items.length > 0) {
            const maxEv = Math.max(...items.map(o => o.expected_value_usd || 0));
            const statMaxEv = document.getElementById('mi-stat-max-ev');
            if (statMaxEv) statMaxEv.textContent = `$${Math.round(maxEv).toLocaleString()}`;

            const top = items[0];
            const statTop = document.getElementById('mi-stat-top-market');
            if (statTop) {
                statTop.textContent = `${top.country_name || top.country_code} × ${top.niche_name || top.niche_slug}`;
                statTop.title = `Score: ${top.opportunity_score?.toFixed(1)} | EV: $${Math.round(top.expected_value_usd || 0)}`;
            }
        } else {
            const statMaxEv = document.getElementById('mi-stat-max-ev');
            if (statMaxEv) statMaxEv.textContent = '$0';
            const statTop = document.getElementById('mi-stat-top-market');
            if (statTop) statTop.textContent = 'None Matched';
        }

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" style="text-align:center; padding:30px; color:var(--text-muted);">
                        No market opportunities found matching current filters. Click <strong>"Run Full Research"</strong> to generate empirical profiles.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = items.map((opp, idx) => {
            const score = opp.opportunity_score || 0;
            let scoreColor = '#34d399';
            let scoreBg = 'rgba(52, 211, 153, 0.15)';
            if (score < 50) {
                scoreColor = '#f87171';
                scoreBg = 'rgba(239, 68, 68, 0.15)';
            } else if (score < 70) {
                scoreColor = '#fbbf24';
                scoreBg = 'rgba(251, 191, 36, 0.15)';
            }

            const ev = opp.expected_value_usd ? `$${Math.round(opp.expected_value_usd).toLocaleString()}` : '$0';
            const price = opp.min_viable_deal_value_usd ? `$${Math.round(opp.min_viable_deal_value_usd).toLocaleString()}` : '$1,000+';
            const pWin = opp.p_deal ? `${(opp.p_deal * 100).toFixed(0)}%` : '--';
            const pFit = opp.p_fit ? `${(opp.p_fit * 100).toFixed(0)}%` : '--';
            const evCount = opp.evidence_count || 0;
            const freshness = opp.signals_freshness_category || 'recent';

            return `
                <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.08);">
                    <td style="font-weight:700; color:#94a3b8;">#${idx + 1}</td>
                    <td>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="font-size:1.15rem;">${opp.flag || '🌐'}</span>
                            <div>
                                <div style="font-weight:600; color:#f8fafc;">${opp.country_name || opp.country_code}</div>
                                <span class="badge" style="font-size:0.65rem; padding:2px 5px; background:rgba(100,116,139,0.2); color:#94a3b8;">${opp.tier || 'Tier 2'}</span>
                            </div>
                        </div>
                    </td>
                    <td>
                        <span style="font-weight:600; color:#38bdf8;">${opp.niche_name || opp.niche_slug}</span>
                    </td>
                    <td>
                        <div>
                            <div style="font-size:0.82rem; font-weight:500; color:#e2e8f0;">${opp.recommended_service_name || 'Workflow Automation'}</div>
                            <span style="font-size:0.68rem; font-family:var(--font-mono); color:var(--text-muted);">${opp.recommended_service_id || 'SERVICE_001'}</span>
                        </div>
                    </td>
                    <td style="font-family:var(--font-mono); font-weight:600; color:#34d399;">${price}</td>
                    <td>
                        <span class="badge" style="background:${scoreBg}; color:${scoreColor}; font-weight:700; font-size:0.82rem; padding:3px 8px; border:1px solid ${scoreColor}40;">
                            ${score.toFixed(1)}
                        </span>
                    </td>
                    <td>
                        <span style="font-size:0.75rem; color:#cbd5e1;">Fit: <strong>${pFit}</strong> • Win: <strong>${pWin}</strong></span>
                    </td>
                    <td style="font-family:var(--font-mono); font-weight:700; color:#38bdf8;">${ev}</td>
                    <td>
                        <div style="display:flex; align-items:center; gap:4px;">
                            <span class="badge" style="font-size:0.65rem; background:rgba(56,189,248,0.1); color:#38bdf8;">${evCount} signals</span>
                        </div>
                    </td>
                    <td style="text-align:right;">
                        <div style="display:inline-flex; gap:6px;">
                            <button type="button" class="btn btn-secondary" onclick="handleInspectMarketTrace('${opp.id}')" style="height:28px; padding:0 10px; font-size:0.72rem;">
                                🔍 Trace
                            </button>
                            <button type="button" class="btn btn-secondary" onclick="handleDeepResearchOpportunity('${opp.id}')" style="height:28px; padding:0 8px; font-size:0.72rem; color:#38bdf8;" title="Execute targeted empirical research">
                                ⚡
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:#f87171; padding:20px;">Error loading opportunities: ${err.message}</td></tr>`;
    }
}

async function handleTriggerMarketRefresh() {
    const btn = document.getElementById('btn-trigger-market-refresh');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span> Researching Markets...';
    }

    try {
        const res = await fetch('/api/market-intelligence/research/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limit_opportunities: 10, target_services: [] })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(`Market research failed: ${err.detail || 'Error'}`);
            return;
        }
        const data = await res.json();
        alert(`Market Research Cycle Completed!\nOpportunities Evaluated: ${data.opportunities_evaluated}\nEvidence Gathered: ${data.evidence_gathered}\nTop Opportunity: ${data.top_opportunity ? `${data.top_opportunity.country_code} × ${data.top_opportunity.niche_slug}` : 'N/A'}`);
        await loadMarketIntelligenceView();
    } catch (err) {
        alert(`Research cycle error: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>⚡</span> Run Full Research';
        }
    }
}

async function handleDiscoverMarketCandidates() {
    const panel = document.getElementById('mi-candidates-panel');
    const container = document.getElementById('mi-candidates-content');
    if (!panel || !container) return;

    panel.style.display = 'block';
    container.innerHTML = '<div style="color:var(--text-muted); padding:10px;">Scanning macro databases for candidate automation markets...</div>';

    try {
        const res = await fetch('/api/market-intelligence/discover/candidates', { method: 'POST' });
        if (!res.ok) {
            container.innerHTML = '<div style="color:#f87171;">Failed to discover candidate markets.</div>';
            return;
        }
        const data = await res.json();
        const countries = data.candidate_countries || [];

        if (countries.length === 0) {
            container.innerHTML = '<div style="color:var(--text-muted);">No new candidate countries discovered at this time.</div>';
            return;
        }

        container.innerHTML = countries.map(c => `
            <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 6px; padding: 12px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:1.3rem;">${c.flag || '🌐'}</span>
                        <div>
                            <div style="font-weight:700; color:#f8fafc;">${c.country_name} (${c.country_code})</div>
                            <span class="badge" style="font-size:0.65rem; background:rgba(168,85,247,0.2); color:#c084fc;">Tier ${c.tier}</span>
                        </div>
                    </div>
                    <span style="font-size:0.75rem; color:#34d399; font-weight:600;">GDP: $${c.gdp_per_capita_usd?.toLocaleString() || '--'}</span>
                </div>
                <div style="font-size:0.75rem; color:var(--text-muted); margin-top:8px; line-height:1.4;">
                    ${c.discovery_rationale || 'High automation propensity and favorable payment rail.'}
                </div>
                <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
                    ${(c.recommended_niches || []).map(n => `<span class="badge" style="font-size:0.65rem; background:rgba(56,189,248,0.1); color:#38bdf8;">${n}</span>`).join('')}
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<div style="color:#f87171;">Discovery error: ${err.message}</div>`;
    }
}

async function handleFeedToPhase10() {
    if (!confirm('Feed top ranked market opportunities into Phase 10 Global Prospect Pool for asynchronous discovery? (Outreach remains strictly locked to 1 active prospect)')) return;

    try {
        const res = await fetch('/api/market-intelligence/feed-phase10', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ top_n: 3, target_per_country: 2 })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(`Feed failed: ${err.detail || 'Error'}`);
            return;
        }
        const data = await res.json();
        alert(`Opportunities Fed to Phase 10!\nImported Prospects: ${data.prospects_imported}\nCountries Fed: ${data.countries_targeted.join(', ')}\nCommercial Lock: 1 Active Prospect (Unchanged)`);
    } catch (err) {
        alert(`Feed error: ${err.message}`);
    }
}

async function handleDeepResearchOpportunity(oppId) {
    try {
        const res = await fetch(`/api/market-intelligence/research/opportunity/${oppId}`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            alert(`Targeted research failed: ${err.detail || 'Error'}`);
            return;
        }
        const data = await res.json();
        alert(`Targeted Research Completed!\nSignals Extracted: ${data.signals_extracted}\nUpdated Score: ${data.updated_score?.toFixed(1)}\nExpected Value: $${Math.round(data.updated_ev || 0).toLocaleString()}`);
        await loadMarketOpportunities();
    } catch (err) {
        alert(`Research error: ${err.message}`);
    }
}

async function handleInspectMarketTrace(oppId) {
    const modal = document.getElementById('modal-market-trace');
    const body = document.getElementById('mi-modal-body');
    if (!modal || !body) return;

    modal.style.display = 'flex';
    body.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted);">Fetching decision trace, signals, and verified evidence...</div>';

    try {
        const [traceRes, evRes] = await Promise.all([
            fetch(`/api/market-intelligence/decision-trace/${oppId}`),
            fetch(`/api/market-intelligence/evidence/${oppId}`)
        ]);

        if (!traceRes.ok) {
            body.innerHTML = '<div style="color:#f87171; padding:20px;">Failed to load decision trace.</div>';
            return;
        }

        const trace = await traceRes.json();
        const evData = evRes.ok ? await evRes.json() : { evidence: [] };
        const evidence = evData.evidence || [];

        // Title and Score Badge
        const titleEl = document.getElementById('mi-modal-title');
        if (titleEl) titleEl.textContent = `${trace.country_code} × ${trace.niche_slug} • ${trace.service_id || 'Automation'}`;
        const scoreBadge = document.getElementById('mi-modal-score-badge');
        if (scoreBadge) {
            scoreBadge.textContent = `SCORE: ${trace.composite_score?.toFixed(1) || '--'}`;
        }

        body.innerHTML = `
            <!-- 5-Point Explainable Rationale Cards -->
            <div style="margin-bottom:20px;">
                <h4 style="color:#38bdf8; font-size:0.9rem; text-transform:uppercase; margin-bottom:10px; border-bottom:1px solid rgba(148,163,184,0.1); padding-bottom:4px;">
                    5-Point Explainable Rationale
                </h4>
                <div style="display:grid; grid-template-columns: 1fr; gap:10px;">
                    <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px 14px;">
                        <div style="font-weight:700; color:#38bdf8; font-size:0.75rem; text-transform:uppercase;">1. Why This Country?</div>
                        <div style="color:#e2e8f0; font-size:0.82rem; margin-top:3px; line-height:1.4;">${trace.why_country || 'High purchasing power and receptive digital infrastructure.'}</div>
                    </div>
                    <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px 14px;">
                        <div style="font-weight:700; color:#a855f7; font-size:0.75rem; text-transform:uppercase;">2. Why This Niche?</div>
                        <div style="color:#e2e8f0; font-size:0.82rem; margin-top:3px; line-height:1.4;">${trace.why_niche || 'Documented lead bleed and repetitive manual operational bottleneck.'}</div>
                    </div>
                    <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px 14px;">
                        <div style="font-weight:700; color:#34d399; font-size:0.75rem; text-transform:uppercase;">3. Why This Service?</div>
                        <div style="color:#e2e8f0; font-size:0.82rem; margin-top:3px; line-height:1.4;">${trace.why_service || 'Directly addresses observed workflow leak with demonstrable ROI.'}</div>
                    </div>
                    <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px 14px;">
                        <div style="font-weight:700; color:#fbbf24; font-size:0.75rem; text-transform:uppercase;">4. Why This Price? ($1,000+ Floor)</div>
                        <div style="color:#e2e8f0; font-size:0.82rem; margin-top:3px; line-height:1.4;">${trace.why_price || 'Unit economics and saved labor hours justify $1,000+ commercial value.'}</div>
                    </div>
                    <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px 14px;">
                        <div style="font-weight:700; color:#f87171; font-size:0.75rem; text-transform:uppercase;">5. Why Now? (Momentum & Window)</div>
                        <div style="color:#e2e8f0; font-size:0.82rem; margin-top:3px; line-height:1.4;">${trace.why_now || 'Regulatory changes, labor shortage, and rising CAC create immediate urgency.'}</div>
                    </div>
                </div>
            </div>

            <!-- Empirical Evidence Provenance -->
            <div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(148,163,184,0.1); padding-bottom:4px;">
                    <h4 style="color:#38bdf8; font-size:0.9rem; text-transform:uppercase; margin:0;">
                        Empirical Evidence & Provenance (${evidence.length} items)
                    </h4>
                </div>
                ${evidence.length === 0 ? `
                    <div style="color:var(--text-muted); font-size:0.8rem; padding:12px; background:rgba(15,23,42,0.4); border-radius:4px;">
                        No explicit web evidence items stored yet for this opportunity. Run targeted research to gather live web citations.
                    </div>
                ` : `
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        ${evidence.map(ev => `
                            <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:10px 12px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span class="badge" style="font-size:0.65rem; background:rgba(56,189,248,0.15); color:#38bdf8;">${ev.evidence_tier || 'Tier 2'}</span>
                                        <strong style="font-size:0.8rem; color:#f8fafc;">${ev.publisher || 'Public Source'}</strong>
                                    </div>
                                    <span style="font-size:0.7rem; color:var(--text-muted);">${ev.published_date ? new Date(ev.published_date).toLocaleDateString() : 'Recent'}</span>
                                </div>
                                <div style="font-size:0.78rem; color:#cbd5e1; line-height:1.4; margin-bottom:6px; font-style:italic;">
                                    "${ev.raw_excerpt || ev.claim || ''}"
                                </div>
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <a href="${ev.source_url}" target="_blank" rel="noopener noreferrer" style="font-size:0.7rem; color:#38bdf8; text-decoration:none; max-width:400px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                        🔗 ${ev.source_url}
                                    </a>
                                    <span style="font-size:0.68rem; color:#94a3b8;">Reliability: ${(ev.reliability_score * 100).toFixed(0)}%</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `}
            </div>
        `;
    } catch (err) {
        body.innerHTML = `<div style="color:#f87171; padding:20px;">Error rendering trace: ${err.message}</div>`;
    }
}

function closeMarketTraceModal() {
    const modal = document.getElementById('modal-market-trace');
    if (modal) modal.style.display = 'none';
}

/* =========================================================================
   PHASE 12: REAL PROSPECT ACQUISITION & EVIDENCE PIPELINE
   ========================================================================= */

async function loadRealProspectsView() {
    try {
        const statusRes = await fetch('/api/prospects/pipeline-status');
        if (statusRes.ok) {
            const statusData = await statusRes.json();
            const elTotal = document.getElementById('rp-stat-total');
            const elPassed = document.getElementById('rp-stat-passed');
            const elBlocked = document.getElementById('rp-stat-blocked');
            const elEv = document.getElementById('rp-stat-evidence');
            if (elTotal) elTotal.textContent = statusData.total_prospects || 0;
            if (elPassed) elPassed.textContent = statusData.evidence_gate_passed || 0;
            if (elBlocked) elBlocked.textContent = statusData.insufficient_evidence_blocked || 0;
            if (elEv) elEv.textContent = statusData.total_verified_evidence_items || 0;

            const slot = statusData.active_slot || {};
            const slotBadge = document.getElementById('rp-slot-status-badge');
            const slotContent = document.getElementById('rp-slot-content');
            if (slotBadge) {
                slotBadge.textContent = slot.is_occupied ? (slot.status || 'ACTIVE') : 'IDLE';
                slotBadge.style.background = slot.is_occupied ? 'rgba(34,197,94,0.2)' : 'rgba(168,85,247,0.15)';
                slotBadge.style.color = slot.is_occupied ? '#4ade80' : '#c084fc';
            }
            if (slotContent) {
                if (slot.is_occupied && slot.business_name) {
                    slotContent.innerHTML = `
                        <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(34,197,94,0.3); border-radius:6px; padding:12px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                <strong style="font-size:0.95rem; color:#f8fafc;">${slot.business_name}</strong>
                                <span class="badge" style="background:#16a34a; color:#fff; font-size:0.7rem;">SLOT 1 ACTIVE</span>
                            </div>
                            <div style="font-size:0.78rem; color:#94a3b8; margin-bottom:8px;">
                                <span>🌐 ${slot.domain || ''}</span> • <span>📍 ${slot.country || ''}</span>
                            </div>
                            <div style="font-size:0.75rem; color:#cbd5e1; background:rgba(0,0,0,0.3); padding:8px; border-radius:4px; margin-bottom:8px;">
                                <strong>Next Action:</strong> ${slot.next_action || 'Proceeding through sequential outreach'}
                            </div>
                            <button type="button" class="btn btn-secondary" onclick="viewProspectEvidence(${slot.business_id})" style="font-size:0.75rem; padding:4px 10px;">
                                🔍 View Provenance Evidence
                            </button>
                        </div>
                    `;
                } else {
                    slotContent.innerHTML = `
                        <div style="text-align:center; padding:20px; color:var(--text-muted); font-size:0.82rem;">
                            <div style="font-size:1.5rem; margin-bottom:8px;">🔓</div>
                            Outreach slot 1 is currently <strong>IDLE</strong>.<br/>
                            Top-ranked verified prospect will be locked upon campaign activation.
                        </div>
                    `;
                }
            }
        }

        const leadsRes = await fetch('/api/leads?limit=50');
        if (leadsRes.ok) {
            const leads = await leadsRes.json();
            renderRealProspectsTable(leads);
        }
    } catch (err) {
        console.error('[loadRealProspectsView] Failed:', err);
    }
}

function renderRealProspectsTable(prospects) {
    const tbody = document.getElementById('rp-prospects-tbody');
    if (!tbody) return;
    if (!prospects || prospects.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:20px; color:var(--text-muted);">No prospects in database. Click "Run Multi-City Acquisition" above.</td></tr>`;
        return;
    }

    tbody.innerHTML = prospects.map(p => {
        const isVerified = p.verification_status === 'VERIFIED';
        const evCount = p.evidence_count !== undefined ? p.evidence_count : (isVerified ? 2 : 0);
        const score = p.prospect_score ? p.prospect_score.toFixed(1) : (p.lead_score?.overall_score || '--');
        const badgeColor = isVerified ? '#4ade80' : '#f87171';
        const badgeBg = isVerified ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)';
        const badgeText = isVerified ? 'VERIFIED' : (p.verification_status || 'INSUFFICIENT');

        return `
            <tr>
                <td style="font-weight:600; color:#f8fafc;">${p.name || p.business_name}</td>
                <td>
                    <div style="font-size:0.8rem; color:#38bdf8;">${p.domain}</div>
                    <div style="font-size:0.72rem; color:#94a3b8;">${p.city ? p.city + ', ' : ''}${p.country}</div>
                </td>
                <td><span class="badge" style="font-size:0.7rem;">${p.niche || 'Local Services'}</span></td>
                <td style="text-align:center; font-weight:700; color:${evCount >= 2 ? '#38bdf8' : '#f87171'};">
                    ${evCount} sources
                </td>
                <td>
                    <span class="badge" style="background:${badgeBg}; color:${badgeColor}; border:1px solid ${badgeColor}; font-size:0.72rem;">
                        ${badgeText}
                    </span>
                </td>
                <td style="font-weight:700; color:#f8fafc;">${score}</td>
                <td style="font-size:0.8rem; color:#34d399; font-weight:600;">$1,000+</td>
                <td>
                    <div style="display:flex; gap:6px;">
                        <button type="button" class="btn btn-outline" onclick="viewProspectEvidence(${p.id})" style="padding:3px 8px; font-size:0.72rem;">
                            Evidence
                        </button>
                        <button type="button" class="btn btn-outline" onclick="handleEvaluateEvidenceGate(${p.id})" style="padding:3px 8px; font-size:0.72rem; color:#c084fc; border-color:rgba(168,85,247,0.4);">
                            Re-check
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function handleTriggerProspectDiscovery() {
    const btn = document.getElementById('btn-trigger-rp-discovery');
    const country = document.getElementById('rp-input-country')?.value || 'US';
    const niche = document.getElementById('rp-input-niche')?.value || 'roofing-contractors';
    const count = parseInt(document.getElementById('rp-input-count')?.value || '5', 10);
    const citiesRaw = document.getElementById('rp-input-cities')?.value || '';
    const cities = citiesRaw ? citiesRaw.split(',').map(c => c.trim()).filter(Boolean) : null;

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span> Discovering & Harvesting Evidence...';
    }

    try {
        const res = await fetch('/api/prospects/discover', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                country_code: country,
                niche_slug: niche,
                target_count: count,
                cities: cities
            })
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Acquisition Completed!\\nDiscovered: ${data.prospects_discovered}\\nGate Passed: ${data.prospects_verified}\\nInsufficient: ${data.prospects_rejected}\\nEvidence items extracted: ${data.evidence_items_extracted}`);
            await loadRealProspectsView();
        } else {
            alert(`Discovery failed: ${data.detail || 'Unknown error'}`);
        }
    } catch (err) {
        alert(`Error executing discovery: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>🚀</span> Run Multi-City Acquisition & Evidence Extraction';
        }
    }
}

async function viewProspectEvidence(businessId) {
    const modal = document.getElementById('modal-prospect-evidence');
    const title = document.getElementById('modal-evidence-title');
    const body = document.getElementById('modal-evidence-body');
    if (!modal || !body) return;

    modal.style.display = 'flex';
    body.innerHTML = '<div style="color:var(--text-muted); padding:20px; text-align:center;">Loading evidence items...</div>';

    try {
        const res = await fetch(`/api/prospects/evidence/${businessId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const biz = data.business;
        const items = data.evidence_items || [];
        const gate = data.gate_evaluation || {};

        if (title) title.textContent = `${biz.name} — Evidence Provenance (${items.length} items)`;

        const gateColor = gate.is_passed ? '#4ade80' : '#f87171';
        const gateBg = gate.is_passed ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)';

        body.innerHTML = `
            <div style="background:${gateBg}; border:1px solid ${gateColor}; border-radius:6px; padding:12px; margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <strong style="color:${gateColor}; font-size:0.9rem;">
                        ${gate.is_passed ? '✓ PASSED HARD EVIDENCE GATE' : '✗ INSUFFICIENT EVIDENCE (BLOCKED)'}
                    </strong>
                    <span style="font-size:0.75rem; color:#cbd5e1;">Score: ${gate.effective_evidence_score?.toFixed(2) || '0.00'} / 0.60 required</span>
                </div>
                <div style="font-size:0.78rem; color:#cbd5e1;">${gate.reason || ''}</div>
                <div style="font-size:0.72rem; color:#94a3b8; margin-top:4px;">
                    Distinct Sources: ${gate.distinct_sources_count || 0} (Min 2 required) • Can Outreach: ${gate.can_outreach ? 'YES' : 'NO'}
                </div>
            </div>

            <h4 style="font-size:0.85rem; color:#94a3b8; text-transform:uppercase; margin-bottom:10px;">Empirical Citations & Proof</h4>
            ${items.length === 0 ? `
                <div style="color:#f87171; font-size:0.8rem; padding:12px; background:rgba(239,68,68,0.1); border-radius:4px;">
                    Zero empirical evidence items recorded. Prospect cannot become contactable.
                </div>
            ` : `
                <div style="display:flex; flex-direction:column; gap:10px;">
                    ${items.map(ev => {
                        const isVer = ev.verification_status === 'VERIFIED';
                        const isUnr = ev.verification_status === 'UNREACHABLE';
                        const stBadgeBg = isVer ? 'rgba(34,197,94,0.18)' : (isUnr ? 'rgba(239,68,68,0.18)' : 'rgba(234,179,8,0.18)');
                        const stBadgeColor = isVer ? '#4ade80' : (isUnr ? '#f87171' : '#facc15');
                        return `
                        <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.08); border-radius:6px; padding:12px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:6px;">
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <span class="badge" style="font-size:0.65rem; background:rgba(56,189,248,0.2); color:#38bdf8;">
                                        Tier ${ev.source_tier} (${escapeHtml(ev.source_type)})
                                    </span>
                                    <span class="badge" style="font-size:0.65rem; background:${stBadgeBg}; color:${stBadgeColor};">
                                        ${escapeHtml(ev.verification_status || (ev.is_verified ? 'VERIFIED' : 'UNVERIFIED'))}
                                    </span>
                                    <strong style="font-size:0.82rem; color:#f8fafc;">${escapeHtml(ev.publisher || ev.source_domain)}</strong>
                                </div>
                                <div style="display:flex; align-items:center; gap:8px;">
                                    ${ev.http_status ? `<span style="font-size:0.68rem; font-family:var(--font-mono); color:#94a3b8;">HTTP ${ev.http_status}</span>` : ''}
                                    <span style="font-size:0.7rem; color:#94a3b8;">${ev.retrieved_at ? new Date(ev.retrieved_at).toLocaleString() : ''}</span>
                                </div>
                            </div>
                            <div style="font-size:0.8rem; color:#cbd5e1; margin-bottom:6px; font-style:italic; background:rgba(0,0,0,0.2); padding:6px 8px; border-radius:4px;">
                                "${escapeHtml(ev.raw_excerpt || ev.claim)}"
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.72rem; flex-wrap:wrap; gap:6px;">
                                <a href="${escapeHtml(ev.source_url)}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8; text-decoration:none; max-width:380px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                                    🔗 ${escapeHtml(ev.source_url)}
                                </a>
                                <div style="display:flex; gap:8px; color:#94a3b8;">
                                    <span>Identity Match: <strong style="color:${ev.business_identity_match ? '#4ade80' : '#f87171'}">${ev.business_identity_match ? '✓ YES' : '✗ NO'}</strong></span>
                                    ${ev.content_hash ? `<span>Hash: <code style="font-size:0.68rem; color:#38bdf8;">${escapeHtml(ev.content_hash.slice(0, 8))}...</code></span>` : ''}
                                    <span>Confidence: ${(ev.confidence_score * 100).toFixed(0)}%</span>
                                </div>
                            </div>
                            ${ev.verification_reason ? `
                                <div style="margin-top:6px; font-size:0.7rem; color:#94a3b8; border-top:1px solid rgba(255,255,255,0.05); padding-top:4px;">
                                    <em>Verification Note:</em> ${escapeHtml(ev.verification_reason)}
                                </div>
                            ` : ''}
                        </div>
                    `}).join('')}
                </div>
            `}
        `;
    } catch (err) {
        body.innerHTML = `<div style="color:#f87171; padding:20px;">Failed to load evidence: ${err.message}</div>`;
    }
}

async function handleEvaluateEvidenceGate(businessId) {
    try {
        const res = await fetch(`/api/prospects/evidence-gate/evaluate/${businessId}`, {method: 'POST'});
        const data = await res.json();
        alert(`Re-evaluation complete!\\nStatus: ${data.verification_status}\\nScore: ${data.effective_evidence_score}\\nReason: ${data.gate_evaluation?.reason}`);
        await loadRealProspectsView();
    } catch (err) {
        alert(`Failed to evaluate gate: ${err.message}`);
    }
}

function closeProspectEvidenceModal() {
    const modal = document.getElementById('modal-prospect-evidence');
    if (modal) modal.style.display = 'none';
}



// ==========================================
// PHASE 14: DECISION ANALYTICS DASHBOARD JS
// ==========================================

let currentAnalyticsTimeFilter = 'all';

async function changeAnalyticsTimeFilter(filter) {
    currentAnalyticsTimeFilter = filter;
    document.querySelectorAll('.btn-time-filter').forEach(b => {
        if (b.getAttribute('data-filter') === filter) {
            b.classList.add('active');
            b.style.background = 'rgba(56,189,248,0.2)';
            b.style.border = '1px solid rgba(56,189,248,0.5)';
            b.style.color = '#38bdf8';
            b.style.fontWeight = '700';
        } else {
            b.classList.remove('active');
            b.style.background = 'transparent';
            b.style.border = 'none';
            b.style.color = '#94a3b8';
            b.style.fontWeight = '600';
        }
    });
    await loadDecisionAnalytics(filter);
}

async function loadDecisionAnalytics(timeFilter) {
    const tf = timeFilter || currentAnalyticsTimeFilter || 'all';

    try {
        const [
            overviewRes,
            funnelRes,
            radarRes,
            qualityRes,
            servicesRes,
            salesRes,
            revenueRes,
            estimatedRes,
            modelOutputsRes,
            dataQualityRes
        ] = await Promise.all([
            fetch(`/api/analytics/overview?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/funnel?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch('/api/analytics/market-radar').then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/quality?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/services?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/sales?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/revenue?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/estimated-value?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch(`/api/analytics/model-outputs?time_filter=${tf}`).then(r => r.json()).catch(() => null),
            fetch('/api/analytics/data-quality').then(r => r.json()).catch(() => null)
        ]);

        // 1. Render Executive Overview
        if (overviewRes) {
            const rev = overviewRes.actual_revenue_collected?.value || 0;
            const revElem = document.getElementById('da-val-revenue');
            if (revElem) revElem.innerText = `$${Number(rev).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 2})}`;

            const activeElem = document.getElementById('da-val-active-prospect');
            const activeDomainElem = document.getElementById('da-val-active-domain');
            if (activeElem && activeDomainElem) {
                if (overviewRes.active_prospect) {
                    activeElem.innerText = `${overviewRes.active_prospect.name} (${overviewRes.active_prospect.domain})`;
                    activeDomainElem.innerText = `Stage: ${overviewRes.active_prospect.pipeline_stage} • ${overviewRes.active_prospect.country}`;
                } else {
                    activeElem.innerText = 'None (Standby)';
                    activeDomainElem.innerText = 'Slot 1 Single Concurrency';
                }
            }

            const verElem = document.getElementById('da-val-verified');
            if (verElem) verElem.innerText = overviewRes.verified_prospects?.value || 0;

            const audElem = document.getElementById('da-val-audited');
            if (audElem) audElem.innerText = overviewRes.audited_prospects?.value || 0;

            const qualElem = document.getElementById('da-val-qualified');
            if (qualElem) qualElem.innerText = overviewRes.qualified_prospects?.value || 0;

            const contElem = document.getElementById('da-val-contactable');
            if (contElem) contElem.innerText = overviewRes.contactable_prospects?.value || 0;

            const wonElem = document.getElementById('da-val-won-deals');
            if (wonElem) wonElem.innerText = overviewRes.won_deals?.value || 0;

            const pipeElem = document.getElementById('da-val-pipeline');
            if (pipeElem) {
                const pval = overviewRes.pipeline_value?.value || 0;
                pipeElem.innerText = `$${Number(pval).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 2})}`;
            }

            const avgDealElem = document.getElementById('da-val-avg-deal-size');
            if (avgDealElem) {
                avgDealElem.innerText = overviewRes.average_deal_size?.display || 'No data yet';
            }
        }

        // 2. Render Acquisition Funnel
        const funnelContainer = document.getElementById('da-funnel-container');
        if (funnelContainer && funnelRes && funnelRes.steps) {
            funnelContainer.innerHTML = funnelRes.steps.map((step, idx) => {
                const isFirst = idx === 0;
                const isLast = idx === funnelRes.steps.length - 1;
                const convPrevText = isFirst ? '100% Top' : (step.conversion_from_previous !== null ? `${step.conversion_from_previous}% conv` : 'Insufficient data');
                const dropText = isFirst ? 'Source input' : (step.dropoff_count > 0 ? `-${step.dropoff_count} (${step.dropoff_rate}%)` : '0 drop-off');

                return `
                    <div style="background:#0f172a; border:1px solid rgba(148,163,184,0.18); border-radius:6px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; min-height:130px;">
                        <div>
                            <div style="font-size:0.72rem; text-transform:uppercase; color:#94a3b8; font-weight:700; margin-bottom:4px;">${step.stage}</div>
                            <div style="font-size:1.5rem; font-weight:800; color:#38bdf8; font-family:'JetBrains Mono', monospace;">${step.count.toLocaleString()}</div>
                        </div>
                        <div style="margin-top:10px; border-top:1px solid rgba(148,163,184,0.1); pt:6px;">
                            <div style="font-size:0.72rem; color:${step.conversion_from_previous > 0 ? '#34d399' : '#64748b'}; font-weight:600;">${convPrevText}</div>
                            <div style="font-size:0.68rem; color:${step.dropoff_count > 0 ? '#f87171' : '#64748b'}; margin-top:2px;">${dropText}</div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // 3. Render Market Radar (Country & Niche)
        const radarContainer = document.getElementById('da-market-radar-content');
        if (radarContainer && radarRes) {
            const countries = radarRes.by_country || [];
            const niches = radarRes.by_niche || [];

            let html = `
                <div style="margin-bottom:16px;">
                    <div style="font-size:0.8rem; font-weight:700; color:#94a3b8; margin-bottom:8px; text-transform:uppercase;">Top Countries (Verified Density)</div>
                    <table style="width:100%; border-collapse:collapse; font-size:0.8rem;">
                        <thead>
                            <tr style="border-bottom:1px solid rgba(148,163,184,0.15); color:#64748b; text-align:left;">
                                <th style="padding:6px;">Country</th>
                                <th style="padding:6px; text-align:right;">Discovered</th>
                                <th style="padding:6px; text-align:right;">Verified [ACTUAL]</th>
                                <th style="padding:6px; text-align:right;">Avg Score [MODEL]</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${countries.length === 0 ? '<tr><td colspan="4" style="padding:10px; text-align:center; color:#64748b;">No data yet</td></tr>' : countries.slice(0, 5).map(c => `
                                <tr style="border-bottom:1px solid rgba(148,163,184,0.06);">
                                    <td style="padding:6px; font-weight:600; color:#f1f5f9;">${c.country}</td>
                                    <td style="padding:6px; text-align:right; font-family:'JetBrains Mono';">${c.total_businesses}</td>
                                    <td style="padding:6px; text-align:right; font-family:'JetBrains Mono'; color:#34d399; font-weight:700;">${c.verified_prospects}</td>
                                    <td style="padding:6px; text-align:right; font-family:'JetBrains Mono'; color:#38bdf8;">${c.avg_prospect_score !== null ? c.avg_prospect_score : 'N/A'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>

                <div>
                    <div style="font-size:0.8rem; font-weight:700; color:#94a3b8; margin-bottom:8px; text-transform:uppercase;">Top Niches (Evidence Quality)</div>
                    <table style="width:100%; border-collapse:collapse; font-size:0.8rem;">
                        <thead>
                            <tr style="border-bottom:1px solid rgba(148,163,184,0.15); color:#64748b; text-align:left;">
                                <th style="padding:6px;">Niche</th>
                                <th style="padding:6px; text-align:right;">Discovered</th>
                                <th style="padding:6px; text-align:right;">Verified [ACTUAL]</th>
                                <th style="padding:6px; text-align:right;">Avg Evidence [ACTUAL]</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${niches.length === 0 ? '<tr><td colspan="4" style="padding:10px; text-align:center; color:#64748b;">No data yet</td></tr>' : niches.slice(0, 5).map(n => `
                                <tr style="border-bottom:1px solid rgba(148,163,184,0.06);">
                                    <td style="padding:6px; font-weight:600; color:#f1f5f9;">${n.niche}</td>
                                    <td style="padding:6px; text-align:right; font-family:'JetBrains Mono';">${n.total_businesses}</td>
                                    <td style="padding:6px; text-align:right; font-family:'JetBrains Mono'; color:#34d399; font-weight:700;">${n.verified_prospects}</td>
                                    <td style="padding:6px; text-align:right; font-family:'JetBrains Mono'; color:#fbbf24;">${n.avg_evidence_score !== null ? n.avg_evidence_score : 'N/A'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
            radarContainer.innerHTML = html;
        }

        // 4. Render Sales Analytics & Conversion Rates
        const salesContainer = document.getElementById('da-sales-analytics-content');
        if (salesContainer && salesRes) {
            const m = salesRes.metrics || {};
            const c = salesRes.counts || {};

            salesContainer.innerHTML = `
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px;">
                    <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                        <div style="font-size:0.72rem; color:#94a3b8; text-transform:uppercase; font-weight:700;">Reply Rate</div>
                        <div style="font-size:1.3rem; font-weight:800; color:${m.reply_rate_pct?.value !== null ? '#34d399' : '#94a3b8'}; margin:4px 0; font-family:'JetBrains Mono';">
                            ${m.reply_rate_pct?.display || 'Insufficient data'}
                        </div>
                        <div style="font-size:0.68rem; color:#64748b;">${c.replied || 0} replies / ${c.contacted || 0} contacted</div>
                    </div>

                    <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                        <div style="font-size:0.72rem; color:#94a3b8; text-transform:uppercase; font-weight:700;">Meeting Booking Rate</div>
                        <div style="font-size:1.3rem; font-weight:800; color:${m.meeting_rate_pct?.value !== null ? '#34d399' : '#94a3b8'}; margin:4px 0; font-family:'JetBrains Mono';">
                            ${m.meeting_rate_pct?.display || 'Insufficient data'}
                        </div>
                        <div style="font-size:0.68rem; color:#64748b;">${c.meetings || 0} booked / ${c.replied || 0} replies</div>
                    </div>

                    <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                        <div style="font-size:0.72rem; color:#94a3b8; text-transform:uppercase; font-weight:700;">Proposal Win Rate</div>
                        <div style="font-size:1.3rem; font-weight:800; color:${m.proposal_win_rate_pct?.value !== null ? '#34d399' : '#94a3b8'}; margin:4px 0; font-family:'JetBrains Mono';">
                            ${m.proposal_win_rate_pct?.display || 'Insufficient data'}
                        </div>
                        <div style="font-size:0.68rem; color:#64748b;">${c.won || 0} won / ${c.proposals || 0} proposals</div>
                    </div>

                    <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                        <div style="font-size:0.72rem; color:#94a3b8; text-transform:uppercase; font-weight:700;">Average Deal Value</div>
                        <div style="font-size:1.3rem; font-weight:800; color:${m.average_deal_value_usd?.value !== null ? '#fbbf24' : '#94a3b8'}; margin:4px 0; font-family:'JetBrains Mono';">
                            ${m.average_deal_value_usd?.display || 'Insufficient data'}
                        </div>
                        <div style="font-size:0.68rem; color:#64748b;">Collected revenue / won count</div>
                    </div>
                </div>

                ${(salesRes.insufficient_data_reasons && salesRes.insufficient_data_reasons.length > 0) ? `
                    <div style="background:rgba(148,163,184,0.06); border:1px solid rgba(148,163,184,0.12); padding:8px 12px; border-radius:6px; font-size:0.72rem; color:#94a3b8;">
                        <span style="font-weight:700; color:#f1f5f9;">Denominator Warnings:</span> ${salesRes.insufficient_data_reasons.join('; ')}
                    </div>
                ` : ''}
            `;
        }

        // 5. Render Service Demand Matrix (10 Catalog Services)
        const servicesContainer = document.getElementById('da-service-demand-content');
        if (servicesContainer && servicesRes && servicesRes.services) {
            servicesContainer.innerHTML = `
                <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
                    <thead>
                        <tr style="border-bottom:1px solid rgba(148,163,184,0.2); color:#64748b; text-align:left;">
                            <th style="padding:8px;">Catalog ID</th>
                            <th style="padding:8px;">Catalog Service Name</th>
                            <th style="padding:8px; text-align:right;">Prospect Matches</th>
                            <th style="padding:8px; text-align:right;">Avg Fit [MODEL]</th>
                            <th style="padding:8px; text-align:right;">Avg P(Win) [MODEL]</th>
                            <th style="padding:8px; text-align:right;">Pipeline Value [PIPELINE]</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${servicesRes.services.map(s => `
                            <tr style="border-bottom:1px solid rgba(148,163,184,0.08);">
                                <td style="padding:8px; font-family:'JetBrains Mono'; color:#38bdf8; font-weight:700;">${s.service_id}</td>
                                <td style="padding:8px; color:#f1f5f9; font-weight:600;">${s.service_name}</td>
                                <td style="padding:8px; text-align:right; font-family:'JetBrains Mono'; font-weight:700; color:${s.match_count > 0 ? '#34d399' : '#64748b'};">${s.match_count}</td>
                                <td style="padding:8px; text-align:right; font-family:'JetBrains Mono'; color:#38bdf8;">${s.avg_fit_score !== null ? s.avg_fit_score : '—'}</td>
                                <td style="padding:8px; text-align:right; font-family:'JetBrains Mono'; color:#c084fc;">${s.avg_p_win !== null ? s.avg_p_win : '—'}</td>
                                <td style="padding:8px; text-align:right; font-family:'JetBrains Mono'; color:#fbbf24; font-weight:700;">$${Number(s.pipeline_value || 0).toLocaleString()}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        // 6. Render Prospect Quality Distributions
        const qualityContainer = document.getElementById('da-quality-distributions-content');
        if (qualityContainer && qualityRes) {
            const renderBucketCard = (title, badge, badgeColor, dist, avgVal, unit) => {
                const keys = Object.keys(dist || {});
                return `
                    <div style="background:#0f172a; padding:16px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                            <span style="font-size:0.8rem; font-weight:700; color:#f1f5f9;">${title}</span>
                            <span class="badge" style="background:rgba(${badgeColor},0.15); color:rgb(${badgeColor}); border:1px solid rgba(${badgeColor},0.4); font-size:0.62rem; font-weight:700; padding:1px 5px; border-radius:3px;">${badge}</span>
                        </div>
                        <div style="font-size:0.75rem; color:#94a3b8; margin-bottom:10px;">Average: <strong style="color:#f8fafc;">${avgVal !== null ? avgVal + (unit || '') : 'No data yet'}</strong></div>
                        <div style="display:flex; flex-direction:column; gap:6px;">
                            ${keys.map(k => {
                                const count = dist[k] || 0;
                                return `
                                    <div style="display:flex; align-items:center; justify-content:space-between; font-size:0.75rem;">
                                        <span style="color:#64748b; font-family:'JetBrains Mono'; width:60px;">${k}</span>
                                        <div style="flex:1; margin:0 8px; background:rgba(148,163,184,0.1); height:8px; border-radius:4px; overflow:hidden;">
                                            <div style="background:rgb(${badgeColor}); height:100%; width:${Math.min(100, count * 15)}%;"></div>
                                        </div>
                                        <span style="color:#f1f5f9; font-family:'JetBrains Mono'; font-weight:700; width:25px; text-align:right;">${count}</span>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
            };

            qualityContainer.innerHTML = `
                ${renderBucketCard('Prospect Scores', 'MODEL HEURISTIC', '56,189,248', qualityRes.prospect_scores?.distribution, qualityRes.prospect_scores?.avg)}
                ${renderBucketCard('Evidence Scores', 'ACTUAL EVIDENCE', '16,185,129', qualityRes.evidence_scores?.distribution, qualityRes.evidence_scores?.avg)}
                ${renderBucketCard('Website Health Scores', 'MEASURED AUDIT', '245,158,11', qualityRes.website_health_scores?.distribution, qualityRes.website_health_scores?.avg, '/100')}
            `;
        }

        // 7. Render Revenue Analytics vs Pipeline
        const revContainer = document.getElementById('da-revenue-analytics-content');
        if (revContainer && revenueRes) {
            const byPeriod = revenueRes.revenue_by_period || [];
            const byCountry = revenueRes.revenue_by_country || [];
            const byService = revenueRes.revenue_by_service || [];

            revContainer.innerHTML = `
                <div style="background:#0f172a; padding:14px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.75rem; text-transform:uppercase; font-weight:700; color:#94a3b8; margin-bottom:8px;">Revenue Over Time</div>
                    ${byPeriod.length === 0 ? '<div style="font-size:0.78rem; color:#64748b;">No paid records in period</div>' : `
                        <div style="display:flex; flex-direction:column; gap:4px; font-size:0.78rem;">
                            ${byPeriod.map(p => `
                                <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(148,163,184,0.06); padding:4px 0;">
                                    <span style="color:#f1f5f9; font-family:'JetBrains Mono';">${p.period}</span>
                                    <span style="color:#fbbf24; font-family:'JetBrains Mono'; font-weight:700;">$${p.amount.toLocaleString()}</span>
                                </div>
                            `).join('')}
                        </div>
                    `}
                </div>

                <div style="background:#0f172a; padding:14px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.75rem; text-transform:uppercase; font-weight:700; color:#94a3b8; margin-bottom:8px;">Revenue By Country</div>
                    ${byCountry.length === 0 ? '<div style="font-size:0.78rem; color:#64748b;">No country revenue yet</div>' : `
                        <div style="display:flex; flex-direction:column; gap:4px; font-size:0.78rem;">
                            ${byCountry.map(c => `
                                <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(148,163,184,0.06); padding:4px 0;">
                                    <span style="color:#f1f5f9;">${c.country}</span>
                                    <span style="color:#fbbf24; font-family:'JetBrains Mono'; font-weight:700;">$${c.amount.toLocaleString()}</span>
                                </div>
                            `).join('')}
                        </div>
                    `}
                </div>

                <div style="background:#0f172a; padding:14px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.75rem; text-transform:uppercase; font-weight:700; color:#94a3b8; margin-bottom:8px;">Revenue By Service</div>
                    ${byService.length === 0 ? '<div style="font-size:0.78rem; color:#64748b;">No service revenue yet</div>' : `
                        <div style="display:flex; flex-direction:column; gap:4px; font-size:0.78rem;">
                            ${byService.map(s => `
                                <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(148,163,184,0.06); padding:4px 0;">
                                    <span style="color:#f1f5f9;">${s.service}</span>
                                    <span style="color:#fbbf24; font-family:'JetBrains Mono'; font-weight:700;">$${s.amount.toLocaleString()}</span>
                                </div>
                            `).join('')}
                        </div>
                    `}
                </div>
            `;
        }

        // 8. Render Estimated Value with Mandatory Disclosure
        const estContainer = document.getElementById('da-estimated-value-content');
        if (estContainer && estimatedRes) {
            estContainer.innerHTML = `
                <div style="display:flex; flex-direction:column; gap:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:12px; border-radius:6px;">
                        <span style="font-size:0.8rem; color:#94a3b8;">Annual Recoverable Customer Value:</span>
                        <span style="font-size:1.2rem; font-weight:800; color:#c084fc; font-family:'JetBrains Mono';">$${Number(estimatedRes.total_estimated_annual_recoverable_value || 0).toLocaleString()}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:12px; border-radius:6px;">
                        <span style="font-size:0.8rem; color:#94a3b8;">Monthly Recoverable Opportunity:</span>
                        <span style="font-size:1.2rem; font-weight:800; color:#c084fc; font-family:'JetBrains Mono';">$${Number(estimatedRes.total_estimated_monthly_recoverable_value || 0).toLocaleString()}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:12px; border-radius:6px;">
                        <span style="font-size:0.8rem; color:#94a3b8;">Prospects With Documented Value:</span>
                        <span style="font-size:1.1rem; font-weight:700; color:#f1f5f9; font-family:'JetBrains Mono';">${estimatedRes.prospects_with_estimate_count || 0}</span>
                    </div>
                    <div style="background:rgba(147,51,234,0.08); border:1px solid rgba(147,51,234,0.3); padding:10px 14px; border-radius:6px; font-size:0.75rem; color:#c084fc; line-height:1.4;">
                        <strong>Mandatory Disclosure:</strong> ${estimatedRes.mandatory_disclosure}
                    </div>
                </div>
            `;
        }

        // 9. Render Internal Model Outputs
        const modelContainer = document.getElementById('da-model-outputs-content');
        if (modelContainer && modelOutputsRes) {
            modelContainer.innerHTML = `
                <div style="display:flex; flex-direction:column; gap:12px;">
                    <div style="background:#0f172a; padding:12px; border-radius:6px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                            <span style="color:#94a3b8; font-weight:600;">Fit Score (Service Match Index):</span>
                            <span style="color:#38bdf8; font-family:'JetBrains Mono'; font-weight:700;">Avg: ${modelOutputsRes.fit_score?.avg !== null ? modelOutputsRes.fit_score.avg : '—'}</span>
                        </div>
                        <div style="font-size:0.7rem; color:#64748b;">${modelOutputsRes.fit_score?.description || ''}</div>
                    </div>

                    <div style="background:#0f172a; padding:12px; border-radius:6px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                            <span style="color:#94a3b8; font-weight:600;">P(Win) (Closure Probability):</span>
                            <span style="color:#c084fc; font-family:'JetBrains Mono'; font-weight:700;">Avg: ${modelOutputsRes.p_win?.avg !== null ? modelOutputsRes.p_win.avg : '—'}</span>
                        </div>
                        <div style="font-size:0.7rem; color:#64748b;">${modelOutputsRes.p_win?.description || ''}</div>
                    </div>

                    <div style="background:#0f172a; padding:12px; border-radius:6px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:4px;">
                            <span style="color:#94a3b8; font-weight:600;">Selection Score (Lock Priority):</span>
                            <span style="color:#fbbf24; font-family:'JetBrains Mono'; font-weight:700;">Avg: ${modelOutputsRes.selection_score?.avg !== null ? modelOutputsRes.selection_score.avg : '—'}</span>
                        </div>
                        <div style="font-size:0.7rem; color:#64748b;">${modelOutputsRes.selection_score?.description || ''}</div>
                    </div>

                    <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3); padding:10px 14px; border-radius:6px; font-size:0.75rem; color:#f87171; line-height:1.4;">
                        <strong>Policy Restriction:</strong> ${modelOutputsRes.disclaimer}
                    </div>
                </div>
            `;
        }

        // 10. Render Data Quality Telemetry
        const qualityGrid = document.getElementById('da-data-quality-grid');
        const qualityBadge = document.getElementById('da-data-quality-status-badge');
        if (qualityGrid && dataQualityRes) {
            if (qualityBadge) {
                const status = dataQualityRes.overall_quality_status || 'HEALTHY';
                qualityBadge.innerText = status;
                if (status === 'HEALTHY') {
                    qualityBadge.className = 'badge badge-emerald';
                } else if (status === 'WARNING') {
                    qualityBadge.className = 'badge badge-gold';
                } else {
                    qualityBadge.className = 'badge badge-cyan';
                }
            }

            qualityGrid.innerHTML = `
                <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.72rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Evidence Coverage</div>
                    <div style="font-size:1.3rem; font-weight:800; color:#34d399; font-family:'JetBrains Mono'; margin:4px 0;">
                        ${dataQualityRes.evidence_coverage_pct?.display || 'Insufficient data'}
                    </div>
                    <div style="font-size:0.68rem; color:#64748b;">${dataQualityRes.verified_businesses || 0} / ${dataQualityRes.total_businesses || 0} verified</div>
                </div>

                <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.72rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Stale Evidence</div>
                    <div style="font-size:1.3rem; font-weight:800; color:${(dataQualityRes.stale_evidence_count?.value || 0) > 0 ? '#f59e0b' : '#34d399'}; font-family:'JetBrains Mono'; margin:4px 0;">
                        ${dataQualityRes.stale_evidence_count?.value || 0}
                    </div>
                    <div style="font-size:0.68rem; color:#64748b;">Retrieved &gt; 30 days ago</div>
                </div>

                <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.72rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Missing Contacts</div>
                    <div style="font-size:1.3rem; font-weight:800; color:${(dataQualityRes.missing_contact_count?.value || 0) > 0 ? '#f59e0b' : '#34d399'}; font-family:'JetBrains Mono'; margin:4px 0;">
                        ${dataQualityRes.missing_contact_count?.value || 0}
                    </div>
                    <div style="font-size:0.68rem; color:#64748b;">Lacks public email &amp; phone</div>
                </div>

                <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.72rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Gate Blocked</div>
                    <div style="font-size:1.3rem; font-weight:800; color:#f87171; font-family:'JetBrains Mono'; margin:4px 0;">
                        ${dataQualityRes.gate_blocked_count?.value || 0}
                    </div>
                    <div style="font-size:0.68rem; color:#64748b;">Evidence gate rejected</div>
                </div>

                <div style="background:#0f172a; padding:12px; border-radius:6px; border:1px solid rgba(148,163,184,0.15);">
                    <div style="font-size:0.72rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Provider Failures</div>
                    <div style="font-size:1.3rem; font-weight:800; color:${(dataQualityRes.provider_failure_count?.value || 0) > 0 ? '#f87171' : '#34d399'}; font-family:'JetBrains Mono'; margin:4px 0;">
                        ${dataQualityRes.provider_failure_count?.value || 0}
                    </div>
                    <div style="font-size:0.68rem; color:#64748b;">Failed discovery/acq runs</div>
                </div>
            `;
        }

    } catch (err) {
        console.error('[DecisionAnalytics] Failed to load telemetry:', err);
    }
}
