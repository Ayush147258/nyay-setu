import type { Metadata } from "next"
import { Inter, Playfair_Display } from "next/font/google"
import "./globals.css"

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
})

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-playfair",
  display: "swap",
  weight: ["400", "600"],
})

export const metadata: Metadata = {
  title: "NyaySetu - India's Autonomous Legal Rights Navigator",
  description:
    "AI-powered legal rights navigator. Speak in Hindi, English, or Hinglish. Get legally valid documents in seconds. Access justice for every Indian citizen.",
  keywords: ["legal", "India", "FIR", "rights", "AI", "Hindi", "NyaySetu"],
  openGraph: {
    title: "NyaySetu - India's Autonomous Legal Rights Navigator",
    description: "India's AI-powered legal rights navigator for every citizen",
    locale: "hi_IN",
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='30' fill='%231B2A38'/%3E%3Ccircle cx='32' cy='32' r='24' fill='none' stroke='%23B8965A' stroke-width='2'/%3E%3Cpath d='M20 26h24M32 26v18M24 44h16' stroke='%23B23A2E' stroke-width='3' stroke-linecap='round' fill='none'/%3E%3C/svg%3E" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,900;1,9..144,500&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Sans+Devanagari:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body className={`${inter.variable} ${playfair.variable} min-h-screen antialiased`}>
        {children}
      </body>
    </html>
  )
}
