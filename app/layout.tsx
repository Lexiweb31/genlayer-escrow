import type { Metadata } from "next";
import { DM_Mono, Manrope } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });
const dmMono = DM_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Merit — Work that can prove itself", template: "%s · Merit" },
  description: "AI-arbitrated freelance escrow on GenLayer's Bradbury testnet.",
  metadataBase: new URL("https://genlayer-escrow.vercel.app"),
  openGraph: {
    title: "Merit — Work that can prove itself",
    description: "Inspectable agreements, validator evidence, and safe settlement proof.",
    images: ["/og-image.svg"],
  },
};

const themeScript = `(()=>{try{const s=localStorage.getItem('merit-theme');const t=s==='light'||s==='dark'?s:(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.dataset.theme=t}catch{document.documentElement.dataset.theme='dark'}})()`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning className={`${manrope.variable} ${dmMono.variable}`}>
    <head><script dangerouslySetInnerHTML={{ __html: themeScript }}/></head>
    <body><Providers><AppShell>{children}</AppShell></Providers></body>
  </html>;
}
