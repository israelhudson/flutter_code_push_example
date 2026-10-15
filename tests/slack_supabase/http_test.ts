// deno-lint-ignore-file require-await
// Test transports intentionally return resolved promises without real network I/O.
import {
  card,
  CHANNEL,
  controlHandler,
  digest,
  IO,
  isolated,
  sendNotice,
  slackHandler,
  slackRequest,
  validSignature,
} from "../../supabase/functions/_shared/poc.ts";

function assert(value: unknown, why = "assertion failed") {
  if (!value) throw Error(why);
}
const id = "poc-" + "a".repeat(32), user = "U0BMFQKC001";
function candidate() {
  return {
    id,
    rc_tag: "poc-v0.1.0-rc.1",
    source_sha: "a".repeat(40),
    channel_id: CHANNEL,
    team_id: "T09CYB7AS77",
    is_lab: true,
    mode: "solo_test",
    status: "pending",
    publication_scope: "none",
    technical_reviewer: user,
    business_reviewer: user,
    creator_slack: user,
    message_ts: "100.100",
    expires_at: new Date(Date.now() + 3600000).toISOString(),
    approvals: [],
    report_text: JSON.stringify({
      title: "Teste local",
      changelog: "Resumo",
      preview_url: "https://israelhudson.github.io/flutter_code_push_example/snapshots/" +
        "a".repeat(40) + "/",
      run_url: "https://github.com/israelhudson/flutter_code_push_example/actions/runs/1",
    }),
  };
}
function fixture(overrides: Partial<IO> = {}) {
  const calls: any[] = [], tasks: Promise<unknown>[] = [], logs: string[] = [];
  const env: Record<string, string> = {
    SUPABASE_URL: "https://" + "a".repeat(20) + ".supabase.co",
    POC_ENABLED: "true",
    POC_SLACK_APP_ID: "APOC",
    POC_SLACK_SIGNING_SECRET: "local-fixture-signing-secret",
    POC_REGISTRATION_SECRET: "fixture-reg",
    POC_PUBLICATION_SECRET: "fixture-pub",
  };
  const io: IO = {
    env: (k) => env[k],
    db: async (path, data) => {
      calls.push([path, data]);
      if (path === "rpc/poc_action") {
        return { ...candidate(), approvals: [{ role: data?.p_action }], changed: true };
      }
      if (path === "rpc/poc_state") return candidate();
      if (path === "rpc/poc_notice") return { send: false };
      throw Error("Unexpected RPC");
    },
    slack: async (method, data) => {
      calls.push([method, data]);
      return { ok: true, channel: "DTEST", ts: "1.001" };
    },
    fetch: (() => {
      throw Error("Network forbidden in fixture");
    }) as typeof fetch,
    wait: (p) => tasks.push(p),
    log: (e) => logs.push(e),
    ...overrides,
  };
  return { io, env, calls, tasks, logs };
}
function payload() {
  return {
    type: "block_actions",
    api_app_id: "APOC",
    team: { id: "T09CYB7AS77" },
    user: { id: user },
    channel: { id: CHANNEL },
    container: { channel_id: CHANNEL, message_ts: "100.100" },
    actions: [{ action_id: "poc_technical", value: id }],
  };
}
async function signed(p: unknown, delta = 0, secret = "local-fixture-signing-secret") {
  const raw = new URLSearchParams({ payload: JSON.stringify(p) }).toString();
  const ts = String(Math.floor(Date.now() / 1000) + delta);
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = "v0=" +
    [
      ...new Uint8Array(
        await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`v0:${ts}:${raw}`)),
      ),
    ].map((x) => x.toString(16).padStart(2, "0")).join("");
  return {
    raw,
    ts,
    signature,
    request: new Request("https://fixture.invalid", {
      method: "POST",
      body: raw,
      headers: { "x-slack-request-timestamp": ts, "x-slack-signature": signature },
    }),
  };
}
Deno.test("HMAC: corpo exato, segredo, prazo e adulteração", async () => {
  const s = await signed(payload());
  assert(await validSignature(s.raw, s.ts, s.signature, "local-fixture-signing-secret"));
  assert(!await validSignature(s.raw + "x", s.ts, s.signature, "local-fixture-signing-secret"));
  assert(!await validSignature(s.raw, s.ts, s.signature, "wrong"));
  assert(
    !await validSignature(
      s.raw,
      s.ts,
      s.signature,
      "local-fixture-signing-secret",
      Date.now() + 301000,
    ),
  );
});
for (
  const [label, mutate] of [
    ["outro canal", (p: any) => p.channel.id = "C0C5DCFU5HU"],
    ["outro workspace", (p: any) => p.team.id = "TOTHER"],
    ["app compartilhado", (p: any) => p.api_app_id = "ASHARED"],
    ["botão estrangeiro", (p: any) => p.actions[0].action_id = "lab_technical"],
    ["candidata Mobile", (p: any) => p.actions[0].value = "test-mobile-123"],
    ["container divergente", (p: any) => p.container.channel_id = "COTHER"],
    ["duas ações", (p: any) => p.actions.push(p.actions[0])],
  ] as const
) {
  Deno.test(`HTTP assinado bloqueia ${label} sem escrever`, async () => {
    const f = fixture(), p = payload();
    mutate(p);
    const r = await slackHandler(f.io)((await signed(p)).request);
    assert(r.status === 403);
    assert(!f.tasks.length && !f.calls.length);
  });
}
Deno.test("HTTP recusa assinatura velha e flag desativada", async () => {
  const f = fixture();
  assert((await slackHandler(f.io)((await signed(payload(), -301)).request)).status === 401);
  f.env.POC_ENABLED = "false";
  assert((await slackHandler(f.io)((await signed(payload())).request)).status === 403);
  assert(f.calls.length === 0);
});
Deno.test("ACK não espera cartão/DM e erro de identidade não produz aceite", async () => {
  const f = fixture({
    db: async () => {
      throw Error("unauthorized_context");
    },
  });
  const r = await slackHandler(f.io)((await signed(payload())).request);
  assert(r.status === 200);
  await Promise.all(f.tasks);
  assert(f.logs.includes("poc_action_not_confirmed"));
  assert(!f.calls.some((x) => x[0] === "chat.postMessage"));
});
Deno.test("Projeto Mobile, URL não HTTPS e redirects são recusados", () => {
  for (
    const url of [
      "https://uvfwvplcziehxrkidrxh.supabase.co",
      "http://" + "a".repeat(20) + ".supabase.co",
      "https://user:pass@" + "a".repeat(20) + ".supabase.co",
      "https://" + "a".repeat(20) + ".supabase.co?project=other",
    ]
  ) {
    let rejected = false;
    try {
      isolated(url);
    } catch {
      rejected = true;
    }
    assert(rejected);
  }
});
Deno.test("Cartão expirado/ajustado não oferece aceite; resumo não inventa pessoas", () => {
  const c: any = candidate();
  c.mode = "two_reviewers";
  c.business_reviewer = "UFIXTUREBUSINESS";
  c.expires_at = "2000-01-01T00:00:00Z";
  const text = JSON.stringify(card(c));
  assert(!text.includes('"action_id":"poc_technical"'));
  assert(!text.includes('"action_id":"poc_business"'));
  assert(!text.includes("Fabrícia"));
  c.expires_at = new Date(Date.now() + 100000).toISOString();
  c.status = "adjustment_requested";
  assert(!JSON.stringify(card(c)).includes('"action_id":"poc_adjust"'));
});
Deno.test("Envio incerto reserva antes do POST e não tenta novamente", async () => {
  const trace: string[] = [];
  let reserved = false;
  const f = fixture({
    db: async (path, data) => {
      trace.push(path + ":" + (data?.p_state ?? data?.p_claim ?? ""));
      if (path === "rpc/poc_notice") {
        if (data?.p_claim && reserved) return { send: false };
        reserved = true;
        return { send: true, recipient: user, pending_role: "business" };
      }
      if (path === "rpc/poc_state") return candidate();
      return null;
    },
    slack: async () => {
      trace.push("POST");
      throw Error("timeout");
    },
  });
  try {
    await sendNotice(f.io, id, "review_pending:business");
  } catch { /* expected uncertain */ }
  await sendNotice(f.io, id, "review_pending:business");
  assert(trace.indexOf("rpc/poc_notice:true") < trace.indexOf("POST"));
  assert(trace.filter((x) => x === "POST").length === 1);
  assert(trace.some((x) => x === "rpc/poc_finish_notice:uncertain"));
});
Deno.test("Controle não aceita workflow/ator arbitrário só por ter secret", async () => {
  const f = fixture({
    db: async (path) =>
      path.startsWith("poc_config")
        ? [{ enabled: true, operator_github: "israelhudson" }]
        : [{ github_id: 18661493 }],
    fetch: (async () =>
      Response.json({
        head_branch: "slack-main",
        event: "workflow_dispatch",
        path: ".github/workflows/poc-slack-prepare.yml",
        actor: { id: 42 },
        triggering_actor: { id: 42 },
      })) as typeof fetch,
  });
  const r = await controlHandler(f.io)(
    new Request("https://fixture.invalid", {
      method: "POST",
      headers: { Authorization: "Bearer fixture-reg" },
      body: JSON.stringify({ operation: "plan", run_id: 1, version: "1.0.0" }),
    }),
  );
  assert(r.status === 409);
});
Deno.test("Controle exige credencial separada para publicação", async () => {
  const f = fixture();
  const r = await controlHandler(f.io)(
    new Request("https://fixture.invalid", {
      method: "POST",
      headers: { Authorization: "Bearer fixture-reg" },
      body: JSON.stringify({ operation: "claim", run_id: 1, candidate: id }),
    }),
  );
  assert(r.status === 401);
  assert(f.calls.length === 0);
});
Deno.test("Digest textual coincide com contrato SHA-256 do banco", async () => {
  assert(
    await digest("abc") === "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
});

Deno.test("Controle aceita operador verificado somente na branch configurada", async () => {
  const f = fixture({
    db: async (path) => {
      if (path.startsWith("poc_config")) {
        return [{ enabled: true, operator_github: "israelhudson" }];
      }
      if (path.startsWith("poc_user_directory")) {
        return [{ github_id: 18661493, github_login: "israelhudson" }];
      }
      if (path.startsWith("poc_candidates")) return [];
      throw Error("Unexpected DB");
    },
    fetch: (async (url) =>
      String(url).includes("actions/runs/")
        ? Response.json({
          head_branch: "slack-main",
          head_sha: "a".repeat(40),
          event: "workflow_dispatch",
          path: ".github/workflows/poc-slack-prepare.yml",
          actor: { id: 18661493 },
          triggering_actor: { id: 18661493 },
        })
        : new Response("not found", { status: 404 })) as typeof fetch,
  });
  const r = await controlHandler(f.io)(
    new Request("https://fixture.invalid", {
      method: "POST",
      headers: { Authorization: "Bearer fixture-reg" },
      body: JSON.stringify({ operation: "plan", run_id: 1, version: "1.0.0", title: "Tema" }),
    }),
  );
  assert(r.status === 200);
  const plan = await r.json();
  assert(plan.source_sha === "a".repeat(40) && plan.rc_tag === "poc-v1.0.0-rc.1");
});

Deno.test("Conclusão exige Release final real; pré-lançamento, draft e recibo falso bloqueiam", async () => {
  for (const failure of ["none", "prerelease", "missing_flag", "draft", "tag", "sha", "receipt"]) {
    const writes: string[] = [];
    const c: any = { ...candidate(), version: "0.1.0", publication_scope: "github_test" };
    const release: any = { id: 42, draft: false, prerelease: false, tag_name: "poc-v0.1.0" };
    if (failure === "prerelease") release.prerelease = true;
    if (failure === "missing_flag") delete release.prerelease;
    if (failure === "draft") release.draft = true;
    if (failure === "tag") release.tag_name = "poc-v9.0.0";
    const f = fixture({
      db: async (path) => {
        if (path.startsWith("poc_config")) {
          return [{ enabled: true, operator_github: "israelhudson" }];
        }
        if (path.startsWith("poc_user_directory")) return [{ github_id: 18661493 }];
        if (path === "rpc/poc_state") return c;
        if (path === "rpc/poc_publish") {
          writes.push(path);
          return { published: true };
        }
        throw Error("Unexpected DB");
      },
      fetch: (async (url) => {
        const path = String(url);
        if (path.includes("actions/runs/")) {
          return Response.json({
            head_branch: "slack-main",
            event: "workflow_dispatch",
            path: ".github/workflows/poc-slack-publish.yml",
            actor: { id: 18661493 },
            triggering_actor: { id: 18661493 },
          });
        }
        if (path.includes("releases/tags/")) return Response.json(release);
        if (path.includes("git/ref/tags/")) {
          return Response.json({
            object: { type: "commit", sha: failure === "sha" ? "b".repeat(40) : c.source_sha },
          });
        }
        throw Error("Unexpected HTTP");
      }) as typeof fetch,
    });
    f.env.POC_PUBLICATION_ENABLED = "true";
    const r = await controlHandler(f.io)(
      new Request("https://fixture.invalid", {
        method: "POST",
        headers: { Authorization: "Bearer fixture-pub" },
        body: JSON.stringify({
          operation: "complete",
          run_id: "1",
          candidate: id,
          receipt: { release_id: 42, prerelease: failure === "receipt" ? true : false },
        }),
      }),
    );
    await Promise.all(f.tasks);
    assert(r.status === (failure === "none" ? 200 : 409), failure);
    assert(
      writes.length === (failure === "none" ? 1 : 0),
      failure + " must not finish publication",
    );
  }
});
Deno.test("Aceite salvo não recebe mensagem de falha quando aviso posterior falha", async () => {
  const f = fixture({
    db: async (path) => {
      if (path === "rpc/poc_action") return { ...candidate(), approvals: [{ role: "technical" }] };
      throw Error("Notification unavailable");
    },
  });
  const r = await slackHandler(f.io)((await signed(payload())).request);
  assert(r.status === 200);
  await Promise.all(f.tasks);
  assert(f.logs.includes("poc_vote_saved_notification_failed"));
  assert(!f.logs.includes("poc_action_not_confirmed"));
});

Deno.test("Slack lê membros por GET e envia mensagens por POST JSON", async () => {
  const read = slackRequest("conversations.members", {
    channel: "C0C8DUJB52L",
    limit: 200,
    cursor: "a+/=",
  }, "fixture-token");
  assert(read.method === "GET" && read.body === null);
  assert(new URL(read.url).searchParams.get("channel") === "C0C8DUJB52L");
  assert(new URL(read.url).searchParams.get("cursor") === "a+/=");
  const post = slackRequest(
    "chat.postMessage",
    { channel: "U0BMFQKC001", text: "fixture" },
    "fixture-token",
  );
  assert(post.method === "POST" && (await post.json()).text === "fixture");
  assert(post.redirect === "error" && read.redirect === "error");
});

Deno.test("Botões de URL confirmam navegação sem RPC, voto ou aviso", async () => {
  for (const action of ["poc_preview", "poc_changelog", "poc_release", "poc_workflow_link"]) {
    const f = fixture();
    const p = payload();
    p.actions[0].action_id = action;
    const r = await slackHandler(f.io)((await signed(p)).request);
    assert(r.status === 200 && f.calls.length === 0 && f.tasks.length === 0);
  }
  const rendered = card(candidate());
  const buttons = rendered.blocks.at(-1)!.elements ?? [];
  assert(buttons[0].action_id === "poc_preview" && buttons[1].action_id === "poc_changelog");
  assert(buttons[0].value === id && buttons[1].value === id);
});

Deno.test("Negar versão registra ação assinada sem modal, justificativa ou dispatch", async () => {
  const f = fixture(), p = payload();
  p.actions[0].action_id = "poc_reject";
  const r = await slackHandler(f.io)((await signed(p)).request);
  assert(r.status === 200);
  await Promise.all(f.tasks);
  const actions = f.calls.filter(([path]) => path === "rpc/poc_action");
  assert(actions.length === 1 && actions[0][1].p_action === "reject");
  assert(actions[0][1].p_user === user && actions[0][1].p_reason === undefined);
  assert(!f.calls.some(([path]) => path === "views.open" || path === "rpc/poc_notice"));
  assert(!f.logs.includes("poc_action_not_confirmed"));
});

Deno.test("Cartão de controles explica limites, permite negar e não inventa preview", () => {
  const c: any = candidate();
  c.report_text = JSON.stringify({
    ...JSON.parse(c.report_text),
    validation_mode: "controls_only",
    preview_url: null,
  });
  let rendered = JSON.stringify(card(c));
  assert(rendered.includes("ENSAIO SOMENTE DE CONTROLES") && rendered.includes("Negar versão"));
  assert(!rendered.includes('"action_id":"poc_preview"'));
  c.status = "adjustment_requested";
  c.adjustment_reason = null;
  rendered = JSON.stringify(card(c));
  assert(rendered.includes("Versão negada") && rendered.includes("sem justificativa"));
  assert(
    !rendered.includes('"action_id":"poc_reject"') &&
      !rendered.includes('"action_id":"poc_technical"'),
  );
});
Deno.test("Botão de URL não aceita outro canal ou assinatura inválida", async () => {
  const p = payload();
  p.actions[0].action_id = "poc_preview";
  p.channel.id = "COTHER";
  const f = fixture();
  assert((await slackHandler(f.io)((await signed(p)).request)).status === 403);
  p.channel.id = CHANNEL;
  assert((await slackHandler(f.io)((await signed(p, 0, "wrong-secret")).request)).status === 401);
  assert(f.calls.length === 0 && f.tasks.length === 0);
});

Deno.test("published card highlights final release and preserves candidate evidence after expiry", () => {
  const c = {
    ...candidate(),
    version: "0.1.0",
    status: "published",
    publication_scope: "github_test",
    approvals: [{ role: "technical" }, { role: "business" }],
    expires_at: "2020-01-01T00:00:00Z",
  };
  const rendered = card(c);
  const text = JSON.stringify(rendered);
  assert(rendered.text.startsWith("✅ Versão 0.1.0 publicada"));
  assert(text.includes("Promovida de: poc-v0.1.0-rc.1"));
  assert(text.includes("publicada · GitHub"));
  assert(!text.includes("Flutter POC"));
  assert(rendered.blocks.some((b) => b.type === "table"));
  assert(!text.includes("candidata bloqueada"));
  const buttons = rendered.blocks.at(-1)!.elements!;
  assert(
    buttons[0].url ===
      "https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v0.1.0",
  );
  assert(buttons.every((b: any) => b.url));
  assert(buttons.some((b: any) => b.text.text === "Preview aprovado"));
});

Deno.test("unpublished cards never claim a final release", () => {
  for (
    const status of [
      "pending",
      "approved",
      "publishing",
      "adjustment_requested",
      "cancelled",
      "expired",
    ]
  ) {
    const rendered = card({ ...candidate(), version: "0.1.0", status });
    const text = JSON.stringify(rendered);
    assert(!text.includes("poc_release"));
    assert(!text.includes("Versão 0.1.0 publicada"));
    assert(text.includes("poc-v0.1.0-rc.1"));
  }
});

Deno.test("Refreshing published versions only edits the original card and never writes approvals or publication", async () => {
  const c = {
    ...candidate(),
    version: "0.1.0",
    status: "published",
    publication_scope: "github_test",
    report_text: JSON.stringify({ validation_mode: "controls_only", title: "Existing release" }),
  };
  const mutations: string[] = [];
  const f = fixture({
    db: async (path) => {
      if (path.startsWith("poc_config")) {
        return [{ enabled: true, operator_github: "israelhudson" }];
      }
      if (path.startsWith("poc_user_directory")) return [{ github_id: 18661493 }];
      if (path === "rpc/poc_state") return c;
      mutations.push(path);
      throw Error("No database write allowed");
    },
    fetch: (async (url) => {
      const path = String(url);
      if (path.includes("actions/runs/")) {
        return Response.json({
          head_branch: "slack-main",
          event: "workflow_dispatch",
          path: ".github/workflows/poc-slack-publish.yml",
          actor: { id: 18661493 },
          triggering_actor: { id: 18661493 },
        });
      }
      if (path.includes("releases/tags/")) {
        return Response.json({
          tag_name: "poc-v0.1.0",
          draft: false,
          prerelease: false,
          assets: [],
        });
      }
      if (path.includes("git/ref/tags/")) {
        return Response.json({ object: { type: "commit", sha: c.source_sha } });
      }
      throw Error("No preview or upload allowed");
    }) as typeof fetch,
  });
  f.env.POC_PUBLICATION_ENABLED = "true";
  const request = (operation: string, secret = "fixture-pub") =>
    new Request("https://fixture.invalid", {
      method: "POST",
      headers: { Authorization: "Bearer " + secret },
      body: JSON.stringify({ operation, run_id: "1", candidate: id }),
    });
  assert((await controlHandler(f.io)(request("refresh_card", "fixture-reg"))).status === 401);
  assert((await controlHandler(f.io)(request("presentation"))).status === 200);
  assert(f.calls.length === 0);
  for (let i = 0; i < 2; i++) {
    assert((await controlHandler(f.io)(request("refresh_card"))).status === 200);
  }
  assert(mutations.length === 0);
  assert(
    f.calls.length === 2 &&
      f.calls.every(([method, data]) => method === "chat.update" && data.ts === c.message_ts),
  );
  c.status = "pending";
  assert((await controlHandler(f.io)(request("refresh_card"))).status === 409);
  assert(f.calls.length === 2);
});
