import { deliverySlackHandler } from "./delivery.ts";
import { IO, isolated, slackHandler, TEAM, validSignature } from "./poc.ts";
const LEGACY = "https://uvfwvplcziehxrkidrxh.supabase.co/functions/v1/slack-approvals";
export function routerHandler(io: IO) {
  return async (request: Request): Promise<Response> => {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const raw = await request.text();
    if (raw.length > 65536) return new Response("Payload too large", { status: 413 });
    const ts = request.headers.get("x-slack-request-timestamp") ?? "";
    const sig = request.headers.get("x-slack-signature") ?? "";
    if (!await validSignature(raw, ts, sig, io.env("POC_SLACK_SIGNING_SECRET") ?? "")) {
      return new Response("Unauthorized", { status: 401 });
    }
    try {
      isolated(io.env("SUPABASE_URL") ?? "");
      if (io.env("POC_SHARED_APP_ROUTING") !== "true") throw Error("Router not enabled");
      const p = JSON.parse(new URLSearchParams(raw).get("payload") ?? "null");
      if (p?.api_app_id !== io.env("POC_SLACK_APP_ID") || p?.team?.id !== TEAM) {
        return new Response("Context rejected", { status: 403 });
      }
      const actions = Array.isArray(p.actions) ? p.actions : [];
      if (
        actions.some((a: any) =>
          String(a.action_id ?? "").startsWith("delivery_") ||
          String(a.value ?? "").startsWith("delivery-")
        )
      ) {
        return deliverySlackHandler(io)(
          new Request(request.url, { method: "POST", headers: request.headers, body: raw }),
        );
      }
      const own = actions.some((a: any) =>
        String(a.action_id ?? "").startsWith("poc_") || String(a.value ?? "").startsWith("poc-")
      ) ||
        String(p.view?.callback_id ?? "").startsWith("poc_");
      // POC namespaces NEVER fall back to legacy, including malformed/mixed actions.
      if (own) {
        return slackHandler(io)(
          new Request(request.url, {
            method: "POST",
            headers: request.headers,
            body: raw,
          }),
        );
      }
      // Existing handlers still authenticate/authorize. Preserve signed bytes and headers.
      const r = await io.fetch(LEGACY, {
        method: "POST",
        redirect: "error",
        signal: AbortSignal.timeout(2200),
        headers: {
          "Content-Type": request.headers.get("content-type") ??
            "application/x-www-form-urlencoded",
          "x-slack-request-timestamp": ts,
          "x-slack-signature": sig,
        },
        body: raw,
      });
      const body = await r.text();
      if (body.length > 65536) {
        throw Error("Legacy response too large");
      }
      return new Response(body, {
        status: r.status,
        headers: { "Content-Type": r.headers.get("content-type") ?? "text/plain" },
      });
    } catch {
      io.log("poc_router_unavailable");
      return new Response("Interaction temporarily unavailable", { status: 503 });
    }
  };
}
