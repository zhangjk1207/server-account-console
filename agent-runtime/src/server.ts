import { createHash, randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import {
  createAgentSession,
  DefaultResourceLoader,
  getAgentDir,
  ModelRuntime,
  resolveCliModel,
  SessionManager,
  SettingsManager,
  type AgentSession,
} from "@earendil-works/pi-coding-agent";

import { ControlPlaneClient } from "./control-plane.js";
import { SYSTEM_PROMPT } from "./prompt.js";
import { createControlPlaneTools } from "./tools.js";

const port = Number(process.env.PORT ?? 8010);
const controlPlaneUrl = process.env.CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";
const runtimeToken = process.env.AGENT_RUNTIME_TOKEN;
const promptTimeoutMs = Number(process.env.AGENT_PROMPT_TIMEOUT_MS ?? 45_000);

interface ModelConfiguration {
  provider: "openai" | "anthropic" | "google" | "openai-compatible";
  model: string;
  base_url: string | null;
  api_key: string;
  thinking_level: "off" | "minimal" | "low" | "medium" | "high";
  enabled: boolean;
}

const operationSessions = new Map<string, { session: AgentSession; configFingerprint: string }>();

function json(response: ServerResponse, status: number, body: unknown) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

async function readJson(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
}

function emit(response: ServerResponse, event: unknown) {
  response.write(`${JSON.stringify(event)}\n`);
}

async function withDeadline<T>(promise: Promise<T>, deadline: number, onTimeout?: () => void): Promise<T> {
  const remaining = Math.max(1, deadline - Date.now());
  let handle: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    handle = setTimeout(() => {
      reject(new Error(`Agent model did not complete within ${Math.round(promptTimeoutMs / 1000)} seconds`));
      onTimeout?.();
    }, remaining);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (handle) clearTimeout(handle);
  }
}

function fingerprint(config: ModelConfiguration): string {
  return createHash("sha256").update(JSON.stringify(config)).digest("hex");
}

async function loadConfiguration(client: ControlPlaneClient): Promise<ModelConfiguration> {
  if (!runtimeToken) throw new Error("AGENT_RUNTIME_TOKEN is not configured");
  const config = await client.getInternal<ModelConfiguration>("/agent-model-config/internal");
  if (!config.enabled) throw new Error("The configured model is disabled");
  return config;
}

async function loadModel(runtime: ModelRuntime, config: ModelConfiguration) {
  if (config.provider === "openai-compatible") {
    if (!config.base_url) throw new Error("OpenAI-compatible models require a base URL");
    const providerId = "server-account-custom";
    runtime.registerProvider(providerId, {
      name: "OpenAI-compatible",
      baseUrl: config.base_url,
      apiKey: config.api_key,
      api: "openai-completions",
      authHeader: true,
      models: [{
        id: config.model,
        name: config.model,
        api: "openai-completions",
        reasoning: config.thinking_level !== "off",
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 128_000,
        maxTokens: 16_384,
      }],
    });
    const model = runtime.getModel(providerId, config.model);
    if (!model) throw new Error(`Unable to register model ${config.model}`);
    return model;
  }
  await runtime.setRuntimeApiKey(config.provider, config.api_key);
  const resolved = resolveCliModel({
    cliProvider: config.provider,
    cliModel: config.model,
    modelRuntime: runtime,
  });
  if (resolved.error || !resolved.model) {
    throw new Error(resolved.error ?? `Unknown model ${config.provider}/${config.model}`);
  }
  return resolved.model;
}

async function getSession(operationId: string, client: ControlPlaneClient, config: ModelConfiguration) {
  const configFingerprint = fingerprint(config);
  const existing = operationSessions.get(operationId);
  if (existing?.configFingerprint === configFingerprint) return existing.session;
  if (existing) await existing.session.abort();
  const modelRuntime = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
  const model = await loadModel(modelRuntime, config);
  const resourceLoader = new DefaultResourceLoader({
    cwd: process.cwd(),
    agentDir: getAgentDir(),
    systemPromptOverride: () => SYSTEM_PROMPT,
  });
  await resourceLoader.reload();
  const { session } = await createAgentSession({
    modelRuntime,
    model,
    resourceLoader,
    sessionManager: SessionManager.inMemory(),
    settingsManager: SettingsManager.inMemory({ compaction: { enabled: true } }),
    noTools: "builtin",
    customTools: createControlPlaneTools(client),
  });
  session.setThinkingLevel(config.thinking_level);
  operationSessions.set(operationId, { session, configFingerprint });
  return session;
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (request.method === "GET" && url.pathname === "/health") {
      const client = new ControlPlaneClient(controlPlaneUrl, "", runtimeToken);
      try {
        const config = await loadConfiguration(client);
        json(response, 200, {
          status: "ok", runtime: "pi", provider_configured: true,
          provider: config.provider, model: config.model,
        });
      } catch (error) {
        json(response, 200, {
          status: "degraded", runtime: "pi", provider_configured: false,
          detail: error instanceof Error ? error.message : String(error),
        });
      }
      return;
    }
    if (request.method !== "POST" || url.pathname !== "/operations/prompt") {
      json(response, 404, { detail: "Not found" });
      return;
    }

    const cookie = request.headers.cookie ?? "";
    const client = new ControlPlaneClient(controlPlaneUrl, cookie, runtimeToken);
    await client.authenticate();
    const modelConfig = await loadConfiguration(client);
    const body = await readJson(request);
    const operationId = typeof body.operation_id === "string" ? body.operation_id : randomUUID();
    const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
    if (!prompt) {
      json(response, 422, { detail: "Prompt is required" });
      return;
    }

    response.writeHead(200, {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
    });
    emit(response, { type: "operation", operation_id: operationId });
    const deadline = Date.now() + promptTimeoutMs;
    const session = await withDeadline(getSession(operationId, client, modelConfig), deadline);
    const unsubscribe = session.subscribe((event) => emit(response, { type: "agent_event", event }));
    try {
      await withDeadline(session.prompt(prompt), deadline, () => { void session.abort(); });
      emit(response, { type: "complete" });
    } finally {
      unsubscribe();
      response.end();
    }
  } catch (error) {
    if (!response.headersSent) {
      json(response, 500, { detail: error instanceof Error ? error.message : "Agent runtime failed" });
    } else {
      emit(response, { type: "error", message: error instanceof Error ? error.message : "Agent runtime failed" });
      response.end();
    }
  }
});

server.listen(port, "0.0.0.0", () => {
  console.log(JSON.stringify({ level: "info", message: "agent runtime listening", port }));
});
