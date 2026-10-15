import { PGlite } from "@electric-sql/pglite";
function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
Deno.test("delivery: two tables, DM roles, durable evidence, rejection/RC2 and single publication", async () => {
  const db = new PGlite();
  try {
    await db.exec(
      "create role anon; create role authenticated; create role service_role bypassrls;",
    );
    await db.exec(
      await Deno.readTextFile("supabase/migrations/20261015003023_delivery_two_table_control.sql"),
    );
    const scalar = async (q: string, p: unknown[] = []) =>
      (await db.query<{ v: any }>(q, p)).rows[0]?.v;
    const blocked = async (q: string, p: unknown[] = []) => {
      let error = false;
      try {
        await db.query(q, p);
      } catch {
        error = true;
      }
      assert(error, "must block");
    };
    const candidate = (rc = 1, previous: string | null = null) => ({
      id: "delivery-" + crypto.randomUUID().replaceAll("-", ""),
      repository: "israelhudson/flutter_code_push_example",
      version: "2.0.0",
      rc_number: rc,
      rc_tag: `poc-v2.0.0-rc.${rc}`,
      source_sha: "a".repeat(40),
      manifest_commit: "b".repeat(40),
      manifest_digest: "c".repeat(64),
      team_id: "T09CYB7AS77",
      channel_id: "C0C8DUJB52L",
      technical_user: "UTECH",
      business_user: "UBIZ",
      solo: false,
      scope: "github_test",
      previous_id: previous,
    });
    const register = (c: any) => scalar("select delivery_register($1) v", [c]);
    const bind = (id: string) =>
      db.query(
        "update delivery_control set technical_channel='DTECH',technical_message='100.1',business_channel='DBIZ',business_message='100.2' where id=$1",
        [id],
      );
    const decide = (id: string, role: string, action = "accept") =>
      scalar("select delivery_decide($1,$2,$3,$4,'T09CYB7AS77',$5,$6) v", [
        id,
        role,
        action,
        role === "technical" ? "UTECH" : "UBIZ",
        role === "technical" ? "DTECH" : "DBIZ",
        role === "technical" ? "100.1" : "100.2",
      ]);
    const c = await register(candidate());
    await bind(c.id);
    assert(!("report_text" in c) && !("expires_at" in c));
    await blocked(
      "select delivery_decide($1,'technical','accept','UBIZ','T09CYB7AS77','DTECH','100.1')",
      [c.id],
    );
    await blocked(
      "select delivery_decide($1,'technical','accept','UTECH','T09CYB7AS77','DBIZ','100.2')",
      [c.id],
    );
    assert((await decide(c.id, "technical")).status === "pending");
    assert((await decide(c.id, "technical")).revision === 1, "duplicate must not write event");
    assert((await decide(c.id, "business", "reject")).status === "rejected");
    await blocked("select delivery_publish($1,'100',false)", [c.id]);
    const c2 = await register(candidate(2, c.id));
    await bind(c2.id);
    assert(c2.technical_at === null && c2.business_at === null);
    await blocked(
      "select delivery_decide($1,'business','accept','UBIZ','T09CYB7AS77','DBIZ','100.2')",
      [c.id],
    );
    await decide(c2.id, "business");
    assert((await decide(c2.id, "technical")).status === "approved");
    await blocked(
      "select delivery_decide($1,'business','reject','UBIZ','T09CYB7AS77','DBIZ','100.2')",
      [c2.id],
    );
    await blocked("select delivery_publish($1,'100',false)", [c2.id]);
    // Worker confirms immutable GitHub events before a publication can be claimed.
    await db.query(
      "update delivery_outbox set state='done',receipt='git-commit' where kind='history'",
    );
    assert((await scalar("select delivery_publish($1,'100') v", [c2.id])).status === "publishing");
    await blocked("select delivery_publish($1,'101')", [c2.id]);
    await db.query(
      "update delivery_outbox set state='done',receipt='git-commit' where kind='history'",
    );
    assert(
      (await scalar("select delivery_publish($1,'100',true) v", [c2.id])).status === "published",
    );
    await db.query(
      "update delivery_outbox set state='done',receipt='git-commit' where kind='history'",
    );
    assert(
      (await scalar("select delivery_publish($1,'100',true) v", [c2.id])).status === "published",
    );
    await blocked("select delivery_register($1)", [{
      ...candidate(),
      version: "1.0.0",
      rc_tag: "poc-v1.0.0-rc.1",
    }]);
    // Expired Slack/dispatch leases must never automatically send a second time.
    await db.query(
      "update delivery_outbox set state='working',lease='old',leased_at=now()-interval '6 minutes' where kind='technical'",
    );
    await scalar("select delivery_take($1) v", [crypto.randomUUID()]);
    assert(
      Number(
        await scalar(
          "select count(*) v from delivery_outbox where kind='technical' and state='uncertain'",
        ),
      ) > 0,
    );
    await db.exec("set role anon");
    await blocked("select * from delivery_control");
    await blocked("select delivery_register('{}')");
  } finally {
    await db.close();
  }
});

Deno.test("delivery outbox: receipts, uncertain effects, cancellation and safe compaction", async () => {
  const db = new PGlite();
  try {
    await db.exec(
      "create role anon; create role authenticated; create role service_role bypassrls;",
    );
    await db.exec(
      await Deno.readTextFile("supabase/migrations/20261015003023_delivery_two_table_control.sql"),
    );
    const value = async (q: string, p: unknown[] = []) =>
      (await db.query<{ v: any }>(q, p)).rows[0]?.v;
    const c = {
      id: "delivery-" + "d".repeat(32),
      repository: "israelhudson/flutter_code_push_example",
      version: "3.0.0",
      rc_number: 1,
      rc_tag: "poc-v3.0.0-rc.1",
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
    const lease = crypto.randomUUID();
    const first = await value("select delivery_take($1) v", [lease]);
    assert(first.task.kind === "history");
    await value("select delivery_finish($1,$2,$3) v", [first.task.id, lease, "f".repeat(40)]);
    const l2 = crypto.randomUUID(), second = await value("select delivery_take($1) v", [l2]);
    assert(second.task.kind === "channel");
    await value("select delivery_begin($1,$2) v", [second.task.id, l2]);
    let denied = false;
    try {
      await value("select delivery_begin($1,$2) v", [second.task.id, l2]);
    } catch {
      denied = true;
    }
    assert(denied, "effect can start only once");
    await value("select delivery_finish($1,$2,$3,$4,$5) v", [
      second.task.id,
      l2,
      "slack-confirmed",
      "C0C8DUJB52L",
      "100.1",
    ]);
    assert((await value("select delivery_cancel($1) v", [c.id])).status === "cancelled");
    assert(await value("select delivery_compact() v") === 0, "pending work must survive");
    await db.exec(
      "update delivery_outbox set state='done',receipt=repeat('e',40),created_at=now()-interval '8 days'",
    );
    assert(await value("select delivery_compact() v") > 0);
    assert(await value("select count(*)::int v from delivery_outbox") === 0);
    assert(
      (await value("select delivery_state($1) v", [c.id])).status === "cancelled",
      "tombstone must survive",
    );
    denied = false;
    try {
      await db.query("update delivery_control set source_sha=repeat('f',40) where id=$1", [c.id]);
    } catch {
      denied = true;
    }
    assert(denied, "SHA stays frozen");
  } finally {
    await db.close();
  }
});
