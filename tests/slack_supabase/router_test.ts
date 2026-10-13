// deno-lint-ignore-file require-await
import { routerHandler } from "../../supabase/functions/_shared/router.ts";
import type { IO } from "../../supabase/functions/_shared/poc.ts";
function assert(v: unknown) {
  if (!v) throw Error("assertion failed");
}
async function fixture(payload: any) {
  const env: Record<string, string> = {
    SUPABASE_URL: "https://" + "a".repeat(20) + ".supabase.co",
    POC_SHARED_APP_ROUTING: "true",
    POC_SLACK_APP_ID: "ASHARED",
    POC_SLACK_SIGNING_SECRET: "fixture-secret",
    POC_ENABLED: "true",
  };
  const calls: any[] = [], tasks: Promise<unknown>[] = [];
  const io: IO = {
    env: (k) => env[k],
    log: () => {},
    wait: (p) => tasks.push(p),
    db: async () => {
      throw Error("Fixture has no candidate");
    },
    slack: async () => {
      throw Error("No Slack send");
    },
    fetch: (async (url, init) => {
      calls.push([url, init]);
      return new Response('{"legacy":true}', {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch,
  };
  const raw = new URLSearchParams({ payload: JSON.stringify(payload) }).toString();
  const ts = String(Math.floor(Date.now() / 1000));
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.POC_SLACK_SIGNING_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = "v0=" +
    [
      ...new Uint8Array(
        await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`v0:${ts}:${raw}`)),
      ),
    ].map((x) => x.toString(16).padStart(2, "0")).join("");
  const request = () =>
    new Request("https://fixture.invalid", {
      method: "POST",
      body: raw,
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "x-slack-signature": sig,
        "x-slack-request-timestamp": ts,
      },
    });
  return { io, calls, tasks, raw, ts, sig, request, env };
}
function payload() {
  return {
    api_app_id: "ASHARED",
    team: { id: "T09CYB7AS77" },
    user: { id: "U0BMFQKC001" },
    type: "block_actions",
    channel: { id: "C0C8DUJB52L" },
    container: { channel_id: "C0C8DUJB52L", message_ts: "1.001" },
    actions: [{ action_id: "mobile_technical", value: "mobile-old" }],
  };
}
Deno.test("Router preserva bytes/assinatura e destino fixo dos cartões antigos", async () => {
  const f = await fixture(payload());
  const r = await routerHandler(f.io)(f.request());
  assert(r.status === 200 && await r.text() === '{"legacy":true}');
  assert(f.calls.length === 1);
  const [url, init] = f.calls[0];
  assert(url === "https://uvfwvplcziehxrkidrxh.supabase.co/functions/v1/slack-approvals");
  assert(
    init.body === f.raw && init.headers["x-slack-signature"] === f.sig &&
      init.headers["x-slack-request-timestamp"] === f.ts && init.redirect === "error",
  );
});
Deno.test("Router nunca encaminha namespace POC/misto ao banco antigo", async () => {
  for (
    const actions of [[{ action_id: "poc_technical", value: "poc-" + "a".repeat(32) }], [{
      action_id: "mobile_technical",
      value: "poc-malformed",
    }], [{ action_id: "mobile_technical", value: "old" }, {
      action_id: "poc_business",
      value: "poc-malformed",
    }]]
  ) {
    const f = await fixture({ ...payload(), actions });
    await routerHandler(f.io)(f.request());
    await Promise.all(f.tasks);
    assert(f.calls.length === 0);
  }
});
Deno.test("Router não encaminha assinatura inválida ou contexto estrangeiro", async () => {
  const f = await fixture(payload());
  const req = f.request();
  req.headers.set("x-slack-signature", "v0=" + "0".repeat(64));
  assert((await routerHandler(f.io)(req)).status === 401);
  assert(f.calls.length === 0);
  const foreign = await fixture({ ...payload(), api_app_id: "AOTHER" });
  assert((await routerHandler(foreign.io)(foreign.request())).status === 403);
  assert(foreign.calls.length === 0);
});
Deno.test("Router de modal POC mantém separação e timeout antigo não cria aceite", async () => {
  const f = await fixture({
    ...payload(),
    type: "view_submission",
    view: { callback_id: "poc_adjustment", private_metadata: "invalid" },
  });
  await routerHandler(f.io)(f.request());
  assert(f.calls.length === 0);
  const old = await fixture(payload());
  old.io.fetch = (() => {
    throw Error("legacy timeout");
  }) as typeof fetch;
  assert((await routerHandler(old.io)(old.request())).status === 503);
});
