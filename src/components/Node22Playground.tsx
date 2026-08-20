import React, { useState } from 'react';
import {
  Terminal,
  Database,
  Play,
  CheckCircle2,
  Cpu,
  Zap,
  Activity,
  Layers,
  FileCode,
  Copy,
  Check,
  RefreshCw,
} from 'lucide-react';
import { NODE22_FEATURES } from '../data/node22Features';

export const Node22Playground: React.FC = () => {
  const [activeFeature, setActiveFeature] = useState(NODE22_FEATURES[0]);
  const [copied, setCopied] = useState(false);

  // Live Test Runner State
  const [testRunning, setTestRunning] = useState(false);
  const [testOutput, setTestOutput] = useState<string | null>(null);
  const [testStats, setTestStats] = useState<any | null>(null);

  // Live Benchmark State
  const [benchmarking, setBenchmarking] = useState(false);
  const [benchmarks, setBenchmarks] = useState<any[] | null>(null);

  // SQLite Sandbox State
  const [sqlQuery, setSqlQuery] = useState("SELECT * FROM users WHERE role = 'admin';");
  const [sqlResults, setSqlResults] = useState<any[]>([
    { id: 'usr_01', name: 'Lead Architect', email: 'architect@node22.dev', role: 'admin', score: 980 },
    { id: 'usr_02', name: 'Principal SRE', email: 'sre@node22.dev', role: 'admin', score: 940 },
  ]);

  const handleCopy = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRunTests = async () => {
    setTestRunning(true);
    try {
      const res = await fetch('/api/scaffold/test-runner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (data.success) {
        setTestOutput(data.data.tapOutput);
        setTestStats(data.data);
      }
    } catch (err) {
      console.error('Test run failed', err);
    } finally {
      setTestRunning(false);
    }
  };

  const handleRunBenchmark = async () => {
    setBenchmarking(true);
    try {
      const res = await fetch('/api/system/benchmark');
      const data = await res.json();
      if (data.success) {
        setBenchmarks(data.data.benchmarks);
      }
    } catch (err) {
      console.error('Benchmark failed', err);
    } finally {
      setBenchmarking(false);
    }
  };

  const handleExecuteSql = () => {
    const mockDb = [
      { id: 'usr_01', name: 'Lead Architect', email: 'architect@node22.dev', role: 'admin', score: 980 },
      { id: 'usr_02', name: 'Principal SRE', email: 'sre@node22.dev', role: 'admin', score: 940 },
      { id: 'usr_03', name: 'Frontend Dev', email: 'frontend@node22.dev', role: 'user', score: 820 },
      { id: 'usr_04', name: 'QA Engineer', email: 'qa@node22.dev', role: 'user', score: 790 },
      { id: 'usr_05', name: 'Security Auditor', email: 'sec@node22.dev', role: 'admin', score: 990 },
    ];

    if (sqlQuery.toLowerCase().includes('admin')) {
      setSqlResults(mockDb.filter(u => u.role === 'admin'));
    } else if (sqlQuery.toLowerCase().includes('score')) {
      setSqlResults(mockDb.filter(u => u.score > 850));
    } else {
      setSqlResults(mockDb);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="flex items-center space-x-2 text-xs font-mono font-bold text-[#ccff00] mb-2 uppercase tracking-widest">
              <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></span>
              <span>INTERACTIVE RUNTIME LAB</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-black text-white tracking-tighter uppercase">
              NODE 22 FEATURE LAB
            </h2>
            <p className="text-sm font-light text-white/60 mt-2 max-w-2xl leading-relaxed">
              Test and benchmark standard library features: Native SQLite (<code className="text-[#ccff00]">node:sqlite</code>), Native Test Runner (<code className="text-[#ccff00]">node:test</code>), Type Stripping, and V8 Maglev throughput.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleRunBenchmark}
              disabled={benchmarking}
              className="flex items-center space-x-2 text-xs font-mono font-bold uppercase tracking-wider bg-white/5 hover:bg-white/10 text-white px-4 py-3 border border-white/10 transition-colors"
            >
              <Activity className={`w-3.5 h-3.5 ${benchmarking ? 'animate-spin text-[#ccff00]' : 'text-white/40'}`} />
              <span>BENCHMARK V8</span>
            </button>

            <button
              onClick={handleRunTests}
              disabled={testRunning}
              className="flex items-center space-x-2 text-xs bg-[#ccff00] hover:bg-[#b8e600] text-black px-5 py-3 font-black uppercase tracking-tight transition-all shadow-[0_0_15px_rgba(204,255,0,0.3)]"
            >
              <Play className={`w-3.5 h-3.5 ${testRunning ? 'animate-spin' : 'stroke-[3]'}`} />
              <span>RUN NODE:TEST</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Features List & Interactive Terminal */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Feature Selector */}
        <div className="space-y-3">
          <div className="text-xs font-mono font-bold text-white/40 uppercase tracking-widest px-1">
            STANDARD CAPABILITIES
          </div>
          <div className="space-y-2">
            {NODE22_FEATURES.map((feat, idx) => {
              const isSelected = activeFeature.id === feat.id;
              return (
                <button
                  key={feat.id}
                  onClick={() => setActiveFeature(feat)}
                  className={`w-full text-left p-5 border transition-all relative ${
                    isSelected
                      ? 'bg-white/10 border-[#ccff00] shadow-[0_0_15px_rgba(204,255,0,0.15)]'
                      : 'bg-[#111111]/60 border-white/10 hover:border-white/30 text-white/60'
                  }`}
                >
                  {isSelected && <div className="absolute top-0 left-0 w-1.5 h-full bg-[#ccff00]"></div>}
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-bold text-xs text-white uppercase tracking-wider">{feat.title}</span>
                    <span className="text-[9px] font-mono px-2 py-0.5 bg-white/10 text-[#ccff00] border border-white/10 font-bold">
                      {feat.badge}
                    </span>
                  </div>
                  <p className="text-[11px] text-white/50 line-clamp-2 leading-relaxed font-light">{feat.summary}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column (2 Cols): Feature Inspector & Code Preview */}
        <div className="lg:col-span-2 space-y-8">
          {/* Feature Details Card */}
          <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div>
                <span className="text-[10px] font-mono bg-white/5 text-[#ccff00] px-2.5 py-1 border border-white/10 uppercase tracking-widest font-bold">
                  {activeFeature.category}
                </span>
                <h3 className="text-2xl font-black text-white uppercase tracking-tight mt-2">{activeFeature.title}</h3>
              </div>

              <button
                onClick={() => handleCopy(activeFeature.codeSnippet)}
                className="flex items-center space-x-1.5 text-xs font-mono font-bold bg-white/5 hover:bg-white/10 text-white px-3.5 py-2 border border-white/10 transition-colors uppercase"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-[#ccff00]" /> : <Copy className="w-3.5 h-3.5 text-white/40" />}
                <span>{copied ? 'COPIED' : 'COPY'}</span>
              </button>
            </div>

            <p className="text-sm text-white/70 leading-relaxed font-light">{activeFeature.description}</p>

            <div className="bg-[#111111] p-5 border border-white/10 space-y-3">
              <div className="text-[10px] font-mono font-bold text-[#ccff00] uppercase tracking-widest">
                ARCHITECTURAL ADVANTAGES
              </div>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono text-white/80">
                {activeFeature.advantages.map((adv, idx) => (
                  <li key={idx} className="flex items-start space-x-2">
                    <span className="text-[#ccff00] font-black">›</span>
                    <span className="font-light">{adv}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Code Block */}
            <div className="bg-[#111111] border border-white/10 overflow-hidden font-mono text-xs">
              <div className="px-4 py-3 bg-black/40 border-b border-white/10 text-[11px] text-white/40 flex items-center justify-between">
                <span>// Standard Library TypeScript Implementation</span>
                <span className="text-[#ccff00]">Node 22 LTS</span>
              </div>
              <pre className="p-5 text-white/90 overflow-x-auto whitespace-pre leading-relaxed">
                <code>{activeFeature.codeSnippet}</code>
              </pre>
            </div>
          </div>

          {/* Feature-Specific Interactive Sandboxes */}
          {activeFeature.id === 'native-sqlite' && (
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center space-x-2">
                  <Database className="w-4 h-4 text-[#ccff00]" />
                  <h4 className="text-sm font-black uppercase tracking-wider text-white">node:sqlite Query Console</h4>
                </div>
                <span className="text-[10px] font-mono text-white/40 uppercase">
                  DatabaseSync (:memory:)
                </span>
              </div>

              <div className="flex gap-3">
                <input
                  type="text"
                  value={sqlQuery}
                  onChange={(e) => setSqlQuery(e.target.value)}
                  className="flex-1 bg-[#111111] border border-white/10 px-4 py-3 text-xs text-white font-mono placeholder-white/30 focus:outline-none focus:border-[#ccff00]"
                  placeholder="SELECT * FROM users WHERE ..."
                />
                <button
                  onClick={handleExecuteSql}
                  className="px-5 py-3 bg-[#ccff00] hover:bg-[#b8e600] text-black font-black text-xs uppercase tracking-tight transition-all shadow-[0_0_10px_rgba(204,255,0,0.2)] shrink-0"
                >
                  EXECUTE
                </button>
              </div>

              <div className="border border-white/10 overflow-x-auto">
                <table className="w-full text-left text-xs font-mono text-white/80">
                  <thead className="bg-[#111111] text-white/40 border-b border-white/10">
                    <tr>
                      <th className="p-3">ID</th>
                      <th className="p-3">NAME</th>
                      <th className="p-3">EMAIL</th>
                      <th className="p-3">ROLE</th>
                      <th className="p-3">SCORE</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 bg-[#0a0a0a]">
                    {sqlResults.map((row, idx) => (
                      <tr key={idx} className="hover:bg-white/5">
                        <td className="p-3 text-[#ccff00] font-bold">{row.id}</td>
                        <td className="p-3 text-white font-bold">{row.name}</td>
                        <td className="p-3 text-white/60">{row.email}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 text-[10px] uppercase font-bold border ${row.role === 'admin' ? 'border-[#ccff00]/40 text-[#ccff00] bg-[#ccff00]/10' : 'border-white/10 text-white/60'}`}>
                            {row.role}
                          </span>
                        </td>
                        <td className="p-3 font-bold text-white">{row.score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Test Runner Output Terminal */}
          {testOutput && (
            <div className="bg-[#111111] border border-white/10 p-6 space-y-4 font-mono relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>
              
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-[#ccff00]" />
                  <span className="text-xs font-bold uppercase tracking-wider text-white">node:test TAP Output</span>
                </div>
                {testStats && (
                  <span className="text-xs text-[#ccff00] font-black">
                    ✓ {testStats.passed}/{testStats.total} PASSED ({testStats.durationMs}ms)
                  </span>
                )}
              </div>

              <pre className="p-4 bg-black/60 border border-white/10 text-xs text-[#ccff00] overflow-x-auto leading-relaxed">
                {testOutput}
              </pre>
            </div>
          )}

          {/* Benchmark Results */}
          {benchmarks && (
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center space-x-2">
                  <Zap className="w-4 h-4 text-[#ccff00]" />
                  <h4 className="text-sm font-black uppercase tracking-wider text-white">V8 Throughput Benchmarks</h4>
                </div>
                <span className="text-[10px] font-mono text-white/40 uppercase">50,000 ITERATIONS</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {benchmarks.map((bench, idx) => (
                  <div key={idx} className="bg-[#111111] p-5 border border-white/10 space-y-2">
                    <div className="text-[10px] font-mono text-[#ccff00] uppercase tracking-widest font-bold">{bench.category}</div>
                    <div className="text-xs font-bold text-white uppercase">{bench.name}</div>
                    <div className="text-2xl font-black text-white font-mono tracking-tight">
                      {bench.opsPerSec.toLocaleString()} <span className="text-[10px] text-white/40 font-normal">ops/s</span>
                    </div>
                    <div className="text-[10px] font-mono text-white/40">{bench.timeMs}ms total ({bench.note})</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
