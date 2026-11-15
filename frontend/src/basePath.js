// The app can be served from the root of a domain ("/") or from a sub-path such as
// "/agentic-grc/" behind a reverse proxy. Vite sets import.meta.env.BASE_URL from
// VITE_BASE_PATH at build time (see vite.config.js). The rest of the code works with
// app paths ("/", "/evidence", "/auth/callback") and converts only at the browser boundary.

export function normalizeBase(base) {
  if (!base || base === "/" || base === "./") return "";
  const trimmed = base.replace(/^\/+|\/+$/g, "");
  return trimmed ? `/${trimmed}` : "";
}

export function createBasePath(base) {
  const prefix = normalizeBase(base);
  return {
    prefix,
    toAppPath(pathname) {
      if (prefix && (pathname === prefix || pathname.startsWith(`${prefix}/`))) {
        return pathname.slice(prefix.length) || "/";
      }
      return pathname || "/";
    },
    toBrowserPath(appPath) {
      const path = appPath.startsWith("/") ? appPath : `/${appPath}`;
      return `${prefix}${path}`;
    },
    assetUrl(publicPath) {
      return `${prefix}/${publicPath.replace(/^\/+/, "")}`;
    },
  };
}

const basePath = createBasePath(import.meta.env.BASE_URL);

export const BASE_PREFIX = basePath.prefix;
export const toAppPath = basePath.toAppPath;
export const toBrowserPath = basePath.toBrowserPath;
export const assetUrl = basePath.assetUrl;

export function currentAppPath() {
  return toAppPath(window.location.pathname);
}

export const DEFAULT_API_BASE_URL = `${BASE_PREFIX}/api/v1`;
