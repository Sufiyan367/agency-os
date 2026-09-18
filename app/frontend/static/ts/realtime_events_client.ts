/**
 * Agency OS — Realtime Events Client & Type Definitions (TypeScript)
 * Implements the Interservice Event Envelope contract with WebSocket and SSE fallback.
 */

export enum CanonicalAgentEventType {
    RUN_STARTED = "RUN_STARTED",
    MARKET_SELECTED = "MARKET_SELECTED",
    MARKET_REBALANCED = "MARKET_REBALANCED",
    DISCOVERY_STARTED = "DISCOVERY_STARTED",
    PROSPECT_FOUND = "PROSPECT_FOUND",
    VERIFICATION_STARTED = "VERIFICATION_STARTED",
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED",
    AUDIT_STARTED = "AUDIT_STARTED",
    AUDIT_COMPLETED = "AUDIT_COMPLETED",
    SCORING_STARTED = "SCORING_STARTED",
    SCORING_COMPLETED = "SCORING_COMPLETED",
    COMMERCIAL_QUALIFICATION = "COMMERCIAL_QUALIFICATION",
    OPPORTUNITY_IDENTIFIED = "OPPORTUNITY_IDENTIFIED",
    OFFER_SELECTED = "OFFER_SELECTED",
    OUTREACH_DRAFTED = "OUTREACH_DRAFTED",
    OUTREACH_DISPATCHED = "OUTREACH_DISPATCHED",
    REPLY_CLASSIFIED = "REPLY_CLASSIFIED",
    DEMO_STARTED = "DEMO_STARTED",
    DEMO_READY = "DEMO_READY",
    PROPOSAL_CREATED = "PROPOSAL_CREATED",
    PAYMENT_REVIEW_REQUIRED = "PAYMENT_REVIEW_REQUIRED",
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED",
    PRODUCTION_AUTHORIZED = "PRODUCTION_AUTHORIZED",
    BUILD_STARTED = "BUILD_STARTED",
    BUILD_COMPLETED = "BUILD_COMPLETED",
    QA_STARTED = "QA_STARTED",
    QA_PASSED = "QA_PASSED",
    DEPLOYMENT_STARTED = "DEPLOYMENT_STARTED",
    DEPLOYED = "DEPLOYED",
    DELIVERY_COMPLETE = "DELIVERY_COMPLETE",
    EXPANSION_OPPORTUNITY = "EXPANSION_OPPORTUNITY",
    SAFEGUARD_TRIGGERED = "SAFEGUARD_TRIGGERED",
    ERROR = "ERROR",
    CEO_ALERT = "CEO_ALERT"
}

export interface AgencyEventPayload {
    message?: string;
    status?: string;
    domain?: string;
    metadata?: Record<string, any>;
    sequence_number?: number;
    error?: string | null;
    completed_at?: string | null;
}

export interface AgencyEventEnvelope<T = AgencyEventPayload> {
    event_id: string;
    event_type: CanonicalAgentEventType | string;
    timestamp: string;
    source: string;
    entity_id: string;
    correlation_id: string;
    payload_version: string;
    payload: T;
    // Legacy fields preserved for backward compatibility
    id?: number;
    run_id?: string;
    business_id?: number | null;
    domain?: string | null;
    message?: string;
    status?: string;
    metadata_json?: Record<string, any>;
}

export type EventHandler<T = AgencyEventPayload> = (event: AgencyEventEnvelope<T>) => void;

export class RealtimeEventsClient {
    private ws: WebSocket | null = null;
    private sse: EventSource | null = null;
    private handlers: Map<string, Set<EventHandler>> = new Map();
    private wildcardHandlers: Set<EventHandler> = new Set();
    private seenEventIds: Set<string> = new Set();
    private isConnected: boolean = false;
    private reconnectTimer: any = null;

    constructor(
        private baseUrl: string = window.location.host,
        private useSsl: boolean = window.location.protocol === 'https:'
    ) {}

    public on(eventType: CanonicalAgentEventType | string, handler: EventHandler): () => void {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, new Set());
        }
        this.handlers.get(eventType)!.add(handler);
        return () => this.handlers.get(eventType)?.delete(handler);
    }

    public onAny(handler: EventHandler): () => void {
        this.wildcardHandlers.add(handler);
        return () => this.wildcardHandlers.delete(handler);
    }

    public connect(): void {
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
                    if (data.type === 'pong') return;
                    this.dispatch(data);
                } catch (_) {}
            };

            this.ws.onclose = () => {
                this.isConnected = false;
                this.startSseFallback();
                this.scheduleReconnect();
            };

            this.ws.onerror = () => {
                if (this.ws) this.ws.close();
            };
        } catch (_) {
            this.startSseFallback();
            this.scheduleReconnect();
        }
    }

    private startSseFallback(): void {
        if (this.sse) return;
        try {
            this.sse = new EventSource('/api/agent/events/sse');
            this.sse.onmessage = (ev) => {
                try {
                    if (!ev.data || ev.data.startsWith(':')) return;
                    const data = JSON.parse(ev.data);
                    this.dispatch(data);
                } catch (_) {}
            };
            this.sse.onerror = () => {
                this.stopSseFallback();
            };
        } catch (_) {}
    }

    private stopSseFallback(): void {
        if (this.sse) {
            this.sse.close();
            this.sse = null;
        }
    }

    private scheduleReconnect(): void {
        if (this.reconnectTimer) return;
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, 8000);
    }

    private dispatch(rawEvent: any): void {
        const eventId = rawEvent.event_id || (rawEvent.id ? `evt_${rawEvent.id}_${rawEvent.sequence_number || 0}` : null);
        if (eventId) {
            if (this.seenEventIds.has(eventId)) return;
            this.seenEventIds.add(eventId);
            if (this.seenEventIds.size > 500) {
                const first = this.seenEventIds.values().next().value;
                if (first) this.seenEventIds.delete(first);
            }
        }

        const envelope: AgencyEventEnvelope = {
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
                try { h(envelope); } catch (e) { console.error(e); }
            });
        }

        this.wildcardHandlers.forEach(h => {
            try { h(envelope); } catch (e) { console.error(e); }
        });
    }

    public disconnect(): void {
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
