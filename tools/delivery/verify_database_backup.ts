/** Offline restore rehearsal. Backup stays private; output contains only counts/digests. */
import { PGlite } from "@electric-sql/pglite";
import { digest } from "../../supabase/functions/_shared/poc.ts";
const [input, output] = Deno.args;
if (!input || !output) {
  throw Error("Usage: verify_database_backup.ts private-backup.json result.json");
}
const raw = await Deno.readTextFile(input);
const backup = JSON.parse(raw).rows[0].backup;
if (backup.project !== "xtvueqciogzkyjkkqxcx") throw Error("Wrong dedicated project");
const tables = [
  "poc_user_directory",
  "poc_config",
  "poc_candidates",
  "poc_approvals",
  "poc_publications",
  "poc_events",
  "poc_private_notices",
  "poc_adjustment_tokens",
];
if (Object.keys(backup.tables).sort().join() !== [...tables].sort().join()) {
  throw Error("Incomplete backup");
}
const stable = (v: any): string =>
  Array.isArray(v)
    ? "[" + v.map(stable).join(",") + "]"
    : v && typeof v === "object"
    ? "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + stable(v[k])).join(",") + "}"
    : JSON.stringify(v);
const rows = (v: any[]) => v.map(stable).sort().join("\n");
const db = new PGlite();
try {
  await db.exec(
    "create role anon; create role authenticated; create role service_role bypassrls; set timezone='UTC';",
  );
  for (
    const file of [
      "20261013200000_poc_slack.sql",
      "20261013203000_poc_slack_indexes.sql",
      "20261014211744_poc_controls_only_rejection.sql",
    ]
  ) await db.exec(await Deno.readTextFile("supabase/migrations/" + file));
  // Remove the fixture seed from this disposable local database only.
  await db.exec("delete from public.poc_config; delete from public.poc_user_directory;");
  for (const table of tables) {
    await db.query(
      `insert into public.${table} overriding system value select * from jsonb_populate_recordset(null::public.${table},$1::jsonb)`,
      [JSON.stringify(backup.tables[table])],
    );
  }
  await db.query("select setval('public.poc_events_id_seq',$1,true)", [backup.evidence_sequence]);
  const verified: any[] = [];
  const verify = async () => {
    for (const table of tables) {
      const restored =
        (await db.query<{ value: any }>(`select to_jsonb(t) value from public.${table} t`)).rows
          .map((r) => r.value);
      if (rows(restored) !== rows(backup.tables[table])) throw Error("Restore mismatch: " + table);
    }
  };
  await verify();
  for (const table of tables) {
    verified.push({
      table,
      count: backup.tables[table].length,
      sha256: await digest(rows(backup.tables[table])),
    });
  }
  const fn = (await db.query<{ name: string; definition: string }>(
    "select proname name,pg_get_functiondef(p.oid) definition from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname like 'poc_%' order by proname",
  )).rows;
  const functionDrift = backup.functions.filter((f: any) =>
    f.definition.replace(/\s+/g, " ").trim() !==
      fn.find((x) => x.name === f.name)?.definition.replace(/\s+/g, " ").trim()
  ).map((f: any) => f.name);
  await db.exec(
    await Deno.readTextFile("supabase/migrations/20261015003023_delivery_two_table_control.sql"),
  );
  await verify();
  const result = {
    kind: "offline_postgres_restore_rehearsal",
    backup_sha256: await digest(raw),
    tables: verified,
    legacy_data_unchanged_after_migration: true,
    legacy_function_drift: functionDrift,
    new_table_counts: (await db.query(
      "select (select count(*) from delivery_control)::int controls,(select count(*) from delivery_outbox)::int outbox",
    )).rows[0],
    contains_private_rows: false,
  };
  await Deno.writeTextFile(output, JSON.stringify(result, null, 2) + "\n");
  console.log(
    JSON.stringify({
      restored_rows: verified.reduce((n, t) => n + t.count, 0),
      tables: verified.length,
      function_drift: functionDrift,
      migration_preserved_data: true,
    }),
  );
  if (functionDrift.length) {
    throw Error("Live function definitions differ; inspect backup before remote migration");
  }
} finally {
  await db.close();
}
