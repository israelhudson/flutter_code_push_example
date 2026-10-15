// deno-lint-ignore-file require-await
import { deliveryControlHandler } from "../../supabase/functions/_shared/delivery.ts";
import { type IO } from "../../supabase/functions/_shared/poc.ts";
function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
const cfg = JSON.parse(await Deno.readTextFile("delivery/delivery-policy.json"));
function fixture() {
  const calls: any[] = [];
  const run: any = {
    path: ".github/workflows/delivery-worker.yml",
    head_branch: "slack-main",
    event: "workflow_dispatch",
    status: "in_progress",
    head_sha: "a".repeat(40),
    actor: { id: 18661493 },
    triggering_actor: { id: 18661493 },
  };
  const env: Record<string, string> = {
    SUPABASE_URL: "https://xtvueqciogzkyjkkqxcx.supabase.co",
    POC_ENABLED: "true",
    DELIVERY_V2_ENABLED: "true",
    POC_REGISTRATION_SECRET: "offline",
    POC_PUBLICATION_SECRET: "publish",
    POC_SLACK_BOT_USER_ID: "UBOT",
  };
  const event = { revision: 2, status: "approved", source_sha: "b".repeat(40) };
  let saved: any = event;
  const io: IO = {
    env: (k) => env[k],
    db: async (path, p) => {
      calls.push({ path, p });
      if (path === "rpc/delivery_task") {
        return { kind: "history", candidate_id: "delivery-" + "a".repeat(32), revision: 2, event };
      }
      return null;
    },
    fetch: (async (url: any) => {
      const path = String(url);
      let data: any;
      if (path.includes("/actions/runs/")) data = run;
      else if (path.includes("/contents/delivery/delivery-policy.json")) {
        data = { encoding: "base64", size: 100, content: btoa(JSON.stringify(cfg)) };
      } else if (path.includes("/event-2.json")) {
        data = { encoding: "base64", size: 100, content: btoa(JSON.stringify(saved)) };
      } else throw Error("unexpected fetch");
      return Response.json(data);
    }) as typeof fetch,
    slack: async () => ({ team_id: cfg.team_id, user_id: "UBOT" }),
    wait: () => {},
    log: () => {},
  };
  const request = (operation: string, data: any = {}, secret = "offline") =>
    new Request("https://test.invalid", {
      method: "POST",
      body: JSON.stringify({ operation, run_id: "123", ...data }),
      headers: { Authorization: "Bearer " + secret },
    });
  return { calls, run, env, io, request, setSaved: (v: any) => saved = v };
}
Deno.test("delivery control authenticates flag, secret, workflow, operator and completed runs before DB", async () => {
  const f = fixture(), handler = deliveryControlHandler(f.io);
  assert(
    (await handler(f.request("take", { lease: crypto.randomUUID() }, "wrong"))).status === 401,
  );
  f.run.actor.id = 1;
  assert((await handler(f.request("take"))).status === 409);
  f.run.actor.id = 18661493;
  f.run.status = "completed";
  assert((await handler(f.request("take"))).status === 409);
  f.run.status = "in_progress";
  f.run.path = ".github/workflows/poc-slack-prepare.yml";
  assert((await handler(f.request("take"))).status === 409);
  f.env.DELIVERY_V2_ENABLED = "false";
  assert((await handler(f.request("take"))).status === 409);
  assert(f.calls.length === 0);
});
Deno.test("delivery control only confirms history after matching immutable GitHub evidence", async () => {
  const f = fixture(), handler = deliveryControlHandler(f.io);
  f.setSaved({ status: "published" });
  const req = () =>
    f.request("finish", { task_id: 1, lease: crypto.randomUUID(), receipt: "c".repeat(40) });
  assert((await handler(req())).status === 409);
  assert(f.calls.length === 1);
  f.setSaved({ revision: 2, status: "approved", source_sha: "b".repeat(40) });
  assert((await handler(req())).status === 200);
  assert(f.calls.at(-1).path === "rpc/delivery_finish");
});
Deno.test("scheduled worker accepts only main and does not authorize manual cancellation", async () => {
  const f = fixture(), handler = deliveryControlHandler(f.io);
  f.run.event = "schedule";
  f.run.head_branch = "main";
  assert((await handler(f.request("take", { lease: crypto.randomUUID() }))).status === 200);
  assert(
    (await handler(f.request("cancel", { candidate: "delivery-" + "a".repeat(32) }))).status ===
      409,
  );
  f.run.head_branch = "foreign";
  assert((await handler(f.request("take"))).status === 409);
});
