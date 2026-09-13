/**
 * Agency OS: Autonomous Demo & Build Pipeline HUD
 * Language: TypeScript
 * Description: Type-safe interface, state management, and real-time dashboard
 *              monitoring for customer demo builds, 20-gate QA telemetry, and sandboxes.
 */

export interface CustomerProjectSummary {
    id: number;
    project_id: str;
    business_id: number;
    business_name: string;
    domain: string;
    customer_slug: string;
    title: string;
    industry: string;
    status: 'REQUESTED' | 'SPEC_READY' | 'DESIGNING' | 'AI_PROTOTYPING' | 'BUILDING' | 'QA' | 'REPAIRING' | 'DEPLOYING' | 'READY' | 'FAILED' | 'BLOCKED';
    current_stage: string;
    demo_url?: string | null;
    demo_id?: string | null;
    qa_score?: number | null;
    qa_status?: 'PASS' | 'WARN' | 'FAIL' | 'BLOCKED' | null;
    created_at: string;
    updated_at: string;
}

export interface QAGateDetail {
    passed: boolean;
    details: string;
    critical: boolean;
}

export interface ProjectDetailResponse {
    project_id: string;
    business_id: number;
    business_name: string;
    customer_slug: string;
    industry: string;
    status: string;
    current_stage: string;
    demo_url?: string | null;
    specification?: {
        version: number;
        checksum: string;
        facts: Array<{ category: string; description: string }>;
        customer_requests: Array<{ request_text: string; priority: string }>;
        ai_inferences: Array<{ inferred_need: string; recommended_solution: string }>;
        required_screens: Array<{ title: string; route: string }>;
    } | null;
    latest_build?: {
        build_number: number;
        status: string;
        duration_ms: number;
        routes: string[];
        artifacts: string[];
    } | null;
    qa_run?: {
        score: number;
        status: string;
        gate_results: Record<string, QAGateDetail>;
        critical_violations: string[];
        non_critical_warnings: string[];
    } | null;
    events: Array<{
        event_type: string;
        stage: string;
        details: Record<string, any>;
        created_at: string;
    }>;
}

export class ProjectPipelineHUD {
    private containerId: string;
    private pollIntervalMs: number;
    private timerId?: number;

    constructor(containerId: string = 'project-pipeline-hud-root', pollIntervalMs: number = 8000) {
        this.containerId = containerId;
        this.pollIntervalMs = pollIntervalMs;
    }

    public async init(): Promise<void> {
        await this.refresh();
        this.startPolling();
    }

    public startPolling(): void {
        if (this.timerId) window.clearInterval(this.timerId);
        this.timerId = window.setInterval(() => this.refresh(), this.pollIntervalMs);
    }

    public stopPolling(): void {
        if (this.timerId) {
            window.clearInterval(this.timerId);
            this.timerId = undefined;
        }
    }

    public async refresh(): Promise<void> {
        const root = document.getElementById(this.containerId);
        if (!root) return;

        try {
            const resp = await fetch('/api/projects');
            if (!resp.ok) {
                console.warn('[ProjectPipelineHUD] Failed to fetch project records:', resp.statusText);
                return;
            }
            const projects: CustomerProjectSummary[] = await resp.json();
            this.render(root, projects);
        } catch (err) {
            console.error('[ProjectPipelineHUD] Network error fetching projects:', err);
        }
    }

    public render(root: HTMLElement, projects: CustomerProjectSummary[]): void {
        if (!projects || projects.length === 0) {
            root.innerHTML = `
                <div class="p-6 bg-slate-900 border border-slate-800 rounded-xl text-center">
                    <p class="text-sm text-slate-400">No automated demo projects currently running.</p>
                    <p class="text-xs text-slate-500 mt-1">Qualified prospect demo requests automatically populate this engineering pipeline.</p>
                </div>
            `;
            return;
        }

        let rowsHtml = '';
        for (const p of projects) {
            const statusBadge = this.getStatusBadge(p.status);
            const qaBadge = p.qa_score !== null && p.qa_score !== undefined
                ? `<span class="px-2 py-0.5 rounded text-xs font-semibold ${p.qa_status === 'PASS' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'}">${p.qa_score}% (${p.qa_status})</span>`
                : `<span class="text-xs text-slate-500">Pending</span>`;

            const demoLink = p.demo_url
                ? `<a href="${p.demo_url}" target="_blank" class="text-xs font-medium text-blue-400 hover:text-blue-300 underline flex items-center gap-1">Open Sandbox ↗</a>`
                : `<span class="text-xs text-slate-500">In Progress</span>`;

            rowsHtml += `
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition">
                    <td class="px-4 py-3 text-xs font-mono text-slate-300">${p.project_id}</td>
                    <td class="px-4 py-3">
                        <div class="text-sm font-semibold text-white">${this.escapeHtml(p.business_name)}</div>
                        <div class="text-xs text-slate-400">${this.escapeHtml(p.domain)} • ${this.escapeHtml(p.industry)}</div>
                    </td>
                    <td class="px-4 py-3">${statusBadge}</td>
                    <td class="px-4 py-3 text-xs text-slate-300 font-mono">${p.current_stage}</td>
                    <td class="px-4 py-3">${qaBadge}</td>
                    <td class="px-4 py-3">${demoLink}</td>
                </tr>
            `;
        }

        root.innerHTML = `
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
                <div class="p-4 border-b border-slate-800 flex items-center justify-between">
                    <div>
                        <h3 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                            <span class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                            Automated Customer Demo & Build Pipeline
                        </h3>
                        <p class="text-xs text-slate-400">Multi-stage autonomous engineering: Spec → Stitch → AI Studio → Build → 20-Gate QA → Sandbox</p>
                    </div>
                    <button onclick="window.pipelineHUD && window.pipelineHUD.refresh()" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs text-slate-200 transition">
                        Refresh
                    </button>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-950 text-slate-400 text-xs uppercase tracking-wider border-b border-slate-800">
                                <th class="px-4 py-2.5">Project ID</th>
                                <th class="px-4 py-2.5">Prospect</th>
                                <th class="px-4 py-2.5">Status</th>
                                <th class="px-4 py-2.5">Stage</th>
                                <th class="px-4 py-2.5">20-Gate QA</th>
                                <th class="px-4 py-2.5">Live Sandbox</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rowsHtml}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    private getStatusBadge(status: string): string {
        switch (status) {
            case 'READY':
                return '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">READY</span>';
            case 'BUILDING':
            case 'DESIGNING':
            case 'AI_PROTOTYPING':
            case 'DEPLOYING':
                return '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-blue-950 text-blue-300 border border-blue-800 animate-pulse">' + status + '</span>';
            case 'QA':
            case 'REPAIRING':
                return '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-800">' + status + '</span>';
            case 'FAILED':
            case 'BLOCKED':
                return '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-800">' + status + '</span>';
            default:
                return '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-300">' + status + '</span>';
        }
    }

    private escapeHtml(str: string): string {
        return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}

// Global browser instance
declare global {
    interface Window {
        pipelineHUD?: ProjectPipelineHUD;
    }
}

if (typeof window !== 'undefined') {
    window.pipelineHUD = new ProjectPipelineHUD();
    document.addEventListener('DOMContentLoaded', () => {
        const el = document.getElementById('project-pipeline-hud-root');
        if (el && window.pipelineHUD) {
            window.pipelineHUD.init();
        }
    });
}
