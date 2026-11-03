import { Container, getContainer } from "@cloudflare/containers";

// One container instance runs the FastAPI server. The server keeps its
// content, attribution, and reward state in memory, so all requests go to
// the same instance.
export class SovsrcApiContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "10m";
  envVars = {
    PORT: "8000",
  };
}

interface Env {
  SOVSRC_API: DurableObjectNamespace<SovsrcApiContainer>;
  ENVIRONMENT: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const container = getContainer(env.SOVSRC_API, "main");
    return container.fetch(request);
  },
} satisfies ExportedHandler<Env>;
