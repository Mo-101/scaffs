import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TrendingUp,
  Globe,
  Sparkles,
  Users,
  UserCircle2,
  NotebookPen,
  Landmark,
  ArrowRight,
  Zap,
  Terminal,
  Layers,
  ChevronRight,
  Filter,
} from "lucide-react";

interface Example {
  titleKey: string;
  descKey: string;
  promptKey: string;
}

interface Category {
  id: string;
  labelKey: string;
  icon: React.ReactNode;
  accentColor: string;
  glowColor: string;
  badgeClass: string;
  examples: Example[];
}

const CATEGORIES: Category[] = [
  {
    id: "backtest",
    labelKey: "welcome.categories.multiMarketBacktest",
    icon: <TrendingUp className="h-4 w-4" />,
    accentColor: "from-emerald-500/20 via-emerald-500/5 to-transparent border-emerald-500/30 text-emerald-400",
    glowColor: "hover:border-emerald-500/50 hover:shadow-[0_0_20px_rgba(16,185,129,0.15)]",
    badgeClass: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    examples: [
      {
        titleKey: "welcome.examples.crossMarketPortfolio",
        descKey: "welcome.examples.crossMarketPortfolioDesc",
        promptKey: "welcome.examples.crossMarketPortfolioPrompt",
      },
      {
        titleKey: "welcome.examples.btcMacd",
        descKey: "welcome.examples.btcMacdDesc",
        promptKey: "welcome.examples.btcMacdPrompt",
      },
      {
        titleKey: "welcome.examples.usTechMaxDiv",
        descKey: "welcome.examples.usTechMaxDivDesc",
        promptKey: "welcome.examples.usTechMaxDivPrompt",
      },
    ],
  },
  {
    id: "research",
    labelKey: "welcome.categories.researchAnalysis",
    icon: <Sparkles className="h-4 w-4" />,
    accentColor: "from-amber-500/20 via-amber-500/5 to-transparent border-amber-500/30 text-amber-400",
    glowColor: "hover:border-amber-500/50 hover:shadow-[0_0_20px_rgba(245,158,11,0.15)]",
    badgeClass: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    examples: [
      {
        titleKey: "welcome.examples.multiFactorAlpha",
        descKey: "welcome.examples.multiFactorAlphaDesc",
        promptKey: "welcome.examples.multiFactorAlphaPrompt",
      },
      {
        titleKey: "welcome.examples.optionsGreeks",
        descKey: "welcome.examples.optionsGreeksDesc",
        promptKey: "welcome.examples.optionsGreeksPrompt",
      },
    ],
  },
  {
    id: "swarm",
    labelKey: "welcome.categories.swarmTeams",
    icon: <Users className="h-4 w-4" />,
    accentColor: "from-violet-500/20 via-violet-500/5 to-transparent border-violet-500/30 text-violet-400",
    glowColor: "hover:border-violet-500/50 hover:shadow-[0_0_20px_rgba(139,92,246,0.15)]",
    badgeClass: "bg-violet-500/10 text-violet-400 border-violet-500/30",
    examples: [
      {
        titleKey: "welcome.examples.investmentCommittee",
        descKey: "welcome.examples.investmentCommitteeDesc",
        promptKey: "welcome.examples.investmentCommitteePrompt",
      },
      {
        titleKey: "welcome.examples.quantStrategyDesk",
        descKey: "welcome.examples.quantStrategyDeskDesc",
        promptKey: "welcome.examples.quantStrategyDeskPrompt",
      },
    ],
  },
  {
    id: "docweb",
    labelKey: "welcome.categories.docWebResearch",
    icon: <Globe className="h-4 w-4" />,
    accentColor: "from-blue-500/20 via-blue-500/5 to-transparent border-blue-500/30 text-blue-400",
    glowColor: "hover:border-blue-500/50 hover:shadow-[0_0_20px_rgba(59,130,246,0.15)]",
    badgeClass: "bg-blue-500/10 text-blue-400 border-blue-500/30",
    examples: [
      {
        titleKey: "welcome.examples.earningsReport",
        descKey: "welcome.examples.earningsReportDesc",
        promptKey: "welcome.examples.earningsReportPrompt",
      },
      {
        titleKey: "welcome.examples.macroResearch",
        descKey: "welcome.examples.macroResearchDesc",
        promptKey: "welcome.examples.macroResearchPrompt",
      },
    ],
  },
  {
    id: "journal",
    labelKey: "welcome.categories.tradeJournal",
    icon: <NotebookPen className="h-4 w-4" />,
    accentColor: "from-orange-500/20 via-orange-500/5 to-transparent border-orange-500/30 text-orange-400",
    glowColor: "hover:border-orange-500/50 hover:shadow-[0_0_20px_rgba(249,115,22,0.15)]",
    badgeClass: "bg-orange-500/10 text-orange-400 border-orange-500/30",
    examples: [
      {
        titleKey: "welcome.examples.analyzeBrokerExport",
        descKey: "welcome.examples.analyzeBrokerExportDesc",
        promptKey: "welcome.examples.analyzeBrokerExportPrompt",
      },
      {
        titleKey: "welcome.examples.diagnoseBehavior",
        descKey: "welcome.examples.diagnoseBehaviorDesc",
        promptKey: "welcome.examples.diagnoseBehaviorPrompt",
      },
    ],
  },
  {
    id: "connectors",
    labelKey: "welcome.categories.tradingConnectors",
    icon: <Landmark className="h-4 w-4" />,
    accentColor: "from-cyan-500/20 via-cyan-500/5 to-transparent border-cyan-500/30 text-cyan-400",
    glowColor: "hover:border-cyan-500/50 hover:shadow-[0_0_20px_rgba(6,182,212,0.15)]",
    badgeClass: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
    examples: [
      {
        titleKey: "welcome.examples.checkConnector",
        descKey: "welcome.examples.checkConnectorDesc",
        promptKey: "welcome.examples.checkConnectorPrompt",
      },
      {
        titleKey: "welcome.examples.analyzePortfolio",
        descKey: "welcome.examples.analyzePortfolioDesc",
        promptKey: "welcome.examples.analyzePortfolioPrompt",
      },
      {
        titleKey: "welcome.examples.quoteTrend",
        descKey: "welcome.examples.quoteTrendDesc",
        promptKey: "welcome.examples.quoteTrendPrompt",
      },
    ],
  },
  {
    id: "shadow",
    labelKey: "welcome.categories.shadowAccount",
    icon: <UserCircle2 className="h-4 w-4" />,
    accentColor: "from-teal-500/20 via-teal-500/5 to-transparent border-teal-500/30 text-teal-400",
    glowColor: "hover:border-teal-500/50 hover:shadow-[0_0_20px_rgba(20,184,166,0.15)]",
    badgeClass: "bg-teal-500/10 text-teal-400 border-teal-500/30",
    examples: [
      {
        titleKey: "welcome.examples.trainShadow",
        descKey: "welcome.examples.trainShadowDesc",
        promptKey: "welcome.examples.trainShadowPrompt",
      },
      {
        titleKey: "welcome.examples.shadowDelta",
        descKey: "welcome.examples.shadowDeltaDesc",
        promptKey: "welcome.examples.shadowDeltaPrompt",
      },
      {
        titleKey: "welcome.examples.shadowReport",
        descKey: "welcome.examples.shadowReportDesc",
        promptKey: "welcome.examples.shadowReportPrompt",
      },
    ],
  },
];

