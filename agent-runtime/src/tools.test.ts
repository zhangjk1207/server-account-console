import { describe, expect, it } from "vitest";

import { ControlPlaneClient } from "./control-plane.js";
import { createControlPlaneTools } from "./tools.js";

describe("control-plane tools", () => {
  it("exposes only the reviewed read-only domain tool set", () => {
    const tools = createControlPlaneTools(new ControlPlaneClient("http://control-plane", "session=test"));

    expect(tools.map((tool) => tool.name)).toEqual([
      "get_control_plane_overview",
      "list_machines",
      "list_members",
      "get_member_access",
      "list_recent_runs",
    ]);
    expect(tools.map((tool) => tool.name)).not.toContain("bash");
  });
});
