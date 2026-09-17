import json
import urllib.request
import urllib.error

webhooks = {
    "lead_qualification": ("http://127.0.0.1:5678/webhook/BTrAHa8BuhMWQxdt/webhook%2520trigger/qualify-lead", {
        "domain": "apex-roofing.com", "estimated_budget_usd": 1500, "team_size": 10, "overall_health_score": 45
    }),
    "lead_enrichment": ("http://127.0.0.1:5678/webhook/hJPTu6SVw195kWzc/webhook%2520trigger/audit-domain", {
        "domain": "salisroofing.com"
    }),
    "personalized_outreach": ("http://127.0.0.1:5678/webhook/RgsGJaGrftR2QI4B/draft%2520request%2520webhook/draft-outreach", {
        "business_name": "Salis Roofing",
        "domain": "salisroofing.com",
        "contact_email": "owner@salisroofing.com",
        "opportunity_score": 85.0,
        "audit_findings": ["Mobile layout issues", "Slow LCP 4.2s"]
    }),
    "reply_classification": ("http://127.0.0.1:5678/webhook/1dVS7MFux59zupN8/inbound%2520reply%2520webhook/classify-reply", {
        "message_body": "Sounds interesting, can you send over a proposal or pricing?",
        "sender_email": "owner@salisroofing.com",
        "business_id": 101
    }),
    "sales_followup": ("http://127.0.0.1:5678/webhook/KPH0ZHVCaQaMcz2C/followup%2520evaluation%2520webhook/evaluate-followup", {
        "business_id": 101,
        "recipient_email": "owner@salisroofing.com",
        "days_since_contact": 3,
        "outreach_type": "initial"
    }),
    "customer_onboarding": ("http://127.0.0.1:5678/webhook/6lTJpl0R8OP6fa3e/webhook%2520trigger/client-onboard-init", {
        "business_name": "Salis Roofing",
        "payment_reference": "UTR-123456"
    }),
    "crm_automation": ("http://127.0.0.1:5678/webhook/4l8w2ytXu9QjDDZT/webhook%2520trigger/crm-sync-event", {
        "lead_id": 101,
        "stage": "QUALIFIED",
        "action": "stage_update"
    }),
    "ai_support": ("http://127.0.0.1:5678/webhook/PCpGI3XFeeovlLes/webhook%2520trigger/support-inbound-ticket", {
        "ticket_id": "TCK-001",
        "message": "Help with DNS settings"
    }),
    "appointment_automation": ("http://127.0.0.1:5678/webhook/do0IjHl1Y0Yn0pRl/webhook%2520trigger/missed-call-intake", {
        "caller_phone": "+1-469-677-0239",
        "caller_name": "Salis"
    }),
}

results = {}
for name, (url, payload) in webhooks.items():
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")[:120]
            print(f"[OK 200] {name:22} -> {body}")
            results[name] = 200
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8")[:120]
        print(f"[HTTP {err.code}] {name:22} -> {err_body}")
        results[name] = err.code
    except Exception as e:
        print(f"[ERR]     {name:22} -> {e}")
        results[name] = str(e)

print("\nSUMMARY:", results)
