import NextAuth, { type NextAuthConfig } from "next-auth"
import type { JWT } from "next-auth/jwt"
import Google from "next-auth/providers/google"
import Credentials from "next-auth/providers/credentials"
import { eq } from "drizzle-orm"
import { getDb } from "@/lib/db"
import { users } from "@/db/schema"
import { DEMO_ACCOUNT_PASSWORD, demoAccountForEmail, type DemoRole } from "@/lib/demo-accounts"

type DbToken = {
  dbUserId?: string
  tenantId?: string
  role?: string | null
  email?: string | null
}

async function upsertGoogleUser(input: {
  email: string
  name?: string | null
  image?: string | null
  googleId?: string | null
}) {
  const db = getDb()
  const [user] = await db
    .insert(users)
    .values({
      email: input.email,
      name: input.name ?? null,
      avatarUrl: input.image ?? null,
      googleId: input.googleId ?? null,
      updatedAt: new Date(),
    })
    .onConflictDoUpdate({
      target: users.email,
      set: {
        name: input.name ?? null,
        avatarUrl: input.image ?? null,
        googleId: input.googleId ?? null,
        updatedAt: new Date(),
      },
    })
    .returning()

  return user
}

async function upsertDemoUser(input: {
  email: string
  name: string
  role: DemoRole
  tenantId: string
}) {
  const db = getDb()
  const [user] = await db
    .insert(users)
    .values({
      email: input.email,
      name: input.name,
      tenantId: input.tenantId,
      role: input.role,
      preferredLang: input.role === "citizen" ? "hi" : "en",
      updatedAt: new Date(),
    })
    .onConflictDoUpdate({
      target: users.email,
      set: {
        name: input.name,
        tenantId: input.tenantId,
        role: input.role,
        preferredLang: input.role === "citizen" ? "hi" : "en",
        updatedAt: new Date(),
      },
    })
    .returning()

  return user
}

async function findUserByEmail(email: string) {
  const db = getDb()
  const [user] = await db.select().from(users).where(eq(users.email, email)).limit(1)
  return user ?? null
}

function applyDbUserToToken(token: JWT, user: Awaited<ReturnType<typeof findUserByEmail>>) {
  const mutableToken = token as typeof token & DbToken
  mutableToken.dbUserId = user?.id
  mutableToken.tenantId = user?.tenantId
  mutableToken.role = user?.role
  mutableToken.email = user?.email ?? token.email
  return mutableToken
}

export const authConfig = {
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
    Credentials({
      name: "Demo account",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = String(credentials?.email ?? "").trim().toLowerCase()
        const password = String(credentials?.password ?? "")
        const demoAccount = demoAccountForEmail(email)
        if (!demoAccount || password !== DEMO_ACCOUNT_PASSWORD) return null

        const dbUser = await upsertDemoUser(demoAccount)
        return {
          id: dbUser.id,
          email: dbUser.email,
          name: dbUser.name ?? demoAccount.name,
        }
      },
    }),
  ],
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  callbacks: {
    async signIn({ account, profile, user }) {
      if (account?.provider !== "google") return true
      const email = user.email ?? profile?.email
      if (!email) return false

      await upsertGoogleUser({
        email,
        name: user.name ?? profile?.name,
        image: user.image ?? (typeof profile?.picture === "string" ? profile.picture : null),
        googleId: account.providerAccountId ?? (typeof profile?.sub === "string" ? profile.sub : null),
      })

      return true
    },
    async jwt({ token, account, profile, user }) {
      if (account?.provider === "google") {
        const email = user?.email ?? token.email ?? profile?.email
        if (email) {
          const dbUser = await upsertGoogleUser({
            email,
            name: user?.name ?? token.name ?? profile?.name,
            image: user?.image ?? token.picture ?? (typeof profile?.picture === "string" ? profile.picture : null),
            googleId: account.providerAccountId ?? (typeof profile?.sub === "string" ? profile.sub : null),
          })
          return applyDbUserToToken(token, dbUser)
        }
      }

      if (account?.provider === "credentials" && user?.email) {
        return applyDbUserToToken(token, await findUserByEmail(user.email))
      }

      if (token.email) {
        return applyDbUserToToken(token, await findUserByEmail(token.email))
      }

      return token as typeof token & DbToken
    },
    async session({ session, token }) {
      if (session.user) {
        const sessionUser = session.user as typeof session.user & {
          id: string
          tenantId: string
          role: string
        }
        sessionUser.id = (token as DbToken).dbUserId ?? ""
        sessionUser.tenantId = (token as DbToken).tenantId ?? "default"
        sessionUser.role = (token as DbToken).role ?? "citizen"
      }
      return session
    },
    async redirect({ baseUrl, url }) {
      if (url.startsWith("/")) return `${baseUrl}${url}`
      if (new URL(url).origin === baseUrl) return url
      return `${baseUrl}/dashboard`
    },
  },
} satisfies NextAuthConfig

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig)