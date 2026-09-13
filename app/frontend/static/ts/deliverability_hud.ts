/**
 * Agency OS: Deliverability & Outreach HUD Type Definitions
 * Language: TypeScript
 * Description: Type-safe contracts for email deliverability monitoring,
 *              14-point deterministic auto-approval eligibility, and live-send authorization.
 */

export interface DnsCheckItem {
    label: string;
    status: 'Verified' | 'Missing' | 'Verification required' | 'Failed';
    verified: boolean;
    record?: string;
    error?: string;
}

export interface ProviderHealth {
    status: 'OK' | 'ERROR' | 'UNCONFIGURED' | 'NOT_CHECKED';
    healthy: boolean;
    authenticated_email?: string | null;
    host?: string;
    port?: number;
    error?: string;
    messages_total?: number;
    inbox_messages_total?: number;
}

export interface DeliverabilityReadinessReport {
    sender: string;
    reply_to: string;
    active_provider: 'gmail' | 'gmail_oauth' | 'titan' | 'titan_smtp' | 'smtp' | 'resend' | 'sendgrid' | 'dry_run';
    dry_run: boolean;
    smtp_readiness: string;
    titan_smtp: ProviderHealth;
    titan_imap: ProviderHealth;
    gmail_oauth: ProviderHealth;
    spf: DnsCheckItem;
    dkim: DnsCheckItem;
    dmarc: DnsCheckItem;
    compliance: {
        can_spam_footer_active: boolean;
        opt_out_rule_active: boolean;
        bounce_rule_active: boolean;
        reply_rule_active: boolean;
    };
    daily_cap: {
        rollout_stage_name: string;
        rollout_daily_cap: number;
        sent_today: number;
        available_capacity: number;
    };
    outreach_lock: 'IDLE' | 'BUSY';
    overall_readiness: 'READY_LIVE' | 'BLOCKED' | 'WARNING' | 'DRY_RUN_SAFE';
}

export interface AutoApprovalCheck {
    name: string;
    passed: boolean;
    detail: string;
}

export interface AutoApprovalEligibilityResult {
    message_id: number;
    is_eligible: boolean;
    checks: AutoApprovalCheck[];
    blocking_reasons: string[];
}

export interface LiveSendAuthorizationRequest {
    auto_send: boolean;
    force_live: boolean;
    actor: 'HUMAN' | 'SYSTEM_AUTO_APPROVAL';
}

export interface LiveSendResponse {
    status: 'APPROVED' | 'REJECTED' | 'FAILED';
    message_id: number;
    actor: string;
    send_result?: {
        event: string;
        recipient: string;
        sender: string;
        provider: string;
        message_id: string;
        delivery_status: string;
    };
    error?: string;
}
