import React, { useState } from 'react';
import {
  Settings,
  Layers,
  Cpu,
  Shield,
  Database,
  Terminal,
  FileCheck,
  Zap,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  Code2,
  Sliders,
  Box,
  Check,
} from 'lucide-react';
import { ScaffoldConfig, ProjectFile } from '../types/scaffold';
import { generateScaffoldFiles } from '../utils/scaffoldGenerator';
import { FileTreeViewer } from './FileTreeViewer';

interface ScaffoldStudioProps {
  currentConfig: ScaffoldConfig;
  setCurrentConfig: React.Dispatch<React.SetStateAction<ScaffoldConfig>>;
  files: ProjectFile[];
  setFiles: React.Dispatch<React.SetStateAction<ProjectFile[]>>;
  onDownloadZip: () => void;
}

export const ScaffoldStudio: React.FC<ScaffoldStudioProps> = ({
  currentConfig,
  setCurrentConfig,
  files,
  setFiles,
  onDownloadZip,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'config' | 'files' | 'architecture'>('config');

  const updateConfig = <K extends keyof ScaffoldConfig>(key: K, value: ScaffoldConfig[K]) => {
    const nextConfig = { ...currentConfig, [key]: value };
    setCurrentConfig(nextConfig);
    const newFiles = generateScaffoldFiles(nextConfig);
    setFiles(newFiles);
  };

  const frameworks: { id: ScaffoldConfig['framework']; name: string; desc: string; badge: string }[] = [
    { id: 'express', name: 'EXPRESS.JS 4/5', desc: 'Standard robust framework with full middleware ecosystem', badge: 'LTS READY' },
    { id: 'hono', name: 'HONO FOR NODE', desc: 'Ultra-lightweight, zero-overhead TypeScript framework', badge: 'HIGH SPEED' },
    { id: 'fastify', name: 'FASTIFY 5', desc: 'High throughput schema-driven architecture with fast-json', badge: 'V8 OPTIMIZED' },
    { id: 'native-http', name: 'NATIVE HTTP/2', desc: 'Zero external runtime dependencies, 100% Node 22 standard library', badge: 'ZERO DEPS' },
  ];

  const databases: { id: ScaffoldConfig['database']; name: string; desc: string; badge: string }[] = [
    { id: 'sqlite-native', name: 'NATIVE SQLITE (node:sqlite)', desc: 'Node 22 built-in synchronous SQLite with zero npm dependencies', badge: 'NATIVE' },
    { id: 'drizzle-sqlite', name: 'DRIZZLE ORM + SQLITE', desc: 'Type-safe SQL schema & relations with migrations', badge: 'TYPE SAFE' },
    { id: 'prisma-pg', name: 'PRISMA + POSTGRES', desc: 'Auto-generated client with relational schema migrations', badge: 'ENTERPRISE' },
    { id: 'none', name: 'STATELESS / MEMORY', desc: 'Pure compute service or external SaaS API persistence', badge: 'LEAN' },
  ];

  const frontends: { id: ScaffoldConfig['frontend']; name: string; desc: string }[] = [
    { id: 'react19-vite', name: 'REACT 19 + VITE', desc: 'Full-stack monorepo with modern React 19 hooks and Tailwind CSS' },
    { id: 'pure-api', name: 'PURE BACKEND API', desc: 'Headless microservice or backend-for-frontend service' },
    { id: 'vue-vite', name: 'VUE 3 + VITE', desc: 'Composition API frontend with Pinia and Vue Router' },
  ];

  const authOptions: { id: ScaffoldConfig['auth']; name: string; desc: string }[] = [
    { id: 'jwt', name: 'JWT + BEARER TOKENS', desc: 'Stateless cryptographic token auth with expiry and claims' },
    { id: 'api-key', name: 'API KEY HEADER GUARD', desc: 'Header-based service-to-service authorization (X-API-Key)' },
    { id: 'session-cookies', name: 'HTTPONLY COOKIES', desc: 'Secure stateful sessions with CSRF protection' },
    { id: 'none', name: 'PUBLIC / OPEN API', desc: 'Open microservice behind API gateway' },
  ];

  return (
    <div className="space-y-8">
      {/* Bold Hero Header Section */}
      <div className="border border-white/10 bg-[#0a0a0a] p-8 lg:p-12 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]" />
        
        <div className="flex flex-col lg:flex-row items-start lg:items-end justify-between gap-8">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <span className="text-xs font-mono py-1 px-3 bg-[#ccff00] text-black font-black uppercase tracking-wider">
                NODE.JS 22 LTS
              </span>
              <span className="text-xs font-mono text-white/50 uppercase tracking-widest">
                STANDARD-COMPLIANT ARCHITECTURE
              </span>
            </div>
            
            <h1 className="text-5xl sm:text-7xl lg:text-8xl font-black tracking-tighter leading-[0.88] text-white">
              NODE<br />TWENTY<br /><span className="text-[#ccff00]">TWO</span>
            </h1>
            
            <p className="text-sm sm:text-base font-light text-white/70 mt-6 max-w-xl leading-relaxed">
              Generating standard-compliant full-stack project structures with Native ESM, V8 Maglev compiler optimizations, built-in SQLite, and zero-dependency test runner.
            </p>
          </div>

          {/* Sub Navigation Tabs */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full lg:w-auto">
            <button
              onClick={() => setActiveSubTab('config')}
              className={`px-5 py-3 text-xs font-mono font-bold uppercase tracking-wider transition-all text-center ${
                activeSubTab === 'config'
                  ? 'bg-[#ccff00] text-black shadow-[0_0_15px_rgba(204,255,0,0.3)]'
                  : 'bg-white/5 text-white/70 border border-white/10 hover:text-white hover:bg-white/10'
              }`}
            >
              01 STACK CONFIG
            </button>
            <button
              onClick={() => setActiveSubTab('files')}
              className={`px-5 py-3 text-xs font-mono font-bold uppercase tracking-wider transition-all text-center ${
                activeSubTab === 'files'
                  ? 'bg-[#ccff00] text-black shadow-[0_0_15px_rgba(204,255,0,0.3)]'
                  : 'bg-white/5 text-white/70 border border-white/10 hover:text-white hover:bg-white/10'
              }`}
            >
              02 INSPECT FILES ({files.length})
            </button>
            <button
              onClick={() => setActiveSubTab('architecture')}
              className={`px-5 py-3 text-xs font-mono font-bold uppercase tracking-wider transition-all text-center ${
                activeSubTab === 'architecture'
                  ? 'bg-[#ccff00] text-black shadow-[0_0_15px_rgba(204,255,0,0.3)]'
                  : 'bg-white/5 text-white/70 border border-white/10 hover:text-white hover:bg-white/10'
              }`}
            >
              03 SYSTEM MAP
            </button>
          </div>
        </div>

        {/* 4 Key Feature Metrics matching Design HTML */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-8 pt-8 border-t border-white/10">
          <div className="bg-white/5 p-5 border border-white/10 flex flex-col justify-between h-[130px]">
            <span className="text-[10px] uppercase tracking-widest text-white/50 font-bold">Runtime Target</span>
            <span className="text-2xl sm:text-3xl font-black text-white">Node.js 22.x</span>
            <div className="flex gap-2">
              <span className="px-2 py-0.5 bg-[#ccff00] text-black text-[10px] font-black">LTS IRON</span>
              <span className="px-2 py-0.5 border border-white/20 text-[10px] font-mono text-white/80">ESM</span>
            </div>
          </div>

          <div className="bg-white/5 p-5 border border-white/10 flex flex-col justify-between h-[130px]">
            <span className="text-[10px] uppercase tracking-widest text-white/50 font-bold">Architecture</span>
            <span className="text-2xl sm:text-3xl font-black text-white truncate">
              {currentConfig.architecturePattern === 'clean' ? 'Layered 3-Tier' : 'Modular FSD'}
            </span>
            <span className="text-[10px] text-white/60 font-mono">Separation of Concerns</span>
          </div>

          <div className="bg-white/5 p-5 border border-white/10 flex flex-col justify-between h-[130px]">
            <span className="text-[10px] uppercase tracking-widest text-white/50 font-bold">Type Safety</span>
            <span className="text-2xl sm:text-3xl font-black text-white">TS Strict</span>
            <div className="w-full bg-white/10 h-1 mt-1">
              <div className="bg-[#ccff00] w-[100%] h-full"></div>
            </div>
          </div>

          <div className="bg-white/5 p-5 border border-white/10 flex flex-col justify-between h-[130px]">
            <span className="text-[10px] uppercase tracking-widest text-white/50 font-bold">Environment</span>
            <span className="text-2xl sm:text-3xl font-black text-[#ccff00]">Native .env</span>
            <span className="text-[10px] text-white/60 font-mono italic">process.loadEnvFile</span>
          </div>
        </div>
      </div>

      {activeSubTab === 'config' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Config Options (2 Cols) */}
          <div className="lg:col-span-2 space-y-8">
            {/* Section 01: Identity */}
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono text-[#ccff00] font-black">01</span>
                  <h3 className="text-lg font-black uppercase tracking-wider text-white">
                    Project Identity & Architecture Pattern
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-white/40 uppercase">METADATA</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider text-white/60 mb-2">
                    Project Slug
                  </label>
                  <input
                    type="text"
                    value={currentConfig.projectName}
                    onChange={(e) => updateConfig('projectName', e.target.value)}
                    className="w-full bg-[#111111] border border-white/10 px-4 py-3 text-sm text-white font-mono focus:outline-none focus:border-[#ccff00]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider text-white/60 mb-2">
                    Architecture Blueprint
                  </label>
                  <select
                    value={currentConfig.architecturePattern}
                    onChange={(e) => updateConfig('architecturePattern', e.target.value as any)}
                    className="w-full bg-[#111111] border border-white/10 px-4 py-3 text-sm text-white focus:outline-none focus:border-[#ccff00]"
                  >
                    <option value="clean">Clean 3-Tier Layered (Controllers & Services)</option>
                    <option value="modular-monolith">Modular Monolith / Feature-Sliced</option>
                    <option value="vertical-slice">Vertical Slice Architecture</option>
                    <option value="microservice">Lean Microservice</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Section 02: Framework */}
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono text-[#ccff00] font-black">02</span>
                  <h3 className="text-lg font-black uppercase tracking-wider text-white">
                    Server Framework & Runtime
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-white/40 uppercase">GATEWAY</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {frameworks.map((fw) => {
                  const isSelected = currentConfig.framework === fw.id;
                  return (
                    <button
                      key={fw.id}
                      onClick={() => updateConfig('framework', fw.id)}
                      className={`text-left p-5 border transition-all relative ${
                        isSelected
                          ? 'bg-white/10 border-[#ccff00] shadow-[0_0_15px_rgba(204,255,0,0.15)]'
                          : 'bg-[#111111]/60 border-white/10 hover:border-white/30 text-white/60'
                      }`}
                    >
                      {isSelected && (
                        <div className="absolute top-0 left-0 w-1.5 h-full bg-[#ccff00]"></div>
                      )}
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-black text-sm text-white tracking-wide">{fw.name}</span>
                        <span className="text-[9px] font-mono px-2 py-0.5 bg-white/10 text-[#ccff00] border border-white/10">
                          {fw.badge}
                        </span>
                      </div>
                      <p className="text-xs text-white/60 leading-relaxed font-light">{fw.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Section 03: Database */}
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono text-[#ccff00] font-black">03</span>
                  <h3 className="text-lg font-black uppercase tracking-wider text-white">
                    Persistence & Database
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-white/40 uppercase">STORAGE</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {databases.map((db) => {
                  const isSelected = currentConfig.database === db.id;
                  return (
                    <button
                      key={db.id}
                      onClick={() => updateConfig('database', db.id)}
                      className={`text-left p-5 border transition-all relative ${
                        isSelected
                          ? 'bg-white/10 border-[#ccff00] shadow-[0_0_15px_rgba(204,255,0,0.15)]'
                          : 'bg-[#111111]/60 border-white/10 hover:border-white/30 text-white/60'
                      }`}
                    >
                      {isSelected && (
                        <div className="absolute top-0 left-0 w-1.5 h-full bg-[#ccff00]"></div>
                      )}
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-black text-sm text-white tracking-wide">{db.name}</span>
                        <span className="text-[9px] font-mono px-2 py-0.5 bg-white/10 text-[#ccff00] border border-white/10">
                          {db.badge}
                        </span>
                      </div>
                      <p className="text-xs text-white/60 leading-relaxed font-light">{db.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Section 04: Frontend & Auth */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
              {/* Frontend Selection */}
              <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <span className="text-sm font-black uppercase tracking-wider text-white">Frontend Client</span>
                  <span className="text-[9px] font-mono text-[#ccff00]">CLIENT</span>
                </div>
                <div className="space-y-2">
                  {frontends.map((fe) => {
                    const isSelected = currentConfig.frontend === fe.id;
                    return (
                      <button
                        key={fe.id}
                        onClick={() => updateConfig('frontend', fe.id)}
                        className={`w-full text-left p-3.5 border transition-all ${
                          isSelected
                            ? 'bg-white/10 border-[#ccff00] text-white'
                            : 'bg-[#111111]/60 border-white/10 text-white/60 hover:border-white/20'
                        }`}
                      >
                        <div className="font-bold text-xs text-white tracking-wide">{fe.name}</div>
                        <p className="text-[11px] text-white/50 mt-0.5">{fe.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Auth Selection */}
              <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <span className="text-sm font-black uppercase tracking-wider text-white">Auth & Security</span>
                  <span className="text-[9px] font-mono text-[#ccff00]">SECURITY</span>
                </div>
                <div className="space-y-2">
                  {authOptions.map((auth) => {
                    const isSelected = currentConfig.auth === auth.id;
                    return (
                      <button
                        key={auth.id}
                        onClick={() => updateConfig('auth', auth.id)}
                        className={`w-full text-left p-3.5 border transition-all ${
                          isSelected
                            ? 'bg-white/10 border-[#ccff00] text-white'
                            : 'bg-[#111111]/60 border-white/10 text-white/60 hover:border-white/20'
                        }`}
                      >
                        <div className="font-bold text-xs text-white tracking-wide">{auth.name}</div>
                        <p className="text-[11px] text-white/50 mt-0.5">{auth.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          {/* Node 22 Feature Toggles & Summary Sidebar (1 Col) */}
          <div className="space-y-8">
            {/* Node 22 Native Built-ins */}
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono text-[#ccff00] font-black">04</span>
                  <h3 className="text-sm font-black uppercase tracking-wider text-white">
                    Node 22 Standard Flags
                  </h3>
                </div>
                <div className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></div>
              </div>

              <div className="space-y-4">
                <label className="flex items-start space-x-3 cursor-pointer p-3 bg-white/5 border border-white/10 hover:border-white/20 transition-colors">
                  <input
                    type="checkbox"
                    checked={currentConfig.enableNativeSqlite}
                    onChange={(e) => updateConfig('enableNativeSqlite', e.target.checked)}
                    className="mt-0.5 accent-[#ccff00] w-4 h-4 bg-black border-white/20"
                  />
                  <div>
                    <div className="text-xs font-bold text-white uppercase tracking-wider">node:sqlite DatabaseSync</div>
                    <div className="text-[11px] text-white/50 font-light">Zero-dep synchronous SQLite3 engine</div>
                  </div>
                </label>

                <label className="flex items-start space-x-3 cursor-pointer p-3 bg-white/5 border border-white/10 hover:border-white/20 transition-colors">
                  <input
                    type="checkbox"
                    checked={currentConfig.enableTypeStripping}
                    onChange={(e) => updateConfig('enableTypeStripping', e.target.checked)}
                    className="mt-0.5 accent-[#ccff00] w-4 h-4 bg-black border-white/20"
                  />
                  <div>
                    <div className="text-xs font-bold text-white uppercase tracking-wider">--experimental-strip-types</div>
                    <div className="text-[11px] text-white/50 font-light">Execute .ts directly at native speed</div>
                  </div>
                </label>

                <label className="flex items-start space-x-3 cursor-pointer p-3 bg-white/5 border border-white/10 hover:border-white/20 transition-colors">
                  <input
                    type="checkbox"
                    checked={currentConfig.enableProcessEnvFile}
                    onChange={(e) => updateConfig('enableProcessEnvFile', e.target.checked)}
                    className="mt-0.5 accent-[#ccff00] w-4 h-4 bg-black border-white/20"
                  />
                  <div>
                    <div className="text-xs font-bold text-white uppercase tracking-wider">process.loadEnvFile()</div>
                    <div className="text-[11px] text-white/50 font-light">Native CLI --env-file injection</div>
                  </div>
                </label>

                <label className="flex items-start space-x-3 cursor-pointer p-3 bg-white/5 border border-white/10 hover:border-white/20 transition-colors">
                  <input
                    type="checkbox"
                    checked={currentConfig.enableNativeWatch}
                    onChange={(e) => updateConfig('enableNativeWatch', e.target.checked)}
                    className="mt-0.5 accent-[#ccff00] w-4 h-4 bg-black border-white/20"
                  />
                  <div>
                    <div className="text-xs font-bold text-white uppercase tracking-wider">node --watch</div>
                    <div className="text-[11px] text-white/50 font-light">Libuv integrated process auto-restart</div>
                  </div>
                </label>
              </div>
            </div>

            {/* Production & Containerization */}
            <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <span className="text-sm font-black uppercase tracking-wider text-white">DevOps & CI</span>
                <span className="text-[9px] font-mono text-white/40">CONTAINERS</span>
              </div>

              <div className="space-y-3">
                <label className="flex items-start space-x-3 cursor-pointer p-3 bg-white/5 border border-white/10">
                  <input
                    type="checkbox"
                    checked={currentConfig.enableDocker}
                    onChange={(e) => updateConfig('enableDocker', e.target.checked)}
                    className="mt-0.5 accent-[#ccff00] w-4 h-4 bg-black border-white/20"
                  />
                  <div>
                    <div className="text-xs font-bold text-white uppercase">node:22-alpine Dockerfile</div>
                    <div className="text-[11px] text-white/50">Multi-stage build with non-root nodeapp</div>
                  </div>
                </label>

                <label className="flex items-start space-x-3 cursor-pointer p-3 bg-white/5 border border-white/10">
                  <input
                    type="checkbox"
                    checked={currentConfig.enableGithubActions}
                    onChange={(e) => updateConfig('enableGithubActions', e.target.checked)}
                    className="mt-0.5 accent-[#ccff00] w-4 h-4 bg-black border-white/20"
                  />
                  <div>
                    <div className="text-xs font-bold text-white uppercase">GitHub Actions CI/CD</div>
                    <div className="text-[11px] text-white/50">Automated lint, node:test & build workflow</div>
                  </div>
                </label>
              </div>
            </div>

            {/* Action Card */}
            <div className="bg-[#111111] border border-white/10 p-6 space-y-4 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>
              
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-[#ccff00] uppercase tracking-wider">
                  STATUS: READY
                </span>
                <span className="text-xs font-mono text-white/40">{files.length} FILES</span>
              </div>

              <p className="text-xs text-white/70 leading-relaxed font-light">
                Production architecture configured and compiled. Ready for direct export or code inspection.
              </p>

              <div className="space-y-2 pt-2">
                <button
                  onClick={onDownloadZip}
                  className="w-full py-3.5 px-4 bg-[#ccff00] hover:bg-[#b8e600] text-black font-black text-xs uppercase tracking-tighter transform hover:-translate-y-0.5 transition-all shadow-[0_0_15px_rgba(204,255,0,0.25)] flex items-center justify-center space-x-2"
                >
                  <span>RUN EXPORT .ZIP</span>
                  <ArrowRight className="w-4 h-4 stroke-[3]" />
                </button>

                <button
                  onClick={() => setActiveSubTab('files')}
                  className="w-full py-3 px-4 bg-white/5 hover:bg-white/10 text-white font-mono font-bold text-xs uppercase tracking-wider border border-white/10 transition-colors text-center"
                >
                  VIEW GENERATED SOURCE
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeSubTab === 'files' && (
        <FileTreeViewer
          files={files}
          projectName={currentConfig.projectName}
          onDownloadZip={onDownloadZip}
        />
      )}

      {activeSubTab === 'architecture' && (
        <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-8 relative">
          <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <div>
              <h3 className="text-2xl font-black uppercase tracking-tight text-white">
                NODE 22 ARCHITECTURE FLOW
              </h3>
              <p className="text-xs font-mono text-white/50 mt-1">
                LAYERED BOUNDARY FROM INCOMING HTTP/WS REQUEST TO V8 MAGLEV EXECUTION
              </p>
            </div>
            <span className="text-xs font-mono bg-white/5 text-[#ccff00] px-3 py-1.5 border border-white/10">
              PATTERN: {currentConfig.architecturePattern.toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            {/* Step 1 */}
            <div className="bg-[#111111] border border-white/10 p-5 space-y-3 relative">
              <span className="text-xl font-mono font-black text-[#ccff00]">01</span>
              <div className="font-black text-sm text-white uppercase tracking-wider">CLIENT LAYER</div>
              <div className="text-xs font-mono text-white/70">React 19 / WS</div>
              <p className="text-[11px] text-white/40 leading-snug">Vite 6 SPA / Mobile Client with SSE Streaming</p>
            </div>

            {/* Step 2 */}
            <div className="bg-[#111111] border border-white/10 p-5 space-y-3 relative">
              <span className="text-xl font-mono font-black text-[#ccff00]">02</span>
              <div className="font-black text-sm text-white uppercase tracking-wider">GATEWAY</div>
              <div className="text-xs font-mono text-white/70">{currentConfig.framework.toUpperCase()}</div>
              <p className="text-[11px] text-white/40 leading-snug">Helmet • CORS • Rate Limiting Security</p>
            </div>

            {/* Step 3 */}
            <div className="bg-[#111111] border border-white/10 p-5 space-y-3 relative">
              <span className="text-xl font-mono font-black text-[#ccff00]">03</span>
              <div className="font-black text-sm text-white uppercase tracking-wider">CONTROLLERS</div>
              <div className="text-xs font-mono text-white/70">Zod • {currentConfig.auth.toUpperCase()}</div>
              <p className="text-[11px] text-white/40 leading-snug">Strict Schema Validation & Claims Verification</p>
            </div>

            {/* Step 4 */}
            <div className="bg-[#111111] border border-white/10 p-5 space-y-3 relative">
              <span className="text-xl font-mono font-black text-[#ccff00]">04</span>
              <div className="font-black text-sm text-white uppercase tracking-wider">SERVICES</div>
              <div className="text-xs font-mono text-white/70">Domain Logic</div>
              <p className="text-[11px] text-white/40 leading-snug">Native crypto.randomUUID() & Business Rules</p>
            </div>

            {/* Step 5 */}
            <div className="bg-[#111111] border border-white/10 p-5 space-y-3 relative">
              <span className="text-xl font-mono font-black text-[#ccff00]">05</span>
              <div className="font-black text-sm text-white uppercase tracking-wider">STORAGE</div>
              <div className="text-xs font-mono text-white/70">{currentConfig.database.toUpperCase()}</div>
              <p className="text-[11px] text-white/40 leading-snug">node:sqlite DatabaseSync & Transactions</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
