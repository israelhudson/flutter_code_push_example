// deno-lint-ignore-file require-await
import { deliveryControlHandler } from "../../supabase/functions/_shared/delivery.ts";
import {
  CHANNEL,
  digest,
  type IO,
  REPOSITORY,
  TEAM,
} from "../../supabase/functions/_shared/poc.ts";
import { canonical } from "../../supabase/functions/_shared/preview.ts";

function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
const id = "delivery-" + "a".repeat(32);
const tooling = "b".repeat(40), source = "c".repeat(40), manifestCommit = "d".repeat(40);
function selection(solo = true) {
  const technical = {
    id: "1b2c3d4e-1515-4000-8000-000000000001",
    revision: 1,
    name: "Israel",
    slack_user: "U0BMFQKC001",
    github_user_id: 18661493,
    github_login: "israelhudson",
  };
  return {
    schema: "delivery-reviewers-v1",
    repository: REPOSITORY,
    team_id: TEAM,
    solo,
    technical,
    business: solo ? { ...technical } : {
      ...technical,
      id: "1b2c3d4e-1515-4000-8000-000000000002",
      name: "Negócio",
      slack_user: "UBUSINESS",
      github_user_id: null,
      github_login: null,
    },
  };
}
function fixture() {
  const cfg: any = {
    schema: "delivery-policy-v2",
    repository: REPOSITORY,
    team_id: TEAM,
    channel_id: CHANNEL,
    source_branch: "main",
    history_branch: "codex/delivery-history",
    operator_github_id: 18661493,
    operator_github_login: "israelhudson",
    solo: true,
    reviewer_source: "database-v1",
  };
  const run = {
    path: ".github/workflows/delivery-prepare.yml",
    head_branch: "main",
    event: "workflow_dispatch",
    status: "in_progress",
    head_sha: tooling,
    actor: { id: 18661493 },
    triggering_actor: { id: 18661493 },
  };
  const env: Record<string, string> = {
    SUPABASE_URL: "https://xtvueqciogzkyjkkqxcx.supabase.co",
    POC_ENABLED: "true",
    DELIVERY_V2_ENABLED: "true",
    POC_REGISTRATION_SECRET: "register",
    POC_PUBLICATION_SECRET: "publish",
    POC_PUBLICATION_ENABLED: "false",
    POC_SLACK_BOT_USER_ID: "UBOT",
  };
  const report: any = {
    id,
    repository: REPOSITORY,
    run_url: `https://github.com/${REPOSITORY}/actions/runs/123`,
    tooling_sha: tooling,
    source_sha: source,
    version: "9.1.0",
    rc_number: 1,
    rc_tag: "poc-v9.1.0-rc.1",
    publication_scope: "none",
    validation_mode: "controls_only",
    preview_performed: false,
    distribution_performed: false,
    preview_url: null,
    preview_sha: null,
    web_content_sha256: null,
    snapshot_manifest_sha256: null,
    platforms: {
      android: { base_release_version: null, effective_patch: null },
      ios: { base_release_version: null, effective_patch: null },
    },
    reviewers: selection(),
    previous_candidate: null,
  };
  const dbCalls: { path: string; data: any }[] = [], fetches: string[] = [];
  let currentOperation = "", tagCollision = false;
  let resolved: any = selection(), row: any = null, resolverError = false, registeredOverride: any;
  let registrationError = false;
  let journal: any = { revision: 0, status: "pending", reviewers: selection() };
  let savedJournal: any;
  const io: IO = {
    env: (key) => env[key],
    db: async (path, data) => {
      dbCalls.push({ path, data });
      if (path === "rpc/delivery_resolve_reviewers") {
        if (resolverError) throw Error("No active default");
        return resolved;
      }
      if (path === "rpc/delivery_state") return data?.p_id ? row : [];
      if (path === "rpc/delivery_register") {
        if (registrationError) throw Error("Defaults changed since planning");
        if (registeredOverride) return registeredOverride;
        const candidate: any = data?.p_candidate;
        return {
          ...candidate,
          technical_user: candidate.reviewers.technical.slack_user,
          business_user: candidate.reviewers.business.slack_user,
          technical_reviewer_id: candidate.reviewers.technical.id,
          business_reviewer_id: candidate.reviewers.business.id,
          reviewer_snapshot: candidate.reviewers,
        };
      }
      if (path === "rpc/delivery_task") {
        return { kind: "history", candidate_id: id, revision: 0, event: journal };
      }
      if (["rpc/delivery_take", "rpc/delivery_finish"].includes(path)) return null;
      throw Error("unexpected DB call " + path);
    },
    fetch: (async (url: any) => {
      const path = String(url);
      fetches.push(path);
      if (path.includes("/actions/runs/")) return Response.json(run);
      const file = (value: any) => {
        const text = JSON.stringify(value);
        const encoded = btoa(String.fromCharCode(...new TextEncoder().encode(text)));
        return Response.json({ encoding: "base64", size: text.length, content: encoded });
      };
      if (path.includes("/contents/delivery/delivery-policy.json")) return file(cfg);
      if (path.includes("/manifest.json")) return file(report);
      if (path.includes("/event-0.json")) return file(savedJournal ?? journal);
      if (path.includes("/git/matching-refs/tags/")) return Response.json([]);
      if (path.includes("/git/ref/heads/")) return new Response("", { status: 404 });
      if (path.includes("/git/ref/tags/")) {
        if (currentOperation === "plan" && !tagCollision) {
          return new Response("", { status: 404 });
        }
        return Response.json({ object: { type: "commit", sha: source } });
      }
      throw Error("unexpected fetch " + path);
    }) as typeof fetch,
    slack: async (method) => {
      assert(method === "auth.test");
      return { team_id: TEAM, user_id: "UBOT" };
    },
    wait: () => {},
    log: () => {},
  };
  const request = async (operation: string, data: any = {}) => {
    currentOperation = operation;
    const secret = operation === "state" ? "publish" : "register";
    const payload = {
      operation,
      run_id: "123",
      version: "9.1.0",
      publication_scope: "none",
      validation_mode: "controls_only",
      ...(operation === "register"
        ? {
          candidate: id,
          manifest_commit: manifestCommit,
          manifest_digest: await digest(JSON.stringify(report)),
        }
        : {}),
      ...data,
    };
    return await deliveryControlHandler(io)(
      new Request("https://test.invalid", {
        method: "POST",
        headers: { Authorization: `Bearer ${secret}` },
        body: JSON.stringify(payload),
      }),
    );
  };
  return {
    cfg,
    run,
    env,
    report,
    dbCalls,
    fetches,
    request,
    resolve: (value: any) => resolved = value,
    missing: () => resolverError = true,
    setRow: (value: any) =>
      row = value
        ? Object.assign(value, {
          version: value.version ?? report.version,
          rc_number: value.rc_number ?? report.rc_number,
        })
        : value,
    setRegistered: (value: any) => registeredOverride = value,
    changedDefaults: () => registrationError = true,
    collideTag: () => tagCollision = true,
    setJournal: (value: any, saved?: any) => {
      journal = value;
      savedJournal = saved;
    },
  };
}

