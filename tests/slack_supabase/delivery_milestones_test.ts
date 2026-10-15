// deno-lint-ignore-file require-await
import {
  deliveryCard,
  deliveryControlHandler,
  deliveryNotice,
} from "../../supabase/functions/_shared/delivery.ts";
import { digest, type IO } from "../../supabase/functions/_shared/poc.ts";

function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
const cfg = JSON.parse(await Deno.readTextFile("delivery/delivery-policy.json"));
const candidate = {
  id: "delivery-" + "a".repeat(32),
  version: "2.0.0",
  rc_number: 2,
  rc_tag: "poc-v2.0.0-rc.2",
  source_sha: "b".repeat(40),
  status: "published",
  publication_run: "456",
  channel_id: cfg.channel_id,
  channel_message: "100.1",
  technical_user: "UTECH",
  business_user: "UBIZ",
};
function task(status = "publishing") {
  return {
    id: 7,
    candidate_id: candidate.id,
    kind: "notice",
    revision: 3,
    event: {
      schema: "delivery-channel-notice-v1",
      candidate: candidate.id,
      revision: 3,
      status,
      source_sha: candidate.source_sha,
      version: candidate.version,
      rc_number: candidate.rc_number,
      rc_tag: candidate.rc_tag,
      publication_run: candidate.publication_run,
    },
  };
}
Deno.test("milestones render the frozen event in a broadcast reply, with no mentions", () => {
  for (const status of ["publishing", "published", "rejected", "cancelled"]) {
    const payload = deliveryNotice(candidate, task(status));
    assert(payload.channel === cfg.channel_id && payload.thread_ts === "100.1");
    assert(payload.reply_broadcast && payload.unfurl_links === false);
    assert(!JSON.stringify(payload).includes("<@") && !JSON.stringify(payload).includes("<!"));
    assert(payload.text.includes(status === "published" ? "/poc-v2.0.0|" : candidate.rc_tag));
    assert(
      payload.text.includes("/actions/runs/456") === ["publishing", "published"].includes(status),
    );
  }
  assert(
    deliveryNotice(candidate, task()).text.startsWith("Publicando"),
    "not current published state",
  );
  assert(deliveryNotice(candidate, task("published")).text.startsWith("Release GitHub"));
});
Deno.test("milestones refuse other candidates, revisions, channels and unsupported states", () => {
  const original = task();
  for (
    const [c, t] of [
      [{ ...candidate, channel_id: "COTHER" }, original],
      [{ ...candidate, channel_message: null }, original],
      [candidate, { ...original, kind: "channel" }],
      [candidate, { ...original, revision: 4 }],
      [candidate, task("approved")],
      [candidate, { ...original, event: { ...original.event, candidate: "other" } }],
      [candidate, { ...original, event: { ...original.event, source_sha: "c".repeat(40) } }],
      [candidate, { ...original, event: { ...original.event, rc_tag: "poc-v2.0.0-rc.1" } }],
      [candidate, { ...original, event: { ...original.event, publication_run: "999" } }],
    ]
  ) {
    let denied = false;
    try {
      deliveryNotice(c, t);
    } catch {
      denied = true;
    }
    assert(denied);
  }
});
async function fixture() {
  const calls: { path: string; data?: any }[] = [];
  const report = { ...candidate, validation_mode: "controls_only" };
  const reportText = JSON.stringify(report);
  const c: any = {
    ...candidate,
    manifest_commit: "c".repeat(40),
    manifest_digest: await digest(reportText),
    solo: true,
    scope: "github_test",
    technical_at: "now",
    business_at: "now",
  };
  const work = { task: task(), candidate: c };
  const run = {
    path: ".github/workflows/delivery-worker.yml",
    head_branch: "main",
    event: "workflow_dispatch",
    status: "in_progress",
    head_sha: "d".repeat(40),
    actor: { id: cfg.operator_github_id },
    triggering_actor: { id: cfg.operator_github_id },
  };
  const release: any = { tag_name: "poc-v2.0.0", draft: false, prerelease: false, assets: [] };
  const bodies = new Map<string, string>();
  let failBegin = false;
  const io: IO = {
    env: (k) =>
      ({
        SUPABASE_URL: "https://xtvueqciogzkyjkkqxcx.supabase.co",
        POC_ENABLED: "true",
        DELIVERY_V2_ENABLED: "true",
        DELIVERY_SOURCE_BRANCH: "main",
        POC_REGISTRATION_SECRET: "offline",
        POC_SLACK_BOT_USER_ID: "UBOT",
      })[k],
    db: async (path, data) => {
      calls.push({ path, data });
      if (path === "rpc/delivery_begin") {
        if (failBegin) throw Error("effect already started");
        return work;
      }
      if (path === "rpc/delivery_state") return c;
      if (path === "rpc/delivery_refresh") return { ...c, revision: 5 };
      if (path === "rpc/delivery_finish") return null;
      throw Error("unexpected database call");
    },
    slack: async (method, data) => {
      calls.push({ path: method, data });
      if (method === "auth.test") return { team_id: cfg.team_id, user_id: "UBOT" };
      assert(method === "chat.postMessage", "exactly one new effect, never card update here");
      return { channel: cfg.channel_id, ts: "200.2" };
    },
    fetch: (async (u) => {
      const path = String(u);
      calls.push({ path });
      if (path.includes("/actions/runs/")) return Response.json(run);
      if (path.includes("/contents/delivery/delivery-policy.json")) {
        return Response.json({ encoding: "base64", size: 100, content: btoa(JSON.stringify(cfg)) });
      }
      if (path.includes("/manifest.json")) {
        return Response.json({
          encoding: "base64",
          size: reportText.length,
          content: btoa(reportText),
        });
      }
      if (path.includes("/releases/tags/")) return Response.json(release);
      if (bodies.has(path)) return new Response(bodies.get(path));
      throw Error("unexpected network call");
    }) as typeof fetch,
    wait: () => {},
    log: () => {},
  };
  const request = (operation = "send", extra = {}) =>
    new Request("https://test.invalid", {
      method: "POST",
      headers: { Authorization: "Bearer offline" },
      body: JSON.stringify({
        operation,
        run_id: "123",
        task_id: 7,
        lease: crypto.randomUUID(),
        candidate: candidate.id,
        ...extra,
      }),
    });
  return { io, calls, work, run, release, c, bodies, request, failBegin: () => failBegin = true };
}
Deno.test("milestone send has its own effect, reply timestamp and receipt; stale effect cannot resend", async () => {
  const f = await fixture(), handler = deliveryControlHandler(f.io);
  assert((await handler(f.request())).status === 200);
  const sent = f.calls.filter((c) => c.path === "chat.postMessage");
  assert(sent.length === 1 && sent[0].data.thread_ts === "100.1");
  const saved = f.calls.find((c) => c.path === "rpc/delivery_finish")?.data;
  assert(saved.p_message === "200.2" && saved.p_receipt === `slack:${cfg.channel_id}:200.2`);
  assert(f.c.channel_message === "100.1", "never replace the canonical card timestamp");
  f.calls.length = 0;
  f.failBegin();
  assert((await handler(f.request())).status === 409);
  assert(!f.calls.some((c) => c.path === "chat.postMessage" || c.path === "rpc/delivery_finish"));
});
Deno.test("refresh verifies a stable release and returns candidate plus presentation without publishing", async () => {
  const f = await fixture(), handler = deliveryControlHandler(f.io);
  const response = await handler(f.request("refresh"));
  assert(response.status === 200);
  const value = await response.json();
  assert(value.candidate.revision === 5 && value.candidate.report_text);
  assert(value.candidate.publication_run === "456" && value.presentation.rows[0][0] === "GitHub");
  assert(f.calls.some((c) => c.path === "rpc/delivery_refresh"));
  assert(!f.calls.some((c) => c.path.startsWith("chat.") || c.path.includes("dispatches")));
  for (
    const delta of [
      { event: "schedule" },
      { head_branch: "slack-main" },
      { path: ".github/workflows/delivery-publish.yml" },
    ]
  ) {
    Object.assign(f.run, delta);
    f.calls.length = 0;
    assert((await handler(f.request("refresh"))).status === 409);
    assert(!f.calls.some((c) => c.path === "rpc/delivery_refresh"));
    Object.assign(f.run, {
      event: "workflow_dispatch",
      head_branch: "main",
      path: ".github/workflows/delivery-worker.yml",
    });
  }
  f.release.prerelease = true;
  f.calls.length = 0;
  assert((await handler(f.request("refresh"))).status === 409);
  assert(!f.calls.some((c) => c.path === "rpc/delivery_refresh"));
});
Deno.test("published GitHub card does not claim the pending Android staging patch is delivered", () => {
  const c = deliveryCard({ ...candidate, androidStagingPending: true }, "channel");
  assert(c.text === "Release GitHub 2.0.0 publicada · Android staging pendente");
  assert(!c.blocks.some((b: any) => b.type === "actions"));
});
Deno.test("Android milestone freezes patch/base without claiming a successful device install", () => {
  const t = task("android_staging");
  Object.assign(t.event, {
    patch_number: 7,
    release_version: "1.1.0+2",
    asset_digest: "f".repeat(64),
  });
  const payload = deliveryNotice(
    { ...candidate, android_staging_notice_digest: "f".repeat(64) },
    t,
  );
  assert(payload.text.includes("Patch Android 7 disponível em staging · app 1.1.0+2"));
  assert(payload.text.includes("Consulte a validação de instalação no cartão"));
  assert(!payload.text.includes("confirmada") && !payload.text.includes("<@"));
  let denied = false;
  try {
    deliveryNotice({ ...candidate, android_staging_notice_digest: "0".repeat(64) }, t);
  } catch {
    denied = true;
  }
  assert(denied, "different frozen digest cannot be announced");
});
Deno.test("refresh derives Android milestone solely from a real verified asset, never HTTP input", async () => {
  const f = await fixture(), handler = deliveryControlHandler(f.io);
  assert((await handler(f.request("refresh", { p_mobile: { patch_number: 99 } }))).status === 200);
  assert(f.calls.find((c) => c.path === "rpc/delivery_refresh")?.data.p_mobile === null);
  const receipt: any = {
    kind: "platform_delivery_receipt_v1",
    candidate_id: f.c.id,
    delivery_version: f.c.version,
    rc_tag: f.c.rc_tag,
    github_tag: "poc-v2.0.0",
    source_sha: f.c.source_sha,
    report_digest: f.c.manifest_digest,
    target: { platform: "android", release_version: "1.1.0+2" },
    patch_number: 7,
    provider_patch_id: 123,
    uploaded: true,
    track: "staging",
  };
  const url =
    "https://github.com/israelhudson/flutter_code_push_example/releases/download/poc-v2.0.0/platform-receipt-android.json";
  const setReceipt = async () => {
    const body = JSON.stringify(receipt);
    const hash = await digest(body);
    f.bodies.set(url, body);
    f.release.assets = [{
      name: "platform-receipt-android.json",
      browser_download_url: url,
      size: body.length,
      digest: "sha256:" + hash,
    }];
    return hash;
  };
  const hash = await setReceipt();
  f.calls.length = 0;
  assert((await handler(f.request("refresh"))).status === 200);
  const mobile = f.calls.find((c) => c.path === "rpc/delivery_refresh")?.data.p_mobile;
  assert(
    mobile.patch_number === 7 && mobile.release_version === "1.1.0+2" &&
      mobile.asset_digest === hash,
  );
  receipt.source_sha = "0".repeat(40);
  await setReceipt();
  f.calls.length = 0;
  assert((await handler(f.request("refresh"))).status === 409);
  assert(!f.calls.some((c) => c.path === "rpc/delivery_refresh"));
});
