import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Agentic Trading Terminal",
  description: "AI agents research; you approve every order.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning: browser extensions (e.g. Kapture) inject
    // attributes/classes onto <html>/<body> before React hydrates, which would
    // otherwise trip a hydration mismatch. Scoped to these elements only.
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
