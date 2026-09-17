/**
 * Agency OS: Deliverability & Outreach HUD Type Definitions
 * Language: TypeScript
 * Description: Type-safe contracts for email deliverability monitoring,
 *              14-point deterministic auto-approval eligibility, and live-send authorization.
 */
/**
 * Deliverability & Outreach HUD Client Controller
 * Manages deliverability readiness telemetry, auto-approval diagnostic badges,
 * and live-send state management.
 */
export class DeliverabilityHUDController {
    constructor() {
        this.report = null;
        this.isPolling = false;
        this.pollIntervalMs = 30000;
    }
    /**
     * Fetches current deliverability readiness telemetry from backend API.
     */
    async fetchReadiness() {
        try {
            const resp = await fetch('/api/email/deliverability-readiness', {
                method: 'GET',
                headers: { 'Accept': 'application/json' }
            });
            if (!resp.ok) {
                console.warn(`[DeliverabilityHUD] Telemetry fetch failed: HTTP ${resp.status}`);
                return null;
            }
            this.report = await resp.json();
            return this.report;
        }
        catch (err) {
            console.error('[DeliverabilityHUD] Network error fetching readiness:', err);
            return null;
        }
    }
    /**
     * Fetches deterministic auto-approval diagnostic breakdown for a specific queue item.
     */
    async fetchAutoApprovalEligibility(messageId) {
        try {
            const resp = await fetch(`/api/queue/${messageId}`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' }
            });
            if (!resp.ok)
                return null;
            const data = await resp.json();
            if (data && data.auto_approval_eligibility) {
                return data.auto_approval_eligibility;
            }
            return null;
        }
        catch (err) {
            console.error(`[DeliverabilityHUD] Error fetching eligibility for message #${messageId}:`, err);
            return null;
        }
    }
    /**
     * Renders deliverability readiness status badge into specified container.
     */
    renderReadinessBadge(container, report) {
        const authStatus = report.auth_status || report.outbound_authorization || 'BLOCKED';
        const isAuthBlocked = authStatus === 'BLOCKED';
        const authBlocker = report.reason || report.outbound_auth_blocker;
        const lockStatus = report.outreach_lock || 'IDLE';
        const cap = report.daily_cap;
        const provLabel = report.primary_provider || (report.active_provider ? report.active_provider.toUpperCase() : 'Titan Email');
        const sender = report.address || report.sender || 'hello@automatedagencyos.tech';
        const spf = report.spf ? report.spf.status : 'Verified';
        const dkim = report.dkim ? report.dkim.status : 'Verified';
        const dmarc = report.dmarc ? report.dmarc.status : 'Not Verified';
        const badgeHtml = `
            <div class="deliverability-hud-pill" title="Sender: ${sender} | SPF: ${spf} | DKIM: ${dkim} | DMARC: ${dmarc} | Outbound: ${authStatus}${authBlocker ? ` (${authBlocker})` : ''}" style="display:inline-flex; align-items:center; gap:8px; padding:6px 12px; background:rgba(24, 24, 27, 0.85); border:1px solid ${isAuthBlocked ? '#ef4444' : '#10b981'}; border-radius:20px; font-size:0.75rem; font-family:'JetBrains Mono', monospace; cursor:help;">
                <span style="width:8px; height:8px; border-radius:50%; background:${isAuthBlocked ? '#ef4444' : '#10b981'}; display:inline-block;"></span>
                <span style="color:#e4e4e7; font-weight:600;">${provLabel} (Primary)</span>
                <span style="color:#71717a;">|</span>
                <span style="color:#a1a1aa;">${sender}</span>
                <span style="color:#71717a;">|</span>
                <span style="color:${isAuthBlocked ? '#f87171' : '#10b981'};">Auth: ${authStatus}${isAuthBlocked && authBlocker ? ` (${authBlocker})` : ''}</span>
                <span style="color:#71717a;">|</span>
                <span style="color:${lockStatus === 'IDLE' ? '#10b981' : '#f59e0b'};">Lock: ${lockStatus}</span>
            </div>
        `;
        container.innerHTML = badgeHtml;
    }
    /**
     * Renders 13-gate diagnostic modal or expander for an outreach queue message.
     */
    renderEligibilityTrace(container, eligibility) {
        if (!eligibility || !eligibility.checks) {
            container.innerHTML = `<p style="color:#71717a; font-size:0.8rem;">No eligibility diagnostic available.</p>`;
            return;
        }
        const checksList = eligibility.checks.map(c => {
            const icon = c.passed ? '✓' : '✗';
            const color = c.passed ? '#10b981' : '#ef4444';
            return `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.75rem;">
                    <span style="color:${color}; font-weight:bold; width:16px;">${icon}</span>
                    <span style="color:#d4d4d8; flex:1; margin-left:6px; font-family:'JetBrains Mono', monospace;">${c.name}</span>
                    <span style="color:#a1a1aa; font-size:0.7rem; text-align:right;">${c.detail}</span>
                </div>
            `;
        }).join('');
        const statusBanner = eligibility.is_eligible
            ? `<div style="padding:6px 10px; background:rgba(16, 185, 129, 0.1); border:1px solid #10b981; border-radius:4px; color:#10b981; font-weight:600; font-size:0.75rem; margin-bottom:8px;">✓ Deterministically Eligible for Auto-Approval</div>`
            : `<div style="padding:6px 10px; background:rgba(239, 68, 68, 0.1); border:1px solid #ef4444; border-radius:4px; color:#ef4444; font-weight:600; font-size:0.75rem; margin-bottom:8px;">⚠ Ineligible: ${eligibility.blocking_reasons.join('; ')}</div>`;
        container.innerHTML = `
            <div style="padding:10px; background:#09090b; border:1px solid rgba(255,255,255,0.08); border-radius:6px;">
                ${statusBanner}
                <div style="max-height:220px; overflow-y:auto;">
                    ${checksList}
                </div>
            </div>
        `;
    }
}
// Attach singleton to global window scope for dashboard integration and auto-mount
if (typeof window !== 'undefined') {
    const controller = new DeliverabilityHUDController();
    window.deliverabilityHUD = controller;
    // Auto-mount HUD on DOM ready if container exists
    const initHUD = async () => {
        const container = document.getElementById('deliverability-readiness-hud-container');
        if (container) {
            const report = await controller.fetchReadiness();
            if (report) {
                controller.renderReadinessBadge(container, report);
            }
        }
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initHUD);
    }
    else {
        initHUD();
    }
}
