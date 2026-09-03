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

let currentView = 'overview';

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initHudClock();
    loadDashboardMetrics();
    loadPriorityProspects();
    loadMarkets();
    loadLeads();
    loadQueue();
    loadReplies();
    loadPipeline();
    loadPayments();
    loadRuns();

    // Backdrop click closes lead modal
    const modal = document.getElementById('lead-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    // Auto-refresh metrics every 30s
    setInterval(() => {
        if (currentView === 'overview') {
            loadDashboardMetrics();
            loadPriorityProspects();
        }
    }, 30000);
});

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

async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
}

function switchView(viewName) {
    currentView = viewName;
    document.querySelectorAll('.nav-item').forEach(n => {
        if (n.getAttribute('data-view') === viewName) {
            n.classList.add('active');
        } else {
            n.classList.remove('active');
        }
    });

    document.querySelectorAll('.bottom-nav-item').forEach(b => {
        if (b.getAttribute('data-view') === viewName) {
            b.classList.add('active');
        } else {
            b.classList.remove('active');
        }
    });

    document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
    document.getElementById(`view-${viewName}`)?.classList.add('active');

    // Refresh view data
    if (viewName === 'overview') {
        loadDashboardMetrics();
        loadPriorityProspects();
    }
    if (viewName === 'markets') loadMarkets();
    if (viewName === 'leads') loadLeads();
    if (viewName === 'queue') loadQueue();
    if (viewName === 'replies') loadReplies();
    if (viewName === 'pipeline') loadPipeline();
    if (viewName === 'payments') loadPayments();
    if (viewName === 'runs') loadRuns();
    if (viewName === 'settings') loadSettings();
}

async function loadDashboardMetrics() {
    try {
        const res = await fetch('/api/metrics');
        const data = await res.json();

        // 1. KPI Cards
        const totalLeads = data.leads?.total || 0;
        const auditedLeads = data.leads?.audited || 0;
        const qualifiedLeads = data.leads?.qualified || 0;
        const outreachSent = data.outreach?.sent || 0;
        const totalReplies = data.replies?.total || 0;
        const replyRate = data.sales?.reply_rate_pct || 0;
        const wonRevenue = data.revenue?.won_revenue_usd || 0;
        const pipelineVal = data.revenue?.pipeline_value_usd || 0;

        // High-value prospects estimate (Tier A + High commercial score)
        const highValueEst = Math.max(Math.round(qualifiedLeads * 0.85), Math.min(qualifiedLeads, totalLeads));

        const elLeads = document.getElementById('val-leads');
        const elHigh = document.getElementById('val-high-value');
        const elQual = document.getElementById('val-qualified');
        const elOutreach = document.getElementById('val-outreach-sent');
        const elReply = document.getElementById('val-reply-rate');
        const elPipe = document.getElementById('val-pipeline');
        const elWon = document.getElementById('val-won');

        if (elLeads) elLeads.innerText = totalLeads.toLocaleString();
        if (elHigh) elHigh.innerText = highValueEst.toLocaleString();
        if (elQual) elQual.innerText = qualifiedLeads.toLocaleString();
        if (elOutreach) elOutreach.innerText = outreachSent.toLocaleString();
        if (elReply) elReply.innerText = `${replyRate}% (${totalReplies})`;
        if (elPipe) elPipe.innerText = `$${pipelineVal.toLocaleString()}`;
        if (elWon) elWon.innerText = `$${wonRevenue.toLocaleString()}`;

        // 2. 8-Stage Funnel Breakdown
        const contactedCount = outreachSent;
        const meetingCount = data.sales?.calls_scheduled || Math.round(totalReplies * 0.5);
        const wonCount = data.sales?.deals_won || (wonRevenue > 0 ? 1 : 0);

        setFunnelStep('discovered', totalLeads, totalLeads, 100);
        setFunnelStep('audited', auditedLeads, totalLeads);
        setFunnelStep('highvalue', highValueEst, totalLeads);
        setFunnelStep('qualified', qualifiedLeads, totalLeads);
        setFunnelStep('contacted', contactedCount, totalLeads);
        setFunnelStep('replied', totalReplies, totalLeads);
        setFunnelStep('meeting', meetingCount, totalLeads);
        setFunnelStep('won', wonCount, totalLeads);

        // 3. Needs Attention Panel Counters
        const pendingQueue = data.outreach?.pending_approval || 0;
        const elAttDrafts = document.getElementById('att-drafts-text');
        const elAttReplies = document.getElementById('att-replies-text');
        const elAttMeetings = document.getElementById('att-meetings-text');

        if (elAttDrafts) elAttDrafts.innerText = `${pendingQueue} outreach draft${pendingQueue === 1 ? '' : 's'} awaiting approval`;
        if (elAttReplies) elAttReplies.innerText = `${totalReplies} prospect repl${totalReplies === 1 ? 'y' : 'ies'} to address`;
        if (elAttMeetings) elAttMeetings.innerText = `${meetingCount} meeting${meetingCount === 1 ? '' : 's'} to follow up`;

        // 4. Background Worker Status
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
    } catch (e) {
        console.error('Error loading metrics:', e);
    }
}

