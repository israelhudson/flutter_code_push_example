import { PGlite } from "@electric-sql/pglite";
import { digest } from "../../supabase/functions/_shared/poc.ts";

function assert(value: unknown, message = "assertion failed") {
  if (!value) throw Error(message);
}
Deno.test("Postgres local: roles, duas ordens, repetição, ajuste/RC2, expiração, publicação e proteção", async () => {
  const db = new PGlite();
  try {
    await db.exec(
      "create role anon; create role authenticated; create role service_role bypassrls;",
    );
    await db.exec(await Deno.readTextFile("supabase/migrations/20261013200000_poc_slack.sql"));
    await db.exec(
      await Deno.readTextFile("supabase/migrations/20261013203000_poc_slack_indexes.sql"),
    );
    await db.exec("update public.poc_config set enabled=true,publication_enabled=true;");
    const sha = "a".repeat(40), ts = "1000.1001", user = "U0BMFQKC001";
    const scalar = async (sql: string, args: unknown[] = []) =>
      (await db.query<{ value: any }>(sql, args)).rows[0].value;
    const reject = async (sql: string, args: unknown[] = []) => {
      let failed = false;
      try {
        await db.query(sql, args);
      } catch {
        failed = true;
      }
      assert(failed, "operation should be rejected");
    };
    const register = async (
      version: string,
      rc: number,
      previous: string | null = null,
      scope = "none",
    ) => {
      const report = JSON.stringify({
        id: "poc-" + crypto.randomUUID().replaceAll("-", ""),
        repository: "israelhudson/flutter_code_push_example",
        version,
        rc_number: rc,
        rc_tag: `poc-v${version}-rc.${rc}`,
        source_sha: sha,
        preview_sha: sha,
        preview_url: `https://israelhudson.github.io/flutter_code_push_example/snapshots/${sha}/`,
        web_content_sha256: "b".repeat(64),
        snapshot_manifest_sha256: "c".repeat(64),
        run_url: "https://github.com/israelhudson/flutter_code_push_example/actions/runs/123",
        previous_candidate: previous,
        publication_scope: scope,
      });
      const c = await scalar("select public.poc_register($1,$2,'israelhudson',$3) value", [
        report,
        await digest(report),
        scope,
      ]);
      await db.query("update public.poc_candidates set message_ts=$1 where id=$2", [ts, c.id]);
      return c;
    };
    const action = (
      id: string,
      role: string,
      actor = user,
      channel = "C0C8DUJB52L",
      message = ts,
      reason: string | null = null,
      token: string | null = null,
    ) =>
      scalar("select public.poc_action($1,$2,$3,'T09CYB7AS77',$4,$5,$6,$7) value", [
        id,
        role,
        actor,
        channel,
        message,
        reason,
        token,
      ]);
    const notice = (id: string, event: string) =>
      scalar("select public.poc_notice($1,$2) value", [id, event]);
    const c1 = await register("0.1.0", 1);
    assert(Date.parse(c1.expires_at) - Date.parse(c1.created_at) === 36 * 3600000);
    let blocked = false;
    try {
      await register("0.2.0", 1);
    } catch {
      blocked = true;
    }
    assert(blocked, "one active flow");
    await reject(
      "select public.poc_action($1,'technical','UOTHER','T09CYB7AS77','C0C8DUJB52L',$2)",
      [c1.id, ts],
    );
    await reject("select public.poc_action($1,'technical',$2,'T09CYB7AS77','C0C5DCFU5HU',$3)", [
      c1.id,
      user,
      ts,
    ]);
    await reject(
      "select public.poc_action($1,'technical',$2,'T09CYB7AS77','C0C8DUJB52L','999.0')",
      [c1.id, user],
    );
    const a1 = await action(c1.id, "technical");
    assert(a1.approvals.length === 1 && a1.status === "pending");
    assert((await action(c1.id, "technical")).changed === false);
    assert((await notice(c1.id, "review_pending:business")).recipient === user);
    assert(
      (await notice(c1.id, "review_pending:business")).send === false,
      "reserved prevents resend",
    );
    await db.query("select public.poc_finish_notice($1,'review_pending:business',$2,'uncertain')", [
      c1.id,
      user,
    ]);
    assert(
      (await notice(c1.id, "review_pending:business")).send === false,
      "uncertain prevents resend",
    );
    assert((await action(c1.id, "business")).status === "approved");
    assert((await notice(c1.id, "approved")).recipient === user);
    await reject("select public.poc_publish($1,'claim','123')", [c1.id]); // is_lab does not authorize scope=none.
    const token = "d".repeat(64);
    await action(c1.id, "open_adjustment", user, "C0C8DUJB52L", ts, null, token);
    await reject("select public.poc_action($1,'adjust',$2,'T09CYB7AS77','C0C8DUJB52L',$3,'x',$4)", [
      c1.id,
      user,
      ts,
      token,
    ]);
    const adjusted = await action(
      c1.id,
      "adjust",
      user,
      "C0C8DUJB52L",
      ts,
      "Corrigir o resumo antes da publicação",
      token,
    );
    assert(
      adjusted.status === "adjustment_requested" && adjusted.adjustment_author === user &&
        adjusted.adjustment_at,
    );
    await reject("select public.poc_action($1,'technical',$2,'T09CYB7AS77','C0C8DUJB52L',$3)", [
      c1.id,
      user,
      ts,
    ]);
    const c2 = await register("0.1.0", 2, c1.id, "github_test");
    const fresh = await scalar("select public.poc_state($1) value", [c2.id]);
    assert(fresh.approvals.length === 0);
    assert((await action(c2.id, "business")).approvals.length === 1);
    assert((await notice(c2.id, "review_pending:technical")).recipient === user);
    assert((await notice(c2.id, "dispatch")).send === false, "1/2 cannot dispatch");
    await action(c2.id, "technical");
    assert((await notice(c2.id, "dispatch")).send === true);
    await db.query(
      "select public.poc_finish_notice($1,'dispatch','israelhudson','sent',null,null,'{\"acknowledged\":true}')",
      [c2.id],
    );
    assert((await notice(c2.id, "dispatch")).send === false);
    const t2 = "e".repeat(64);
    await action(c2.id, "open_adjustment", user, "C0C8DUJB52L", ts, null, t2);
    await reject("select public.poc_publish($1,'claim','124')", [c2.id]);
    await action(c2.id, "cancel_adjustment", user, "C0C8DUJB52L", ts, null, t2);
    const claim = await scalar("select public.poc_publish($1,'claim','124') value", [c2.id]);
    assert(claim.publication.state === "publishing");
    await reject("select public.poc_publish($1,'claim','125')", [c2.id]);
    const receipt = {
      tag: "poc-v0.1.0",
      source_sha: sha,
      report_digest: c2.report_digest,
      release_id: 1234,
      release_url:
        "https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v0.1.0",
      distribution_performed: false,
    };
    await scalar("select public.poc_publish($1,'complete','124',$2) value", [
      c2.id,
      JSON.stringify(receipt),
    ]);
    const repeated = await scalar("select public.poc_publish($1,'claim','125') value", [c2.id]);
    assert(repeated.already_published && repeated.receipt.release_id === 1234);
    const c3 = await register("0.2.0", 1);
    await reject("update public.poc_candidates set source_sha=$1 where id=$2", [
      "f".repeat(40),
      c3.id,
    ]);
    await db.exec("set role anon;");
    await reject("select * from public.poc_candidates");
    await reject("select public.poc_state($1)", [c3.id]);
    await db.exec("reset role;");
    const rls = (await db.query<{ relrowsecurity: boolean }>(
      "select relrowsecurity from pg_class where relname like 'poc_%' and relkind='r'",
    )).rows;
    assert(rls.length === 8 && rls.every((x) => x.relrowsecurity));
    await db.exec("set role service_role;");
    assert((await scalar("select public.poc_state($1) value", [c3.id])).id === c3.id);
    await reject("update public.poc_events set actor='forged'");
    await reject("update public.poc_approvals set slack_user_id='forged'");
    await db.exec("reset role;");
    await db.exec("set role authenticated;");
    await reject("select * from public.poc_candidates");
    await db.exec("reset role;");
    // Separate real-reviewer fixture, never written to a remote database.
    await db.query("update public.poc_candidates set status='cancelled' where id=$1", [c3.id]);
    await db.exec(
      "insert into public.poc_user_directory values('fixture-business',42,'UFIXTUREBUSINESS','Pessoa fictícia',now()); update public.poc_config set mode='two_reviewers',business_reviewer='UFIXTUREBUSINESS';",
    );
    const c4 = await register("0.3.0", 1);
    await reject("select public.poc_action($1,'business',$2,'T09CYB7AS77','C0C8DUJB52L',$3)", [
      c4.id,
      user,
      ts,
    ]);
    await action(c4.id, "business", "UFIXTUREBUSINESS");
    assert((await notice(c4.id, "review_pending:technical")).recipient === user);
    await action(c4.id, "technical");
    assert((await notice(c4.id, "approved")).recipient === user);
    await db.query("update public.poc_candidates set status='cancelled' where id=$1", [c4.id]);
    const expired = "poc-" + "f".repeat(32);
    await db.query(
      `insert into public.poc_candidates select (jsonb_populate_record(null::public.poc_candidates,to_jsonb(c)||jsonb_build_object('id',$1::text,'version','0.4.0','rc_tag','poc-v0.4.0-rc.1','status','pending','created_at','2000-01-01T00:00:00Z','expires_at','2000-01-02T12:00:00Z'))).* from public.poc_candidates c where c.id=$2`,
      [expired, c4.id],
    );
    await reject("select public.poc_action($1,'technical',$2,'T09CYB7AS77','C0C8DUJB52L',$3)", [
      expired,
      user,
      ts,
    ]);
    await reject("select public.poc_publish($1,'claim','999')", [expired]);
    assert((await notice(expired, "review_pending:business")).send === false);
    const definers = (await db.query<{ n: number }>(
      "select count(*)::int n from pg_proc where left(proname,4)='poc_' and prosecdef",
    )).rows[0].n;
    assert(definers === 0);
  } finally {
    await db.close();
  }
});