Deno.test("reviewers plan resolves automatic defaults in solo without request-selected people", async () => {
  const f = fixture();
  const ioResult = await f.request("plan", { reviewers: { technical: "attacker" } });
  assert(ioResult.status === 200);
  const plan = await ioResult.json();
  assert(canonical(plan.reviewers) === canonical(selection()));
  assert(plan.rc_number === 1 && plan.source_sha === tooling);
  assert(f.dbCalls[0].path === "rpc/delivery_resolve_reviewers");
  assert(
    canonical(f.dbCalls[0].data) === canonical({
      p_repository: REPOSITORY,
      p_team: TEAM,
      p_solo: true,
    }),
  );
});

Deno.test("reviewers plan selects distinct automatic technical and business defaults outside solo", async () => {
  const f = fixture();
  f.cfg.solo = false;
  f.resolve(selection(false));
  const result = await f.request("plan");
  assert(result.status === 200);
  const plan = await result.json();
  assert(plan.reviewers.technical.id !== plan.reviewers.business.id);
  assert(plan.reviewers.solo === false);
});

Deno.test("reviewers plan never falls back to JSON when defaults are missing", async () => {
  const f = fixture();
  f.missing();
  assert((await f.request("plan")).status === 409);
  assert(f.dbCalls.length === 1);
  assert(!f.fetches.some((p) => p.includes("/git/")));
  for (const source of [undefined, "json", "database-v1"]) {
    const old = fixture();
    old.cfg.reviewer_source = source;
    old.cfg.technical = { slack_user: "UOLD" };
    old.cfg.business = { slack_user: "UOLD" };
    assert((await old.request("plan")).status === 409);
    assert(old.dbCalls.length === 0);
  }
});

