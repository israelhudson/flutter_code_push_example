import { PGlite } from "@electric-sql/pglite";

function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}

async function database() {
  const db = new PGlite();
  await db.exec("create role anon; create role authenticated; create role service_role bypassrls;");
  for (
    const migration of [
      "20261015003023_delivery_two_table_control.sql",
      "20261015014626_recover_delivery_before_effect.sql",
    ]
  ) {
    await db.exec(await Deno.readTextFile(`supabase/migrations/${migration}`));
  }
  const value = async (q: string, p: unknown[] = []) =>
    (await db.query<{ v: any }>(q, p)).rows[0]?.v;
  const blocked = async (q: string, p: unknown[] = []) => {
    let denied = false;
    try {
      await db.query(q, p);
    } catch {
      denied = true;
    }
    assert(denied, "operation must stay blocked");
  };
  const c = {
    id: "delivery-" + "e".repeat(32),
    repository: "israelhudson/flutter_code_push_example",
    version: "4.0.0",
    rc_number: 1,
    rc_tag: "poc-v4.0.0-rc.1",
    source_sha: "a".repeat(40),
    manifest_commit: "b".repeat(40),
    manifest_digest: "c".repeat(64),
    team_id: "T09CYB7AS77",
    channel_id: "C0C8DUJB52L",
    technical_user: "USOLO",
    business_user: "USOLO",
    solo: true,
    scope: "none",
  };
  await value("select delivery_register($1) v", [c]);
  return { db, value, blocked, c };
}

Deno.test("delivery recovery: expired reservations retry before any effect and reject stale owners", async () => {
  const { db, value, blocked, c } = await database();
  try {
    // Initial notifications are irrelevant to the injected interruption windows.
    await db.exec("update delivery_outbox set state='done',receipt='fixture',completed_at=now()");
    for (
      const [revision, kind] of ["history", "channel", "technical", "business", "dispatch"]
        .entries()
    ) {
      const oldLease = crypto.randomUUID(), lease = crypto.randomUUID();
      const id = await value(
        `insert into delivery_outbox(candidate_id,kind,revision,state,attempts,lease,leased_at)
         values($1,$2,$3,'working',1,$4,now()-interval '6 minutes') returning id v`,
        [c.id, kind, revision + 1, oldLease],
      );
      const work = await value("select delivery_take($1) v", [lease]);
      assert(work.task.id === Number(id) && work.task.kind === kind);
      assert(work.task.attempts === 2 && work.task.lease === lease);
      await blocked("select delivery_finish($1,$2,'stale')", [id, oldLease]);
      if (kind !== "history") {
        await value("select delivery_begin($1,$2) v", [id, lease]);
        await blocked("select delivery_begin($1,$2)", [id, lease]);
      }
      const channel = kind === "channel" ? c.channel_id : "DPRIVATE";
      await value("select delivery_finish($1,$2,$3,$4,$5) v", [
        id,
        lease,
        "confirmed-once",
        channel,
        "100.1",
      ]);
      assert(await value("select delivery_take($1) v", [crypto.randomUUID()]) === null);
    }
    assert(await value("select count(*)::int v from pg_tables where schemaname='public'") === 2);
  } finally {
    await db.close();
  }
});

Deno.test("delivery recovery: ambiguous effects stay uncertain and block later updates", async () => {
  const { db, value, c } = await database();
  try {
    await db.exec("update delivery_outbox set state='done',receipt='fixture',completed_at=now()");
    for (const kind of ["channel", "technical", "business", "dispatch"]) {
      await db.query(
        `insert into delivery_outbox(candidate_id,kind,revision,state,lease,leased_at)
         values($1,$2,1,'effect',$3,now()-interval '6 minutes')`,
        [c.id, kind, crypto.randomUUID()],
      );
    }
    assert(await value("select delivery_take($1) v", [crypto.randomUUID()]) === null);
    assert(
      await value("select count(*)::int v from delivery_outbox where state='uncertain'") === 4,
    );
    assert(
      await value(
        "select count(*)::int v from delivery_outbox where state='uncertain' and lease is not null",
      ) === 0,
    );
    await db.query(
      "insert into delivery_outbox(candidate_id,kind,revision) values($1,'technical',2)",
      [c.id],
    );
    assert(await value("select delivery_take($1) v", [crypto.randomUUID()]) === null);
    const lease = crypto.randomUUID();
    await db.query(
      "insert into delivery_outbox(candidate_id,kind,revision,state,lease,leased_at) values($1,'channel',2,'working',$2,now())",
      [c.id, lease],
    );
    assert(await value("select delivery_take($1) v", [crypto.randomUUID()]) === null);
    assert(
      await value("select lease v from delivery_outbox where kind='channel' and revision=2") ===
        lease,
      "a fresh reservation remains owned",
    );
  } finally {
    await db.close();
  }
});

Deno.test("delivery rejection: only the same validated account, role and DM can repeat a rejection", async () => {
  const { db, value, blocked, c } = await database();
  try {
    await db.query(
      "update delivery_control set technical_channel='DTECH',technical_message='100.1',business_channel='DBIZ',business_message='100.2' where id=$1",
      [c.id],
    );
    const decision =
      "select delivery_decide($1,'technical','reject','USOLO','T09CYB7AS77','DTECH','100.1') v";
    const rejected = await value(decision, [c.id]);
    const count = await value("select count(*)::int v from delivery_outbox");
    assert(rejected.status === "rejected" && rejected.revision === 1);
    assert(JSON.stringify(await value(decision, [c.id])) === JSON.stringify(rejected));
    assert(await value("select count(*)::int v from delivery_outbox") === count);
    for (
      const sql of [
        "select delivery_decide($1,'business','reject','USOLO','T09CYB7AS77','DBIZ','100.2')",
        "select delivery_decide($1,'technical','reject','USOLO','T09CYB7AS77','DBIZ','100.2')",
        "select delivery_decide($1,'technical','reject','UOTHER','T09CYB7AS77','DTECH','100.1')",
        "select delivery_decide($1,'business','accept','USOLO','T09CYB7AS77','DBIZ','100.2')",
      ]
    ) await blocked(sql, [c.id]);
    assert(await value("select count(*)::int v from delivery_outbox") === count);
    for (const role of ["anon", "authenticated"]) {
      assert(
        !await value("select has_function_privilege($1,'public.delivery_take(text)','EXECUTE') v", [
          role,
        ]),
      );
      assert(
        !await value(
          "select has_function_privilege($1,'public.delivery_decide(text,text,text,text,text,text,text)','EXECUTE') v",
          [role],
        ),
      );
    }
  } finally {
    await db.close();
  }
});