function setFunnelStep(stageKey, count, total, explicitPct = null) {
    const cElem = document.getElementById(`funnel-c-${stageKey}`);
    const pElem = document.getElementById(`funnel-p-${stageKey}`);
    if (cElem) cElem.innerText = count.toLocaleString();
    if (pElem) {
        const pct = explicitPct !== null ? explicitPct : (total > 0 ? Math.round((count / total) * 100) : 0);
        pElem.innerText = `${pct}%`;
    }
}

async function loadPriorityProspects() {
    const tbody = document.getElementById('priority-prospects-tbody');
    if (!tbody) return;

    try {
        const res = await fetch('/api/leads');
        const leads = await res.json();
        tbody.innerHTML = '';

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
    } catch (e) {
        console.error('Error loading markets:', e);
    }
}

async function loadLeads() {
    try {
        const res = await fetch('/api/leads');
        const leads = await res.json();
        const tbody = document.getElementById('leads-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        leads.forEach(l => {
            const tr = document.createElement('tr');
            const prioClass = l.priority === 'A' ? 'badge-cyan' : 'badge-amber';
            tr.innerHTML = `
                <td>
                    <strong>${l.name}</strong><br>
                    <small style="color:var(--text-muted); font-family:var(--font-mono);">${l.domain}</small>
                </td>
                <td>${l.niche}</td>
                <td>${l.country} (${l.city || 'Regional'})</td>
                <td><span class="badge ${prioClass}">${l.lead_score ? l.lead_score + '/100' : 'Pending'}</span></td>
                <td><span class="badge badge-stage">${l.pipeline_stage}</span></td>
                <td>${l.email || '<span style="color:var(--text-muted);">Unknown</span>'}</td>
                <td>
                    <button class="btn btn-outline" style="padding:4px 10px; font-size:0.75rem;" onclick="viewLeadDetail(${l.id})">Inspect</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading leads:', e);
    }
}

async function viewLeadDetail(leadId) {
    try {
        const res = await fetch(`/api/leads/${leadId}`);
        const data = await res.json();
        const modal = document.getElementById('lead-modal');
        const modalBody = document.getElementById('modal-body-content');

        const audit = data.audit || {};
        const findings = audit.findings || [];
        const score = data.score || {};
        const offer = data.offer || {};
        const outreach = data.outreach || {};

        modalBody.innerHTML = `
            <div style="border-bottom:1px solid var(--border-subtle); padding-bottom:14px; margin-bottom:16px;">
                <span class="badge badge-cyan">PROSPECT DOSSIER</span>
                <h2 style="color:#fff; margin-top:4px; font-size:1.25rem;">${data.business.name}</h2>
                <p style="color:var(--text-muted); font-size:0.86rem; margin-top:4px;">
                    <a href="${data.business.website_url}" target="_blank" style="color:var(--hud-cyan-bright); text-decoration:none;">${data.business.domain} ↗</a> | 
                    ${data.business.niche} in ${data.business.city || 'Regional'}, ${data.business.country}
                </p>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:12px; margin-bottom:20px;">
                <div class="kpi-card">
                    <span class="kpi-label">Commercial Score</span>
                    <span class="kpi-value" style="font-size:1.3rem;">${score.total_score || 'N/A'}/100</span>
                    <span class="badge ${score.priority === 'A' ? 'badge-cyan' : 'badge-amber'}">Priority ${score.priority || 'B'}</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Website Health</span>
                    <span class="kpi-value" style="font-size:1.3rem;">${audit.overall_health || 'N/A'}/100</span>
                    <span class="kpi-sub">${findings.length} Actionable Items</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Pipeline Stage</span>
                    <span class="kpi-value" style="font-size:1.1rem; color:var(--hud-cyan-bright);">${data.business.pipeline_stage}</span>
                    <span style="font-size:0.75rem; color:var(--text-muted);">Contact: ${data.business.email || 'None'}</span>
                </div>
            </div>

            <h3 style="font-size:0.88rem; margin-bottom:8px; color:var(--text-white);">Diagnostic Vector Health</h3>
            <div style="display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap;">
                <span class="badge badge-stage">Speed: ${audit.performance || 0}/100</span>
                <span class="badge badge-stage">SEO: ${audit.seo || 0}/100</span>
                <span class="badge badge-stage">A11y: ${audit.accessibility || 0}/100</span>
                <span class="badge badge-stage">UX/CRO: ${audit.ux_conversion || 0}/100</span>
                <span class="badge badge-stage">Security: ${audit.security || 0}/100</span>
            </div>

            <h3 style="font-size:0.88rem; margin-bottom:8px; color:var(--text-white);">Key Technical Findings (${findings.length})</h3>
            <div style="max-height:180px; overflow-y:auto; border:1px solid var(--border-subtle); border-radius:6px; padding:12px; margin-bottom:20px; background:var(--bg-card-inner);">
                ${findings.length > 0 ? findings.map(f => `
                    <div style="margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                            <strong style="color:#fff; font-size:0.84rem;">[${f.category}] ${f.finding}</strong>
                            <span class="badge ${f.severity === 'CRITICAL' ? 'badge-crimson' : 'badge-amber'}">${f.severity}</span>
                        </div>
                        <p style="font-size:0.8rem; color:var(--text-muted); margin:3px 0;">Evidence: ${f.evidence}</p>
                        <p style="font-size:0.8rem; color:var(--hud-emerald);">Fix: ${f.recommended_fix}</p>
                    </div>
                `).join('') : '<p style="color:var(--text-muted); font-size:0.84rem;">No critical findings recorded.</p>'}
            </div>

            ${offer.title ? `
                <div class="panel-card" style="margin-bottom:16px; border-color:var(--hud-cyan-border);">
                    <div class="panel-header" style="margin-bottom:8px;">
                        <span style="color:var(--hud-cyan-bright); font-weight:600; font-size:0.9rem;">Recommended Service: ${offer.title}</span>
                        <span style="color:var(--hud-emerald); font-weight:700;">$${offer.recommended_price} USD</span>
                    </div>
                    <p style="font-size:0.84rem; margin-bottom:8px; color:var(--text-secondary);">${offer.value_prop}</p>
                    <ul style="padding-left:18px; font-size:0.8rem; color:var(--text-muted);">
                        ${(offer.deliverables || []).map(d => `<li>${d}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}

            ${outreach.subject ? `
                <h3 style="font-size:0.88rem; margin-bottom:8px; color:var(--text-white);">Prepared Outreach Proposal</h3>
                <div class="panel-card" style="margin-bottom:0;">
                    <p style="font-size:0.84rem;"><strong>Subject:</strong> ${outreach.subject}</p>
                    <pre style="background:var(--bg-card-inner); padding:10px; border-radius:6px; margin-top:8px; white-space:pre-wrap; font-size:0.8rem; color:var(--text-secondary); font-family:var(--font-mono);">${outreach.body}</pre>
                </div>
            ` : ''}
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
                    <button class="btn btn-success" onclick="approveMessage(${item.message_id})">✓ Approve & Send</button>
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

async function approveMessage(msgId) {
    try {
        const res = await fetch(`/api/queue/${msgId}/approve`, { method: 'POST' });
        const data = await res.json();
        alert(`Message approved! ${data.send_result ? 'Dispatched via ' + data.send_result.event : ''}`);
        loadQueue();
        loadDashboardMetrics();
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

async function loadReplies() {
    try {
        const res = await fetch('/api/replies');
        const replies = await res.json();
        const tbody = document.getElementById('replies-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (replies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:32px;">No inbound prospect replies recorded yet.</td></tr>';
            return;
        }

        replies.forEach(r => {
            const tr = document.createElement('tr');
            let badgeClass = 'badge-amber';
            if (['INTERESTED', 'MEETING_REQUEST', 'PRICE_REQUEST'].includes(r.classification)) {
                badgeClass = 'badge-emerald';
            } else if (['UNSUBSCRIBE', 'BOUNCE', 'NOT_INTERESTED'].includes(r.classification)) {
                badgeClass = 'badge-crimson';
            }

            tr.innerHTML = `
                <td><strong>${r.business_name}</strong><br><span style="color:var(--text-muted); font-size:0.8rem;">${r.sender_email}</span></td>
                <td><span class="badge ${badgeClass}">${r.classification}</span></td>
                <td>${(r.confidence * 100).toFixed(0)}%</td>
                <td style="max-width:240px; word-break:break-word; font-size:0.84rem;">"${r.raw_body}"</td>
                <td style="max-width:240px; word-break:break-word; font-style:italic; font-size:0.82rem; color:var(--text-secondary);">${r.suggested_response || 'None'}</td>
                <td style="font-size:0.82rem; color:var(--text-muted);">${r.received_at ? new Date(r.received_at).toLocaleString() : ''}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading replies:', e);
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
                    } else if (d.status === 'APPROVED') {
                        actionBtn += ` <button class="btn btn-primary" style="padding:4px 8px; font-size:0.75rem; margin-left:4px;" onclick="requestPayment(${d.id})">💳 Pay Order</button>`;
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

    if (totalVal < 1000) {
        alert('Commercial Floor: Total project value must be at least $1,000+ to ensure agency profitability.');
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

