/** Isolated worker integration rehearsal: real SQL + Slack, fixture GitHub run/history.
 * No remote function/flag changes. No dispatch, tags, preview or Release.
 */
import { deliveryControlHandler } from "../../supabase/functions/_shared/delivery.ts";
import { type IO, slackRequest } from "../../supabase/functions/_shared/poc.ts";
const output = Deno.args[0];
const mode = Deno.args[1] ?? "prepare";
if (!output) throw Error("Private output directory required");
const privateDir = Deno.env.get("HOME") + "/.codex/private/slack-supabase-poc/";
const token = (await Deno.readTextFile(privateDir + "exclusive-bot-token")).trim();
const config = JSON.parse(await Deno.readTextFile("delivery/delivery-policy.json"));
const quote = (v: unknown) => "'" + String(v).replaceAll("'", "''") + "'";
async function sql(query: string) {
  const r = await new Deno.Command("supabase", {
    args: [
      "db",
      "query",
      "--linked",
      "--project-ref",
      "xtvueqciogzkyjkkqxcx",
      "--output",
      "json",
      query,
    ],
    stdout: "piped",
    stderr: "piped",
  }).output();
  if (!r.success) throw Error("SQL rehearsal failed: " + new TextDecoder().decode(r.stderr));
  return JSON.parse(new TextDecoder().decode(r.stdout)).rows;
}
async function db(path: string, p: Record<string, unknown> = {}) {
  if (!/^rpc\/delivery_[a-z_]+$/.test(path)) throw Error("RPC denied");
  const args = Object.entries(p).map(([k, v]) =>
    k + " => " + (v === null ? "null" : quote(typeof v === "object" ? JSON.stringify(v) : v))
  ).join(",");
  return (await sql("select public." + path.slice(4) + "(" + args + ") result"))[0].result;
}
const auth = await fetch(slackRequest("auth.test", {}, token)).then((r) => r.json());
if (!auth.ok || auth.team_id !== config.team_id || auth.user_id === "U0C750FTCS3") {
  throw Error("Exclusive bot required");
}
const env: Record<string, string> = {
  SUPABASE_URL: "https://xtvueqciogzkyjkkqxcx.supabase.co",
  POC_ENABLED: "true",
  DELIVERY_V2_ENABLED: "true",
  POC_PUBLICATION_ENABLED: "false",
  POC_SOURCE_BRANCH: "main",
  DELIVERY_SOURCE_BRANCH: "main",
  POC_SLACK_BOT_USER_ID: auth.user_id,
  POC_REGISTRATION_SECRET: "local-rehearsal-no-remote-access",
};
const receipts: any[] = [];
const io: IO = {
  env: (k) => env[k],
  db,
  // deno-lint-ignore require-await -- fixture implements the async fetch interface
  fetch: (async (input: any) => {
    const url = String(input);
    if (url.endsWith("/actions/runs/123")) {
      return Response.json({
        path: ".github/workflows/delivery-worker.yml",
        event: "workflow_dispatch",
        head_branch: "main",
        head_sha: "b".repeat(40),
        status: "in_progress",
        actor: { id: config.operator_github_id },
        triggering_actor: { id: config.operator_github_id },
      });
    }
    if (url.includes("/contents/delivery/delivery-policy.json?")) {
      return Response.json({
        encoding: "base64",
        size: 1000,
        content: btoa(JSON.stringify(config)),
      });
    }
    throw Error("External GitHub effect forbidden in rehearsal");
  }) as typeof fetch,
  slack: async (method, data) => {
    if (!["auth.test", "chat.postMessage", "chat.update"].includes(method)) {
      throw Error(
        "Slack method denied",
      );
    }
    if (method !== "auth.test") {
      data = structuredClone(data);
      data.text = "TESTE DO WORKER · sem release · " + data.text;
      const blocks = data.blocks as any[];
      blocks.unshift({
        type: "section",
        text: {
          type: "plain_text",
          text:
            "🧪 Teste de DMs/worker — publicação bloqueada. Aceites de validação, sem release, preview ou patch.",
        },
      });
      for (
        const b of blocks
      ) {
        if (b.text?.type === "mrkdwn" && b.text.text.includes("/releases/tag/")) {
          b.text.text =
            "<https://github.com/israelhudson/flutter_code_push_example/pull/53|Código sob teste — PR #53>";
        }
      }
    }
    const r = await fetch(slackRequest(method, data, token)).then((r) => r.json());
    if (!r.ok) throw Error("Slack error: " + r.error);
    receipts.push({ method, channel: r.channel, ts: r.ts });
    return r;
  },
  wait: () => {},
  log: () => {},
};
const handler = deliveryControlHandler(io);
async function control(operation: string, data: any = {}) {
  const r = await handler(
    new Request("https://local-rehearsal.invalid", {
      method: "POST",
      headers: { authorization: "Bearer " + env.POC_REGISTRATION_SECRET },
      body: JSON.stringify({ operation, run_id: "123", ...data }),
    }),
  );
  if (!r.ok) throw Error("Worker handler rejected " + operation + ": " + r.status);
  return r.json();
}
async function drain() {
  for (let i = 0; i < 50; i++) {
    const lease = crypto.randomUUID(), w = await control("take", { lease });
    if (!w) return;
    if (w.task.kind === "dispatch") throw Error("Unexpected dispatch");
    if (w.task.kind === "history") {
      // Fixture receipt only: this test does not claim GitHub journal validation.
      await db("rpc/delivery_finish", {
        p_id: w.task.id,
        p_lease: lease,
        p_receipt: "f".repeat(40),
      });
    } else await control("send", { task_id: w.task.id, lease });
  }
  throw Error("Queue did not drain");
}
await Deno.mkdir(output, { recursive: true });
let c: any;
if (mode === "prepare") {
  if ((await sql("select count(*) n from delivery_control"))[0].n !== 0) {
    throw Error("Requires empty v2");
  }
  if (config.solo !== true || config.reviewer_source !== "database-v1") {
    throw Error("Rehearsal requires the explicit solo database-reviewer policy");
  }
  const reviewers = await db("rpc/delivery_resolve_reviewers", {
    p_repository: config.repository,
    p_team: config.team_id,
    p_solo: config.solo,
  });
  c = {
    id: "delivery-" + crypto.randomUUID().replaceAll("-", ""),
    repository: config.repository,
    version: "99.0.1",
    rc_number: 1,
    rc_tag: "poc-v99.0.1-rc.1",
    source_sha: "a".repeat(40),
    manifest_commit: "b".repeat(40),
    manifest_digest: "c".repeat(64),
    team_id: config.team_id,
    channel_id: config.channel_id,
    technical_user: reviewers.technical.slack_user,
    business_user: reviewers.business.slack_user,
    reviewers,
    solo: true,
    scope: "none",
  };
  await Deno.writeTextFile(output + "/fixture.json", JSON.stringify(c, null, 2));
  await db("rpc/delivery_register", { p_candidate: c });
  await drain();
} else {
  c = JSON.parse(await Deno.readTextFile(output + "/fixture.json"));
  const s = await db("rpc/delivery_state", { p_id: c.id });
  if (mode === "drain") {
    // Only process messages after real Slack callbacks; do not synthesize decisions.
  } else if (mode === "accept") {
    for (const role of ["technical", "business"]) {
      await db("rpc/delivery_decide", {
        p_id: c.id,
        p_role: role,
        p_action: "accept",
        p_user: c.technical_user,
        p_team: c.team_id,
        p_channel: s[role + "_channel"],
        p_message: s[role + "_message"],
      });
    }
  } else if (mode === "close") {
    await db("rpc/delivery_cancel", { p_id: c.id });
    // Simulate a worker dying after reserving history; only this fixture is affected.
    const abandoned = await control("take", { lease: crypto.randomUUID() });
    if (abandoned?.candidate.id !== c.id || abandoned.task.kind !== "history") {
      throw Error("Expected fixture history");
    }
    await sql(
      "update delivery_outbox set leased_at=now()-interval '6 minutes' where id=" +
        Number(abandoned.task.id),
    );
    receipts.push({ test: "expired_history_lease_recovered", task_id: abandoned.task.id });
  } else throw Error("Unknown mode");
  await drain();
}
const state = await db("rpc/delivery_state", { p_id: c.id });
if ((await sql("select count(*) n from delivery_outbox where kind='dispatch'"))[0].n !== 0) {
  throw Error("Dispatch must remain absent");
}
await Deno.writeTextFile(
  output + "/" + mode + "-receipts.json",
  JSON.stringify(
    {
      test: "real SQL and Slack; fixture GitHub authorization/history; local handler",
      state,
      receipts,
    },
    null,
    2,
  ) + "\n",
);
console.log(
  JSON.stringify({
    mode,
    status: state.status,
    technical_channel: state.technical_channel,
    business_channel: state.business_channel,
    channel_message: state.channel_message,
    slack_calls: receipts.length,
  }),
);

if (mode === "close") {
  await sql(
    "delete from delivery_outbox where candidate_id=" + quote(c.id) +
      "; delete from delivery_control where id=" + quote(c.id),
  );
}
