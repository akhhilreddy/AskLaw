import Sidebar from "../components/dashboard/Sidebar";

function AppLayout({ children }) {
  return (
    <div className="flex h-screen bg-[#1A1A1A] text-zinc-100 overflow-hidden">
      <Sidebar />

      <main className="flex-1 bg-[#1A1A1A]">
        {children}
      </main>
    </div>
  );
}

export default AppLayout;