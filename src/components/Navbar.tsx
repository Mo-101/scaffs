import React from 'react';
import {
  Layers,
  Sparkles,
  Cpu,
  Terminal,
  Activity,
  FolderTree,
  Download,
  Copy,
  Check,
  Zap,
} from 'lucide-react';
import { NodeSystemInfo } from '../types/scaffold';

export type ActiveTab = 'scaffold' | 'templates' | 'ai-architect' | 'sandbox' | 'inspector' | 'api-docs';

interface NavbarProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  systemInfo: NodeSystemInfo | null;
  onDownloadCurrentZip: () => void;
  projectName: string;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  systemInfo,
  onDownloadCurrentZip,
  projectName,
}) => {
  const [copiedCli, setCopiedCli] = React.useState(false);

  const handleCopyCli = () => {
    navigator.clipboard.writeText(`npx create-node22-app ${projectName.toLowerCase()} --template fullstack`);
    setCopiedCli(true);
    setTimeout(() => setCopiedCli(false), 2000);
  };

  const navItems: { id: ActiveTab; label: string; num: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'scaffold', label: 'SCAFFOLD ENGINE', num: '01', icon: FolderTree },
    { id: 'templates', label: 'STARTERS & BLUEPRINTS', num: '02', icon: Layers },
    { id: 'ai-architect', label: 'AI ARCHITECT', num: '03', icon: Sparkles },
    { id: 'sandbox', label: 'FEATURE LAB', num: '04', icon: Terminal },
    { id: 'inspector', label: 'V8 INSPECTOR', num: '05', icon: Activity },
    { id: 'api-docs', label: 'API SANDBOX', num: '06', icon: Zap },
  ];

  return (
    <header className="bg-[#0a0a0a] border-b border-white/10 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          {/* Logo & Headline */}
          <div className="flex items-baseline gap-3 cursor-pointer" onClick={() => setActiveTab('scaffold')}>
            <span className="text-[#ccff00] font-black text-4xl sm:text-5xl tracking-tighter select-none">
              N22
            </span>
            <div className="flex flex-col">
              <span className="text-sm sm:text-base font-light tracking-[0.25em] uppercase text-white/90">
                SCAFFOLD ENGINE
              </span>
              <span className="text-[10px] font-mono text-white/40 tracking-wider hidden sm:block">
                NODE 22 LTS • V8 MAGLEV • NATIVE ESM
              </span>
            </div>
          </div>

          {/* Center Nav */}
          <nav className="hidden lg:flex items-center space-x-1">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`flex items-center space-x-2 px-3 py-2 text-xs font-mono transition-all uppercase tracking-wider ${
                    isActive
                      ? 'bg-[#ccff00] text-black font-black shadow-[0_0_15px_rgba(204,255,0,0.3)]'
                      : 'text-white/60 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <span className={`text-[10px] ${isActive ? 'text-black/70' : 'text-[#ccff00]'}`}>
                    {item.num}
                  </span>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Right Action Items */}
          <div className="flex items-center space-x-3">
            {/* Version Pill */}
            <div className="hidden sm:flex items-center space-x-2 text-xs font-mono py-1.5 px-3 bg-white/5 border border-white/10 text-white/80">
              <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_10px_#ccff00]"></span>
              <span>{systemInfo ? systemInfo.nodeVersion : 'v22.x LTS'}</span>
            </div>

            <button
              onClick={handleCopyCli}
              title="Copy CLI command"
              className="hidden xl:flex items-center space-x-1.5 bg-white/5 hover:bg-white/10 text-white/80 text-xs px-3 py-2 border border-white/10 font-mono transition-colors"
            >
              {copiedCli ? <Check className="w-3.5 h-3.5 text-[#ccff00]" /> : <Copy className="w-3.5 h-3.5 text-white/40" />}
              <span>npx create-node22-app</span>
            </button>

            <button
              onClick={onDownloadCurrentZip}
              className="bg-[#ccff00] text-black hover:bg-[#b8e600] font-black text-xs px-4 py-2.5 uppercase tracking-tight flex items-center space-x-1.5 transform hover:-translate-y-0.5 transition-all shadow-[0_0_15px_rgba(204,255,0,0.25)]"
            >
              <Download className="w-4 h-4 stroke-[2.5]" />
              <span>EXPORT .ZIP</span>
            </button>
          </div>
        </div>

        {/* Mobile Navigation Row */}
        <div className="flex lg:hidden overflow-x-auto py-2.5 space-x-2 border-t border-white/10 scrollbar-none">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 text-xs font-mono whitespace-nowrap uppercase tracking-wider ${
                  isActive
                    ? 'bg-[#ccff00] text-black font-black'
                    : 'text-white/60 bg-white/5 border border-white/10 hover:text-white'
                }`}
              >
                <span className={`text-[10px] ${isActive ? 'text-black/70' : 'text-[#ccff00]'}`}>{item.num}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
