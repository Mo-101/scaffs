import React, { useState } from 'react';
import {
  Zap,
  Send,
  Loader2,
  CheckCircle2,
  Copy,
  Check,
  Code,
  Clock,
  Activity,
  Layers,
} from 'lucide-react';

export const ApiSandbox: React.FC = () => {
  const endpoints = [
    {
      name: 'GET NODE 22 DIAGNOSTICS',
      method: 'GET',
      path: '/api/system/node-info',
      body: null,
      desc: 'Retrieves active Node.js 22 LTS runtime version, memory usage, and platform capabilities.',
    },
    {
      name: 'RUN V8 PERFORMANCE BENCHMARK',
      method: 'GET',
      path: '/api/system/benchmark',
      body: null,
      desc: 'Executes 50,000 native crypto UUID, JSON parse, and structuredClone operations.',
    },
    {
      name: 'EXECUTE NATIVE TEST RUNNER',
      method: 'POST',
      path: '/api/scaffold/test-runner',
      body: JSON.stringify({
        testSuite: [
          { name: 'Scaffold Integrity: validates tsconfig for Node 22', status: 'pass', durationMs: 1.1 },
          { name: 'Node 22: node:sqlite DatabaseSync initializes table', status: 'pass', durationMs: 2.2 },
          { name: 'Security: checks JWT and CORS headers', status: 'pass', durationMs: 0.9 },
        ],
      }, null, 2),
      desc: 'Executes test assertions using node:test and returns TAP formatted output.',
    },
    {
      name: 'AI CODE GENERATOR',
      method: 'POST',
      path: '/api/ai/code-gen',
      body: JSON.stringify({
        componentType: 'NativeSqliteRepository',
        specification: 'Create a typed user repository with transactions using node:sqlite DatabaseSync',
      }, null, 2),
      desc: 'Generates strict TypeScript code for Node 22 components via Gemini 3.7.',
    },
  ];

  const [selectedEndpoint, setSelectedEndpoint] = useState(endpoints[0]);
  const [requestBody, setRequestBody] = useState<string>(endpoints[0].body || '');
  const [response, setResponse] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<number | null>(null);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const handleSelect = (ep: typeof endpoints[0]) => {
    setSelectedEndpoint(ep);
    setRequestBody(ep.body || '');
    setResponse(null);
    setStatus(null);
    setDurationMs(null);
  };

  const handleSendRequest = async () => {
    setLoading(true);
    setResponse(null);
    setStatus(null);

    const start = performance.now();
    try {
      const options: RequestInit = {
        method: selectedEndpoint.method,
        headers: { 'Content-Type': 'application/json' },
      };

      if (selectedEndpoint.method === 'POST' && requestBody) {
        options.body = requestBody;
      }

      const res = await fetch(selectedEndpoint.path, options);
      const data = await res.json();
      const elapsed = performance.now() - start;

      setStatus(res.status);
      setDurationMs(Number(elapsed.toFixed(2)));
      setResponse(data);
    } catch (err: any) {
      setStatus(500);
      setResponse({ error: err.message });
      setDurationMs(Number((performance.now() - start).toFixed(2)));
    } finally {
      setLoading(false);
    }
  };

  const handleCopyResponse = () => {
    if (!response) return;
    navigator.clipboard.writeText(JSON.stringify(response, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="flex items-center space-x-2 text-xs font-mono font-bold text-[#ccff00] mb-2 uppercase tracking-widest">
              <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></span>
              <span>LIVE API CONSOLE</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-black text-white tracking-tighter uppercase">
              REST API SANDBOX
            </h2>
            <p className="text-sm font-light text-white/60 mt-2 max-w-2xl leading-relaxed">
              Inspect, execute, and debug backend endpoints on this live server process in real time with high-precision latency telemetry.
            </p>
          </div>
        </div>
      </div>

      {/* Grid: Endpoint selector & Request Builder */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Endpoints List */}
        <div className="space-y-3">
          <div className="text-xs font-mono font-bold text-white/40 uppercase tracking-widest px-1">
            AVAILABLE API ROUTES
          </div>
          <div className="space-y-2">
            {endpoints.map((ep, idx) => {
              const isSelected = selectedEndpoint.path === ep.path && selectedEndpoint.method === ep.method;
              return (
                <button
                  key={idx}
                  onClick={() => handleSelect(ep)}
                  className={`w-full text-left p-5 border transition-all relative ${
                    isSelected
                      ? 'bg-white/10 border-[#ccff00] shadow-[0_0_15px_rgba(204,255,0,0.15)]'
                      : 'bg-[#111111]/60 border-white/10 hover:border-white/30 text-white/60'
                  }`}
                >
                  {isSelected && <div className="absolute top-0 left-0 w-1.5 h-full bg-[#ccff00]"></div>}
                  <div className="flex items-center space-x-2 mb-2">
                    <span
                      className={`text-[9px] font-mono font-black px-2 py-0.5 uppercase ${
                        ep.method === 'GET' ? 'bg-white/10 text-white border border-white/20' : 'bg-[#ccff00] text-black'
                      }`}
                    >
                      {ep.method}
                    </span>
                    <span className="font-mono text-xs text-white font-bold truncate">{ep.path}</span>
                  </div>
                  <p className="text-[11px] text-white/50 line-clamp-2 leading-relaxed font-light">{ep.desc}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column (2 Cols): Request Builder & Live Response */}
        <div className="lg:col-span-2 space-y-8">
          {/* Request Header Bar */}
          <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-4">
            <div className="flex items-center gap-3">
              <span
                className={`text-xs font-mono font-black px-3 py-2 uppercase ${
                  selectedEndpoint.method === 'GET'
                    ? 'bg-white/10 text-white border border-white/20'
                    : 'bg-[#ccff00] text-black'
                }`}
              >
                {selectedEndpoint.method}
              </span>
              <input
                type="text"
                readOnly
                value={selectedEndpoint.path}
                className="flex-1 bg-[#111111] border border-white/10 px-4 py-2.5 text-xs text-white font-mono"
              />
              <button
                onClick={handleSendRequest}
                disabled={loading}
                className="flex items-center space-x-1.5 px-6 py-2.5 bg-[#ccff00] hover:bg-[#b8e600] text-black font-black text-xs uppercase tracking-tight transition-all shadow-[0_0_15px_rgba(204,255,0,0.3)] shrink-0"
              >
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                <span>EXECUTE</span>
              </button>
            </div>

            {/* Request Body Editor (for POST) */}
            {selectedEndpoint.method === 'POST' && (
              <div className="space-y-2">
                <label className="block text-xs font-mono font-bold uppercase tracking-wider text-white/60">
                  JSON Request Body
                </label>
                <textarea
                  rows={6}
                  value={requestBody}
                  onChange={(e) => setRequestBody(e.target.value)}
                  className="w-full bg-[#111111] border border-white/10 p-4 text-xs font-mono text-white focus:outline-none focus:border-[#ccff00] resize-y"
                />
              </div>
            )}
          </div>

          {/* Response Inspector */}
          {response && (
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-4 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center space-x-3">
                  <span className="text-xs font-mono font-bold uppercase tracking-wider text-white">HTTP RESPONSE</span>
                  {status && (
                    <span
                      className={`text-xs font-mono font-bold px-2 py-0.5 uppercase ${
                        status < 400 ? 'bg-[#ccff00] text-black' : 'bg-red-500 text-white'
                      }`}
                    >
                      STATUS: {status}
                    </span>
                  )}
                  {durationMs && (
                    <span className="text-xs text-white/50 font-mono flex items-center gap-1">
                      <Clock className="w-3 h-3 text-white/30" />
                      {durationMs}ms
                    </span>
                  )}
                </div>

                <button
                  onClick={handleCopyResponse}
                  className="flex items-center space-x-1.5 text-xs font-mono font-bold bg-white/5 hover:bg-white/10 text-white px-3 py-1.5 border border-white/10 transition-colors uppercase"
                >
                  {copied ? <Check className="w-3 h-3 text-[#ccff00]" /> : <Copy className="w-3 h-3 text-white/40" />}
                  <span>{copied ? 'COPIED' : 'COPY'}</span>
                </button>
              </div>

              <pre className="bg-[#111111] p-5 border border-white/10 text-xs font-mono text-white/90 overflow-x-auto max-h-96 leading-relaxed">
                <code>{JSON.stringify(response, null, 2)}</code>
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
