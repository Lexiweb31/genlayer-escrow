import "server-only";

export interface ServerConfig {
  renderApiBaseUrl: URL;
  genlayerNetwork: string;
  genlayerExplorerBaseUrl: URL;
}

export class ServerConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ServerConfigurationError";
  }
}

function readRequired(name: string, developmentFallback?: string): string {
  const value = process.env[name]?.trim();
  if (value) return value;
  if (process.env.NODE_ENV !== "production" && developmentFallback) return developmentFallback;
  throw new ServerConfigurationError(`Required server environment variable ${name} is not configured.`);
}

function parseServerUrl(name: string, value: string, allowLocalHttp: boolean): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new ServerConfigurationError(`${name} must be a valid absolute URL.`);
  }

  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new ServerConfigurationError(`${name} must not contain credentials, query parameters, or fragments.`);
  }

  const local = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1" || parsed.hostname === "::1";
  if (parsed.protocol !== "https:" && !(allowLocalHttp && local && parsed.protocol === "http:")) {
    throw new ServerConfigurationError(`${name} must use HTTPS outside local development.`);
  }

  parsed.pathname = parsed.pathname.replace(/\/+$/, "");
  return parsed;
}

export function getServerConfig(): ServerConfig {
  const allowLocalHttp = process.env.NODE_ENV !== "production";
  const renderApiBaseUrl = parseServerUrl(
    "RENDER_API_BASE_URL",
    readRequired("RENDER_API_BASE_URL", "http://127.0.0.1:8000"),
    allowLocalHttp,
  );
  const genlayerNetwork = readRequired("GENLAYER_NETWORK", "testnet_bradbury");
  const genlayerExplorerBaseUrl = parseServerUrl(
    "GENLAYER_EXPLORER_BASE_URL",
    readRequired("GENLAYER_EXPLORER_BASE_URL", "https://explorer-bradbury.genlayer.com"),
    false,
  );

  return { renderApiBaseUrl, genlayerNetwork, genlayerExplorerBaseUrl };
}

export function publicNetworkLabel(network: string): string {
  const normalized = network.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  if (normalized === "testnet_bradbury" || normalized === "bradbury") return "Bradbury testnet";
  return "Configured GenLayer network";
}
