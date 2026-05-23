import React from 'react';
import { Home, Folder, Star, User, Plus, Bell, CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import './_group.css';

export function MobileDashboard() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-zinc-100/50 p-4 font-sans text-zinc-900">
      {/* Phone Frame */}
      <div className="w-[390px] h-[844px] bg-[#f4f4f5] rounded-[44px] shadow-2xl border-[8px] border-zinc-900 relative overflow-hidden flex flex-col">
        
        {/* Dynamic Island Area / Status Bar space */}
        <div className="h-12 w-full shrink-0 flex items-center justify-between px-6 pt-2">
           <span className="text-xs font-semibold">9:41</span>
           <div className="flex gap-1.5 items-center">
             <div className="w-4 h-3 bg-zinc-900 rounded-sm"></div>
             <div className="w-3 h-3 bg-zinc-900 rounded-full"></div>
             <div className="w-5 h-3 bg-zinc-900 rounded-sm"></div>
           </div>
        </div>

        {/* Header */}
        <header className="px-6 py-2 flex items-center justify-between shrink-0">
          <h1 className="text-xl font-bold tracking-tight text-zinc-900">Credanta</h1>
          <div className="flex items-center gap-3">
            <button className="relative p-2 rounded-full hover:bg-zinc-200/50 transition-colors">
              <Bell className="w-5 h-5 text-zinc-600" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full border-2 border-[#f4f4f5]"></span>
            </button>
            <div className="w-9 h-9 rounded-full bg-zinc-200 border-2 border-white shadow-sm overflow-hidden flex items-center justify-center">
              <img src="https://api.dicebear.com/7.x/notionists/svg?seed=Sarah" alt="User Avatar" className="w-full h-full object-cover" />
            </div>
          </div>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto hide-scrollbar pb-32">
          {/* Greeting */}
          <section className="px-6 py-6">
            <h2 className="text-2xl font-semibold mb-1">Good morning, Sarah 👋</h2>
            <p className="text-zinc-500 text-sm">Here is your compliance overview.</p>
          </section>

          {/* Status Summary */}
          <section className="px-6 mb-8 flex gap-3 overflow-x-auto hide-scrollbar pb-2">
            <div className="credanta-card shrink-0 w-32 p-4 flex flex-col gap-3 credanta-shadow">
              <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                <CheckCircle2 className="w-4 h-4 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-zinc-900">12</p>
                <p className="text-xs font-medium text-zinc-500">Valid</p>
              </div>
            </div>
            
            <div className="credanta-card shrink-0 w-32 p-4 flex flex-col gap-3 credanta-shadow border-amber-200 bg-amber-50/30">
              <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center">
                <Clock className="w-4 h-4 text-amber-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-zinc-900">2</p>
                <p className="text-xs font-medium text-zinc-500">Expiring</p>
              </div>
            </div>

            <div className="credanta-card shrink-0 w-32 p-4 flex flex-col gap-3 credanta-shadow border-red-200 bg-red-50/30">
              <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                <AlertCircle className="w-4 h-4 text-red-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-zinc-900">1</p>
                <p className="text-xs font-medium text-zinc-500">Expired</p>
              </div>
            </div>
          </section>

          {/* Credential List */}
          <section className="px-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Your Credentials</h3>
              <button className="text-sm font-medium text-blue-600 hover:text-blue-700">View all</button>
            </div>
            
            <div className="flex flex-col gap-3">
              {/* Row 1: Valid */}
              <div className="credanta-card p-4 flex items-center justify-between credanta-shadow relative overflow-hidden group cursor-pointer">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-green-500"></div>
                <div className="flex items-center gap-4 pl-2">
                  <div className="w-10 h-10 rounded-xl bg-zinc-100 flex items-center justify-center text-xl">📜</div>
                  <div>
                    <h4 className="font-semibold text-[15px] text-zinc-900">RN License</h4>
                    <p className="text-xs text-zinc-500 mt-0.5">Expires Dec 2026</p>
                  </div>
                </div>
                <span className="px-2.5 py-1 text-[10px] font-bold tracking-wide uppercase bg-green-100 text-green-700 rounded-full">Valid</span>
              </div>

              {/* Row 2: Expiring */}
              <div className="credanta-card p-4 flex items-center justify-between credanta-shadow relative overflow-hidden group cursor-pointer bg-amber-50/10">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-500"></div>
                <div className="flex items-center gap-4 pl-2">
                  <div className="w-10 h-10 rounded-xl bg-zinc-100 flex items-center justify-center text-xl">🏥</div>
                  <div>
                    <h4 className="font-semibold text-[15px] text-zinc-900">BLS Certification</h4>
                    <p className="text-xs text-amber-600 font-medium mt-0.5">Expires in 14 days</p>
                  </div>
                </div>
                <span className="px-2.5 py-1 text-[10px] font-bold tracking-wide uppercase bg-amber-100 text-amber-700 rounded-full">Expiring</span>
              </div>

              {/* Row 3: Expired */}
              <div className="credanta-card p-4 flex items-center justify-between credanta-shadow relative overflow-hidden group cursor-pointer bg-red-50/10 border-red-200">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-red-500"></div>
                <div className="flex items-center gap-4 pl-2">
                  <div className="w-10 h-10 rounded-xl bg-zinc-100 flex items-center justify-center text-xl">🫀</div>
                  <div>
                    <h4 className="font-semibold text-[15px] text-zinc-900">ACLS Certification</h4>
                    <p className="text-xs text-red-600 font-medium mt-0.5">Expired Mar 2024</p>
                  </div>
                </div>
                <span className="px-2.5 py-1 text-[10px] font-bold tracking-wide uppercase bg-red-100 text-red-700 rounded-full">Expired</span>
              </div>

              {/* Row 4: Valid */}
              <div className="credanta-card p-4 flex items-center justify-between credanta-shadow relative overflow-hidden group cursor-pointer">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-green-500"></div>
                <div className="flex items-center gap-4 pl-2">
                  <div className="w-10 h-10 rounded-xl bg-zinc-100 flex items-center justify-center text-xl">🔒</div>
                  <div>
                    <h4 className="font-semibold text-[15px] text-zinc-900">HIPAA Training</h4>
                    <p className="text-xs text-zinc-500 mt-0.5">Expires Aug 2026</p>
                  </div>
                </div>
                <span className="px-2.5 py-1 text-[10px] font-bold tracking-wide uppercase bg-green-100 text-green-700 rounded-full">Valid</span>
              </div>
            </div>
          </section>
        </div>

        {/* FAB */}
        <button className="absolute bottom-[104px] right-6 w-14 h-14 bg-blue-600 hover:bg-blue-700 text-white rounded-full flex items-center justify-center shadow-lg shadow-blue-600/30 transition-transform active:scale-95">
          <Plus className="w-6 h-6" />
        </button>

        {/* Bottom Nav */}
        <nav className="absolute bottom-0 left-0 right-0 h-24 credanta-glass border-t border-zinc-200/60 pb-8 px-6 flex items-center justify-between z-10">
          <button className="flex flex-col items-center gap-1 min-w-[64px] py-2 px-3 rounded-2xl bg-blue-50 text-blue-600 transition-colors">
            <Home className="w-6 h-6 fill-blue-600/20" strokeWidth={2.5} />
            <span className="text-[10px] font-semibold">Home</span>
          </button>
          
          <button className="flex flex-col items-center gap-1 min-w-[64px] py-2 px-3 rounded-2xl text-zinc-400 hover:text-zinc-600 transition-colors">
            <Folder className="w-6 h-6" strokeWidth={2} />
            <span className="text-[10px] font-medium">Docs</span>
          </button>
          
          <button className="flex flex-col items-center gap-1 min-w-[64px] py-2 px-3 rounded-2xl text-zinc-400 hover:text-zinc-600 transition-colors">
            <Star className="w-6 h-6" strokeWidth={2} />
            <span className="text-[10px] font-medium">Premium</span>
          </button>
          
          <button className="flex flex-col items-center gap-1 min-w-[64px] py-2 px-3 rounded-2xl text-zinc-400 hover:text-zinc-600 transition-colors">
            <User className="w-6 h-6" strokeWidth={2} />
            <span className="text-[10px] font-medium">Profile</span>
          </button>
        </nav>
        
      </div>
    </div>
  );
}
