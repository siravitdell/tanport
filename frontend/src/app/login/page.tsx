"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError, api } from "@/lib/api";

type Mode = "login" | "register";

function errorText(err: unknown, mode: Mode): string {
  if (!(err instanceof ApiError)) return "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ลองใหม่อีกครั้ง";
  switch (err.status) {
    case 401:
      return "อีเมลหรือรหัสผ่านไม่ถูกต้อง";
    case 403:
      return err.message.includes("disabled") ? "ตอนนี้ปิดรับสมัครสมาชิก" : "รหัสเชิญไม่ถูกต้อง";
    case 409:
      return "อีเมลนี้มีบัญชีอยู่แล้ว";
    case 422:
      return mode === "register"
        ? "ตรวจสอบอีเมล และรหัสผ่านต้องยาวอย่างน้อย 10 ตัวอักษร"
        : "ตรวจสอบอีเมลและรหัสผ่าน";
    case 429: {
      const minutes = err.retryAfterS ? Math.ceil(err.retryAfterS / 60) : null;
      return minutes ? `ลองหลายครั้งเกินไป รออีก ${minutes} นาที` : "ลองหลายครั้งเกินไป รอสักครู่";
    }
    default:
      return `เกิดข้อผิดพลาด (${err.status})`;
  }
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already logged in (valid cookie) → straight to the app.
  useEffect(() => {
    let active = true;
    api.me().then(
      () => {
        if (active) router.replace("/");
      },
      () => {}, // 401 is the normal case here
    );
    return () => {
      active = false;
    };
  }, [router]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const field = (name: string) => String(form.get(name) ?? "");
    setPending(true);
    setError(null);
    try {
      if (mode === "login") {
        await api.login(field("email"), field("password"));
      } else {
        await api.register({
          email: field("email"),
          password: field("password"),
          invite_code: field("invite_code"),
          display_name: field("display_name").trim() || null,
        });
      }
      router.replace("/");
    } catch (err) {
      setError(errorText(err, mode));
      setPending(false);
    }
  }

  const inputClass =
    "mt-1.5 w-full rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-ink outline-none focus:border-ink";

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex justify-end p-4 sm:p-6">
        <ThemeToggle />
      </div>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 sm:items-center">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 text-2xl font-bold">
            <Logo />
            TanPort
          </div>

          <div className="rounded-2xl border border-line bg-surface p-6 sm:p-8">
            <div role="tablist" className="mb-6 grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
              {(["login", "register"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={mode === m}
                  onClick={() => {
                    setMode(m);
                    setError(null);
                  }}
                  className={
                    mode === m
                      ? "rounded-lg bg-hero py-2 font-semibold text-hero-ink"
                      : "rounded-lg py-2 font-medium text-ink-2"
                  }
                >
                  {m === "login" ? "เข้าสู่ระบบ" : "สมัครสมาชิก"}
                </button>
              ))}
            </div>

            <form onSubmit={onSubmit} className="space-y-4">
              <label className="block text-sm font-medium text-ink-2">
                อีเมล
                <input name="email" type="email" required autoComplete="email" className={inputClass} />
              </label>
              <label className="block text-sm font-medium text-ink-2">
                รหัสผ่าน
                <input
                  name="password"
                  type="password"
                  required
                  minLength={mode === "register" ? 10 : undefined}
                  maxLength={128}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  className={inputClass}
                />
                {mode === "register" && (
                  <span className="mt-1 block text-xs text-muted">อย่างน้อย 10 ตัวอักษร</span>
                )}
              </label>
              {mode === "register" && (
                <>
                  <label className="block text-sm font-medium text-ink-2">
                    ชื่อที่แสดง <span className="text-muted">(ไม่บังคับ)</span>
                    <input name="display_name" maxLength={100} autoComplete="nickname" className={inputClass} />
                  </label>
                  <label className="block text-sm font-medium text-ink-2">
                    รหัสเชิญ
                    <input name="invite_code" required autoComplete="off" className={inputClass} />
                  </label>
                </>
              )}

              {error && (
                <p role="alert" className="rounded-xl bg-surface-2 px-3.5 py-2.5 text-sm text-down">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={pending}
                className="w-full rounded-xl bg-hero py-2.5 font-semibold text-hero-ink disabled:opacity-60"
              >
                {pending ? "กำลังดำเนินการ…" : mode === "login" ? "เข้าสู่ระบบ" : "สมัครสมาชิก"}
              </button>
            </form>
          </div>
          <p className="mt-4 text-center text-sm text-muted">สมัครได้เฉพาะผู้ที่มีรหัสเชิญ</p>
        </div>
      </main>
    </div>
  );
}
