// Autonomous B2B Lead-Gen Dashboard Client

let currentView = 'overview';

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadDashboardMetrics();
    loadMarkets();
    loadLeads();
    loadQueue();
    loadPipeline();
    loadRuns();
});

function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const targetView = item.getAttribute('data-view');
            switchView(targetView);
        });
    });

    document.getElementById('btn-run-cycle').addEventListener('click', runAutonomousCycle);
}

function switchView(viewName) {
    currentView = viewName;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`.nav-item[data-view="${viewName}"]`)?.classList.add('active');

    document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
    document.getElementById(`view-${viewName}`)?.classList.add('active');

    // Refresh view data
    if (viewName === 'overview') loadDashboardMetrics();
    if (viewName === 'markets') loadMarkets();
    if (viewName === 'leads') loadLeads();
    if (viewName === 'queue') loadQueue();
    if (viewName === 'pipeline') loadPipeline();
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
            <h2>${data.business.name}</h2>
            <p style="color:#9ca3af; margin-bottom:16px;">
                <a href="${data.business.website_url}" target="_blank" style="color:#3b82f6;">${data.business.domain}</a> | 
                ${data.business.niche} in ${data.business.city || ''}, ${data.business.country}
            </p>

            <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin-bottom:24px;">
                <div class="metric-card">
                    <span class="metric-label">Commercial Score</span>
                    <span class="metric-val" style="font-size:1.4rem;">${score.total_score || 'N/A'}/100</span>
                    <span class="badge ${score.priority === 'A' ? 'badge-a' : 'badge-b'}">Priority ${score.priority}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Website Health</span>
                    <span class="metric-val" style="font-size:1.4rem;">${audit.overall_health || 'N/A'}/100</span>
                    <span class="metric-sub">${findings.length} Actionable Items</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Pipeline Stage</span>
                    <span class="metric-val" style="font-size:1.2rem;">${data.business.pipeline_stage}</span>
                    <span style="font-size:0.8rem; color:#9ca3af;">Contact: ${data.business.email || 'None'}</span>
                </div>
            </div>

            <h3 style="margin-bottom:8px;">Diagnostic Vector Health</h3>
            <div style="display:flex; gap:12px; margin-bottom:24px; flex-wrap:wrap;">
                <span class="badge badge-b">Speed: ${audit.performance}/100</span>
                <span class="badge badge-b">SEO: ${audit.seo}/100</span>
                <span class="badge badge-b">A11y: ${audit.accessibility}/100</span>
                <span class="badge badge-b">UX/CRO: ${audit.ux_conversion}/100</span>
                <span class="badge badge-b">Security: ${audit.security}/100</span>
                <span class="badge badge-b">Content: ${audit.content}/100</span>
            </div>

            <h3 style="margin-bottom:8px;">Key Technical Findings (${findings.length})</h3>
            <div style="max-height:220px; overflow-y:auto; border:1px solid #1f293d; border-radius:6px; padding:12px; margin-bottom:24px;">
                ${findings.map(f => `
                    <div style="margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
                        <div style="display:flex; justify-content:space-between;">
                            <strong>[${f.category}] ${f.finding}</strong>
                            <span class="badge ${f.severity === 'CRITICAL' ? 'badge-low' : 'badge-c'}">${f.severity}</span>
                        </div>
                        <p style="font-size:0.85rem; color:#9ca3af; margin:4px 0;">Evidence: ${f.evidence}</p>
                        <p style="font-size:0.85rem; color:#10b981;">Fix: ${f.recommended_fix}</p>
                    </div>
                `).join('')}
            </div>

            ${offer.title ? `
                <div class="card" style="margin-bottom:24px; border-color:#3b82f6;">
                    <div class="card-title" style="color:#60a5fa;">
                        <span>Recommended Service: ${offer.title}</span>
                        <span>$${offer.recommended_price} USD</span>
                    </div>
                    <p style="font-size:0.9rem; margin-bottom:12px;">${offer.value_prop}</p>
                    <ul style="padding-left:20px; font-size:0.85rem; color:#9ca3af;">
                        ${offer.deliverables.map(d => `<li>${d}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}

            ${outreach.subject ? `
                <h3 style="margin-bottom:8px;">Prepared Personalized Outreach (${outreach.variant})</h3>
                <div class="card">
                    <p><strong>Subject:</strong> ${outreach.subject}</p>
                    <pre style="background:#0b0f19; padding:12px; border-radius:6px; margin-top:8px; white-space:pre-wrap; font-size:0.85rem; color:#d1d5db;">${outreach.body}</pre>
                </div>
            ` : ''}
        `;

        modal.classList.add('active');
    } catch (e) {
        console.error('Error fetching lead detail:', e);
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
            container.innerHTML = '<p style="color:#9ca3af;">No outreach messages currently pending approval. Run a cycle to populate!</p>';
            return;
        }

        queue.forEach(item => {
            const card = document.createElement('div');
            card.className = 'card';
            card.innerHTML = `
                <div class="card-title">
                    <div>
                        <strong>${item.business_name}</strong> (${item.domain})
                        <span class="badge badge-a" style="margin-left:8px;">Score: ${item.lead_score}/100</span>
                    </div>
                    <div>
                        <span class="badge badge-stage">${item.recommended_service} ($${item.recommended_price})</span>
                    </div>
                </div>
                <p style="font-size:0.88rem; margin-bottom:6px;"><strong>To:</strong> ${item.recipient_email}</p>
                <p style="font-size:0.88rem; margin-bottom:10px;"><strong>Subject:</strong> ${item.subject}</p>
                <div style="background:#0b0f19; padding:12px; border-radius:6px; margin-bottom:16px; max-height:140px; overflow-y:auto; font-size:0.85rem; color:#d1d5db; white-space:pre-wrap;">
                    ${item.body}
                </div>
                <div style="display:flex; gap:12px;">
                    <button class="btn btn-success" onclick="approveMessage(${item.message_id})">Approve & Send</button>
                    <button class="btn btn-danger" onclick="rejectMessage(${item.message_id})">Reject</button>
                    <button class="btn btn-outline" onclick="viewLeadDetail(${item.business_id})">View Audit</button>
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
