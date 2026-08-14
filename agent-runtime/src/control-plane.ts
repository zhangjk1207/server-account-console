export type Overview = {
  machines: { total: number; reachable: number; attention: number };
  members: { active: number; with_keys: number };
  grants: { active: number };
  runs: { active: number; failed_recently: number };
};

export class ControlPlaneClient {
  constructor(
    private readonly baseUrl: string,
    private readonly cookie: string,
    private readonly runtimeToken?: string,
  ) {}

  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}/api${path}`, {
      headers: { cookie: this.cookie },
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(detail?.detail ?? `Control plane request failed (${response.status})`);
    }
    return response.json() as Promise<T>;
  }

  async getInternal<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}/api${path}`, {
      headers: {
        accept: "application/json",
        ...(this.runtimeToken ? { "x-agent-runtime-token": this.runtimeToken } : {}),
      },
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(detail?.detail ?? `Control plane internal request failed (${response.status})`);
    }
    return response.json() as Promise<T>;
  }

  authenticate(): Promise<{ authenticated: boolean }> {
    return this.get("/auth/me");
  }
}
