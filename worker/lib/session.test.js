import { describe, it, expect } from "vitest";
import { parseCookie, sessionCookie, clearCookie } from "./session.js";

describe("cookie", () => {
  it("parseCookie 取指定名", () => {
    const h = "lns=abc.def; lnrole=owner; x=1";
    expect(parseCookie(h, "lns")).toBe("abc.def");
    expect(parseCookie(h, "lnrole")).toBe("owner");
    expect(parseCookie(h, "nope")).toBe("");
    expect(parseCookie(null, "lns")).toBe("");
  });
  it("sessionCookie 含安全属性与 Domain", () => {
    const c = sessionCookie("tok123", { maxAge: 100 });
    expect(c).toContain("lns=tok123");
    expect(c).toContain("Domain=.xdzq.org");
    expect(c).toContain("HttpOnly");
    expect(c).toContain("Secure");
    expect(c).toContain("SameSite=Lax");
    expect(c).toContain("Max-Age=100");
  });
  it("clearCookie 立即过期", () => {
    expect(clearCookie("lns")).toContain("Max-Age=0");
  });
});
