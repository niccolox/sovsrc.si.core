import { Container, getContainer } from "@cloudflare/containers";
import { createRemoteJWKSet, jwtVerify } from "jose";

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
  // Cloudflare Access gateway for the MCP endpoint.
  // TEAM_DOMAIN: https://<team>.cloudflareaccess.com
  // POLICY_AUD: the AUD tag of the Access application for hello.sovsrc.si/mcp
  TEAM_DOMAIN?: string;
  POLICY_AUD?: string;
}

// Paths that require a valid Cloudflare Access JWT.
const PROTECTED_PREFIXES = ["/mcp"];

const jwksCache = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

function jwksFor(teamDomain: string) {
  let jwks = jwksCache.get(teamDomain);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(`${teamDomain}/cdn-cgi/access/certs`));
    jwksCache.set(teamDomain, jwks);
  }
  return jwks;
}

function deny(message: string, status = 403): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Verify the Access JWT that Cloudflare adds in Cf-Access-Jwt-Assertion.
 * Returns the verified email, or a Response that denies the request.
 * The check runs in the Worker, so the workers.dev hostname, which Access
 * does not cover, is protected as well.
 */
async function verifyAccess(request: Request, env: Env): Promise<string | Response> {
  if (!env.TEAM_DOMAIN || !env.POLICY_AUD) {
    return deny("Access gateway is not configured: set TEAM_DOMAIN and POLICY_AUD");
  }
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!token) {
    return deny("Missing Cloudflare Access token", 401);
  }
  try {
    const { payload } = await jwtVerify(token, jwksFor(env.TEAM_DOMAIN), {
      issuer: env.TEAM_DOMAIN,
      audience: env.POLICY_AUD,
    });
    return (payload.email as string | undefined) ?? (payload.sub ?? "unknown");
  } catch (error) {
    return deny(`Invalid Cloudflare Access token: ${(error as Error).message}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const container = getContainer(env.SOVSRC_API, "main");

    if (PROTECTED_PREFIXES.some((p) => url.pathname === p || url.pathname.startsWith(p + "/"))) {
      const result = await verifyAccess(request, env);
      if (result instanceof Response) {
        return result;
      }
      // Pass the verified identity to the container and drop the raw token.
      const headers = new Headers(request.headers);
      headers.delete("cf-access-jwt-assertion");
      headers.delete("cookie");
      headers.set("X-Access-User", result);
      return container.fetch(new Request(request, { headers }));
    }

    return container.fetch(request);
  },
} satisfies ExportedHandler<Env>;