const CAPABILITY_CHIPS = [
  { key: "welcome.capabilities.financeSkills", icon: Zap },
  { key: "welcome.capabilities.swarmTeams", icon: Users },
  { key: "welcome.capabilities.autoTools", icon: Terminal },
  { key: "welcome.capabilities.markets", icon: Globe },
  { key: "welcome.capabilities.connectors", icon: Landmark },
  { key: "welcome.capabilities.timeframes", icon: TrendingUp },
  { key: "welcome.capabilities.optimizers", icon: Layers },
  { key: "welcome.capabilities.riskMetrics", icon: Sparkles },
  { key: "welcome.capabilities.options", icon: Sparkles },
  { key: "welcome.capabilities.pdfWeb", icon: Globe },
  { key: "welcome.capabilities.factorML", icon: Layers },
  { key: "welcome.capabilities.journalAnalyzer", icon: NotebookPen },
  { key: "welcome.capabilities.shadowBacktest", icon: UserCircle2 },
  { key: "welcome.capabilities.memory", icon: Zap },
  { key: "welcome.capabilities.sessionSearch", icon: Terminal },
] as const;

interface Props {
  onExample: (s: string) => void;
}

export function WelcomeScreen({ onExample }: Props) {
  const { t } = useTranslation();
  const [activeCategory, setActiveCategory] = useState<string>("all");

  const filteredCategories =
    activeCategory === "all"
      ? CATEGORIES
      : CATEGORIES.filter((c) => c.id === activeCategory);

  return (
    <div className="relative w-full max-w-5xl mx-auto py-6 px-4 space-y-8 animate-in fade-in duration-500">
      {/* Ambient background glow effects */}
      <div className="pointer-events-none absolute -top-12 left-1/2 -translate-x-1/2 w-96 h-96 bg-primary/10 rounded-full blur-3xl -z-10" />
      <div className="pointer-events-none absolute top-1/3 right-10 w-72 h-72 bg-info/10 rounded-full blur-3xl -z-10" />

      {/* Hero Header Section */}
      <div className="flex flex-col items-center text-center space-y-4">
        {/* Futuristic Status Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/10 text-xs font-mono tracking-wider text-primary backdrop-blur-md shadow-sm">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span>SCAFFS QUANT INTELLIGENCE • LIVE RUNTIME</span>
        </div>

        {/* Brand Icon & Heading */}
        <div className="relative group">
          <div className="h-20 w-20 mx-auto rounded-3xl flex items-center justify-center shadow-xl border border-primary/30 bg-gradient-to-b from-card to-background p-2 transition-all duration-300 group-hover:scale-105 group-hover:border-primary/60 group-hover:shadow-primary/20">
            <img
              src="/Scaffs.png"
              alt="Scaffs"
              className="h-full w-full object-contain filter drop-shadow-md"
            />
          </div>
        </div>

        <div className="space-y-1.5 max-w-xl">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-foreground via-foreground/90 to-muted-foreground bg-clip-text text-transparent">
            {t("welcome.title", "Scaffs")}
          </h1>
          <p className="text-xs sm:text-sm font-medium text-primary/90 font-mono tracking-wide">
            {t("welcome.subtitle", "Financial AI Agent & Algorithmic Trading Platform")}
          </p>
          <p className="text-sm text-muted-foreground leading-relaxed pt-1">
            {t("welcome.describePrompt", "Describe a trading strategy to get started.")}
          </p>
        </div>

        {/* Futuristic Interactive Capability Matrix Chips */}
        <div className="flex flex-wrap justify-center gap-1.5 max-w-3xl pt-2">
          {CAPABILITY_CHIPS.map(({ key, icon: Icon }) => {
            const label = t(key as any);
            return (
              <button
                key={key}
                type="button"
                onClick={() => onExample(`Backtest a multi-asset quantitative strategy leveraging ${label}.`)}
                className="group inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-card/60 hover:bg-primary/15 border border-border/70 hover:border-primary/40 text-muted-foreground hover:text-primary transition-all duration-150 backdrop-blur-sm cursor-pointer shadow-2xs hover:shadow-xs"
                title={`Click to formulate a strategy prompt with ${label}`}
              >
                <Icon className="h-3 w-3 text-primary/70 group-hover:text-primary transition-colors" />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Interactive Examples Section */}
      <div className="space-y-4">
        {/* Filter Navigation Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/50 pb-3">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold tracking-tight text-foreground">
              {t("welcome.tryExample", "Try an example:")}
            </span>
          </div>

          {/* Interactive Category Filter Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setActiveCategory("all")}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                activeCategory === "all"
                  ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                  : "bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              All Categories
            </button>
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setActiveCategory(cat.id)}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  activeCategory === cat.id
                    ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                    : "bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground"
                }`}
              >
                {cat.icon}
                <span>{t(cat.labelKey as any)}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Futuristic Card Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {filteredCategories.map((cat) =>
            cat.examples.map((ex) => (
              <div
                key={ex.titleKey}
                onClick={() => onExample(t(ex.promptKey as any))}
                className={`group relative flex flex-col justify-between p-4 rounded-2xl border bg-gradient-to-b from-card/80 via-card/40 to-background/80 backdrop-blur-md transition-all duration-200 cursor-pointer ${cat.accentColor} ${cat.glowColor} hover:-translate-y-0.5 hover:shadow-lg`}
              >
                {/* Top Badge & Category */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-semibold border ${cat.badgeClass}`}
                    >
                      {cat.icon}
                      <span>{t(cat.labelKey as any)}</span>
                    </span>
                    <span className="opacity-0 group-hover:opacity-100 transition-opacity text-xs font-mono font-medium text-primary inline-flex items-center gap-0.5">
                      Launch <ArrowRight className="h-3 w-3" />
                    </span>
                  </div>

                  {/* Card Title & Desc */}
                  <div>
                    <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors leading-snug">
                      {t(ex.titleKey as any)}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                      {t(ex.descKey as any)}
                    </p>
                  </div>
                </div>

                {/* Bottom Prompt Snippet Trigger */}
                <div className="mt-3 pt-2.5 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                  <span className="truncate pr-2 opacity-70 group-hover:opacity-100">
                    {t(ex.promptKey as any)}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Cyber Quick Command Bar */}
      <div className="w-full rounded-xl border border-primary/20 bg-card/60 backdrop-blur-md p-3 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-xs">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
          <Terminal className="h-4 w-4 text-primary shrink-0" />
          <span className="text-primary font-bold">scaffs&gt;</span>
          <span className="text-foreground/90 font-sans text-xs">
            e.g. Create a dual MA crossover strategy for 000001.SZ, backtest 2024
          </span>
        </div>
        <button
          type="button"
          onClick={() =>
            onExample("Create a dual MA crossover strategy for 000001.SZ, backtest 2024")
          }
          className="shrink-0 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium transition-all shadow-xs inline-flex items-center gap-1.5 cursor-pointer"
        >
          <span>Run Prompt</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
