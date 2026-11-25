"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { ApiError, type User, api } from "@/lib/api";

const UserContext = createContext<User | null>(null);

/** The logged-in user, or null while it is still loading. */
export function useUser(): User | null {
  return useContext(UserContext);
}

/**
 * proxy.ts only checks that a session cookie exists; this asks the API whether it is still valid
 * and sends a 401 to /login. Children always render (each page loads its own data, and useApi
 * also redirects on 401), so a page doesn't wait for /me before it starts fetching.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    let active = true;
    api.me().then(
      (me) => {
        if (active) setUser(me);
      },
      (err: unknown) => {
        if (active && err instanceof ApiError && err.status === 401) router.replace("/login");
        // Other errors (API down) show up in the pages' own error states.
      },
    );
    return () => {
      active = false;
    };
  }, [router]);

  return <UserContext.Provider value={user}>{children}</UserContext.Provider>;
}
