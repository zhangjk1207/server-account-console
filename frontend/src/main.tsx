import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { AgentApp } from "./AgentApp";
import "./styles.css";
import "./agent.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AgentApp />
  </StrictMode>,
);
