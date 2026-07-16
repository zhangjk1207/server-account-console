import { describe, expect, it } from "vitest";

import config from "./vite.config";

describe("Vite local API proxy", () => {
  it("also proxies API calls while serving a production preview", () => {
    const resolved = typeof config === "function" ? config({ command:"serve", mode:"production", isSsrBuild:false, isPreview:true }) : config;
    expect(resolved.preview?.proxy?.["/api"]).toBeDefined();
  });
});