Deno.test("reviewers plan rejects same-person non-solo and malformed resolver identities", async () => {
  const f = fixture();
  f.cfg.solo = false;
  f.resolve({ ...selection(), solo: false });
  assert((await f.request("plan")).status === 409);
  assert(!f.fetches.some((p) => p.includes("/git/")));
  for (const patch of [{ id: "username" }, { revision: 0 }, { slack_user: "israel" }]) {
    const invalid = fixture(), reviewers = selection();
    Object.assign(reviewers.technical, patch);
    invalid.resolve(reviewers);
    assert((await invalid.request("plan")).status === 409);
  }
});

Deno.test("reviewers register takes the immutable manifest snapshot and checks SQL frozen references", async () => {
  const f = fixture();
  assert((await f.request("register", { technical_user: "UATTACKER" })).status === 200);
  assert(!f.dbCalls.some((c) => c.path === "rpc/delivery_resolve_reviewers"));
  const candidate = f.dbCalls.at(-1)?.data.p_candidate;
  assert(canonical(candidate.reviewers) === canonical(f.report.reviewers));
  assert(!("technical_user" in candidate) && !("business_user" in candidate));
  const mismatch = fixture();
  mismatch.setRegistered({
    solo: true,
    reviewer_snapshot: selection(),
    technical_reviewer_id: "other",
    business_reviewer_id: selection().business.id,
    technical_user: "U0BMFQKC001",
    business_user: "U0BMFQKC001",
  });
  assert((await mismatch.request("register")).status === 409);
});

Deno.test("reviewers register rejects missing or substituted manifest before SQL registration", async () => {
  for (
    const mutate of [
      (report: any) => delete report.reviewers,
      (report: any) => report.reviewers.team_id = "TOTHER",
      (report: any) => report.reviewers.solo = false,
    ]
  ) {
    const f = fixture();
    mutate(f.report);
    assert((await f.request("register")).status === 409);
    assert(!f.dbCalls.some((c) => c.path === "rpc/delivery_register"));
  }
  const f = fixture();
  assert((await f.request("register", { manifest_digest: "0".repeat(64) })).status === 409);
  assert(f.dbCalls.length === 0);
});

Deno.test("reviewers register surfaces atomic SQL refusal when defaults change after plan", async () => {
  const f = fixture();
  f.changedDefaults();
  assert((await f.request("register")).status === 409);
  assert(f.dbCalls.at(-1)?.path === "rpc/delivery_register");
  // Re-resolving now and silently replacing the manifest is forbidden.
  assert(!f.dbCalls.some((c) => c.path === "rpc/delivery_resolve_reviewers"));
});

Deno.test("reviewers new registration refuses legacy or mixed JSON reviewer policy", async () => {
  for (const mixed of [false, true]) {
    const f = fixture();
    if (mixed) f.cfg.technical = { slack_user: "UOLD" };
    else delete f.cfg.reviewer_source;
    assert((await f.request("register")).status === 409);
    assert(f.dbCalls.length === 1 && f.dbCalls[0].path === "rpc/delivery_state");
    assert(!f.dbCalls.some((c) => c.path === "rpc/delivery_register"));
  }
});

