/**
 * Agency OS — Realtime Events Client & Type Definitions (TypeScript)
 * Implements the Interservice Event Envelope contract with WebSocket and SSE fallback.
 */
export var CanonicalAgentEventType;
(function (CanonicalAgentEventType) {
    CanonicalAgentEventType["RUN_STARTED"] = "RUN_STARTED";
    CanonicalAgentEventType["MARKET_SELECTED"] = "MARKET_SELECTED";
    CanonicalAgentEventType["MARKET_REBALANCED"] = "MARKET_REBALANCED";
    CanonicalAgentEventType["DISCOVERY_STARTED"] = "DISCOVERY_STARTED";
    CanonicalAgentEventType["PROSPECT_FOUND"] = "PROSPECT_FOUND";
    CanonicalAgentEventType["VERIFICATION_STARTED"] = "VERIFICATION_STARTED";
    CanonicalAgentEventType["VERIFICATION_COMPLETED"] = "VERIFICATION_COMPLETED";
    CanonicalAgentEventType["AUDIT_STARTED"] = "AUDIT_STARTED";
    CanonicalAgentEventType["AUDIT_COMPLETED"] = "AUDIT_COMPLETED";
    CanonicalAgentEventType["SCORING_STARTED"] = "SCORING_STARTED";
    CanonicalAgentEventType["SCORING_COMPLETED"] = "SCORING_COMPLETED";
    CanonicalAgentEventType["COMMERCIAL_QUALIFICATION"] = "COMMERCIAL_QUALIFICATION";
    CanonicalAgentEventType["OPPORTUNITY_IDENTIFIED"] = "OPPORTUNITY_IDENTIFIED";
    CanonicalAgentEventType["OFFER_SELECTED"] = "OFFER_SELECTED";
    CanonicalAgentEventType["OUTREACH_DRAFTED"] = "OUTREACH_DRAFTED";
    CanonicalAgentEventType["OUTREACH_DISPATCHED"] = "OUTREACH_DISPATCHED";
    CanonicalAgentEventType["REPLY_CLASSIFIED"] = "REPLY_CLASSIFIED";
    CanonicalAgentEventType["DEMO_STARTED"] = "DEMO_STARTED";
    CanonicalAgentEventType["DEMO_READY"] = "DEMO_READY";
    CanonicalAgentEventType["PROPOSAL_CREATED"] = "PROPOSAL_CREATED";
    CanonicalAgentEventType["PAYMENT_REVIEW_REQUIRED"] = "PAYMENT_REVIEW_REQUIRED";
    CanonicalAgentEventType["PAYMENT_CONFIRMED"] = "PAYMENT_CONFIRMED";
    CanonicalAgentEventType["PRODUCTION_AUTHORIZED"] = "PRODUCTION_AUTHORIZED";
    CanonicalAgentEventType["BUILD_STARTED"] = "BUILD_STARTED";
    CanonicalAgentEventType["BUILD_COMPLETED"] = "BUILD_COMPLETED";
    CanonicalAgentEventType["QA_STARTED"] = "QA_STARTED";
    CanonicalAgentEventType["QA_PASSED"] = "QA_PASSED";
    CanonicalAgentEventType["DEPLOYMENT_STARTED"] = "DEPLOYMENT_STARTED";
    CanonicalAgentEventType["DEPLOYED"] = "DEPLOYED";
    CanonicalAgentEventType["DELIVERY_COMPLETE"] = "DELIVERY_COMPLETE";
    CanonicalAgentEventType["EXPANSION_OPPORTUNITY"] = "EXPANSION_OPPORTUNITY";
    CanonicalAgentEventType["SAFEGUARD_TRIGGERED"] = "SAFEGUARD_TRIGGERED";
    CanonicalAgentEventType["ERROR"] = "ERROR";
    CanonicalAgentEventType["CEO_ALERT"] = "CEO_ALERT";
})(CanonicalAgentEventType || (CanonicalAgentEventType = {}));
export class RealtimeEventsClient {
    constructor(baseUrl = window.location.host, useSsl = window.location.protocol === 'https:') {
        this.baseUrl = baseUrl;
        this.useSsl = useSsl;
        this.ws = null;
        this.sse = null;
        this.handlers = new Map();
        this.wildcardHandlers = new Set();
        this.seenEventIds = new Set();
        this.isConnected = false;
        this.reconnectTimer = null;
    }
    on(eventType, handler) {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, new Set());
        }
        this.handlers.get(eventType).add(handler);
        return () => this.handlers.get(eventType)?.delete(handler);
    }
    onAny(handler) {
        this.wildcardHandlers.add(handler);
        return () => this.wildcardHandlers.delete(handler);
    }
    connect() {
        const protocol = this.useSsl ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${this.baseUrl}/ws/agent-activity`;
        try {
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => {
                this.isConnected = true;
                this.stopSseFallback();
            };
            this.ws.onmessage = (ev) => {
                try {
                    const data = JSON.parse(ev.data);
                    if (data.type === 'pong')
                        return;
                    this.dispatch(data);
                }
                catch (_) { }
            };
            this.ws.onclose = () => {
                this.isConnected = false;
                this.startSseFallback();
                this.scheduleReconnect();
            };
            this.ws.onerror = () => {
                if (this.ws)
                    this.ws.close();
            };
        }
        catch (_) {
            this.startSseFallback();
            this.scheduleReconnect();
        }
    }
    startSseFallback() {
        if (this.sse)
            return;
        try {
            this.sse = new EventSource('/api/agent/events/sse');
            this.sse.onmessage = (ev) => {
                try {
                    if (!ev.data || ev.data.startsWith(':'))
                        return;
                    const data = JSON.parse(ev.data);
                    this.dispatch(data);
                }
                catch (_) { }
            };
            this.sse.onerror = () => {
                this.stopSseFallback();
            };
        }
        catch (_) { }
    }
    stopSseFallback() {
        if (this.sse) {
            this.sse.close();
            this.sse = null;
        }
    }
    scheduleReconnect() {
        if (this.reconnectTimer)
            return;
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, 8000);
    }
    dispatch(rawEvent) {
        const eventId = rawEvent.event_id || (rawEvent.id ? `evt_${rawEvent.id}_${rawEvent.sequence_number || 0}` : null);
        if (eventId) {
            if (this.seenEventIds.has(eventId))
                return;
            this.seenEventIds.add(eventId);
            if (this.seenEventIds.size > 500) {
                const first = this.seenEventIds.values().next().value;
                if (first)
                    this.seenEventIds.delete(first);
            }
        }
        const envelope = {
            event_id: eventId || 'evt_unknown',
            event_type: rawEvent.event_type || 'UNKNOWN',
            timestamp: rawEvent.timestamp || rawEvent.created_at || new Date().toISOString(),
            source: rawEvent.source || 'agency_os.core',
            entity_id: rawEvent.entity_id || String(rawEvent.business_id || rawEvent.domain || 'system'),
            correlation_id: rawEvent.correlation_id || rawEvent.run_id || '',
            payload_version: rawEvent.payload_version || '1.0',
            payload: rawEvent.payload || {
                message: rawEvent.message,
                status: rawEvent.status,
                domain: rawEvent.domain,
                metadata: rawEvent.metadata_json,
                sequence_number: rawEvent.sequence_number,
                error: rawEvent.error
            },
            ...rawEvent
        };
        const typeHandlers = this.handlers.get(envelope.event_type);
        if (typeHandlers) {
            typeHandlers.forEach(h => {
                try {
                    h(envelope);
                }
                catch (e) {
                    console.error(e);
                }
            });
        }
        this.wildcardHandlers.forEach(h => {
            try {
                h(envelope);
            }
            catch (e) {
                console.error(e);
            }
        });
    }
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.stopSseFallback();
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
}
