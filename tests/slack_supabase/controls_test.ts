import { PGlite } from "@electric-sql/pglite";
import { digest } from "../../supabase/functions/_shared/poc.ts";

function assert(value: unknown, message = "assertion failed") {
  if (!value) throw Error(message);
}
Deno.test("Postgres: negar sem motivo, RC2 limpa, controles explícitos e publicação idempotente", async () => {
  const db = new PGlite();
  try {
    await db.exec(
      "create role anon; create role authenticated; create role service_role bypassrls;",
    );
    for (
      const name of [
        "20261013200000_poc_slack.sql",
        "20261013203000_poc_slack_indexes.sql",
        "20261014211744_poc_controls_only_rejection.sql",
      ]
    ) {
      await db.exec(await Deno.readTextFile("supabase/migrations/" + name));
    }
    await db.exec("update public.poc_config set enabled=true,publication_enabled=true;");
    const scalar = async (sql: string, args: unknown[] = []) =>
      (await db.query<{ value: any }>(sql, args)).rows[0].value;
    const blocked = async (task: () => Promise<unknown>) => {
      let failed = false;
      try {
        await task();
      } catch {
        failed = true;
      }
      assert(failed, "operation must be blocked");
    };
    const report: any = {
      id: "poc-" + "1".repeat(32),
      repository: "israelhudson/flutter_code_push_example",
      version: "0.1.0",
      rc_number: 1,
      rc_tag: "poc-v0.1.0-rc.1",
      source_sha: "a".repeat(40),
      validation_mode: "controls_only",
      publication_scope: "github_test",
      previous_candidate: null,
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
      run_url: "https://github.com/israelhudson/flutter_code_push_example/actions/runs/123",
    };
    const register = async (r: any) => {
      const text = JSON.stringify(r);
      return await scalar("select public.poc_register($1,$2,'israelhudson','github_test') value", [
        text,
        await digest(text),
      ]);
    };
    for (
      const change of [
        { validation_mode: "full" },
        { validation_mode: undefined },
        { validation_mode: "skip" },
        { preview_url: "https://example.com" },
        { preview_url: undefined },
        { preview_performed: true },
        { preview_performed: "false" },
        { distribution_performed: true },
        { platforms: {} },
      ]
    ) await blocked(() => register({ ...report, ...change }));
    const c1 = await register(report);
    await db.query("update public.poc_candidates set message_ts='100.1' where id=$1", [c1.id]);
    const action = (id: string, role: string, user = "U0BMFQKC001") =>
      scalar("select public.poc_action($1,$2,$3,'T09CYB7AS77','C0C8DUJB52L','100.1') value", [
        id,
        role,
        user,
      ]);
    await blocked(() => action(c1.id, "reject", "UOTHER"));
    await action(c1.id, "technical");
    await blocked(() => scalar("select public.poc_publish($1,'claim','1') value", [c1.id]));
    const rejected = await action(c1.id, "reject");
    assert(
      rejected.status === "adjustment_requested" && rejected.adjustment_reason === null &&
        rejected.adjustment_author === "U0BMFQKC001",
    );
    assert(rejected.approvals.length === 1, "historical vote must remain evidence");
    await blocked(() => action(c1.id, "business"));
    await blocked(() => action(c1.id, "reject"));
    await blocked(() => scalar("select public.poc_publish($1,'claim','1') value", [c1.id]));
    assert(!(await scalar("select public.poc_notice($1,'dispatch') value", [c1.id])).send);
    const r2 = {
      ...report,
      id: "poc-" + "2".repeat(32),
      rc_number: 2,
      rc_tag: "poc-v0.1.0-rc.2",
      previous_candidate: c1.id,
      source_sha: "b".repeat(40),
    };
    const c2 = await register(r2);
    assert((await scalar("select public.poc_state($1) value", [c2.id])).approvals.length === 0);
    await blocked(() => register({ ...r2, preview_url: "https://example.com" }));
    await blocked(() =>
      db.query("update public.poc_candidates set report_text=$1 where id=$2", [
        JSON.stringify(report),
        c2.id,
      ])
    );
    await db.query("update public.poc_candidates set message_ts='100.1' where id=$1", [c2.id]);
    await action(c2.id, "business");
    await blocked(() => scalar("select public.poc_publish($1,'claim','2') value", [c2.id]));
    await action(c2.id, "technical");
    assert((await scalar("select public.poc_notice($1,'dispatch') value", [c2.id])).send);
    assert(!(await scalar("select public.poc_notice($1,'dispatch') value", [c2.id])).send);
    await scalar("select public.poc_publish($1,'claim','2') value", [c2.id]);
    await blocked(() => action(c2.id, "reject"));
    const receipt = {
      source_sha: r2.source_sha,
      report_digest: c2.report_digest,
      tag: "poc-v0.1.0",
      release_id: 123,
      release_url:
        "https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v0.1.0",
      distribution_performed: false,
    };
    await scalar("select public.poc_publish($1,'complete','2',$2) value", [
      c2.id,
      JSON.stringify(receipt),
    ]);
    const repeated = await scalar("select public.poc_publish($1,'claim','3') value", [c2.id]);
    assert(repeated.already_published && repeated.receipt.release_id === 123);
    assert(await scalar("select count(*)::int value from public.poc_publications") === 1);
    await blocked(() =>
      register({
        ...r2,
        id: "poc-" + "3".repeat(32),
        rc_number: 3,
        rc_tag: "poc-v0.1.0-rc.3",
        previous_candidate: c2.id,
      })
    );
    await db.exec("set role anon;");
    await blocked(() => action(c2.id, "reject"));
  } finally {
    await db.close();
  }
});