Deno.test("reviewers register retries exact legacy manifest without electing defaults or rewriting history", async () => {
  const f = fixture();
  delete f.cfg.reviewer_source;
  delete f.report.reviewers;
  f.cfg.technical = { slack_user: "UOLD" };
  f.cfg.business = { slack_user: "UOLD" };
  const row = {
    id,
    source_sha: source,
    rc_tag: f.report.rc_tag,
    solo: true,
    manifest_commit: manifestCommit,
    manifest_digest: await digest(JSON.stringify(f.report)),
    technical_user: "UOLD",
    business_user: "UOLD",
    reviewer_snapshot: null,
    technical_reviewer_id: null,
    business_reviewer_id: null,
  };
  f.setRow(row);
  assert((await f.request("register")).status === 200);
  assert(f.dbCalls.length === 1 && f.dbCalls[0].path === "rpc/delivery_state");
  row.manifest_commit = "e".repeat(40);
  assert((await f.request("register")).status === 409);
  row.manifest_commit = manifestCommit;
  row.id = "delivery-" + "b".repeat(32);
  assert((await f.request("register")).status === 409);
  f.setRow(null);
  assert((await f.request("register")).status === 409);
  assert(!f.dbCalls.some((c) => c.path === "rpc/delivery_register"));
});

Deno.test("reviewers register retries a new frozen selection without rereading current defaults", async () => {
  const f = fixture();
  f.missing();
  f.cfg.solo = false; // A future policy change must not reassign an existing evaluation.
  f.setRow({
    id,
    source_sha: source,
    rc_tag: f.report.rc_tag,
    solo: true,
    manifest_commit: manifestCommit,
    manifest_digest: await digest(JSON.stringify(f.report)),
    reviewer_snapshot: selection(),
    technical_reviewer_id: selection().technical.id,
    business_reviewer_id: selection().business.id,
    technical_user: "U0BMFQKC001",
    business_user: "U0BMFQKC001",
  });
  assert((await f.request("register")).status === 200);
  assert(f.dbCalls.length === 1 && f.dbCalls[0].path === "rpc/delivery_state");
});

Deno.test("reviewers state validates frozen snapshot but reads historical candidates without registry lookup", async () => {
  const f = fixture();
  f.run.path = ".github/workflows/delivery-publish.yml";
  const row = {
    id,
    source_sha: source,
    rc_tag: f.report.rc_tag,
    solo: true,
    manifest_commit: manifestCommit,
    manifest_digest: await digest(JSON.stringify(f.report)),
    reviewer_snapshot: selection(),
    technical_reviewer_id: selection().technical.id,
    business_reviewer_id: selection().business.id,
    technical_user: "U0BMFQKC001",
    business_user: "U0BMFQKC001",
  };
  f.setRow(row);
  assert((await f.request("state", { candidate: id })).status === 200);
  row.technical_user = "UOTHER";
  assert((await f.request("state", { candidate: id })).status === 409);
  const legacy = fixture();
  legacy.run.path = ".github/workflows/delivery-publish.yml";
  delete legacy.cfg.reviewer_source;
  delete legacy.report.reviewers;
  legacy.cfg.technical = { slack_user: "UOLD" };
  legacy.cfg.business = { slack_user: "UOLD" };
  legacy.setRow({
    id,
    source_sha: source,
    rc_tag: legacy.report.rc_tag,
    solo: true,
    manifest_commit: manifestCommit,
    manifest_digest: await digest(JSON.stringify(legacy.report)),
    technical_user: "UOLD",
    business_user: "UOLD",
  });
  assert((await legacy.request("state", { candidate: id })).status === 200);
  assert(!legacy.dbCalls.some((c) => c.path === "rpc/delivery_resolve_reviewers"));
});

Deno.test("reviewers worker accepts historical policy and validates nested journal contents", async () => {
  const f = fixture();
  f.run.path = ".github/workflows/delivery-worker.yml";
  delete f.cfg.reviewer_source;
  f.cfg.technical = { slack_user: "UOLD" };
  f.cfg.business = { slack_user: "UOLD" };
  assert((await f.request("take", { lease: crypto.randomUUID() })).status === 200);
  const event = { revision: 0, reviewers: selection(), status: "pending" };
  f.setJournal(event, { status: "pending", reviewers: selection(), revision: 0 });
  assert(
    (await f.request("finish", {
      task_id: 1,
      lease: crypto.randomUUID(),
      receipt: source,
    })).status === 200,
  );
  const forged = selection();
  forged.technical.slack_user = "UOTHER";
  f.setJournal(event, { ...event, reviewers: forged });
  assert(
    (await f.request("finish", {
      task_id: 1,
      lease: crypto.randomUUID(),
      receipt: source,
    })).status === 409,
  );
});
