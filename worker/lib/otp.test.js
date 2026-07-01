import { describe, it, expect } from "vitest";
import { genCode, hashCode, constEq } from "./otp.js";

describe("otp", () => {
  it("genCode 是 6 位数字、含前导零可能", () => {
    for (let i = 0; i < 200; i++) {
      const c = genCode();
      expect(c).toMatch(/^\d{6}$/);
    }
  });
  it("hashCode 确定且随 salt/email 变化", async () => {
    const a = await hashCode("123456", "x@a.com", "s1");
    const b = await hashCode("123456", "x@a.com", "s1");
    const c = await hashCode("123456", "x@a.com", "s2");
    expect(a).toBe(b);
    expect(a).not.toBe(c);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
  });
  it("constEq 相等/不等", () => {
    expect(constEq("abc", "abc")).toBe(true);
    expect(constEq("abc", "abd")).toBe(false);
    expect(constEq("abc", "ab")).toBe(false);
  });
});
