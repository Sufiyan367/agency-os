-- ==============================================================================
-- PostgreSQL Migration: Local-First AI Lead Recovery & Outreach
-- ==============================================================================

-- 1. Businesses
CREATE TABLE IF NOT EXISTS local_businesses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL UNIQUE,
    website_url VARCHAR(500) DEFAULT '',
    niche VARCHAR(100) NOT NULL,
    city VARCHAR(100),
    state VARCHAR(50) DEFAULT 'TX',
    country VARCHAR(50) DEFAULT 'US',
    email VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_businesses_name ON local_businesses(name);
CREATE INDEX IF NOT EXISTS idx_businesses_niche ON local_businesses(niche);
CREATE INDEX IF NOT EXISTS idx_businesses_email ON local_businesses(email);

-- 2. Leads
CREATE TABLE IF NOT EXISTS local_leads (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES local_businesses(id) ON DELETE CASCADE,
    contact_name VARCHAR(200) DEFAULT 'Business Owner',
    contact_email VARCHAR(255) NOT NULL,
    contact_phone VARCHAR(50),
    status VARCHAR(50) DEFAULT 'NEW',
    qualification VARCHAR(20) DEFAULT 'WARM',
    lead_score DOUBLE PRECISION DEFAULT 0.0,
    intent_level VARCHAR(20) DEFAULT 'MEDIUM',
    confidence DOUBLE PRECISION DEFAULT 0.85,
    pain_points JSONB DEFAULT '[]'::jsonb,
    recommended_service VARCHAR(255) DEFAULT '',
    reasoning TEXT DEFAULT '',
    human_takeover BOOLEAN DEFAULT FALSE,
    human_takeover_reason VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_leads_business_id ON local_leads(business_id);
CREATE INDEX IF NOT EXISTS idx_leads_contact_email ON local_leads(contact_email);
CREATE INDEX IF NOT EXISTS idx_leads_status ON local_leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_qualification ON local_leads(qualification);
CREATE INDEX IF NOT EXISTS idx_leads_human_takeover ON local_leads(human_takeover);

-- 3. Audits
CREATE TABLE IF NOT EXISTS local_audits (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES local_businesses(id) ON DELETE CASCADE,
    url_audited VARCHAR(500) NOT NULL,
    overall_health_score DOUBLE PRECISION DEFAULT 50.0,
    performance_score DOUBLE PRECISION DEFAULT 50.0,
    seo_score DOUBLE PRECISION DEFAULT 50.0,
    accessibility_score DOUBLE PRECISION DEFAULT 50.0,
    security_score DOUBLE PRECISION DEFAULT 50.0,
    mobile_responsive BOOLEAN DEFAULT TRUE,
    findings JSONB DEFAULT '[]'::jsonb,
    summary TEXT DEFAULT '',
    audited_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_audits_business_id ON local_audits(business_id);

-- 4. Outreach Messages
CREATE TABLE IF NOT EXISTS local_outreach_messages (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES local_leads(id) ON DELETE CASCADE,
    channel VARCHAR(50) DEFAULT 'EMAIL',
    recipient VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING_APPROVAL',
    is_mocked BOOLEAN DEFAULT TRUE,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    sent_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_outreach_lead_id ON local_outreach_messages(lead_id);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON local_outreach_messages(status);

-- 5. Followup Schedule
CREATE TABLE IF NOT EXISTS local_followups (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES local_leads(id) ON DELETE CASCADE,
    step_number INTEGER DEFAULT 1,
    scheduled_for TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    sent_at TIMESTAMP WITHOUT TIME ZONE,
    cancel_reason VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_followups_lead_id ON local_followups(lead_id);
CREATE INDEX IF NOT EXISTS idx_followups_status ON local_followups(status);
CREATE INDEX IF NOT EXISTS idx_followups_scheduled ON local_followups(scheduled_for);

-- 6. Lead Events (Full Audit Log)
CREATE TABLE IF NOT EXISTS local_lead_events (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES local_leads(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_events_lead_id ON local_lead_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON local_lead_events(event_type);
