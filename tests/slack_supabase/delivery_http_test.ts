// deno-lint-ignore-file require-await
import { deliveryCard, deliverySlackHandler } from "../../supabase/functions/_shared/delivery.ts";
import { type IO } from "../../supabase/functions/_shared/poc.ts";
function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
const candidate = {
  id: "delivery-" + "a".repeat(32),
  version: "2.0.0",
  rc_number: 1,
  rc_tag: "poc-v2.0.0-rc.1",
  status: "pending",
  technical_user: "UTECH",
  business_user: "UBIZ",
  solo: false,
};
Deno.test("delivery cards: public tracking, role-specific DMs, closed decisions and run link", () => {
  const channel = deliveryCard(candidate, "channel");
  assert(!channel.blocks.some((b: any) => b.type === "actions"));
  const technical = JSON.stringify(deliveryCard(candidate, "technical"));
  assert(
    technical.includes("delivery_technical_accept") &&
      !technical.includes("delivery_business_accept"),
  );
  for (const status of ["approved", "rejected", "publishing", "published"]) {
    const card = deliveryCard({
      ...candidate,
      status,
      technical_at: "now",
      business_at: "now",
      publication_run: "123",
    }, "technical");
    assert(!card.blocks.some((b: any) => b.type === "actions"));
    assert(JSON.stringify(card).includes("/actions/runs/123"));
  }
});
async function signed(
  payload: any,
  secret = "test-secret",
  timestamp = String(Math.floor(Date.now() / 1000)),
) {
  const raw = new URLSearchParams({ payload: JSON.stringify(payload) }).toString();
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const hash = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`v0:${timestamp}:${raw}`),
  );
  const sig = "v0=" +
    [...new Uint8Array(hash)].map((x) => x.toString(16).padStart(2, "0")).join("");
  return new Request("https://test.invalid", {
    method: "POST",
    body: raw,
    headers: { "x-slack-request-timestamp": timestamp, "x-slack-signature": sig },
  });
}
Deno.test("delivery webhook commits before ACK/wakeup, refuses forgery, and does not fake success on DB failure", async () => {
  const calls: string[] = [];
  const waits: Promise<unknown>[] = [];
  const env: Record<string, string> = {
    SUPABASE_URL: "https://xtvueqciogzkyjkkqxcx.supabase.co",
    POC_ENABLED: "true",
    DELIVERY_V2_ENABLED: "true",
    POC_SLACK_APP_ID: "ANEW",
    POC_SLACK_SIGNING_SECRET: "test-secret",
  };
  let fail = false;
  const io: IO = {
    env: (k) => env[k],
    db: async (path, p) => {
      assert(path === "rpc/delivery_decide");
      assert(p?.p_role === "technical");
      calls.push("commit");
      if (fail) throw Error("offline");
      return {};
    },
    fetch: (async () => {
      calls.push("wake");
      return new Response(null, { status: 204 });
    }) as typeof fetch,
    slack: async () => {
      throw Error("Slack must not block ACK");
    },
    wait: (p) => {
      waits.push(p);
    },
    log: () => {},
  };
  const p = {
    type: "block_actions",
    api_app_id: "ANEW",
    team: { id: "T09CYB7AS77" },
    user: { id: "UTECH" },
    channel: { id: "DTECH" },
    container: { channel_id: "DTECH", message_ts: "100.1" },
    message: { ts: "100.1" },
    actions: [{ action_id: "delivery_technical_accept", value: candidate.id }],
  };
  const handler = deliverySlackHandler(io);
  assert((await handler(await signed(p))).status === 200);
  await Promise.all(waits);
  assert(calls.join(",") === "commit,wake");
  calls.length = 0;
  assert((await handler(await signed(p, "wrong"))).status === 401);
  assert(calls.length === 0);
  assert((await handler(await signed(p, "test-secret", "1"))).status === 401);
  assert((await handler(await signed({ ...p, api_app_id: "OTHER" }))).status !== 200);
  fail = true;
  assert((await handler(await signed(p))).status === 503);
  assert(calls.join(",") === "commit");
});
