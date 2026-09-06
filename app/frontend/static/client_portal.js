// Client Portal Frontend Logic
async function loadPortalData() {
  try {
    const res = await fetch('/api/client/portal-data');
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (!res.ok) {
      console.error('Failed to load portal data', res.status);
      return;
    }
    const data = await res.json();
    renderPortal(data);
  } catch (err) {
    console.error('Network error loading portal data:', err);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderPortal(data) {
  // Navigation & Header
  const navCompany = document.getElementById('nav-company-name');
  if (navCompany) navCompany.textContent = data.company_name || data.client_name || 'Client';
  
  const welcomeTitle = document.getElementById('welcome-client-name');
  if (welcomeTitle) {
    welcomeTitle.textContent = data.company_name ? `${data.company_name} — Project Workspace` : 'Client Project Workspace';
  }

  // Active Service KPI
  const activeProj = data.active_project;
  const kpiService = document.getElementById('kpi-service-name');
  const kpiServiceSub = document.getElementById('kpi-service-sub');
  if (kpiService) {
    kpiService.textContent = activeProj ? activeProj.service_type || activeProj.title : 'Digital Turnaround';
  }
  if (kpiServiceSub && activeProj) {
    kpiServiceSub.textContent = activeProj.title;
  }

  // Project Status KPI
  const kpiStatus = document.getElementById('kpi-project-status');
  const kpiStatusSub = document.getElementById('kpi-status-sub');
  if (kpiStatus) {
    const status = activeProj ? activeProj.status : (data.onboarding_status || 'IN_PROGRESS');
    kpiStatus.innerHTML = `<span class="status-pill ${status === 'COMPLETED' ? 'success' : 'progress'}">${escapeHtml(status)}</span>`;
  }
  if (kpiStatusSub && activeProj && activeProj.created_at) {
    const d = new Date(activeProj.created_at);
    kpiStatusSub.textContent = `Started ${d.toLocaleDateString()}`;
  }

  // Deliverables Count & List
  const deliverables = data.deliverables || [];
  const kpiDeliv = document.getElementById('kpi-deliverables-count');
  if (kpiDeliv) kpiDeliv.textContent = deliverables.length;

  const delivBadge = document.getElementById('deliverables-badge');
  if (delivBadge) delivBadge.textContent = `${deliverables.length} ${deliverables.length === 1 ? 'Asset' : 'Assets'}`;

  const delivContainer = document.getElementById('deliverables-list');
  if (delivContainer) {
    if (deliverables.length === 0) {
      delivContainer.innerHTML = `<p style="color: var(--cp-text-muted); font-size: 13px;">No completed deliverables released yet. Assets will appear here as engineering milestones are completed.</p>`;
    } else {
      delivContainer.innerHTML = deliverables.map(del => `
        <div class="deliverable-item">
          <div>
            <div style="font-weight: 500; font-size: 14px;">${escapeHtml(del.title)}</div>
            <div style="font-size: 12px; color: var(--cp-text-muted); margin-top: 2px;">Type: ${escapeHtml(del.type)}</div>
          </div>
          <span class="status-pill ${del.status === 'DELIVERED' ? 'success' : 'progress'}">${escapeHtml(del.status)}</span>
        </div>
      `).join('');
    }
  }

  // Tasks / Milestones List
  const tasks = data.tasks || [];
  const tasksBadge = document.getElementById('tasks-badge');
  if (tasksBadge) tasksBadge.textContent = `${tasks.length} ${tasks.length === 1 ? 'Milestone' : 'Milestones'}`;

  const tasksContainer = document.getElementById('tasks-list');
  if (tasksContainer) {
    if (tasks.length === 0) {
      tasksContainer.innerHTML = `<p style="color: var(--cp-text-muted); font-size: 13px;">Engineering plan is currently being structured. Milestones will be reflected upon staging completion.</p>`;
    } else {
      tasksContainer.innerHTML = tasks.map(t => `
        <div class="task-row">
          <div style="display: flex; align-items: center; gap: 10px;">
            <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${t.completed || t.status === 'COMPLETED' ? 'var(--cp-success)' : 'var(--cp-accent)'};"></span>
            <span style="font-size: 13px; font-weight: 500;">${escapeHtml(t.task)}</span>
          </div>
          <span class="status-pill ${t.completed || t.status === 'COMPLETED' ? 'success' : 'progress'}">${t.completed || t.status === 'COMPLETED' ? 'COMPLETED' : escapeHtml(t.status || 'IN_PROGRESS')}</span>
        </div>
      `).join('');
    }
  }

  // Payments / Billing
  const payments = data.payments || [];
  const contractAmt = data.contract_amount || 0;
  const kpiPayStatus = document.getElementById('kpi-payment-status');
  const kpiPayAmt = document.getElementById('kpi-payment-amount');

  let paidTotal = 0;
  payments.forEach(p => {
    if (p.status === 'COMPLETED' || p.status === 'PAID') {
      paidTotal += Number(p.amount) || 0;
    }
  });

  if (kpiPayStatus) {
    if (contractAmt > 0 && paidTotal >= contractAmt) {
      kpiPayStatus.innerHTML = `<span class="status-pill success">PAID IN FULL</span>`;
    } else if (paidTotal > 0) {
      kpiPayStatus.innerHTML = `<span class="status-pill progress">PARTIALLY PAID</span>`;
    } else {
      kpiPayStatus.innerHTML = `<span class="status-pill pending">PENDING</span>`;
    }
  }
  if (kpiPayAmt) {
    kpiPayAmt.textContent = `Paid: $${paidTotal.toLocaleString('en-US', {minimumFractionDigits: 2})} / $${contractAmt.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
  }

  const billingContainer = document.getElementById('billing-history');
  if (billingContainer) {
    if (payments.length === 0) {
      billingContainer.innerHTML = `<p style="color: var(--cp-text-muted); font-size: 13px;">No invoice or payment transactions recorded yet.</p>`;
    } else {
      billingContainer.innerHTML = payments.map(p => {
        const d = p.created_at ? new Date(p.created_at).toLocaleDateString() : 'Recent';
        return `
          <div class="billing-row">
            <div>
              <div style="font-weight: 500;">${escapeHtml(p.payment_type || 'INVOICE')}</div>
              <div style="color: var(--cp-text-muted); font-size: 11px;">${d} &bull; ${escapeHtml(p.currency || 'USD')}</div>
            </div>
            <div style="text-align: right;">
              <div style="font-weight: 600;">$${Number(p.amount).toFixed(2)}</div>
              <span class="status-pill ${p.status === 'COMPLETED' || p.status === 'PAID' ? 'success' : 'pending'}" style="font-size: 10px; padding: 2px 6px;">${escapeHtml(p.status)}</span>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // Support
  const supportLink = document.getElementById('support-email-link');
  if (supportLink && data.support_email) {
    supportLink.href = `mailto:${data.support_email}`;
    supportLink.textContent = data.support_email;
  }
}

async function handleLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {
    console.error('Logout error:', e);
  }
  // Clear cookies and redirect
  document.cookie = 'agency_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  window.location.href = '/login';
}

document.addEventListener('DOMContentLoaded', () => {
  loadPortalData();
});
