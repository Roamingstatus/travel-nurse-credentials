import React from "react";
import { 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  Upload, 
  MoreHorizontal, 
  ShieldCheck,
  Eye,
  LogOut,
  Contrast,
  ArrowRight
} from "lucide-react";
import "./_group.css";

export function DesktopDashboard() {
  return (
    <div className="min-h-screen bg-[#f4f4f5] text-[#18181b] font-sans antialiased overflow-hidden flex flex-col">
      {/* Topbar */}
      <header className="sticky top-0 z-50 credanta-glass border-b border-zinc-200 px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-12">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-blue-600" />
            <span className="text-xl font-bold tracking-tight text-zinc-900">Credanta</span>
          </div>
          
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium">
            <a href="#" className="relative text-zinc-900 h-16 flex items-center">
              Dashboard
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 rounded-t-full" />
            </a>
            <a href="#" className="text-zinc-500 hover:text-zinc-900 transition-colors h-16 flex items-center">
              Credentials
            </a>
            <a href="#" className="text-zinc-500 hover:text-zinc-900 transition-colors h-16 flex items-center">
              Premium
            </a>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <button className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-zinc-100 text-zinc-500 transition-colors">
            <Contrast className="w-5 h-5" />
          </button>
          <div className="w-px h-6 bg-zinc-200" />
          <button className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-zinc-100 text-zinc-600 text-sm font-medium transition-colors">
            Sign out
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full max-w-[920px] mx-auto px-6 pt-12 pb-24">
        
        {/* Hero Section */}
        <section className="mb-10">
          <h1 className="text-3xl font-bold tracking-tight mb-2">Sarah Chen, RN</h1>
          <div className="flex items-center gap-4">
            <span className="text-[15px] text-zinc-500 font-medium">Your credential vault is 85% complete</span>
            <div className="w-48 h-2 bg-zinc-200 rounded-full overflow-hidden">
              <div className="h-full bg-blue-600 animate-progress rounded-full" style={{ width: '85%' }} />
            </div>
          </div>
        </section>

        {/* Alert Banner */}
        <div className="mb-10 flex items-center justify-between bg-amber-50 border border-amber-200/60 rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center text-amber-600">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <span className="text-[15px] font-medium text-amber-900">2 credentials expiring soon</span>
          </div>
          <button className="text-sm font-medium text-amber-700 hover:text-amber-800 flex items-center gap-1 transition-colors">
            Review now <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        {/* Status Cards */}
        <section className="mb-12">
          <h2 className="text-lg font-semibold mb-4 text-zinc-900">Credential Status</h2>
          <div className="grid grid-cols-3 gap-4">
            {/* Valid */}
            <div className="credanta-card credanta-shadow p-5 relative overflow-hidden group cursor-default">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-emerald-500" />
              <div className="flex items-start justify-between mb-2">
                <span className="text-sm font-medium text-zinc-500">Valid</span>
                <CheckCircle2 className="w-5 h-5 text-emerald-500 opacity-80" />
              </div>
              <div className="text-[32px] font-bold text-zinc-900">12</div>
            </div>

            {/* Expiring Soon */}
            <div className="credanta-card credanta-shadow p-5 relative overflow-hidden group cursor-default">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-500" />
              <div className="flex items-start justify-between mb-2">
                <span className="text-sm font-medium text-zinc-500">Expiring Soon</span>
                <AlertTriangle className="w-5 h-5 text-amber-500 opacity-80" />
              </div>
              <div className="text-[32px] font-bold text-zinc-900">2</div>
            </div>

            {/* Expired */}
            <div className="credanta-card credanta-shadow p-5 relative overflow-hidden group cursor-default">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-red-500" />
              <div className="flex items-start justify-between mb-2">
                <span className="text-sm font-medium text-zinc-500">Expired</span>
                <XCircle className="w-5 h-5 text-red-500 opacity-80" />
              </div>
              <div className="text-[32px] font-bold text-zinc-900">1</div>
            </div>
          </div>
        </section>

        {/* Recent Credentials List */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-zinc-900">Recent Credentials</h2>
            <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-sm">
              <Upload className="w-4 h-4" />
              Upload Credential
            </button>
          </div>

          <div className="credanta-card overflow-hidden">
            <table className="w-full text-left text-[15px]">
              <thead className="bg-zinc-50/50 border-b border-zinc-200 text-sm font-medium text-zinc-500">
                <tr>
                  <th className="px-5 py-3 font-medium">Credential</th>
                  <th className="px-5 py-3 font-medium">Expiry</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                
                <tr className="hover:bg-zinc-50/50 transition-colors group">
                  <td className="px-5 py-4">
                    <div className="font-medium text-zinc-900">State Nursing License (CA)</div>
                    <div className="text-sm text-zinc-500 mt-0.5">Board of Registered Nursing</div>
                  </td>
                  <td className="px-5 py-4 text-zinc-600">Oct 31, 2024</td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200/50">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Valid
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>

                <tr className="hover:bg-zinc-50/50 transition-colors group">
                  <td className="px-5 py-4">
                    <div className="font-medium text-zinc-900">BLS Certification</div>
                    <div className="text-sm text-zinc-500 mt-0.5">American Heart Association</div>
                  </td>
                  <td className="px-5 py-4 text-zinc-600">Dec 15, 2023</td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200/50">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Expiring Soon
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>

                <tr className="hover:bg-zinc-50/50 transition-colors group">
                  <td className="px-5 py-4">
                    <div className="font-medium text-zinc-900">ACLS Certification</div>
                    <div className="text-sm text-zinc-500 mt-0.5">American Heart Association</div>
                  </td>
                  <td className="px-5 py-4 text-zinc-600">Jan 22, 2024</td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200/50">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Expiring Soon
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>

                <tr className="hover:bg-zinc-50/50 transition-colors group">
                  <td className="px-5 py-4">
                    <div className="font-medium text-zinc-900">PALS Certification</div>
                    <div className="text-sm text-zinc-500 mt-0.5">American Heart Association</div>
                  </td>
                  <td className="px-5 py-4 text-zinc-600">Aug 01, 2023</td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200/50">
                      <div className="w-1.5 h-1.5 rounded-full bg-red-500" /> Expired
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button className="p-1.5 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 rounded-md transition-colors">
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>

              </tbody>
            </table>
          </div>
        </section>

      </main>
    </div>
  );
}