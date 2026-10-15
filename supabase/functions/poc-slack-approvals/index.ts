import { runtime, slackHandler } from "../_shared/poc.ts";
import { deliverySlackHandler } from "../_shared/delivery.ts";
const io = runtime();
Deno.serve(async (request: Request) => {
  // Routing is not authorization. Both handlers verify the original signature.
  const raw = await request.clone().text();
  if (raw.length > 65536) return new Response("Too large", { status: 413 });
  try {
    const p = JSON.parse(new URLSearchParams(raw).get("payload") ?? "{}");
    if (p.actions?.some((a: any) => String(a.action_id).startsWith("delivery_"))) {
      return deliverySlackHandler(io)(request);
    }
  } catch { /* Let the legacy authenticated parser reject malformed requests. */ }
  if (io.env("POC_LEGACY_RETIRED") === "true") {
    return new Response("Este cartão pertence ao histórico. Use as DMs da nova entrega.", {
      status: 200,
    });
  }
  return slackHandler(io)(request);
});
