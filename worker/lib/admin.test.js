import { describe, it, expect } from "vitest";
import { parseUserId, buildUserUpdate } from "./admin.js";

describe("admin helpers", () => {
  it("parseUserId 取路径末段数字", () => {
    expect(parseUserId("/admin/users/42")).toBe(42);
    expect(parseUserId("/admin/users/")).toBe(null);
    expect(parseUserId("/admin/users/abc")).toBe(null);
  });
  it("buildUserUpdate 只白名单 name/role/status,过滤非法", () => {
    expect(buildUserUpdate({ name: "A", role: "owner", status: "disabled" }))
      .toEqual({ sql: "name=?, role=?, status=?", vals: ["A", "owner", "disabled"] });
    expect(buildUserUpdate({ role: "hacker", evil: 1 })).toEqual({ sql: "", vals: [] });
    expect(buildUserUpdate({ status: "active" })).toEqual({ sql: "status=?", vals: ["active"] });
  });
});
