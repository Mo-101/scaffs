import { Link } from "react-router-dom";
import { ArrowRight, Bot, BarChart3, Zap, UserCircle2, Activity } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cardAccent } from "@/lib/cardAccents";
import { cn } from "@/lib/utils";

export function Home() {
  const { t } = useTranslation();

  const FEATURES = [
    {
      icon: Bot,
      title: t("home.featureAgent", "Financial AI Agent"),
      desc: t(
        "home.featureAgentDesc",
        "Natural-language quant research, multi-market strategy generation, and autonomous backtesting.",
      ),
      link: "/agent",
      badge: "ReAct Agent",
    },
    {
      icon: BarChart3,
      title: t("home.featureBacktest", "Factor & Portfolio Lab"),
      desc: t(
        "home.featureBacktestDesc",
        "Multi-asset risk parity, Sharpe optimization, and alpha synthesis across minute and daily bars.",
      ),
      link: "/alpha-zoo",
      badge: "Alpha Zoo",
    },
    {
      icon: Zap,
      title: t("home.featureStreaming", "Paper Trading Engine"),
      desc: t(
        "home.featureStreamingDesc",
        "Live Binance Testnet streaming, isolated-margin order execution, and fail-closed safety gates.",
      ),
      link: "/paper-trading",
      badge: "Live Bridge",
    },
    {
      icon: UserCircle2,
      title: t("home.featureReplay", "Shadow Account & Bias Audit"),
      desc: t(
        "home.featureReplayDesc",
        "Trade journal behavioral bias diagnostics, counterfactual replay, and 8-section attribution reports.",
      ),
      link: "/runtime",
      badge: "Shadow Ledger",
    },
  ];

  return (
    <div className="relative min-h-[90vh] flex flex-col items-center justify-center p-6 sm:p-10 space-y-12 overflow-hidden animate-in fade-in duration-500">
      {/* Ambient background holographic glow */}
      <div className="pointer-events-none absolute top-12 left-1/2 -translate-x-1/2 w-[500px] h-[500px] bg-primary/15 rounded-full blur-3xl -z-10" />
      <div className="pointer-events-none absolute bottom-10 right-1/4 w-80 h-80 bg-info/10 rounded-full blur-3xl -z-10" />

      {/* Hero Section */}
      <div className="max-w-3xl text-center space-y-6 flex flex-col items-center">
        {/* Live Status Pill */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-primary/30 bg-primary/10 text-xs font-mono tracking-wider text-primary backdrop-blur-md shadow-sm">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span>SCAFFS QUANT INTELLIGENCE • SYSTEM READY</span>
        </div>

        {/* Featured Second Image Emblem */}
        <div className="relative group my-2">
          <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-primary/50 via-info/40 to-primary/50 blur-lg opacity-70 group-hover:opacity-100 transition duration-500 animate-pulse" />
          <div className="relative h-44 w-44 sm:h-52 sm:w-52 rounded-3xl flex items-center justify-center border border-primary/40 bg-card/80 backdrop-blur-xl p-3 shadow-2xl transition-transform duration-300 group-hover:scale-105">
            <img
              src="/scaffs-home.png"
              alt="Scaffs Quantum Emblem"
              className="h-full w-full object-contain filter drop-shadow-[0_0_25px_rgba(56,189,248,0.35)]"
            />
          </div>
        </div>

        {/* Title & Tagline */}
        <div className="space-y-2">
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-foreground via-foreground/90 to-muted-foreground bg-clip-text text-transparent">
            {t("home.title", "Scaffs")}
          </h1>
          <p className="text-sm sm:text-base text-primary/90 font-mono tracking-wide font-medium">
            Financial AI Agent Team & Algorithmic Trading Platform
          </p>
          <p className="text-sm sm:text-base text-muted-foreground max-w-xl mx-auto leading-relaxed pt-1">
            {t(
              "home.subtitle",
              "Natural-language financial research, multi-factor alpha modeling, governed Binance paper trading, and automated behavioral shadow audit.",
            )}
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          <Link
            to="/agent"
            className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-sm transition-all shadow-md hover:shadow-primary/25 inline-flex items-center gap-2 group"
          >
            <span>{t("home.startResearch", "Start Research Agent")}</span>
            <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
          <Link
            to="/runtime"
            className="px-5 py-2.5 rounded-xl border border-border/80 hover:border-primary/40 bg-card/60 hover:bg-card text-foreground font-medium text-sm transition-all backdrop-blur-sm inline-flex items-center gap-2"
          >
            <Activity className="h-4 w-4 text-primary" />
            <span>Runtime Monitor</span>
          </Link>
        </div>
      </div>

      {/* Feature Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 max-w-6xl w-full">
        {FEATURES.map(({ icon: Icon, title, desc, link, badge }, i) => {
          const accent = cardAccent(i);
          return (
            <Link
              to={link}
              key={title}
              className={cn(
                "group glass-surface glass-card rounded-2xl p-5 space-y-3 bg-gradient-to-br transition-all duration-200 hover:-translate-y-1 hover:shadow-lg border cursor-pointer flex flex-col justify-between",
                accent.gradient,
                accent.border,
              )}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div
                    className={cn(
                      "inline-flex h-10 w-10 items-center justify-center rounded-xl transition-transform group-hover:scale-110",
                      accent.iconBg,
                    )}
                  >
                    <Icon className={cn("h-5 w-5", accent.text)} />
                  </div>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-md border border-border/60 bg-muted/40 text-muted-foreground">
                    {badge}
                  </span>
                </div>
                <div>
                  <h3 className="font-semibold text-sm text-foreground group-hover:text-primary transition-colors">
                    {title}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{desc}</p>
                </div>
              </div>
              <div className="pt-2 border-t border-border/30 flex items-center justify-between text-xs text-primary font-medium opacity-80 group-hover:opacity-100">
                <span>Explore</span>
                <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
