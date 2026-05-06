import { beforeEach, describe, expect, it, vi } from "vitest";

import { deleteProject, getAuthHeaders, listProjects } from "./api";

describe("api auth and errors", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("does not create a dev token unless dev auth is explicitly enabled", () => {
    vi.stubEnv("VITE_ENABLE_DEV_AUTH", "false");

    expect(getAuthHeaders()).toEqual({});
    expect(localStorage.getItem("tender_token")).toBeNull();
  });

  it("uses the configured dev auth token when explicit dev auth is enabled", () => {
    vi.stubEnv("VITE_ENABLE_DEV_AUTH", "true");
    vi.stubEnv("VITE_DEV_AUTH_TOKEN", "local-token");

    expect(getAuthHeaders()).toEqual({ Authorization: "Bearer local-token" });
    expect(localStorage.getItem("tender_token")).toBe("local-token");
  });

  it("surfaces non-json error response text", async () => {
    vi.stubEnv("VITE_ENABLE_DEV_AUTH", "false");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("upstream exploded", { status: 502 }),
    );

    await expect(listProjects()).rejects.toThrow("upstream exploded");
  });

  it("clears stored token on unauthorized responses", async () => {
    vi.stubEnv("VITE_ENABLE_DEV_AUTH", "false");
    localStorage.setItem("tender_token", "expired-token");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ detail: "Invalid token" }, { status: 401 }),
    );

    await expect(listProjects()).rejects.toThrow("登录已失效，请重新登录");
    expect(localStorage.getItem("tender_token")).toBeNull();
  });

  it("handles no-content responses", async () => {
    vi.stubEnv("VITE_ENABLE_DEV_AUTH", "false");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));

    await expect(deleteProject("project-1")).resolves.toBeUndefined();
  });
});
