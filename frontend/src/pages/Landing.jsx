import React from "react";
import { ShieldAlert, BrainCircuit, Search, CheckCircle2, ArrowRight } from "lucide-react";

export default function Landing({ onLaunch }) {
  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-50 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-600 rounded-lg text-white">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <span className="text-xl font-bold tracking-tight text-white">MPLADS Audit AI</span>
        </div>
        <button onClick={onLaunch} className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition flex items-center gap-2 shadow-lg shadow-indigo-500/20">
          Launch Dashboard <ArrowRight className="w-4 h-4" />
        </button>
      </header>
      <section className="px-8 py-20 max-w-6xl mx-auto text-center flex flex-col items-center justify-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-sm font-medium mb-6">
          <BrainCircuit className="w-4 h-4" /> AI-Driven Financial Integrity for Public Funds
        </div>
        <h1 className="text-4xl md:text-6xl font-extrabold text-white tracking-tight leading-tight max-w-4xl">
          Autonomous Anomaly Detection & Transparency for <span className="text-indigo-400">MPLADS Development Works</span>
        </h1>
        <p className="mt-6 text-lg text-slate-400 max-w-2xl leading-relaxed">
          Transforming public fund oversight into actionable, explainable intelligence. Detecting fund misuse, duplicate proposals, and physical vs. financial progress mismatches in real time.
        </p>
        <div className="mt-8 flex flex-wrap gap-4 justify-center">
          <button onClick={onLaunch} className="px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition text-lg flex items-center gap-2 shadow-xl shadow-indigo-600/25">
            Open Risk Intelligence Center <ArrowRight className="w-5 h-5" />
          </button>
        </div>
      </section>
      <section className="px-8 py-16 bg-slate-950/50 border-y border-slate-800">
        <div className="max-w-6xl mx-auto grid md:grid-cols-3 gap-8">
          <div className="p-6 rounded-xl bg-slate-900 border border-slate-800">
            <Search className="w-8 h-8 text-indigo-400 mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">The Anomaly Problem</h3>
            <p className="text-slate-400 text-sm leading-relaxed">Thousands of constituency projects receive 100% disbursed funds while physical completion remains stagnated or unverified due to manual oversight bottlenecks.</p>
          </div>
          <div className="p-6 rounded-xl bg-slate-900 border border-slate-800">
            <BrainCircuit className="w-8 h-8 text-emerald-400 mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">Explainable AI (XAI)</h3>
            <p className="text-slate-400 text-sm leading-relaxed">Every flag is backed by transparent statistical rules and feature attribution—showing auditors exactly why a project is high risk without black-box opacity.</p>
          </div>
          <div className="p-6 rounded-xl bg-slate-900 border border-slate-800">
            <CheckCircle2 className="w-8 h-8 text-cyan-400 mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">Auditor Decision Flow</h3>
            <p className="text-slate-400 text-sm leading-relaxed">Equips nodal officers and vigilance committees with verifiable audit trails, role-based workflows, direct resolution tracking, and citizen reporting access.</p>
          </div>
        </div>
      </section>
      <footer className="mt-auto border-t border-slate-800 bg-slate-950 px-8 py-6 text-center text-slate-500 text-sm">
        MPLADS AI Optimization System — Built for Transparency, Integrity, and Decision Support.
      </footer>
    </div>
  );
}