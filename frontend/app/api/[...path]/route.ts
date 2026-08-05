import { NextRequest, NextResponse } from "next/server";
import http from "node:http";
import https from "node:https";

const BACKEND_URL = process.env.BACKEND_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const BACKEND_TIMEOUT_MS = Number(process.env.BACKEND_PROXY_TIMEOUT_MS ?? 15 * 60 * 1000);

export const runtime = "nodejs";

function backendRequest(targetUrl: URL, request: NextRequest, body: string | undefined): Promise<{ body: Buffer; headers: http.IncomingHttpHeaders; status: number; statusText: string }> {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.delete("accept-encoding");

  const client = targetUrl.protocol === "https:" ? https : http;

  return new Promise((resolve, reject) => {
    const upstream = client.request(
      targetUrl,
      {
        method: request.method,
        headers: Object.fromEntries(headers.entries()),
        timeout: BACKEND_TIMEOUT_MS,
      },
      (response) => {
        const chunks: Buffer[] = [];
        response.on("data", (chunk: Buffer | string) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        response.on("end", () => {
          resolve({
            body: Buffer.concat(chunks),
            headers: response.headers,
            status: response.statusCode ?? 502,
            statusText: response.statusMessage ?? "Bad Gateway",
          });
        });
      },
    );

    upstream.on("timeout", () => {
      upstream.destroy(new Error(`Backend request timed out after ${BACKEND_TIMEOUT_MS}ms`));
    });
    upstream.on("error", reject);
    if (body) {
      upstream.write(body);
    }
    upstream.end();
  });
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const requestUrl = new URL(request.url);
  const joinedPath = path.join("/");
  const targetUrl = new URL(joinedPath + requestUrl.search, BACKEND_URL.endsWith("/") ? BACKEND_URL : `${BACKEND_URL}/`);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  if (joinedPath.endsWith("run-stream")) {
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("content-length");
    let streamed: Response;
    try {
      streamed = await fetch(targetUrl, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Backend stream request failed";
      return NextResponse.json({ detail: message }, { status: 502 });
    }
    return new NextResponse(streamed.body, {
      status: streamed.status,
      statusText: streamed.statusText,
      headers: streamed.headers,
    });
  }

  let response: Awaited<ReturnType<typeof backendRequest>>;
  try {
    response = await backendRequest(targetUrl, request, body);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend request failed";
    const status = message.includes("timed out") ? 504 : 502;
    return NextResponse.json({ detail: message }, { status });
  }

  const responseHeaders = new Headers();
  Object.entries(response.headers).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => responseHeaders.append(key, item));
    } else if (value !== undefined) {
      responseHeaders.set(key, value);
    }
  });
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");

  const responseBody = response.body.byteLength
    ? response.body.buffer.slice(response.body.byteOffset, response.body.byteOffset + response.body.byteLength) as ArrayBuffer
    : null;

  return new NextResponse(responseBody, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
