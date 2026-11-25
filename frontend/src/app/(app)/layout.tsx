import { AuthProvider } from "@/components/AuthProvider";
import { Header } from "@/components/Header";

/** Every page in this group needs a logged-in user. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthProvider>
      <Header />
      <main className="mx-auto max-w-[1400px] px-4 py-8 sm:px-8 sm:py-12">{children}</main>
    </AuthProvider>
  );
}
