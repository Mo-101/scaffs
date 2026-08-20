import React, { useState } from 'react';
import {
  Sparkles,
  Send,
  Loader2,
  CheckCircle2,
  Code2,
  Download,
  Layers,
  ArrowRight,
  RefreshCw,
  Cpu,
  Shield,
  Database,
  Box,
  FileCode,
} from 'lucide-react';
import { ProjectFile } from '../types/scaffold';
import { downloadProjectZip } from '../utils/zipExport';
import { FileTreeViewer } from './FileTreeViewer';

interface AiArchitectProps {
  onLoadGeneratedProject: (projectName: string, files: ProjectFile[]) => void;
}

export const AiArchitect: React.FC<AiArchitectProps> = ({ onLoadGeneratedProject }) => {
  const [prompt, setPrompt] = useState('');
  const [framework, setFramework] = useState('Express');
  const [database, setDatabase] = useState('SQLite (Native node:sqlite)');
  const [auth, setAuth] = useState('JWT + Bearer');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<any | null>(null);

  const presets = [
    {
      title: 'Fintech Payment Gateway',
      desc: 'Idempotency keys, webhook signatures, transaction ledger with node:sqlite',
      prompt: 'Fintech Payment Processing API with stripe-like webhook verification, HMAC signatures, idempotency key cache, and SQLite ledger storage',
      framework: 'Express',
      db: 'SQLite (Native node:sqlite)',
    },
    {
      title: 'Realtime IoT Telemetry Ingest',
      desc: 'High-frequency sensor stream ingest with batch inserts and metrics',
      prompt: 'Realtime IoT Sensor Data Ingestion microservice with WebSockets, batch SQLite insertions, and automated alert threshold triggers',
      framework: 'Hono',
      db: 'SQLite (Native node:sqlite)',
    },
    {
      title: 'SaaS Multi-Tenant Auth & RBAC',
      desc: 'Organization workspaces, role-based access control, and audit logs',
      prompt: 'Multi-tenant B2B SaaS platform with organization isolation, JWT auth, RBAC permissions guard, and audit log tracking',
      framework: 'Express',
      db: 'SQLite (Native node:sqlite)',
    },
    {
      title: 'GenAI Document Analysis Agent',
      desc: 'Server-side Gemini 3.7 LLM document analyzer with SSE streaming',
      prompt: 'AI-powered document analyzer and summarizer with Server-Sent Events streaming, vector embeddings, and structured JSON output extraction',
      framework: 'Express',
      db: 'SQLite (Native node:sqlite)',
    },
  ];

  const handleGenerate = async (customPrompt?: string) => {
    const textToUse = customPrompt || prompt;
    if (!textToUse.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/ai/architect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: textToUse,
          framework,
          database,
          auth,
        }),
      });

      const json = await res.json();
      if (json.success && json.data) {
        setPlan(json.data);
      } else {
        setError(json.error || 'Failed to generate architecture blueprint.');
      }
    } catch (err: any) {
      setError(err.message || 'Network error occurred while connecting to AI Architect.');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyPreset = (p: typeof presets[0]) => {
    setPrompt(p.prompt);
    setFramework(p.framework);
    setDatabase(p.db);
    handleGenerate(p.prompt);
  };

  return (
    <div className="space-y-8">
      {/* Top AI Header */}
      <div className="bg-[#0a0a0a] border border-white/10 p-8 lg:p-12 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

        <div className="flex flex-col lg:flex-row items-start lg:items-end justify-between gap-6">
          <div>
            <div className="flex items-center space-x-2 text-xs font-mono font-bold text-[#ccff00] mb-2 uppercase tracking-widest">
              <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></span>
              <span>GEMINI 3.7 ORCHESTRATION</span>
            </div>
            <h2 className="text-4xl sm:text-6xl font-black text-white tracking-tighter uppercase leading-[0.9]">
              AI ARCHITECT &<br />CODE SYNTHESIS
            </h2>
            <p className="text-sm font-light text-white/60 mt-4 max-w-2xl leading-relaxed">
              Describe your software system in plain English. Gemini analyzes domain requirements, generates a multi-tier blueprint, and produces complete production files for Node 22 LTS.
            </p>
          </div>

          <div className="flex items-center space-x-2 text-xs font-mono py-2 px-4 bg-white/5 border border-white/10 text-white/80">
            <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></span>
            <span>MODEL: GEMINI-3.7-FLASH</span>
          </div>
        </div>
      </div>

      {/* Input Prompt Section */}
      <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-mono font-bold uppercase tracking-wider text-white/80">
              System Specification Prompt
            </label>
            <span className="text-[10px] font-mono text-[#ccff00]">PROMPT INPUT</span>
          </div>
          <textarea
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. Build a high-throughput webhook receiver with SQLite idempotency ledger, HMAC verification, and Docker container..."
            className="w-full bg-[#111111] border border-white/10 p-4 text-sm text-white font-mono placeholder-white/30 focus:outline-none focus:border-[#ccff00] resize-none"
          />
        </div>

        {/* Configurations Bar */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
          <div>
            <label className="block text-[11px] font-mono uppercase tracking-wider text-white/50 mb-1.5">
              Gateway Framework
            </label>
            <select
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              className="w-full bg-[#111111] border border-white/10 px-3 py-2.5 text-xs text-white focus:outline-none focus:border-[#ccff00] font-mono"
            >
              <option value="Express">Express.js (Node 22)</option>
              <option value="Hono">Hono for Node</option>
              <option value="Fastify">Fastify 5</option>
              <option value="Native HTTP">Native HTTP (Zero-Dep)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-mono uppercase tracking-wider text-white/50 mb-1.5">
              Persistence Engine
            </label>
            <select
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
              className="w-full bg-[#111111] border border-white/10 px-3 py-2.5 text-xs text-white focus:outline-none focus:border-[#ccff00] font-mono"
            >
              <option value="SQLite (Native node:sqlite)">SQLite (Native node:sqlite)</option>
              <option value="Drizzle ORM + SQLite">Drizzle ORM + SQLite</option>
              <option value="PostgreSQL">PostgreSQL</option>
              <option value="In-Memory / None">In-Memory / Stateless</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-mono uppercase tracking-wider text-white/50 mb-1.5">
              Security Protocol
            </label>
            <select
              value={auth}
              onChange={(e) => setAuth(e.target.value)}
              className="w-full bg-[#111111] border border-white/10 px-3 py-2.5 text-xs text-white focus:outline-none focus:border-[#ccff00] font-mono"
            >
              <option value="JWT + Bearer">JWT + Bearer Tokens</option>
              <option value="API Key">API Key Header Guard</option>
              <option value="Session Cookies">Session Cookies</option>
              <option value="None">None / Public API</option>
            </select>
          </div>
        </div>

        {/* Action Row */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-white/10">
          <div className="flex items-center space-x-2 overflow-x-auto w-full sm:w-auto scrollbar-none py-1">
            <span className="text-[10px] font-mono text-white/40 uppercase shrink-0">PRESETS:</span>
            {presets.map((p, idx) => (
              <button
                key={idx}
                onClick={() => handleApplyPreset(p)}
                className="text-[11px] font-mono bg-white/5 hover:bg-white/10 text-white/80 px-3 py-1.5 border border-white/10 shrink-0 transition-colors"
              >
                {p.title}
              </button>
            ))}
          </div>

          <button
            onClick={() => handleGenerate()}
            disabled={loading || !prompt.trim()}
            className="w-full sm:w-auto px-6 py-3 bg-[#ccff00] hover:bg-[#b8e600] disabled:opacity-40 text-black font-black text-xs uppercase tracking-tight transition-all shadow-[0_0_15px_rgba(204,255,0,0.3)] flex items-center justify-center space-x-2 shrink-0"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin stroke-[3]" />
                <span>SYNTHESIZING ARCHITECTURE...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>SYNTHESIZE SCAFFOLD</span>
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="p-4 bg-red-950/50 border border-red-500/50 text-xs font-mono text-red-300">
            [ERROR]: {error}
          </div>
        )}
      </div>

      {/* Generated Blueprint View */}
      {plan && (
        <div className="space-y-8">
          {/* Plan Header */}
          <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-6 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6">
              <div>
                <div className="flex items-center space-x-2 text-xs font-mono text-[#ccff00] mb-1 font-bold uppercase tracking-wider">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>SYNTHESIS COMPLETE</span>
                </div>
                <h3 className="text-3xl font-black text-white uppercase tracking-tight">{plan.projectName || 'node22-scaffold'}</h3>
                <p className="text-xs text-white/60 font-light mt-1 max-w-2xl">{plan.description}</p>
              </div>

              <div className="flex items-center space-x-3">
                <button
                  onClick={() => downloadProjectZip(plan.projectName, plan.suggestedFiles)}
                  className="flex items-center space-x-1.5 text-xs font-mono font-bold bg-white/5 hover:bg-white/10 text-white px-4 py-2.5 border border-white/10 transition-colors uppercase"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>EXPORT .ZIP</span>
                </button>

                <button
                  onClick={() => onLoadGeneratedProject(plan.projectName, plan.suggestedFiles)}
                  className="flex items-center space-x-1.5 text-xs bg-[#ccff00] hover:bg-[#b8e600] text-black font-black px-4 py-2.5 uppercase tracking-tight transition-all shadow-[0_0_15px_rgba(204,255,0,0.25)]"
                >
                  <span>OPEN IN STUDIO</span>
                  <ArrowRight className="w-3.5 h-3.5 stroke-[3]" />
                </button>
              </div>
            </div>

            {/* Architecture Highlights & Layers */}
            {plan.architecture && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                <div className="bg-[#111111] p-6 border border-white/10 space-y-4">
                  <div className="text-xs font-mono font-bold text-white uppercase tracking-wider flex items-center justify-between">
                    <span>ARCHITECTURAL LAYERS</span>
                    <span className="text-[#ccff00]">{plan.architecture.pattern}</span>
                  </div>
                  <div className="space-y-2">
                    {plan.architecture.layers?.map((layer: any, idx: number) => (
                      <div key={idx} className="text-xs text-white/80 flex items-start space-x-2 font-mono">
                        <span className="text-[#ccff00] font-black">›</span>
                        <div>
                          <strong className="text-white uppercase">{layer.name}:</strong> <span className="font-light text-white/60">{layer.description}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-[#111111] p-6 border border-white/10 space-y-4">
                  <div className="text-xs font-mono font-bold text-white uppercase tracking-wider flex items-center justify-between">
                    <span>NODE 22 NATIVE OPTIMIZATIONS</span>
                    <span className="text-[#ccff00]">V8 ENGINE</span>
                  </div>
                  <ul className="space-y-2 text-xs font-mono text-white/80">
                    {plan.architecture.recommendedNodeFeatures?.map((feat: string, idx: number) => (
                      <li key={idx} className="flex items-start space-x-2">
                        <span className="text-[#ccff00] font-black">✓</span>
                        <span className="font-light text-white/70">{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          {/* Generated Code Files */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                GENERATED MODULES ({plan.suggestedFiles?.length || 0})
              </h3>
            </div>

            <FileTreeViewer
              files={plan.suggestedFiles || []}
              projectName={plan.projectName || 'ai-scaffold'}
              onDownloadZip={() => downloadProjectZip(plan.projectName, plan.suggestedFiles)}
            />
          </div>
        </div>
      )}
    </div>
  );
};
