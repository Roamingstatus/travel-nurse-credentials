import React from "react";
import { Check, Shield, FileText, Share2, ChevronDown, CheckCircle2 } from "lucide-react";
import "./_group.css";

export function PremiumPage() {
  return (
    <div className="min-h-screen bg-[#f4f4f5] font-sans text-[#18181b] flex flex-col">
      {/* Top Navigation */}
      <nav className="sticky top-0 z-50 w-full border-b border-zinc-200 bg-white/80 backdrop-blur-md">
        <div className="flex h-16 items-center px-6 max-w-7xl mx-auto w-full justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2 font-bold text-xl tracking-tight text-[#2563eb]">
              <Shield className="h-6 w-6" />
              <span>Credanta</span>
            </div>
            <div className="hidden md:flex gap-6 text-sm font-medium text-[#71717a]">
              <a href="#" className="hover:text-[#18181b] transition-colors">Dashboard</a>
              <a href="#" className="hover:text-[#18181b] transition-colors">Credentials</a>
              <a href="#" className="text-[#2563eb]">Premium</a>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="h-8 w-8 rounded-full bg-zinc-200 flex items-center justify-center text-sm font-medium">JD</div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="bg-animated-gradient w-full pt-20 pb-16 px-6 relative overflow-hidden">
        <div className="max-w-3xl mx-auto text-center relative z-10">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-6 animate-fade-up">
            Unlock your full <span className="text-[#2563eb]">credential vault</span>
          </h1>
          <p className="text-lg md:text-xl text-[#71717a] max-w-2xl mx-auto animate-fade-up delay-100">
            Upgrade to get smart reminders, recruiter sharing, and agency-ready compliance tools.
          </p>
        </div>
      </div>

      {/* Pricing Cards */}
      <div className="max-w-6xl mx-auto px-6 -mt-8 relative z-20 pb-24 w-full">
        <div className="grid md:grid-cols-3 gap-6 lg:gap-8 items-end">
          
          {/* Free Tier */}
          <div className="bg-white rounded-[12px] p-8 border border-zinc-200 credanta-shadow animate-fade-up delay-100 h-full flex flex-col">
            <div className="mb-6">
              <h3 className="text-xl font-semibold mb-2">Free</h3>
              <p className="text-[#71717a] text-sm h-10">Everything to get started</p>
              <div className="mt-4 flex items-baseline text-4xl font-bold">
                $0<span className="text-lg text-[#71717a] font-normal ml-1">/mo</span>
              </div>
            </div>
            <button className="w-full py-2.5 px-4 rounded-[12px] bg-zinc-100 text-zinc-400 font-medium mb-8 cursor-not-allowed">
              Your current plan
            </button>
            <div className="space-y-4 flex-1">
              <div className="flex items-start gap-3">
                <Check className="h-5 w-5 text-[#71717a] shrink-0 mt-0.5" />
                <span className="text-sm">Upload credentials</span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="h-5 w-5 text-[#71717a] shrink-0 mt-0.5" />
                <span className="text-sm">Basic expiry tracking</span>
              </div>
              <div className="flex items-start gap-3">
                <Check className="h-5 w-5 text-[#71717a] shrink-0 mt-0.5" />
                <span className="text-sm">Download ZIP packet</span>
              </div>
            </div>
          </div>

          {/* Premium Tier */}
          <div className="bg-white rounded-[12px] p-8 border-2 border-[#2563eb] premium-card-shadow relative transform md:-translate-y-4 animate-fade-up delay-200 h-full flex flex-col z-10">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#2563eb] text-white text-xs font-bold uppercase tracking-wider py-1 px-3 rounded-full">
              Most Popular
            </div>
            <div className="mb-6">
              <h3 className="text-xl font-semibold mb-2 text-[#2563eb]">Premium</h3>
              <p className="text-[#71717a] text-sm h-10">For the serious traveler</p>
              <div className="mt-4 flex items-baseline text-4xl font-bold">
                $9<span className="text-lg text-[#71717a] font-normal ml-1">/mo</span>
              </div>
            </div>
            <button className="w-full py-2.5 px-4 rounded-[12px] bg-[#2563eb] hover:bg-blue-700 text-white font-medium mb-8 transition-colors shadow-sm">
              Upgrade to Premium
            </button>
            <div className="space-y-4 flex-1">
              <div className="flex items-start gap-3">
                <Check className="h-5 w-5 text-[#2563eb] shrink-0 mt-0.5" />
                <span className="text-sm font-medium">Everything in Free</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-[#2563eb] shrink-0 mt-0.5" />
                <span className="text-sm">Smart expiry reminders</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-[#2563eb] shrink-0 mt-0.5" />
                <span className="text-sm">AI-powered checklist</span>
              </div>
              <div className="flex items-start gap-3">
                <FileText className="h-5 w-5 text-[#2563eb] shrink-0 mt-0.5" />
                <span className="text-sm">Resume export</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-[#2563eb] shrink-0 mt-0.5" />
                <span className="text-sm">Priority support</span>
              </div>
            </div>
          </div>

          {/* Premium+ Tier */}
          <div className="bg-white rounded-[12px] p-8 border border-zinc-200 credanta-shadow animate-fade-up delay-300 h-full flex flex-col">
            <div className="mb-6">
              <h3 className="text-xl font-semibold mb-2">Premium+</h3>
              <p className="text-[#71717a] text-sm h-10">For agency-ready nurses</p>
              <div className="mt-4 flex items-baseline text-4xl font-bold">
                $19<span className="text-lg text-[#71717a] font-normal ml-1">/mo</span>
              </div>
            </div>
            <button className="w-full py-2.5 px-4 rounded-[12px] bg-[#18181b] hover:bg-black text-white font-medium mb-8 transition-colors shadow-sm">
              Upgrade to Premium+
            </button>
            <div className="space-y-4 flex-1">
              <div className="flex items-start gap-3">
                <Check className="h-5 w-5 text-[#18181b] shrink-0 mt-0.5" />
                <span className="text-sm font-medium">Everything in Premium</span>
              </div>
              <div className="flex items-start gap-3">
                <Share2 className="h-5 w-5 text-[#18181b] shrink-0 mt-0.5" />
                <span className="text-sm">Recruiter share links</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-[#18181b] shrink-0 mt-0.5" />
                <span className="text-sm">Live public credential view</span>
              </div>
              <div className="flex items-start gap-3">
                <FileText className="h-5 w-5 text-[#18181b] shrink-0 mt-0.5" />
                <span className="text-sm">Agency packet builder</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-[#18181b] shrink-0 mt-0.5" />
                <span className="text-sm">White-glove onboarding</span>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Feature Comparison */}
      <div className="bg-white py-24 border-y border-zinc-200 w-full">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold mb-4">Compare Features</h2>
            <p className="text-[#71717a]">Find the perfect plan for your travel nursing career.</p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr>
                  <th className="py-4 px-6 border-b-2 border-zinc-200 font-medium text-[#71717a] w-2/5">Feature</th>
                  <th className="py-4 px-6 border-b-2 border-zinc-200 font-semibold text-center w-1/5">Free</th>
                  <th className="py-4 px-6 border-b-2 border-[#2563eb] font-semibold text-center text-[#2563eb] w-1/5">Premium</th>
                  <th className="py-4 px-6 border-b-2 border-zinc-200 font-semibold text-center w-1/5">Premium+</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {[
                  { name: "Upload credentials", free: true, prem: true, premPlus: true },
                  { name: "Basic expiry tracking", free: true, prem: true, premPlus: true },
                  { name: "Download ZIP packet", free: true, prem: true, premPlus: true },
                  { name: "Smart expiry reminders (SMS/Email)", free: false, prem: true, premPlus: true },
                  { name: "AI-powered compliance checklist", free: false, prem: true, premPlus: true },
                  { name: "Resume export & formatting", free: false, prem: true, premPlus: true },
                  { name: "Recruiter share links with analytics", free: false, prem: false, premPlus: true },
                  { name: "Agency packet builder", free: false, prem: false, premPlus: true },
                ].map((feature, i) => (
                  <tr key={i} className={i % 2 === 0 ? "bg-[#f4f4f5]/50" : ""}>
                    <td className="py-4 px-6 border-b border-zinc-100 font-medium">{feature.name}</td>
                    <td className="py-4 px-6 border-b border-zinc-100 text-center">
                      {feature.free ? <Check className="h-5 w-5 text-zinc-400 mx-auto" /> : <span className="text-zinc-300">—</span>}
                    </td>
                    <td className="py-4 px-6 border-b border-zinc-100 text-center bg-blue-50/30">
                      {feature.prem ? <Check className="h-5 w-5 text-[#2563eb] mx-auto" /> : <span className="text-zinc-300">—</span>}
                    </td>
                    <td className="py-4 px-6 border-b border-zinc-100 text-center">
                      {feature.premPlus ? <Check className="h-5 w-5 text-[#18181b] mx-auto" /> : <span className="text-zinc-300">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* FAQ Section */}
      <div className="max-w-5xl mx-auto px-6 py-24 w-full">
        <div className="text-center mb-16">
          <h2 className="text-3xl font-bold mb-4">Frequently Asked Questions</h2>
          <p className="text-[#71717a]">Everything you need to know about the product and billing.</p>
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          {[
            {
              q: "Can I cancel anytime?",
              a: "Yes, you can cancel your subscription at any time from your billing settings. You'll retain access to your premium features until the end of your current billing cycle."
            },
            {
              q: "What counts as a credential?",
              a: "A credential is any document required for compliance: state licenses, certifications (BLS, ACLS), medical records, fit tests, or background checks."
            },
            {
              q: "Is my data secure?",
              a: "Absolutely. We use bank-level encryption (AES-256) to store your documents. Your data is never shared with third parties without your explicit consent via share links."
            },
            {
              q: "How does recruiter sharing work?",
              a: "On Premium+, you can generate secure, expiring links to your credential packet. You control exactly which documents are included and can revoke access instantly."
            }
          ].map((faq, i) => (
            <div key={i} className="bg-white rounded-[12px] p-6 border border-zinc-200 credanta-shadow">
              <h4 className="font-semibold text-lg flex justify-between items-start mb-3">
                {faq.q}
                <ChevronDown className="h-5 w-5 text-[#71717a] shrink-0 mt-0.5 transform rotate-180" />
              </h4>
              <p className="text-[#71717a] text-sm leading-relaxed">
                {faq.a}
              </p>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}