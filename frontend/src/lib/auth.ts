import NextAuth, { type NextAuthConfig } from "next-auth"
import Google from "next-auth/providers/google"
import { eq } from "drizzle-orm"
import { getDb } from "@/lib/db"
import { users } from "@/db/schema"

type DbToken = {
  dbUserId?: string
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

async function findUserByEmail(email: string) {
  const db = getDb()
  const [user] = await db.select().from(users).where(eq(users.email, email)).limit(1)
  return user ?? null
}

export const authConfig = {
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
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
      const mutableToken = token as typeof token & DbToken

      if (account?.provider === "google") {
        const email = user?.email ?? token.email ?? profile?.email
        if (email) {
          const dbUser = await upsertGoogleUser({
            email,
            name: user?.name ?? token.name ?? profile?.name,
            image: user?.image ?? token.picture ?? (typeof profile?.picture === "string" ? profile.picture : null),
            googleId: account.providerAccountId ?? (typeof profile?.sub === "string" ? profile.sub : null),
          })
          mutableToken.dbUserId = dbUser.id
        }
      } else if (!mutableToken.dbUserId && token.email) {
        const dbUser = await findUserByEmail(token.email)
        mutableToken.dbUserId = dbUser?.id
      }

      return mutableToken
    },
    async session({ session, token }) {
      if (session.user) {
        ;(session.user as typeof session.user & { id: string }).id = (token as DbToken).dbUserId ?? ""
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
