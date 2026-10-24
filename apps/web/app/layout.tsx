import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "StockWise AI - FMCG Distribution Intelligence",
  description: "Local-first FMCG Distribution Intelligence and Inventory Optimization Engine",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased selection:bg-primary/30 selection:text-white">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
