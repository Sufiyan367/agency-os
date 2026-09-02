// Autonomous B2B Lead-Gen Dashboard Client

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
        if (currentView === 'overview') loadDashboardMetrics();
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

    document.getElementById('btn-run-cycle').addEventListener('click', runAutonomousCycle);
}

function toggleMobileDrawer() {
    const drawer = document.getElementById('mobile-drawer');
    const backdrop = document.getElementById('mobile-drawer-backdrop');
    if (!drawer) return;
    const isOpen = drawer.classList.contains('open');
    if (isOpen) {
        drawer.classList.remove('open');
        if (backdrop) backdrop.style.display = 'none';
    } else {
        drawer.classList.add('open');
        if (backdrop) backdrop.style.display = 'block';
    }
}

function navToView(viewName) {
    switchView(viewName);
    const drawer = document.getElementById('mobile-drawer');
    const backdrop = document.getElementById('mobile-drawer-backdrop');
    if (drawer && drawer.classList.contains('open')) {
        drawer.classList.remove('open');
        if (backdrop) backdrop.style.display = 'none';
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

    const titles = {
        'overview': '// COMMAND CENTER TELEMETRY',
        'markets': '// GLOBAL MARKET RADAR',
        'leads': '// TARGET PROSPECT REGISTRY',
        'queue': '// OUTREACH AUTHORIZATION TERMINAL',
        'replies': '// INBOUND SIGNAL INTERCEPTION',
        'pipeline': '// SALES PIPELINE KANBAN',
        'payments': '// FINANCIAL LEDGER & DEALS',
        'runs': '// SCHEDULER & WORKER HEARTBEATS'
    };
    const titleElem = document.getElementById('page-title');
    if (titleElem && titles[viewName]) {
        titleElem.innerText = titles[viewName];
    }

    // Refresh view data
    if (viewName === 'overview') loadDashboardMetrics();
    if (viewName === 'markets') loadMarkets();
    if (viewName === 'leads') loadLeads();
    if (viewName === 'queue') loadQueue();
    if (viewName === 'replies') loadReplies();
    if (viewName === 'pipeline') loadPipeline();
    if (viewName === 'payments') loadPayments();
    if (viewName === 'runs') loadRuns();
}

async function loadDashboardMetrics() {
    try {
        const res = await fetch('/api/metrics');
        const data = await res.json();

        document.getElementById('val-pipeline').innerText = `$${(data.revenue.pipeline_value_usd || 0).toLocaleString()}`;
        document.getElementById('val-won').innerText = `$${(data.revenue.won_revenue_usd || 0).toLocaleString()}`;
        document.getElementById('val-leads').innerText = data.leads.total || 0;
        document.getElementById('val-qualified').innerText = data.leads.qualified || 0;
        document.getElementById('val-outreach-sent').innerText = data.outreach.sent || 0;
        document.getElementById('val-reply-rate').innerText = `${data.sales.reply_rate_pct || 0}%`;

        // Update pipeline summary cards
        const funnelElem = document.getElementById('funnel-breakdown');
        if (funnelElem) {
            funnelElem.innerHTML = `
                <div style="display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap;">
                    <div class="metric-card" style="flex:1;">
                        <span class="metric-label">Discovery -> Audited</span>
                        <span class="metric-val" style="font-size:1.3rem;">${data.leads.audited} / ${data.leads.total}</span>
                    </div>
                    <div class="metric-card" style="flex:1;">
                        <span class="metric-label">Audited -> Qualified</span>
                        <span class="metric-val" style="font-size:1.3rem;">${data.leads.qualified} (${data.leads.qualification_rate_pct}%)</span>
                    </div>
                    <div class="metric-card" style="flex:1;">
                        <span class="metric-label">Outreach Approval Rate</span>
                        <span class="metric-val" style="font-size:1.3rem;">${data.outreach.approval_rate_pct}%</span>
                    </div>
                    <div class="metric-card" style="flex:1;">
                        <span class="metric-label">Qualified Reply Rate</span>
                        <span class="metric-val" style="font-size:1.3rem;">${data.sales.qualified_reply_rate_pct}%</span>
                    </div>
                </div>
            `;
        }
        // Fetch real-time worker telemetry
        try {
            const wRes = await fetch('/api/worker/status');
            if (wRes.ok) {
                const wData = await wRes.json();
                const statusElem = document.getElementById('worker-hud-status');
                const ticksElem = document.getElementById('worker-hud-ticks');
                const lastTickElem = document.getElementById('worker-hud-last-tick');
                
                if (statusElem) {
                    if (wData.is_running) {
                        statusElem.innerText = 'ONLINE // ACTIVE';
                        statusElem.style.color = 'var(--emerald)';
                    } else {
                        statusElem.innerText = 'STANDBY // READY';
                        statusElem.style.color = 'var(--amber)';
                    }
                }
                if (ticksElem) {
                    ticksElem.innerText = `${wData.ticks_executed || 0} TICKS`;
                }
                if (lastTickElem && wData.last_tick_at) {
                    const d = new Date(wData.last_tick_at);
                    lastTickElem.innerText = d.toLocaleTimeString();
                }
            }
        } catch (we) {
            console.debug('Worker status poll:', we);
        }
    } catch (e) {
        console.error('Error loading metrics:', e);
    }
}

async function loadMarkets() {
    try {
        const res = await fetch('/api/markets');
        const markets = await res.json();
        const tbody = document.getElementById('markets-table-body');
        tbody.innerHTML = '';

        markets.forEach((m, idx) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>#${idx + 1}</strong></td>
                <td><strong>${m.country}</strong> (${m.country_code})</td>
                <td>${m.niche}</td>
                <td><span class="badge ${m.opportunity_score >= 80 ? 'badge-a' : 'badge-b'}">${m.opportunity_score}/100</span></td>
                <td>$${m.expected_deal_value.toLocaleString()}</td>
                <td>${m.digital_weakness}/100</td>
                <td style="font-size:0.85rem; color:#9ca3af;">${m.reasoning}</td>
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
        tbody.innerHTML = '';

        leads.forEach(l => {
            const tr = document.createElement('tr');
            const prioClass = l.priority === 'A' ? 'badge-a' : (l.priority === 'B' ? 'badge-b' : 'badge-c');
            tr.innerHTML = `
                <td><strong>${l.name}</strong><br><small style="color:#6b7280;">${l.domain}</small></td>
                <td>${l.niche}</td>
                <td>${l.country} (${l.city || 'Regional'})</td>
                <td><span class="badge ${prioClass}">${l.lead_score ? l.lead_score + '/100' : 'Pending'} (${l.priority || 'N/A'})</span></td>
                <td><span class="badge badge-stage">${l.pipeline_stage}</span></td>
                <td>${l.email || '<span style="color:#6b7280;">Unknown</span>'}</td>
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

        const audit = data.audit;
        const findings = audit.findings || [];
        const score = data.score;
        const offer = data.offer;
        const outreach = data.outreach;

        modalBody.innerHTML = `
            <div style="border-bottom:1px solid rgba(0,229,255,0.2); padding-bottom:12px; margin-bottom:16px;">
                <span class="badge badge-b">// TARGET PROSPECT DOSSIER</span>
                <h2 style="font-family:var(--font-hud); color:#fff; margin-top:4px; font-size:1.25rem;">${data.business.name}</h2>
                <p style="color:#94a3b8; font-size:0.88rem; margin-top:4px;">
                    <a href="${data.business.website_url}" target="_blank" style="color:var(--hud-cyan); text-decoration:none;">${data.business.domain} ↗</a> | 
                    ${data.business.niche} in ${data.business.city || 'Regional'}, ${data.business.country}
                </p>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:12px; margin-bottom:20px;">
                <div class="metric-card">
                    <span class="metric-label">Commercial Score</span>
                    <span class="metric-val" style="font-size:1.35rem;">${score.total_score || 'N/A'}/100</span>
                    <span class="badge ${score.priority === 'A' ? 'badge-a' : 'badge-b'}">Priority ${score.priority || 'B'}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Website Health</span>
                    <span class="metric-val" style="font-size:1.35rem;">${audit.overall_health || 'N/A'}/100</span>
                    <span class="metric-sub">${findings.length} Actionable Items</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Pipeline Stage</span>
                    <span class="metric-val" style="font-size:1.1rem; color:var(--hud-cyan);">${data.business.pipeline_stage}</span>
                    <span style="font-size:0.75rem; color:#94a3b8; word-break:break-all;">Contact: ${data.business.email || 'None'}</span>
                </div>
            </div>

            <h3 style="font-family:var(--font-hud); font-size:0.88rem; margin-bottom:8px; color:var(--hud-cyan);">Diagnostic Vector Health</h3>
            <div style="display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap;">
                <span class="badge badge-b">Speed: ${audit.performance}/100</span>
                <span class="badge badge-b">SEO: ${audit.seo}/100</span>
                <span class="badge badge-b">A11y: ${audit.accessibility}/100</span>
                <span class="badge badge-b">UX/CRO: ${audit.ux_conversion}/100</span>
                <span class="badge badge-b">Security: ${audit.security}/100</span>
                <span class="badge badge-b">Content: ${audit.content}/100</span>
            </div>

            <h3 style="font-family:var(--font-hud); font-size:0.88rem; margin-bottom:8px; color:var(--hud-cyan);">Key Technical Findings (${findings.length})</h3>
            <div style="max-height:200px; overflow-y:auto; border:1px solid rgba(0,229,255,0.15); border-radius:4px; padding:12px; margin-bottom:20px; background:rgba(4,9,20,0.6);">
                ${findings.length > 0 ? findings.map(f => `
                    <div style="margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                            <strong style="color:#fff; font-size:0.88rem;">[${f.category}] ${f.finding}</strong>
                            <span class="badge ${f.severity === 'CRITICAL' ? 'badge-c' : 'badge-b'}">${f.severity}</span>
                        </div>
                        <p style="font-size:0.82rem; color:#94a3b8; margin:3px 0;">Evidence: ${f.evidence}</p>
                        <p style="font-size:0.82rem; color:var(--hud-emerald);">Fix: ${f.recommended_fix}</p>
                    </div>
                `).join('') : '<p style="color:#94a3b8; font-size:0.85rem;">No critical findings recorded.</p>'}
            </div>

            ${offer.title ? `
                <div class="card" style="margin-bottom:16px; border-color:var(--hud-cyan);">
                    <div class="card-title" style="color:var(--hud-cyan); font-size:0.9rem;">
                        <span>Recommended Service: ${offer.title}</span>
                        <span style="color:var(--hud-emerald);">$${offer.recommended_price} USD</span>
                    </div>
                    <p style="font-size:0.88rem; margin-bottom:8px; color:#e2e8f0;">${offer.value_prop}</p>
                    <ul style="padding-left:18px; font-size:0.82rem; color:#94a3b8;">
                        ${offer.deliverables.map(d => `<li>${d}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}

            ${outreach.subject ? `
                <h3 style="font-family:var(--font-hud); font-size:0.88rem; margin-bottom:8px; color:var(--hud-cyan);">Prepared Personalized Outreach (${outreach.variant})</h3>
                <div class="card" style="margin-bottom:0;">
                    <p style="font-size:0.88rem;"><strong>Subject:</strong> ${outreach.subject}</p>
                    <pre style="background:rgba(4,9,20,0.8); padding:10px; border-radius:4px; margin-top:8px; white-space:pre-wrap; font-size:0.82rem; color:#cbd5e1; font-family:var(--font-mono);">${outreach.body}</pre>
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
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(0,229,255,0.2); padding-bottom:12px; margin-bottom:16px; flex-wrap:wrap; gap:8px;">
                <div>
                    <span class="badge badge-a">// CLIENT DELIVERY PACKET</span>
                    <h2 style="font-family:var(--font-hud); color:#fff; margin-top:4px; font-size:1.15rem;">Technical Remediation Deliverable</h2>
                </div>
                <button class="btn btn-primary" onclick="navigator.clipboard.writeText(document.getElementById('report-text-content').innerText); alert('Audit report copied to clipboard!');">📋 Copy Packet</button>
            </div>
            <div id="report-text-content" style="background:rgba(4,9,20,0.9); padding:16px; border-radius:4px; border:1px solid rgba(0,229,255,0.15); max-height:60vh; overflow-y:auto; font-family:var(--font-mono); font-size:0.82rem; color:#d1d5db; white-space:pre-wrap; line-height:1.6;">${data.markdown || 'No report content generated.'}</div>
        `;
        modal.classList.add('active');
    } catch (e) {
        alert('Error fetching delivery report: ' + e);
    }
}

function closeModal() {
    document.getElementById('lead-modal').classList.remove('active');
}

async function loadQueue() {
    try {
        const res = await fetch('/api/queue');
        const queue = await res.json();
        const container = document.getElementById('queue-cards-container');
        container.innerHTML = '';

        if (queue.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding:32px 16px; color:var(--text-muted); font-family:var(--font-mono); font-size:0.85rem;">// NO OUTREACH TRANSMISSIONS PENDING AUTHORIZATION. ENGAGE AUTONOMOUS PROTOCOL TO POPULATE.</div>';
            return;
        }

        queue.forEach(item => {
            const card = document.createElement('div');
            card.className = 'card';
            card.innerHTML = `
                <div class="card-title">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <strong style="color:#fff;">${item.business_name}</strong>
                        <span style="color:var(--hud-cyan); font-family:var(--font-mono); font-size:0.8rem;">(${item.domain})</span>
                        <span class="badge badge-a">Score: ${item.lead_score}/100</span>
                    </div>
                    <div>
                        <span class="badge badge-stage">${item.recommended_service} ($${item.recommended_price})</span>
                    </div>
                </div>
                <p style="font-size:0.85rem; margin-bottom:4px;"><strong style="color:var(--text-muted);">TO:</strong> <span style="font-family:var(--font-mono); color:var(--text-cyan);">${item.recipient_email}</span></p>
                <p style="font-size:0.85rem; margin-bottom:8px;"><strong style="color:var(--text-muted);">SUBJECT:</strong> <span style="color:#fff;">${item.subject}</span></p>
                <div style="background:rgba(4,9,20,0.85); padding:12px; border-radius:4px; margin-bottom:12px; max-height:140px; overflow-y:auto; font-size:0.82rem; color:#cbd5e1; white-space:pre-wrap; font-family:var(--font-mono); border:1px solid rgba(0,229,255,0.1);">
                    ${item.body}
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
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
                            <strong>${l.name}</strong>
                            <small style="color:#9ca3af;">${l.niche}</small>
                            <span class="badge ${l.priority === 'A' ? 'badge-a' : 'badge-b'}" style="align-self:flex-start;">
                                ${l.lead_score ? l.lead_score + '/100' : 'Score Pending'}
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
        tbody.innerHTML = '';

        runs.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${r.run_id}</code></td>
                <td>${r.job_name}</td>
                <td><span class="badge badge-a">${r.status}</span></td>
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
    btn.disabled = true;
    btn.innerText = '⚡ Running Cycle...';
    try {
        const res = await fetch('/api/run-cycle', { method: 'POST' });
        const data = await res.json();
        alert(`Autonomous Loop Completed in ${data.duration_seconds}s! Discovered: ${data.new_leads_discovered}, Audited: ${data.websites_audited}, Scored: ${data.leads_scored}, Queued: ${data.outreach_queued_for_approval}`);
        loadDashboardMetrics();
        loadMarkets();
        loadLeads();
        loadQueue();
        loadPipeline();
        loadRuns();
    } catch (e) {
        alert('Error triggering loop: ' + e);
    } finally {
        btn.disabled = false;
        btn.innerText = '⚡ Run Autonomous Cycle';
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
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); font-family:var(--font-mono); font-size:0.85rem; padding:28px;">// NO INBOUND SIGNALS INTERCEPTED. WAITING FOR PROSPECT TRANSMISSIONS.</td></tr>';
            return;
        }

        replies.forEach(r => {
            const tr = document.createElement('tr');
            let badgeClass = 'badge-b';
            if (['INTERESTED', 'MEETING_REQUEST', 'PRICE_REQUEST'].includes(r.classification)) {
                badgeClass = 'badge-a';
            } else if (['UNSUBSCRIBE', 'BOUNCE', 'NOT_INTERESTED'].includes(r.classification)) {
                badgeClass = 'badge-c';
            }

            tr.innerHTML = `
                <td><strong>${r.business_name}</strong><br><span style="color:#6b7280; font-size:0.85rem;">${r.sender_email}</span></td>
                <td><span class="badge ${badgeClass}">${r.classification}</span></td>
                <td>${(r.confidence * 100).toFixed(0)}%</td>
                <td style="max-width:260px; word-break:break-word; font-size:0.9rem;">"${r.raw_body}"</td>
                <td style="max-width:260px; word-break:break-word; font-style:italic; font-size:0.85rem; color:#d1d5db;">${r.suggested_response || 'None'}</td>
                <td style="font-size:0.85rem; color:#9ca3af;">${r.received_at ? new Date(r.received_at).toLocaleString() : ''}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading replies:', e);
    }
}

async function loadPayments() {
    try {
        const res = await fetch('/api/payments');
        const payments = await res.json();
        const tbody = document.getElementById('payments-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (payments.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted); font-family:var(--font-mono); font-size:0.85rem; padding:28px;">// FINANCIAL LEDGER ZEROED. PENDING CONTRACT EXECUTION.</td></tr>';
            return;
        }

        payments.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${p.reference_id}</code></td>
                <td><strong>${p.company_name}</strong></td>
                <td style="font-weight:bold; color:#10b981;">$${p.amount.toLocaleString()}</td>
                <td>${p.currency}</td>
                <td><span class="badge badge-a">${p.status}</span></td>
                <td>${p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</td>
                <td><button class="btn btn-secondary" onclick="viewAuditReport(${p.business_id || p.customer_id})">📄 Delivery Pack</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading payments:', e);
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
