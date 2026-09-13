-- ==============================================================================
-- Agency OS: Production Deliverability & Outreach Funnel Audit Query
-- Dialect: ANSI SQL (Compatible with SQLite 3.35+ and PostgreSQL 12+)
-- Description: Computes rolling 30-day outreach metrics, daily send velocity,
--              delivery rates, reply classification conversion, and actor audit.
-- ==============================================================================

WITH daily_outreach_metrics AS (
    SELECT 
        DATE(created_at) AS send_date,
        COUNT(id) AS total_prepared,
        SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) AS total_approved,
        SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) AS total_sent,
        SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS total_failed,
        SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS total_rejected,
        SUM(CASE WHEN status = 'PENDING_APPROVAL' THEN 1 ELSE 0 END) AS total_pending,
        SUM(CASE WHEN actor_type = 'SYSTEM_AUTO_APPROVAL' THEN 1 ELSE 0 END) AS auto_approved_count,
        SUM(CASE WHEN actor_type = 'HUMAN' AND approved_at IS NOT NULL THEN 1 ELSE 0 END) AS human_approved_count
    FROM outreach_messages
    WHERE created_at >= DATETIME('now', '-30 days')
    GROUP BY DATE(created_at)
),
reply_conversion_metrics AS (
    SELECT 
        DATE(received_at) AS reply_date,
        COUNT(id) AS total_replies,
        SUM(CASE WHEN classification = 'POSITIVE' THEN 1 ELSE 0 END) AS positive_replies,
        SUM(CASE WHEN classification = 'QUESTION' THEN 1 ELSE 0 END) AS question_replies,
        SUM(CASE WHEN classification = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_replies,
        SUM(CASE WHEN classification = 'UNSUBSCRIBE' THEN 1 ELSE 0 END) AS opt_outs,
        SUM(CASE WHEN classification = 'NEEDS_HUMAN' THEN 1 ELSE 0 END) AS human_escalations
    FROM replies
    WHERE received_at >= DATETIME('now', '-30 days')
    GROUP BY DATE(received_at)
),
cumulative_audit AS (
    SELECT 
        d.send_date,
        d.total_prepared,
        d.total_approved,
        d.total_sent,
        d.total_failed,
        d.auto_approved_count,
        d.human_approved_count,
        COALESCE(r.total_replies, 0) AS total_replies,
        COALESCE(r.positive_replies, 0) AS positive_replies,
        COALESCE(r.opt_outs, 0) AS opt_outs,
        -- Window function: Running 7-day cumulative sent count
        SUM(d.total_sent) OVER (
            ORDER BY d.send_date 
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_sent_volume,
        -- Running total of all dispatched messages
        SUM(d.total_sent) OVER (
            ORDER BY d.send_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_sent_volume
    FROM daily_outreach_metrics d
    LEFT JOIN reply_conversion_metrics r ON d.send_date = r.reply_date
)
SELECT 
    send_date,
    total_prepared,
    total_approved,
    total_sent,
    total_failed,
    auto_approved_count,
    human_approved_count,
    total_replies,
    positive_replies,
    opt_outs,
    rolling_7d_sent_volume,
    cumulative_sent_volume,
    -- Analytical ratios with zero-division protection
    ROUND(
        CAST(total_sent AS FLOAT) / NULLIF(total_approved, 0) * 100.0, 
        2
    ) AS approval_to_send_pct,
    ROUND(
        CAST(total_replies AS FLOAT) / NULLIF(total_sent, 0) * 100.0, 
        2
    ) AS reply_rate_pct,
    ROUND(
        CAST(positive_replies AS FLOAT) / NULLIF(total_replies, 0) * 100.0, 
        2
    ) AS positive_conversion_pct
FROM cumulative_audit
ORDER BY send_date DESC;
