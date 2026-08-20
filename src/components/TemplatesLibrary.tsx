import React, { useState } from 'react';
import {
  Layers,
  Cpu,
  Sparkles,
  Radio,
  Package,
  Download,
  Eye,
  CheckCircle,
  ArrowRight,
  Search,
} from 'lucide-react';
import { ProjectTemplate } from '../types/scaffold';
import { TEMPLATES } from '../data/templates';
import { downloadProjectZip } from '../utils/zipExport';
import { FileTreeViewer } from './FileTreeViewer';

interface TemplatesLibraryProps {
  onLoadTemplate: (template: ProjectTemplate) => void;
}

export const TemplatesLibrary: React.FC<TemplatesLibraryProps> = ({ onLoadTemplate }) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [previewTemplate, setPreviewTemplate] = useState<ProjectTemplate | null>(null);

  const categories = ['All', 'Full-Stack', 'Microservice', 'AI & LLM', 'Real-Time', 'Enterprise'];

  const filteredTemplates = TEMPLATES.filter((tpl) => {
    const matchesCategory = selectedCategory === 'All' || tpl.category === selectedCategory;
    const matchesSearch =
      tpl.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tpl.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tpl.tagline.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="space-y-8">
      {/* Header & Filter Bar */}
      <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="flex items-center space-x-2 text-xs font-mono font-bold text-[#ccff00] mb-2 uppercase tracking-widest">
              <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></span>
              <span>VERIFIED PRODUCTION BLUEPRINTS</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-black text-white tracking-tighter uppercase">
              STARTERS & BLUEPRINTS
            </h2>
            <p className="text-sm font-light text-white/60 mt-2 max-w-2xl leading-relaxed">
              Complete, end-to-end architectures engineered for extreme throughput, zero runtime bloat, and modern Node 22 LTS standard APIs.
            </p>
          </div>

          {/* Search Box */}
          <div className="relative w-full md:w-80">
            <Search className="w-4 h-4 text-white/40 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search blueprints..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#111111] border border-white/10 pl-10 pr-4 py-3 text-xs text-white font-mono placeholder-white/30 focus:outline-none focus:border-[#ccff00]"
            />
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex items-center space-x-2 overflow-x-auto pt-4 border-t border-white/10 scrollbar-none">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-4 py-2 text-xs font-mono uppercase tracking-wider transition-all shrink-0 font-bold ${
                selectedCategory === cat
                  ? 'bg-[#ccff00] text-black shadow-[0_0_15px_rgba(204,255,0,0.3)]'
                  : 'bg-white/5 border border-white/10 text-white/60 hover:text-white hover:bg-white/10'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Templates Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredTemplates.map((template) => (
          <div
            key={template.id}
            className="bg-[#0a0a0a] border border-white/10 hover:border-white/30 p-6 flex flex-col justify-between transition-all relative group"
          >
            <div className="space-y-4">
              {/* Header Badge */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-widest text-[#ccff00] font-bold">
                  {template.category}
                </span>
                <span className="text-[9px] font-mono px-2 py-0.5 bg-white/5 text-white/80 border border-white/10 font-bold uppercase">
                  {template.badge}
                </span>
              </div>

              {/* Title & Tagline */}
              <div>
                <h3 className="text-xl font-black text-white tracking-tight uppercase group-hover:text-[#ccff00] transition-colors">
                  {template.name}
                </h3>
                <p className="text-xs text-white/60 mt-2 leading-relaxed font-light">{template.tagline}</p>
              </div>

              {/* Highlights */}
              <ul className="space-y-2 pt-3 border-t border-white/10 font-mono text-[11px] text-white/70">
                {template.highlights.slice(0, 3).map((hl, idx) => (
                  <li key={idx} className="flex items-start space-x-2">
                    <span className="text-[#ccff00] font-black">›</span>
                    <span className="line-clamp-1">{hl}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Actions */}
            <div className="pt-6 mt-6 border-t border-white/10 flex items-center justify-between gap-3">
              <button
                onClick={() => setPreviewTemplate(template)}
                className="flex items-center space-x-1.5 text-xs font-mono text-white/70 hover:text-white bg-white/5 hover:bg-white/10 px-3.5 py-2.5 border border-white/10 transition-colors uppercase tracking-wider font-bold"
              >
                <Eye className="w-3.5 h-3.5" />
                <span>INSPECT</span>
              </button>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => downloadProjectZip(template.config.projectName, template.files)}
                  title="Download .ZIP directly"
                  className="p-2.5 bg-white/5 hover:bg-white/10 text-white border border-white/10 transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                </button>

                <button
                  onClick={() => onLoadTemplate(template)}
                  className="flex items-center space-x-1.5 text-xs bg-[#ccff00] hover:bg-[#b8e600] text-black font-black px-4 py-2.5 uppercase tracking-tight transition-all shadow-[0_0_10px_rgba(204,255,0,0.2)]"
                >
                  <span>LOAD</span>
                  <ArrowRight className="w-3.5 h-3.5 stroke-[3]" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Preview Modal */}
      {previewTemplate && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
          <div className="bg-[#0a0a0a] border border-white/10 w-full max-w-5xl shadow-2xl flex flex-col max-h-[90vh] relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

            {/* Modal Header */}
            <div className="p-6 border-b border-white/10 flex items-center justify-between bg-[#111111]/60">
              <div>
                <span className="text-[10px] font-mono text-[#ccff00] uppercase tracking-widest font-bold">
                  {previewTemplate.category}
                </span>
                <h3 className="text-xl font-black text-white uppercase tracking-tight">{previewTemplate.name}</h3>
              </div>

              <div className="flex items-center space-x-3">
                <button
                  onClick={() => {
                    onLoadTemplate(previewTemplate);
                    setPreviewTemplate(null);
                  }}
                  className="px-4 py-2 bg-[#ccff00] hover:bg-[#b8e600] text-black font-black text-xs uppercase tracking-tight transition-all flex items-center space-x-1.5"
                >
                  <span>USE IN STUDIO</span>
                  <ArrowRight className="w-3.5 h-3.5 stroke-[3]" />
                </button>
                <button
                  onClick={() => setPreviewTemplate(null)}
                  className="px-3 py-2 bg-white/5 hover:bg-white/10 text-white/60 hover:text-white font-mono text-xs border border-white/10"
                >
                  ESC [✕]
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1">
              <FileTreeViewer
                files={previewTemplate.files}
                projectName={previewTemplate.config.projectName}
                onDownloadZip={() => downloadProjectZip(previewTemplate.config.projectName, previewTemplate.files)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
