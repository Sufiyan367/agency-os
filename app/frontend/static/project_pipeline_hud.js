/**
 * Agency OS: Autonomous Demo & Build Pipeline HUD Controller
 * Language: JavaScript (ES2020)
 * Description: Client controller rendering live project build states,
 *              20-gate QA scores, and customer sandbox links.
 */

export class ProjectPipelineHUD {
    constructor(containerId = 'project-pipeline-hud-root', pollIntervalMs = 8000) {
        this.containerId = containerId;
        this.pollIntervalMs = pollIntervalMs;
        this.timerId = null;
    }

    async init() {
        await this.refresh();
        this.startPolling();
    }

    startPolling() {
        if (this.timerId) window.clearInterval(this.timerId);
        this.timerId = window.setInterval(() => this.refresh(), this.pollIntervalMs);
    }

    stopPolling() {
        if (this.timerId) {
            window.clearInterval(this.timerId);
            this.timerId = null;
        }
    }

    async refresh() {
        const root = document.getElementById(this.containerId);
        if (!root) return;

        try {
            const resp = await fetch('/api/projects');
            if (!resp.ok) {
                console.warn('[ProjectPipelineHUD] Failed to fetch project records:', resp.statusText);
                return;
            }
            const projects = await resp.json();
            this.render(root, projects);
        } catch (err) {
            console.error('[ProjectPipelineHUD] Network error fetching projects:', err);
        }
    }

    render(root, projects) {
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
            const qaBadge = (p.qa_score !== null && p.qa_score !== undefined)
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

    getStatusBadge(status) {
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

    escapeHtml(str) {
        return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
