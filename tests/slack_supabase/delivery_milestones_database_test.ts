import { PGlite } from "@electric-sql/pglite";

function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
async function database(migrate = true) {
  const db = new PGlite();
  await db.exec("create role anon; create role authenticated; create role service_role bypassrls;");
  const milestoneMigration = "supabase/migrations/20261015180152_delivery_channel_milestones.sql";
  for (
    const migration of [
      "20261015003023_delivery_two_table_control.sql",
      "20261015014626_recover_delivery_before_effect.sql",
      "20261015132214_delivery_reviewer_defaults.sql",
    ]
  ) await db.exec(await Deno.readTextFile(`supabase/migrations/${migration}`));
  const apply = async () => await db.exec(await Deno.readTextFile(milestoneMigration));
  if (migrate) await apply();
  const value = async (q: string, p: unknown[] = []) =>
    (await db.query<{ v: any }>(q, p)).rows[0]?.v;
  const blocked = async (q: string, p: unknown[] = []) => {
    let denied = false;
    try {
      await db.query(q, p);
    } catch {
      denied = true;
    }
    assert(denied, "must block: " + q);
  };
  const register = async (rc = 1, previous: string | null = null) => {
    const reviewers = await value(
      "select delivery_resolve_reviewers('israelhudson/flutter_code_push_example','T09CYB7AS77',true) v",
    );
    const c = await value("select delivery_register($1) v", [{
      id: "delivery-" + crypto.randomUUID().replaceAll("-", ""),
      repository: "israelhudson/flutter_code_push_example",
      version: "9.0.0",
      rc_number: rc,
      rc_tag: `poc-v9.0.0-rc.${rc}`,
      source_sha: "a".repeat(40),
      manifest_commit: "b".repeat(40),
      manifest_digest: "c".repeat(64),
      team_id: "T09CYB7AS77",
      channel_id: "C0C8DUJB52L",
      solo: true,
      scope: "github_test",
      previous_id: previous,
      reviewers,
    }]);
    await db.query(
      "update delivery_control set channel_message='100.0',technical_channel='DTECH',technical_message='100.1',business_channel='DBIZ',business_message='100.2' where id=$1",
      [c.id],
    );
    return c;
  };
  const decide = (id: string, role: string, action = "accept") =>
    value("select delivery_decide($1,$2,$3,'U0BMFQKC001','T09CYB7AS77',$4,$5) v", [
      id,
      role,
      action,
      role === "technical" ? "DTECH" : "DBIZ",
      role === "technical" ? "100.1" : "100.2",
    ]);
  const settle = () =>
    db.exec("update delivery_outbox set state='done',receipt=repeat('f',40),completed_at=now()");
  return { db, value, blocked, apply, register, decide, settle };
}
Deno.test("milestone migration preserves every historical byte and adds no tables or backfill", async () => {
  const f = await database(false);
  try {
    const c = await f.register();
    await f.decide(c.id, "technical", "reject");
    const snapshot = () =>
      f.value(
        "select jsonb_build_object('controls',(select jsonb_agg(to_jsonb(c)-'android_staging_notice_digest' order by id) from delivery_control c),'outbox',(select jsonb_agg(to_jsonb(o) order by id) from delivery_outbox o))::text v",
      );
    const before = await snapshot();
    await f.apply();
    assert(await snapshot() === before, "migration cannot mutate old rows");
    await f.value("select delivery_enqueue($1) v", [c.id]);
    assert(await snapshot() === before, "re-enqueue cannot backfill an old milestone");
    assert(await f.value("select count(*)::int v from pg_tables where schemaname='public'") === 3);
    for (const role of ["anon", "authenticated"]) {
      assert(
        !await f.value(
          "select has_function_privilege($1,'delivery_refresh(text,jsonb)','execute') v",
          [
            role,
          ],
        ),
      );
    }
    assert(
      await f.value(
        "select has_function_privilege('service_role','delivery_refresh(text,jsonb)','execute') v",
      ),
    );
    await f.blocked("select delivery_refresh($1)", [c.id]);
  } finally {
    await f.db.close();
  }
});
Deno.test("Android milestone announces the first verified receipt once, including after compaction", async () => {
  const f = await database();
  try {
    const c = await f.register();
    await f.decide(c.id, "technical");
    await f.decide(c.id, "business");
    await f.settle();
    await f.value("select delivery_publish($1,'123',false) v", [c.id]);
    await f.value("select delivery_publish($1,'123',true) v", [c.id]);
    await f.value("select delivery_refresh($1) v", [c.id]);
    assert(
      await f.value(
        "select count(*)::int v from delivery_outbox where kind='notice' and event->>'status'='android_staging'",
      ) === 0,
    );
    const mobile = {
      schema: "delivery-android-staging-notice-v1",
      patch_number: 7,
      release_version: "1.1.0+2",
      asset_digest: "d".repeat(64),
    };
    for (
      const delta of [{ patch_number: 0 }, { asset_digest: "unknown" }, {
        release_version: "1.1.0",
      }, { schema: "ad-hoc" }]
    ) {
      await f.blocked("select delivery_refresh($1,$2)", [c.id, { ...mobile, ...delta }]);
    }
    const first = await f.value("select delivery_refresh($1,$2) v", [c.id, mobile]);
    assert(
      first.status === "published" && first.android_staging_notice_digest === mobile.asset_digest,
    );
    const event = await f.value(
      "select event v from delivery_outbox where kind='notice' and event->>'status'='android_staging'",
    );
    assert(
      event.patch_number === 7 && event.release_version === "1.1.0+2" &&
        event.asset_digest === mobile.asset_digest,
    );
    assert(
      await f.value(
        "select event->'android_staging'->>'asset_digest' v from delivery_outbox where kind='history' and revision=$1",
        [first.revision],
      ) === mobile.asset_digest,
    );
    await f.value("select delivery_refresh($1,$2) v", [c.id, mobile]);
    assert(
      await f.value(
        "select count(*)::int v from delivery_outbox where kind='notice' and event->>'status'='android_staging'",
      ) === 1,
    );
    await f.blocked("select delivery_refresh($1,$2)", [c.id, {
      ...mobile,
      asset_digest: "e".repeat(64),
    }]);
    await f.blocked("update delivery_control set android_staging_notice_digest=null where id=$1", [
      c.id,
    ]);
    await f.db.exec(
      "update delivery_outbox set state='done',receipt=repeat('f',40),completed_at=now()-interval '8 days'",
    );
    assert(await f.value("select delivery_compact() v") > 0);
    await f.value("select delivery_refresh($1,$2) v", [c.id, mobile]);
    assert(
      await f.value("select count(*)::int v from delivery_outbox where kind='notice'") === 0,
      "tombstone prevents reannouncement after compaction",
    );
    assert(
      await f.value("select android_staging_notice_digest v from delivery_control where id=$1", [
        c.id,
      ]) === mobile.asset_digest,
    );
    assert(await f.value("select count(*)::int v from pg_tables where schemaname='public'") === 3);
  } finally {
    await f.db.close();
  }
});
Deno.test("milestones: reject RC1, fresh RC2, no acceptance spam, single publication and safe refresh", async () => {
  const f = await database();
  try {
    const c = await f.register();
    await f.decide(c.id, "technical", "reject");
    const rejected = await f.value("select event::text v from delivery_outbox where kind='notice'");
    await f.decide(c.id, "technical", "reject");
    await f.value("select delivery_enqueue($1) v", [c.id]);
    assert(await f.value("select count(*)::int v from delivery_outbox where kind='notice'") === 1);
    const rc2 = await f.register(2, c.id);
    assert(rc2.technical_at === null && rc2.business_at === null);
    await f.decide(rc2.id, "technical");
    await f.decide(rc2.id, "business");
    assert(
      await f.value(
        "select count(*)::int v from delivery_outbox where candidate_id=$1 and kind='notice'",
        [rc2.id],
      ) === 0,
    );
    await f.settle();
    await f.value("select delivery_publish($1,'123',false) v", [rc2.id]);
    const frozen = await f.value(
      "select event::text v from delivery_outbox where candidate_id=$1 and kind='notice'",
      [rc2.id],
    );
    const published = await f.value("select delivery_publish($1,'123',true) v", [rc2.id]);
    await f.value("select delivery_publish($1,'123',true) v", [rc2.id]);
    assert(
      await f.value(
        "select count(*)::int v from delivery_outbox where candidate_id=$1 and kind='notice'",
        [rc2.id],
      ) === 2,
    );
    assert(
      await f.value(
        "select event::text v from delivery_outbox where kind='notice' and event->>'status'='publishing'",
        [],
      ) === frozen,
    );
    assert(
      await f.value(
        "select event::text v from delivery_outbox where candidate_id=$1 and kind='notice'",
        [c.id],
      ) === rejected,
    );
    const refreshed = await f.value("select delivery_refresh($1) v", [rc2.id]);
    assert(refreshed.revision === published.revision + 1);
    const omitRevision = ({ revision: _revision, ...rest }: any) => rest;
    assert(JSON.stringify(omitRevision(refreshed)) === JSON.stringify(omitRevision(published)));
    assert(
      await f.value(
        "select count(*)::int v from delivery_outbox where candidate_id=$1 and kind='notice'",
        [rc2.id],
      ) === 2,
    );
    await f.db.exec(
      "update delivery_outbox set state='done',receipt=repeat('f',40),completed_at=now()-interval '8 days'",
    );
    assert(await f.value("select delivery_compact() v") > 0);
    await f.value("select delivery_refresh($1) v", [rc2.id]);
    assert(
      await f.value("select count(*)::int v from delivery_outbox where kind='notice'") === 0,
      "refresh after compaction must not reannounce publication",
    );
    assert(
      await f.value("select channel_message v from delivery_control where id=$1", [rc2.id]) ===
        "100.0",
    );
  } finally {
    await f.db.close();
  }
});
Deno.test("notice effects wait for history/card, recover reservations and quarantine ambiguous sends", async () => {
  const f = await database();
  try {
    const c = await f.register();
    await f.settle();
    await f.value("select delivery_cancel($1) v", [c.id]);
    // The pending history is not evidence yet. Complete other ordinary DM work.
    await f.db.exec(
      "update delivery_outbox set state='done',receipt='fixture',completed_at=now() where kind in ('technical','business')",
    );
    const historyLease = crypto.randomUUID();
    const history = await f.value("select delivery_take($1) v", [historyLease]);
    assert(history.task.kind === "history");
    const cardLease = crypto.randomUUID();
    const card = await f.value("select delivery_take($1) v", [cardLease]);
    assert(card.task.kind === "channel");
    assert(
      await f.value("select delivery_take($1) v", [crypto.randomUUID()]) === null,
      "history and card gate notice",
    );
    await f.value("select delivery_finish($1,$2,$3) v", [
      history.task.id,
      historyLease,
      "f".repeat(40),
    ]);
    assert(
      await f.value("select delivery_take($1) v", [crypto.randomUUID()]) === null,
      "unfinished card gate notice",
    );
    await f.value("select delivery_finish($1,$2,'card',$3,'100.0') v", [
      card.task.id,
      cardLease,
      c.channel_id,
    ]);
    const oldLease = crypto.randomUUID();
    const notice = await f.value("select delivery_take($1) v", [oldLease]);
    assert(notice.task.kind === "notice");
    await f.blocked("select delivery_finish($1,$2,$3,$4,'200.0')", [
      notice.task.id,
      oldLease,
      `slack:${c.channel_id}:200.0`,
      c.channel_id,
    ]);
    await f.db.query(
      "update delivery_outbox set leased_at=now()-interval '6 minutes' where id=$1",
      [notice.task.id],
    );
    const lease = crypto.randomUUID();
    const recovered = await f.value("select delivery_take($1) v", [lease]);
    assert(recovered.task.id === notice.task.id && recovered.task.attempts === 2);
    await f.blocked("select delivery_begin($1,$2)", [notice.task.id, oldLease]);
    await f.value("select delivery_begin($1,$2) v", [notice.task.id, lease]);
    await f.blocked("select delivery_begin($1,$2)", [notice.task.id, lease]);
    await f.blocked("select delivery_finish($1,$2,'wrong','COTHER','200.0')", [
      notice.task.id,
      lease,
    ]);
    await f.blocked("select delivery_finish($1,$2,'wrong',$3,'200.0')", [
      notice.task.id,
      lease,
      c.channel_id,
    ]);
    await f.blocked("select delivery_finish($1,$2,$3,$4,'100.0')", [
      notice.task.id,
      lease,
      `slack:${c.channel_id}:100.0`,
      c.channel_id,
    ]);
    await f.db.query(
      "update delivery_outbox set leased_at=now()-interval '6 minutes' where id=$1",
      [notice.task.id],
    );
    assert(await f.value("select delivery_take($1) v", [crypto.randomUUID()]) === null);
    assert(
      await f.value("select state v from delivery_outbox where id=$1", [notice.task.id]) ===
        "uncertain",
    );
    assert(
      await f.value("select delivery_compact() v") === 0,
      "unconfirmed notice must survive compaction",
    );
    // A confirmed receipt can reconcile the original effect, without any resend.
    // Production reconciliation requires external evidence; this is a local fixture.
    await f.db.query(
      "update delivery_outbox set state='effect',lease=$2,leased_at=now() where id=$1",
      [notice.task.id, lease],
    );
    await f.value("select delivery_finish($1,$2,$3,$4,'200.0') v", [
      notice.task.id,
      lease,
      `slack:${c.channel_id}:200.0`,
      c.channel_id,
    ]);
    await f.value("select delivery_finish($1,$2,$3,$4,'200.0') v", [
      notice.task.id,
      lease,
      `slack:${c.channel_id}:200.0`,
      c.channel_id,
    ]);
    assert(
      await f.value("select channel_message v from delivery_control where id=$1", [c.id]) ===
        "100.0",
    );
    assert(await f.value("select delivery_take($1) v", [crypto.randomUUID()]) === null);
  } finally {
    await f.db.close();
  }
});
