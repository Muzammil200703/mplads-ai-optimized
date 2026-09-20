import React from 'react';

export default function Landing({ onLaunch }) {
  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col justify-between p-8 font-sans">
      <header className="flex justify-between items-center max-w-6xl mx-auto w-full py-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-xl text-white shadow-lg shadow-indigo-500/30">M</div>
          <span className="text-xl font-bold tracking-tight text-white">MPLADS<span className="text-indigo-400">-AI</span></span>
        </div>
        <button onClick={onLaunch} className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-5 py-2.5 rounded-lg transition-all shadow-md hover:shadow-indigo-500/20 active:scale-95">
          Launch App &rarr;
        </button>
      </header>

      <main className="max-w-4xl mx-auto text-center py-20 px-4 flex-1 flex flex-col justify-center items-center">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-sm font-medium mb-8">
          <span>AI-Powered Public Expenditure Intelligence</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-white mb-6 leading-tight">
          Transparency & Forensics for <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">MPLADS Projects</span>
        </h1>
        <p className="text-lg md:text-xl text-slate-400 max-w-2xl mb-10 leading-relaxed">
          Real-time anomaly detection, audit risk scoring, and automated forensic tracking for parliamentary constituency development funds.
        </p>
        <div className="flex flex-col sm:flex-row space-y-4 sm:space-y-0 sm:space-x-4">
          <button onClick={onLaunch} className="bg-indigo-600 hover:bg-indigo-500 text-white text-lg font-semibold px-8 py-4 rounded-xl shadow-xl shadow-indigo-600/30 hover:shadow-indigo-500/40 transition-all active:scale-95">
            Explore Dashboard Now
          </button>
        </div>
      </main>

      <footer className="max-w-6xl mx-auto w-full py-6 text-center text-xs text-slate-500 border-t border-slate-800">
        &copy; 2026 MPLADS-AI Transparency Platform. All rights reserved.
      </footer>
    </div>
  );
}