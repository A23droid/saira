import { Sidebar } from "@/components/layout/sidebar";
import { MobileNav } from "@/components/layout/mobile-nav";
import { RequireAuth } from "@/components/layout/require-auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-paper">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <MobileNav />
        <main className="flex-1 px-5 py-8 md:px-10 md:py-10">
          <div className="mx-auto w-full max-w-6xl">
            <RequireAuth>{children}</RequireAuth>
          </div>
        </main>
      </div>
    </div>
  );
}
