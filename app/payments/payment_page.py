"""
Agency OS — Customer-Facing Payment Page Renderer
Renders high-clarity, minimal, responsive HTML payment page for customers.
Enforces commercial transparency:
- 40% advance deposit vs 60% handover balance
- Google Pay UPI / Foreign Inward Remittance instructions (mrsufiyansurve@okaxis)
- Operator reconciliation submission form (Bank UTR / Ref)
- Zero fake success & anti-fraud security notices
"""

import html
from typing import Optional, Dict, Any
from app.core.config import settings


def render_customer_payment_html(
    payment: Any,
    business: Optional[Any] = None,
    proposal: Optional[Any] = None,
    provider_configured: bool = False,
    submitted: bool = False
) -> str:
    """
    Renders the customer payment HTML interface.
    """
    biz_name = html.escape(business.name if business else "Client Organization")
    domain = html.escape(business.domain if business and business.domain else "")
    prop_title = html.escape(proposal.title if proposal and hasattr(proposal, "title") else "Autonomous Agency Delivery")

    ref_id = html.escape(payment.gpay_reference or payment.reference_id or f"PAY-{payment.id}")
    
    # Financials
    total_value = float(getattr(proposal, "total_value", getattr(proposal, "total_price_usd", 500.0)) or 500.0)
    # Ensure minimum floor
    if total_value < 500.0:
        total_value = 500.0

    advance_amount = float(payment.amount or (total_value * 0.40))
    if advance_amount < 200.0:
        advance_amount = max(200.0, total_value * 0.40)

    balance_amount = max(0.0, total_value - advance_amount)

    currency = html.escape(payment.currency or "USD")

    # Status handling
    status = (payment.status or "PAYMENT_PENDING").upper()
    confirmed_statuses = {"PAYMENT_CONFIRMED", "VERIFIED_PAYMENT", "COMPLETED", "PAID", "SETTLED"}
    is_confirmed = status in confirmed_statuses
    is_under_review = status in {"PAYMENT_REVIEW_REQUIRED", "PAYMENT_PENDING_VERIFICATION", "REVIEW_REQUIRED"} or submitted

    # Provider & UPI details
    upi_id = getattr(settings, "GOOGLE_PAY_UPI_ID", "mrsufiyansurve@okaxis")
    merchant_name = getattr(settings, "GOOGLE_PAY_MERCHANT_NAME", "Sufiyan Surve / Agency OS")
    gpay_uri = f"upi://pay?pa={upi_id}&pn={merchant_name.replace(' ', '%20')}&am={advance_amount:.2f}&cu={currency}&tr={ref_id}&tn=Invoice%20{ref_id}"

    # Status badge HTML
    if is_confirmed:
        badge_class = "badge-success"
        badge_text = "PAYMENT CONFIRMED — PRODUCTION AUTHORIZED"
        status_desc = "Advance payment has been verified and settled. Production build pipeline is currently active."
    elif is_under_review:
        badge_class = "badge-warning"
        badge_text = "PAYMENT REVIEW REQUIRED — UNDER RECONCILIATION"
        status_desc = "Your transaction reference has been registered and is undergoing operator bank ledger reconciliation. Production build unlocks upon verified confirmation."
    else:
        badge_class = "badge-pending"
        badge_text = "PAYMENT PENDING — 40% ADVANCE DUE"
        status_desc = "Please transfer the 40% milestone advance via Google Pay UPI or Bank Remittance to initiate production."

    # Submission form or confirmation block
    if is_confirmed:
        verified_date = payment.verified_at.strftime("%Y-%m-%d %H:%M UTC") if hasattr(payment, "verified_at") and payment.verified_at else "Verified"
        verified_by = html.escape(payment.verified_by or "Finance Desk")
        action_card = f"""
        <div class="receipt-box">
            <div class="check-icon">✓</div>
            <h3 style="color:#10b981; font-size:1.1rem; margin-bottom:6px;">Advance Payment Confirmed</h3>
            <p style="color:#94a3b8; font-size:0.85rem; margin-bottom:14px;">
                Verified on <strong>{verified_date}</strong> by <strong>{verified_by}</strong>.<br>
                Remittance Reference: <span class="mono">{ref_id}</span>
            </p>
            <div class="pill-info">
                Production build authorized. The delivery engine is currently executing milestones.
            </div>
        </div>
        """
    else:
        action_card = f"""
        <div class="card" style="margin-top:24px;">
            <h3 style="color:#ffffff; font-size:1.05rem; margin-bottom:6px;">Submit Bank Transaction Reference</h3>
            <p style="color:#94a3b8; font-size:0.82rem; margin-bottom:16px;">
                Once you have transferred the funds via Google Pay UPI or direct bank wire, enter your Bank UTR / Transaction Reference Number below to notify the finance operations desk.
            </p>
            <form action="/pay/{ref_id}/submit-reference" method="POST" id="ref-form">
                <input type="hidden" name="payment_id" value="{payment.id}">
                <div class="form-group">
                    <label>Bank UTR / Transaction Reference Number <span style="color:#ef4444;">*</span></label>
                    <input type="text" name="payment_reference" id="payment_reference" required
                           placeholder="e.g. 429381928491, HDFC_UTR_12345, or SWIFT Ref"
                           value="{html.escape(payment.gpay_reference or '')}"
                           class="input-field" />
                </div>
                <div class="form-group">
                    <label>Transfer Remarks / Bank Name (Optional)</label>
                    <input type="text" name="notes" id="notes"
                           placeholder="e.g. Sent via Google Pay / ICICI Wire"
                           class="input-field" />
                </div>
                <button type="submit" class="btn-submit" id="submit-btn">
                    Submit Reference for Bank Verification
                </button>
            </form>
            <p style="color:#64748b; font-size:0.75rem; margin-top:12px; line-height:1.4;">
                <strong>Anti-Fraud Guarantee:</strong> Submitting a reference notifies the operator to verify settlement against live bank ledgers. Production build unlocks strictly upon human operator verification.
            </p>
        </div>
        """

    # Gateway card
    if provider_configured:
        gateway_html = f"""
        <div class="method-card">
            <div class="method-header">
                <div>
                    <span class="method-title">Credit / Debit Card (Automated Gateway)</span>
                    <p class="method-desc">Instant card payment with automated receipt.</p>
                </div>
                <span class="badge-active">ACTIVE</span>
            </div>
            <a href="/api/payments/{payment.id}/checkout" class="btn-gateway">Pay via Card Gateway</a>
        </div>
        """
    else:
        gateway_html = f"""
        <div class="method-card method-disabled">
            <div class="method-header">
                <div>
                    <span class="method-title">Card Gateway (Stripe / Razorpay)</span>
                    <p class="method-desc">Direct card checkout gateway.</p>
                </div>
                <span class="badge-unconfigured">PAYMENT_PROVIDER_CONFIGURATION_REQUIRED</span>
            </div>
            <p style="color:#94a3b8; font-size:0.8rem; margin-top:8px;">
                Card processor is in standby mode. Please use Direct Google Pay UPI or Bank Remittance below for immediate processing.
            </p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Commercial Payment &amp; Remittance — {biz_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #09090b;
            color: #f4f4f5;
            font-family: 'Inter', -apple-system, sans-serif;
            line-height: 1.5;
            padding: 32px 16px;
        }}
        .container {{
            max-width: 820px;
            margin: 0 auto;
            background: #121214;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 16px 48px rgba(0,0,0,0.7);
        }}
        .header {{
            padding: 28px 32px;
            background: linear-gradient(180deg, rgba(56,189,248,0.08) 0%, rgba(18,18,20,0) 100%);
            border-bottom: 1px solid rgba(255,255,255,0.08);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .section {{
            padding: 24px 32px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .section-title {{
            font-size: 0.95rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94a3b8;
            margin-bottom: 14px;
        }}
        .mono {{
            font-family: 'JetBrains Mono', monospace;
            color: #38bdf8;
        }}
        .pill {{
            background: rgba(56,189,248,0.12);
            color: #38bdf8;
            border: 1px solid rgba(56,189,248,0.3);
            border-radius: 20px;
            padding: 4px 12px;
            font-size: 0.72rem;
            font-weight: 600;
            display: inline-block;
        }}
        .badge-pending {{
            background: rgba(56,189,248,0.15);
            color: #38bdf8;
            border: 1px solid rgba(56,189,248,0.4);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-warning {{
            background: rgba(245,158,11,0.15);
            color: #f59e0b;
            border: 1px solid rgba(245,158,11,0.4);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-success {{
            background: rgba(16,185,129,0.15);
            color: #10b981;
            border: 1px solid rgba(16,185,129,0.4);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-unconfigured {{
            background: rgba(239,68,68,0.12);
            color: #f87171;
            border: 1px solid rgba(239,68,68,0.3);
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}
        .pricing-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-top: 14px;
        }}
        .pricing-card {{
            background: #09090b;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 16px;
        }}
        .pricing-card.highlight {{
            border-color: rgba(56,189,248,0.4);
            background: linear-gradient(180deg, rgba(56,189,248,0.06) 0%, rgba(9,9,11,1) 100%);
        }}
        .card {{
            background: #09090b;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 20px;
        }}
        .method-card {{
            background: #09090b;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 14px;
        }}
        .method-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .method-title {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #ffffff;
        }}
        .method-desc {{
            font-size: 0.8rem;
            color: #94a3b8;
            margin-top: 2px;
        }}
        .detail-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,20,0.04);
            font-size: 0.85rem;
        }}
        .detail-label {{ color: #71717a; }}
        .detail-val {{ font-weight: 600; color: #f4f4f5; }}
        .form-group {{
            margin-bottom: 14px;
        }}
        .form-group label {{
            display: block;
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 6px;
            font-weight: 500;
        }}
        .input-field {{
            width: 100%;
            background: #18181b;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            padding: 10px 14px;
            color: #f4f4f5;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.15s;
        }}
        .input-field:focus {{
            border-color: #38bdf8;
        }}
        .btn-submit {{
            background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
            color: #ffffff;
            border: none;
            padding: 12px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            width: 100%;
            transition: opacity 0.15s;
        }}
        .btn-submit:hover {{ opacity: 0.92; }}
        .btn-upi {{
            background: #10b981;
            color: #ffffff;
            text-decoration: none;
            display: inline-block;
            padding: 10px 18px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 10px;
        }}
        .receipt-box {{
            background: rgba(16,185,129,0.08);
            border: 1px solid rgba(16,185,129,0.3);
            border-radius: 10px;
            padding: 24px;
            text-align: center;
        }}
        .check-icon {{
            font-size: 2rem;
            color: #10b981;
            margin-bottom: 8px;
        }}
        .pill-info {{
            display: inline-block;
            background: rgba(16,185,129,0.15);
            color: #34d399;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 600;
        }}
        .alert {{
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.82rem;
            margin-bottom: 16px;
        }}
        .alert-info {{
            background: rgba(56,189,248,0.1);
            border: 1px solid rgba(56,189,248,0.25);
            color: #38bdf8;
        }}
        .alert-warn {{
            background: rgba(245,158,11,0.1);
            border: 1px solid rgba(245,158,11,0.25);
            color: #f59e0b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div>
                <span class="pill">SECURE PAYMENT PORTAL</span>
                <h1 style="font-size:1.45rem; font-weight:700; color:#ffffff; margin-top:8px;">{biz_name}</h1>
                <p style="color:#94a3b8; font-size:0.82rem;">{prop_title} {f"· {domain}" if domain else ""}</p>
            </div>
            <div style="text-align:right;">
                <div style="font-size:0.72rem; color:#71717a;">Payment Reference</div>
                <div style="font-size:1.05rem; font-weight:700; color:#38bdf8;" class="mono">{ref_id}</div>
                <div style="margin-top:6px;"><span class="{badge_class}">{badge_text}</span></div>
            </div>
        </div>

        <!-- Status Summary -->
        <div class="section">
            <div class="alert {'alert-warn' if is_under_review else ('alert-info' if not is_confirmed else '')}" style="margin-bottom:0;">
                <strong>Status:</strong> {status_desc}
            </div>
        </div>

        <!-- Transparent Milestone Pricing -->
        <div class="section">
            <div class="section-title">Transparent Milestone Pricing</div>
            <div class="pricing-grid">
                <div class="pricing-card">
                    <div style="font-size:0.72rem; color:#71717a; text-transform:uppercase;">Total Fixed Turnkey</div>
                    <div style="font-size:1.4rem; font-weight:700; color:#ffffff; margin-top:4px;">${total_value:,.2f} USD</div>
                    <div style="font-size:0.7rem; color:#71717a; margin-top:2px;">Contract Value (Min $500 Floor)</div>
                </div>
                <div class="pricing-card highlight">
                    <div style="font-size:0.72rem; color:#38bdf8; text-transform:uppercase; font-weight:700;">40% Milestone Advance</div>
                    <div style="font-size:1.4rem; font-weight:700; color:#38bdf8; margin-top:4px;">${advance_amount:,.2f} USD</div>
                    <div style="font-size:0.7rem; color:#38bdf8; margin-top:2px;">Required to Unlock Production</div>
                </div>
                <div class="pricing-card">
                    <div style="font-size:0.72rem; color:#71717a; text-transform:uppercase;">60% Handover Balance</div>
                    <div style="font-size:1.4rem; font-weight:700; color:#f4f4f5; margin-top:4px;">${balance_amount:,.2f} USD</div>
                    <div style="font-size:0.7rem; color:#71717a; margin-top:2px;">Due strictly upon verified handover</div>
                </div>
            </div>
        </div>

        <!-- Payment Methods -->
        <div class="section">
            <div class="section-title">Authorized Payment Rails</div>

            <!-- Primary: Google Pay / UPI Manual Remittance -->
            <div class="method-card">
                <div class="method-header">
                    <div>
                        <span class="method-title">Google Pay / Direct UPI Remittance</span>
                        <p class="method-desc">Primary settlement method for instant zero-fee wire &amp; UPI transfers.</p>
                    </div>
                    <span class="badge-pending" style="background:rgba(16,185,129,0.15); color:#10b981; border-color:rgba(16,185,129,0.3);">RECOMMENDED</span>
                </div>

                <div style="margin-top:14px; background:#121214; border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:14px;">
                    <div class="detail-row">
                        <span class="detail-label">Beneficiary Name</span>
                        <span class="detail-val">{merchant_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Recipient UPI ID</span>
                        <span class="detail-val mono">{upi_id}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Required Advance Deposit</span>
                        <span class="detail-val" style="color:#38bdf8;">${advance_amount:,.2f} {currency}</span>
                    </div>
                    <div class="detail-row" style="border-bottom:none;">
                        <span class="detail-label">Remittance Reference Code</span>
                        <span class="detail-val mono" style="font-size:1rem; color:#38bdf8;">{ref_id}</span>
                    </div>
                </div>

                <div style="margin-top:12px; display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <a href="{gpay_uri}" class="btn-upi">Pay via Google Pay / UPI App</a>
                    <span style="font-size:0.75rem; color:#71717a;">Or transfer via your banking app to <strong>{upi_id}</strong></span>
                </div>

                <p style="color:#94a3b8; font-size:0.75rem; margin-top:12px; line-height:1.4;">
                    <strong>Currency &amp; FX Policy:</strong> All projects are quoted and contracted in USD. For Indian UPI / IMPS transfers, transfer at the day's standard interbank remittance rate. <strong>CRITICAL:</strong> Please include <span class="mono">{ref_id}</span> in the transfer remarks/description.
                </p>
            </div>

            <!-- Secondary: Card Gateway -->
            {gateway_html}

            <!-- Reference Submission Form or Receipt -->
            {action_card}
        </div>
    </div>

    <script>
    const form = document.getElementById('ref-form');
    if (form) {{
        form.addEventListener('submit', async function(e) {{
            const btn = document.getElementById('submit-btn');
            const refInput = document.getElementById('payment_reference');
            if (!refInput.value.trim() || refInput.value.trim().length < 3) {{
                e.preventDefault();
                alert('Please enter a valid bank UTR / transaction reference number (min 3 characters).');
                return;
            }}
            btn.disabled = true;
            btn.textContent = 'Submitting Reference for Verification...';
        }});
    }}
    </script>
</body>
</html>
"""
