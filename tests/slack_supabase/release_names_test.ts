// deno-lint-ignore-file require-await
import { PGlite } from "@electric-sql/pglite";
import { candidateNames, releaseNames } from "../../supabase/functions/_shared/release_names.ts";
import {
  deliveryCard,
  deliveryControlHandler,
  deliveryNotice,
} from "../../supabase/functions/_shared/delivery.ts";
import {
  defaultRows,
  mobileRow,
  versionPresentation,
} from "../../supabase/functions/_shared/versions.ts";
import {
  CHANNEL,
  digest,
  type IO,
  REPOSITORY,
  TEAM,
} from "../../supabase/functions/_shared/poc.ts";

function assert(value: unknown, message = "assertion failed") {
  if (!value) throw Error(message);
}
const id = "delivery-" + "a".repeat(32);
const source = "b".repeat(40);
function c(legacy = false) {
  return {
    id,
    version: "12.0.0",
    rc_number: 1,
    ...candidateNames("12.0.0", 1, legacy ? "legacy" : "official"),
    source_sha: source,
    report_digest: "c".repeat(64),
    report_text: JSON.stringify({ validation_mode: "controls_only" }),
    status: "published",
    publication_run: "123",
    channel_id: CHANNEL,
    channel_message: "100.1",
    technical_user: "UTECH",
    business_user: "UBIZ",
  };
}
function receipt(candidate: any) {
  return {
    kind: "platform_delivery_receipt_v1",
    candidate_id: id,
    delivery_version: candidate.version,
    rc_tag: candidate.rc_tag,
    github_tag: releaseNames(candidate).final_tag,
    source_sha: source,
    report_digest: candidate.report_digest,
    target: { platform: "android", release_version: "1.1.0+2" },
    patch_number: 5,
    provider_patch_id: 123,
    uploaded: true,
    track: "staging",
  };
}
Deno.test("frozen names: new official family, old family retained and mixed identities rejected", () => {
  assert(candidateNames("12.0.0", 1).rc_tag === "v12.0.0-rc.1");
  assert(candidateNames("12.0.0", 1).branch === "release/12.0.0");
  assert(releaseNames(c(true)).final_tag === "poc-v12.0.0");
  assert(releaseNames(c(false)).final_tag === "v12.0.0");
  for (
    const patch of [{ rc_tag: "v12.0.0-rc.2" }, { branch: "poc-release/12.0.0" }, {
      version: "12.0.1",
    }]
  ) {
    let denied = false;
    try {
      releaseNames({ ...c(), ...patch });
    } catch {
      denied = true;
    }
    assert(denied);
  }
});
Deno.test("both frozen families render their own Slack links, version table and verified asset URLs", async () => {
  for (const legacy of [false, true]) {
    const candidate = c(legacy), names = releaseNames(candidate), r = receipt(candidate);
    assert(defaultRows(candidate)[0][1] === names.final_tag);
    assert(
      JSON.stringify(deliveryCard(candidate, "channel")).includes(
        `/releases/tag/${names.final_tag}`,
      ),
    );
    const notice = deliveryNotice(candidate, {
      kind: "notice",
      revision: 3,
      event: {
        schema: "delivery-channel-notice-v1",
        candidate: id,
        revision: 3,
        status: "published",
        source_sha: source,
        version: candidate.version,
        rc_number: 1,
        rc_tag: candidate.rc_tag,
        publication_run: "123",
      },
    });
    assert(notice.text.includes(`/releases/tag/${names.final_tag}`));
    assert(mobileRow(candidate, r)[1] === "1.1.0+2 (patch 5)");
    const payload = JSON.stringify(r),
      url =
        `https://github.com/${REPOSITORY}/releases/download/${names.final_tag}/platform-receipt-android.json`;
    const asset = {
      name: "platform-receipt-android.json",
      browser_download_url: url,
      size: payload.length,
      digest: "sha256:" + await digest(payload),
    };
    const result = await versionPresentation(
      {
        fetch: (async (u) => {
          assert(String(u) === url);
          return new Response(payload);
        }) as typeof fetch,
      },
      candidate,
      { tag_name: names.final_tag, draft: false, prerelease: false, assets: [asset] },
    );
    assert(result.rows[2][1] === "1.1.0+2 (patch 5)");
    let denied = false;
    try {
      mobileRow(candidate, { ...r, github_tag: legacy ? "v12.0.0" : "poc-v12.0.0" });
    } catch {
      denied = true;
    }
    assert(denied);
  }
});
function planFixture() {
  const tags: any[] = [], branches = new Map<string, any>(), rows: any[] = [];
  const person = {
    id: "1b2c3d4e-1515-4000-8000-000000000001",
    revision: 1,
    name: "Israel",
    slack_user: "USOLO",
    github_user_id: 18661493,
    github_login: "israelhudson",
  };
  const reviewers = {
    schema: "delivery-reviewers-v1",
    repository: REPOSITORY,
    team_id: TEAM,
    solo: true,
    technical: person,
    business: person,
  };
  const policy = {
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
  const io: IO = {
    env: (k) =>
      ({
        SUPABASE_URL: "https://xtvueqciogzkyjkkqxcx.supabase.co",
        POC_ENABLED: "true",
        DELIVERY_V2_ENABLED: "true",
        POC_REGISTRATION_SECRET: "offline",
      })[k],
    db: async (path) => {
      if (path === "rpc/delivery_state") return rows;
      if (path === "rpc/delivery_resolve_reviewers") return reviewers;
      throw Error(path);
    },
    fetch: (async (u) => {
      const path = String(u);
      if (path.includes("/actions/runs/")) {
        return Response.json({
          path: ".github/workflows/delivery-prepare.yml",
          head_branch: "main",
          event: "workflow_dispatch",
          status: "in_progress",
          head_sha: source,
          actor: { id: 18661493 },
          triggering_actor: { id: 18661493 },
        });
      }
      if (path.includes("/contents/delivery/delivery-policy.json")) {
        return Response.json({
          encoding: "base64",
          size: 100,
          content: btoa(JSON.stringify(policy)),
        });
      }
      if (path.includes("/git/matching-refs/tags/")) {
        const prefix = path.split("/git/matching-refs/")[1];
        return Response.json(tags.filter((t) => t.ref.startsWith("refs/" + prefix)));
      }
      if (path.includes("/git/ref/heads/")) {
        const name = path.split("/git/ref/heads/")[1];
        const branch = branches.get(name);
        return branch ? Response.json(branch) : new Response("", { status: 404 });
      }
      if (path.includes("/git/ref/tags/")) {
        const name = path.split("/git/ref/tags/")[1];
        const tag = tags.find((t) => t.ref === "refs/tags/" + name);
        return tag ? Response.json(tag) : new Response("", { status: 404 });
      }
      throw Error(path);
    }) as typeof fetch,
    slack: async () => {
      throw Error("no Slack during plan");
    },
    wait: () => {},
    log: () => {},
  };
  const plan = () =>
    deliveryControlHandler(io)(
      new Request("https://test.invalid", {
        method: "POST",
        headers: { Authorization: "Bearer offline" },
        body: JSON.stringify({
          operation: "plan",
          run_id: "123",
          version: "12.0.0",
          publication_scope: "none",
          validation_mode: "controls_only",
        }),
      }),
    );
  return { tags, branches, rows, plan, io };
}
Deno.test("claim/complete keep frozen final tags and reject a counterpart namespace created after plan", async () => {
  for (const legacy of [false, true]) {
    const base = planFixture().io, candidate: any = c(legacy), names = releaseNames(candidate);
    const other = candidateNames(candidate.version, 1, legacy ? "official" : "legacy");
    const report = {
      id,
      version: candidate.version,
      rc_number: 1,
      rc_tag: candidate.rc_tag,
      branch: names.branch,
      source_sha: source,
      validation_mode: "controls_only",
      publication_scope: "github_test",
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
    };
    const text = JSON.stringify(report);
    candidate.manifest_commit = "d".repeat(40);
    candidate.manifest_digest = await digest(text);
    let collision = false, publishedCalls = 0;
    const io: IO = {
      ...base,
      env: (key) =>
        key === "POC_PUBLICATION_SECRET"
          ? "publish"
          : key === "POC_PUBLICATION_ENABLED"
          ? "true"
          : base.env(key),
      db: async (path) => {
        if (path === "rpc/delivery_state") return candidate;
        if (path === "rpc/delivery_publish") {
          publishedCalls++;
          return candidate;
        }
        throw Error(path);
      },
      fetch: (async (u, options) => {
        const url = String(u);
        if (url.includes("/actions/runs/")) {
          return Response.json({
            path: ".github/workflows/delivery-publish.yml",
            head_branch: "main",
            head_sha: source,
            event: "workflow_dispatch",
            status: "in_progress",
            actor: { id: 18661493 },
            triggering_actor: { id: 18661493 },
          });
        }
        if (url.includes("/manifest.json")) {
          return Response.json({ encoding: "base64", size: text.length, content: btoa(text) });
        }
        if (url.endsWith("/git/ref/tags/" + other.final_tag)) {
          return collision
            ? Response.json({ object: { type: "commit", sha: source } })
            : new Response("", { status: 404 });
        }
        if (
          url.endsWith("/git/ref/tags/" + candidate.rc_tag) ||
          url.endsWith("/git/ref/tags/" + names.final_tag)
        ) return Response.json({ object: { type: "commit", sha: source } });
        if (url.endsWith("/releases/tags/" + names.final_tag)) {
          return Response.json({
            id: 77,
            tag_name: names.final_tag,
            draft: false,
            prerelease: false,
            html_url: "https://github.com/" + REPOSITORY + "/releases/tag/" + names.final_tag,
          });
        }
        if (url.includes("/git/ref/") || url.includes("/releases/tags/")) {
          return new Response("", { status: 404 });
        }
        return base.fetch(u, options);
      }) as typeof fetch,
    };
    const request = (operation: string) =>
      new Request("https://test.invalid", {
        method: "POST",
        headers: { Authorization: "Bearer publish" },
        body: JSON.stringify({
          operation,
          run_id: "123",
          candidate: id,
          receipt: { release_id: 77 },
        }),
      });
    for (const operation of ["claim", "complete"]) {
      const response = await deliveryControlHandler(io)(request(operation));
      assert(response.status === 200);
      const data = await response.json();
      assert(data.receipt.tag === names.final_tag);
    }
    assert(publishedCalls === 2);
    collision = true;
    for (const operation of ["claim", "complete"]) {
      assert((await deliveryControlHandler(io)(request(operation))).status === 409);
    }
    assert(publishedCalls === 2, "namespace collision cannot reach publication RPC");
  }
});
Deno.test("plan uses official names for a fresh version and preserves each existing RC family", async () => {
  const fresh = planFixture();
  const response = await fresh.plan();
  assert(response.status === 200);
  const plan = await response.json();
  assert(plan.rc_tag === "v12.0.0-rc.1" && plan.branch === "release/12.0.0");
  for (const legacy of [false, true]) {
    const f = planFixture(), previous = { ...c(legacy), status: "rejected" };
    f.rows.push(previous);
    f.branches.set(previous.branch, { object: { type: "commit", sha: "d".repeat(40) } });
    f.tags.push({ ref: "refs/tags/" + previous.rc_tag, object: { type: "commit", sha: source } });
    const result = await f.plan();
    assert(result.status === 200);
    const next = await result.json();
    assert(next.rc_tag === candidateNames("12.0.0", 2, legacy ? "legacy" : "official").rc_tag);
    assert(next.source_sha === "d".repeat(40) && next.previous_candidate === id);
  }
});
Deno.test("plan blocks downgrade, collisions and orphan candidates across both namespaces", async () => {
  for (
    const tag of [
      "v12.0.0",
      "poc-v12.0.0",
      "v13.0.0",
      "poc-v13.0.0",
      "v12.0.0-rc.1",
      "poc-v12.0.0-rc.1",
    ]
  ) {
    const f = planFixture();
    f.tags.push({ ref: "refs/tags/" + tag });
    assert((await f.plan()).status === 409, tag);
  }
  for (const branch of ["release/12.0.0", "poc-release/12.0.0"]) {
    const f = planFixture();
    f.branches.set(branch, { object: { type: "commit", sha: source } });
    assert((await f.plan()).status === 409, branch);
  }
  const missing = planFixture();
  missing.rows.push({ ...c(), status: "rejected" });
  assert((await missing.plan()).status === 409, "RC2 cannot silently fall back to main");
  const mixed = planFixture();
  mixed.rows.push({ ...c(), status: "rejected" });
  mixed.branches.set("release/12.0.0", { object: { type: "commit", sha: source } });
  mixed.tags.push({ ref: "refs/tags/poc-v12.0.0-rc.1" });
  assert((await mixed.plan()).status === 409);
});
Deno.test("SQL allows new official tags, preserves all old bytes and cannot change family for RC2", async () => {
  const db = new PGlite();
  try {
    await db.exec("create role anon;create role authenticated;create role service_role bypassrls;");
    for (
      const file of [
        "20261015003023_delivery_two_table_control.sql",
        "20261015014626_recover_delivery_before_effect.sql",
        "20261015132214_delivery_reviewer_defaults.sql",
        "20261015180152_delivery_channel_milestones.sql",
      ]
    ) await db.exec(await Deno.readTextFile("supabase/migrations/" + file));
    const value = async (sql: string, p: unknown[] = []) =>
      (await db.query<{ v: any }>(sql, p)).rows[0]?.v;
    const blocked = async (sql: string, p: unknown[]) => {
      let denied = false;
      try {
        await db.query(sql, p);
      } catch {
        denied = true;
      }
      assert(denied);
    };
    const reviewers = await value("select delivery_resolve_reviewers($1,$2,true) v", [
      REPOSITORY,
      TEAM,
    ]);
    const make = (legacy: boolean, version = "12.0.0", rc = 1, previous: string | null = null) => ({
      id: "delivery-" + crypto.randomUUID().replaceAll("-", ""),
      repository: REPOSITORY,
      version,
      rc_number: rc,
      ...candidateNames(version, rc, legacy ? "legacy" : "official"),
      source_sha: source,
      manifest_commit: "d".repeat(40),
      manifest_digest: "e".repeat(64),
      team_id: TEAM,
      channel_id: CHANNEL,
      solo: true,
      scope: "none",
      previous_id: previous,
      reviewers,
    });
    const old = await value("select delivery_register($1) v", [make(true)]);
    await value("select delivery_cancel($1) v", [old.id]);
    const snapshot = () =>
      value(
        "select jsonb_build_object('controls',(select jsonb_agg(to_jsonb(c) order by id) from delivery_control c),'outbox',(select jsonb_agg(to_jsonb(o) order by id) from delivery_outbox o))::text v",
      );
    const before = await snapshot();
    await db.exec(
      await Deno.readTextFile("supabase/migrations/20261015183439_official_delivery_tag_names.sql"),
    );
    assert(await snapshot() === before);
    await blocked("select delivery_register($1)", [make(false, "12.0.0", 2, old.id)]);
    const old2 = await value("select delivery_register($1) v", [make(true, "12.0.0", 2, old.id)]);
    assert(old2.rc_tag === "poc-v12.0.0-rc.2");
    await value("select delivery_cancel($1) v", [old2.id]);
    const official = await value("select delivery_register($1) v", [make(false, "13.0.0")]);
    assert(official.rc_tag === "v13.0.0-rc.1");
    await value("select delivery_cancel($1) v", [official.id]);
    await blocked("select delivery_register($1)", [make(true, "13.0.0", 2, official.id)]);
    const next = await value("select delivery_register($1) v", [
      make(false, "13.0.0", 2, official.id),
    ]);
    assert(next.rc_tag === "v13.0.0-rc.2");
    assert(await value("select count(*)::int v from pg_tables where schemaname='public'") === 3);
    await blocked("update delivery_control set rc_tag='v12.0.0-rc.1' where id=$1", [old.id]);
  } finally {
    await db.close();
  }
});
