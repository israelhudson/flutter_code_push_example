import { PGlite } from "@electric-sql/pglite";

const repository = "israelhudson/flutter_code_push_example";
const team = "T09CYB7AS77";
const israel = "1b2c3d4e-1515-4000-8000-000000000001";
const substitute = "1b2c3d4e-1515-4000-8000-000000000002";
const migration = "supabase/migrations/20261015132214_delivery_reviewer_defaults.sql";
function assert(ok: unknown, message = "assertion failed") {
  if (!ok) throw Error(message);
}
function same(a: unknown, b: unknown, message = "values differ") {
  assert(JSON.stringify(a) === JSON.stringify(b), message);
}
async function database(apply = true) {
  const db = new PGlite();
  await db.exec("create role anon; create role authenticated; create role service_role bypassrls;");
  for (
    const file of [
      "20261015003023_delivery_two_table_control.sql",
      "20261015014626_recover_delivery_before_effect.sql",
    ]
  ) await db.exec(await Deno.readTextFile(`supabase/migrations/${file}`));
  if (apply) await db.exec(await Deno.readTextFile(migration));
  const value = async (q: string, p: unknown[] = []) =>
    (await db.query<{ v: any }>(q, p)).rows[0]?.v;
  const blocked = async (q: string, p: unknown[] = [], text?: string) => {
    let error: unknown;
    try {
      await db.query(q, p);
    } catch (e) {
      error = e;
    }
    assert(error, `must reject: ${q}`);
    if (text) assert(String(error).includes(text), `unexpected error: ${error}`);
  };
  const resolve = (solo = true) =>
    value("select delivery_resolve_reviewers($1,$2,$3) v", [repository, team, solo]);
  const candidate = async (overrides: Record<string, unknown> = {}) => ({
    id: "delivery-" + crypto.randomUUID().replaceAll("-", ""),
    repository,
    version: "8.0.0",
    rc_number: 1,
    rc_tag: "poc-v8.0.0-rc.1",
    source_sha: "a".repeat(40),
    manifest_commit: "b".repeat(40),
    manifest_digest: "c".repeat(64),
    team_id: team,
    channel_id: "C0C8DUJB52L",
    technical_user: "USPOOF",
    business_user: "USPOOF",
    solo: true,
    scope: "none",
    reviewers: apply ? await resolve() : undefined,
    ...overrides,
  });
  const register = (c: unknown) => value("select delivery_register($1) v", [c]);
  const bind = (id: string) =>
    db.query(
      "update delivery_control set technical_channel='DTECH',technical_message='100.1',business_channel='DBIZ',business_message='100.2' where id=$1",
      [id],
    );
  const decide = (c: any, role: string, action = "accept") =>
    value("select delivery_decide($1,$2,$3,$4,$5,$6,$7) v", [
      c.id,
      role,
      action,
      role === "technical" ? c.technical_user : c.business_user,
      team,
      role === "technical" ? "DTECH" : "DBIZ",
      role === "technical" ? "100.1" : "100.2",
    ]);
  const addSubstitute = () =>
    db.query(
      `insert into delivery_reviewers(id,repository,name,slack_team_id,slack_user_id,
       github_user_id,github_login,can_technical,can_business)
       values($1,$2,'Substituto',$3,'USUB',9999,'substitute',true,true)`,
      [substitute, repository, team],
    );
  return { db, value, blocked, resolve, candidate, register, bind, decide, addSubstitute };
}

Deno.test("reviewers: exactly three tables, automatic solo defaults and server-only read catalog", async () => {
  const { db, value, blocked, resolve, candidate, register } = await database();
  try {
    same(
      await value(
        "select array_agg(tablename order by tablename) v from pg_tables where schemaname='public'",
      ),
      [
        "delivery_control",
        "delivery_outbox",
        "delivery_reviewers",
      ],
    );
    const reviewers = await resolve();
    assert(reviewers.schema === "delivery-reviewers-v1" && reviewers.solo === true);
    assert(reviewers.technical.id === israel && reviewers.business.id === israel);
    assert(reviewers.technical.revision === 1 && reviewers.technical.github_user_id === 18661493);
    await blocked("select delivery_resolve_reviewers($1,$2,false)", [repository, team], "Distinct");
    await blocked("select delivery_resolve_reviewers($1,'TOTHER',true)", [repository]);
    await blocked("select delivery_resolve_reviewers($1,$2,null)", [repository, team], "required");
    for (const role of ["anon", "authenticated"]) {
      await db.exec(`set role ${role}`);
      await blocked("select * from delivery_reviewers");
      await blocked("select delivery_resolve_reviewers($1,$2,true)", [repository, team]);
      await blocked("select delivery_register('{}')");
      await db.exec("reset role");
    }
    assert(
      await value("select relrowsecurity v from pg_class where oid='delivery_reviewers'::regclass"),
    );
    await db.exec("set role service_role");
    assert(await value("select count(*)::int v from delivery_reviewers") === 1);
    await blocked("update delivery_reviewers set name='Changed'");
    await blocked("delete from delivery_reviewers");
    await blocked(
      "insert into delivery_reviewers(repository,name,slack_team_id,slack_user_id) values($1,'X',$2,'UX')",
      [repository, team],
    );
    same(await resolve(), reviewers);
    const frozen = await register(await candidate());
    assert(
      frozen.technical_user === "U0BMFQKC001" && frozen.business_user === "U0BMFQKC001",
      "caller cannot spoof reviewers",
    );
    assert(frozen.technical_reviewer_id === israel && frozen.business_reviewer_id === israel);
    same(frozen.reviewer_snapshot, reviewers);
    same(
      await value("select event->'reviewers' v from delivery_outbox where kind='history'"),
      reviewers,
    );
    await db.exec("reset role");
    assert(
      await value(
        "select count(*)::int v from pg_proc where proname like 'delivery_%' and prosecdef",
      ) === 0,
    );
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: missing defaults, duplicate defaults and invalid catalog changes fail closed", async () => {
  const { db, value, blocked, resolve, addSubstitute } = await database();
  try {
    await addSubstitute();
    await blocked("update delivery_reviewers set default_technical=true where id=$1", [substitute]);
    await blocked("update delivery_reviewers set active=false where id=$1", [israel]);
    await blocked("update delivery_reviewers set can_business=false where id=$1", [israel]);
    for (
      const change of [
        "slack_user_id='UOTHER'",
        "slack_team_id='TOTHER'",
      ]
    ) {
      await blocked(`update delivery_reviewers set ${change} where id=$1`, [israel], "immutable");
    }
    await db.query("update delivery_reviewers set default_business=false where id=$1", [israel]);
    assert(
      await value("select revision::int v from delivery_reviewers where id=$1", [israel]) === 2,
    );
    await blocked("select delivery_resolve_reviewers($1,$2,true)", [repository, team]);
    await db.query("update delivery_reviewers set default_business=true where id=$1", [substitute]);
    const r = await resolve(false);
    assert(r.technical.id === israel && r.business.id === substitute);
    assert(r.solo === false && r.business.revision === 2);
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: catalog change between planning and register rejects stale snapshot without writes", async () => {
  const { db, value, blocked, candidate, register, resolve } = await database();
  try {
    const planned = await candidate();
    await db.query("update delivery_reviewers set name='Israel atualizado' where id=$1", [israel]);
    await blocked("select delivery_register($1)", [planned], "Reviewer selection changed");
    assert(await value("select count(*)::int v from delivery_control") === 0);
    assert(await value("select count(*)::int v from delivery_outbox") === 0);
    await blocked("select delivery_register($1)", [{ ...planned, reviewers: undefined }]);
    const frozen = await register({ ...planned, reviewers: await resolve() });
    await blocked("delete from delivery_reviewers where id=$1", [israel]);
    await blocked("update delivery_control set reviewer_snapshot='{}' where id=$1", [frozen.id]);
    await blocked("update delivery_control set technical_reviewer_id=null where id=$1", [
      frozen.id,
    ]);
    const before = await value("select to_jsonb(c) v from delivery_control c where id=$1", [
      frozen.id,
    ]);
    await db.query("update delivery_reviewers set name='Novo nome' where id=$1", [israel]);
    same(await register(planned), before, "already frozen manifest retries are historical");
    await blocked(
      "select delivery_register($1)",
      [{ ...planned, manifest_digest: "d".repeat(64) }],
      "Immutable",
    );
    // PGlite validates SQL behavior, not parallel remote sessions. Inspect the lock
    // contract explicitly; real connection contention is a separate deployment check.
    const registerSql = await value(
      "select pg_get_functiondef('delivery_register(jsonb)'::regprocedure) v",
    );
    const resolveSql = await value(
      "select pg_get_functiondef('delivery_resolve_reviewers(text,text,boolean)'::regprocedure) v",
    );
    const lockSql = await value(
      "select pg_get_functiondef('delivery_reviewers_lock()'::regprocedure) v",
    );
    assert(registerSql.includes("delivery_resolve_reviewers"));
    assert(resolveSql.includes("pg_advisory_xact_lock(1515003)"));
    assert(lockSql.includes("pg_advisory_xact_lock(1515003)"));
    assert(
      await value("select (tgtype & 1)=0 v from pg_trigger where tgname='delivery_reviewers_lock'"),
      "catalog lock must be statement-level before row locks",
    );
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: changing default affects future candidates, preserves assignment and rejects stale callbacks", async () => {
  const { db, value, blocked, candidate, register, bind, decide, resolve, addSubstitute } =
    await database();
  try {
    const first = await register(await candidate());
    await bind(first.id);
    await addSubstitute();
    await db.exec("begin");
    await db.query("update delivery_reviewers set default_business=false where id=$1", [israel]);
    await db.query("update delivery_reviewers set default_business=true where id=$1", [substitute]);
    await db.exec("commit");
    assert((await resolve(false)).business.id === substitute);
    assert((await decide(first, "technical")).status === "pending");
    assert(
      (await decide(first, "business", "reject")).status === "rejected",
      "original reviewer keeps assigned role",
    );
    const repeated = await decide(first, "business", "reject");
    assert(repeated.revision === 2);
    const second = await register(
      await candidate({
        rc_number: 2,
        rc_tag: "poc-v8.0.0-rc.2",
        previous_id: first.id,
        solo: false,
        reviewers: await resolve(false),
      }),
    );
    assert(second.business_reviewer_id === substitute && second.technical_reviewer_id === israel);
    assert(
      second.technical_at === null && second.business_at === null,
      "RC2 cannot inherit decisions",
    );
    await bind(second.id);
    await blocked(
      "select delivery_decide($1,'business','accept','U0BMFQKC001',$2,'DBIZ','100.2')",
      [second.id, team],
    );
    await decide(second, "technical");
    assert((await decide(second, "business")).status === "approved");
    assert(
      await value("select count(*)::int v from delivery_outbox where kind='dispatch'") === 0,
      "scope none never creates a dispatch",
    );
    await blocked("select delivery_publish($1,'123',false)", [second.id], "scope");
    assert(
      (await value("select reviewer_snapshot v from delivery_control where id=$1", [first.id]))
        .business.id === israel,
    );
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: revocation blocks new decisions but preserves committed decisions and retries", async () => {
  const { db, value, blocked, candidate, register, bind, decide } = await database();
  try {
    const c = await register(await candidate());
    await bind(c.id);
    const accepted = await decide(c, "technical");
    await db.query(
      "update delivery_reviewers set default_technical=false,default_business=false,active=false where id=$1",
      [israel],
    );
    same(await decide(c, "technical"), accepted, "retry acknowledges committed history");
    await blocked(
      "select delivery_decide($1,'business','accept','U0BMFQKC001',$2,'DBIZ','100.2')",
      [c.id, team],
      "inactive",
    );
    assert(await value("select business_at is null v from delivery_control where id=$1", [c.id]));
    await db.query("update delivery_reviewers set active=true,can_business=false where id=$1", [
      israel,
    ]);
    await blocked(
      "select delivery_decide($1,'business','reject','U0BMFQKC001',$2,'DBIZ','100.2')",
      [c.id, team],
      "authorized",
    );
    assert(await value("select count(*)::int v from delivery_outbox where kind='dispatch'") === 0);
    assert(await value("select count(*)::int v from delivery_outbox where kind='history'") === 2);
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: migration leaves historical candidate and outbox unchanged, legacy retry still works", async () => {
  const { db, value, candidate, register, bind, decide } = await database(false);
  try {
    const c = await register(await candidate());
    await bind(c.id);
    const accepted = await decide(c, "technical");
    const beforeEvents = await value(
      "select jsonb_agg(to_jsonb(o) order by id) v from delivery_outbox o",
    );
    await db.exec(await Deno.readTextFile(migration));
    const historical = await value(
      "select to_jsonb(c)-array['technical_reviewer_id','business_reviewer_id','reviewer_snapshot'] v from delivery_control c where id=$1",
      [c.id],
    );
    same(historical, accepted);
    same(
      await value("select jsonb_agg(to_jsonb(o) order by id) v from delivery_outbox o"),
      beforeEvents,
    );
    assert(
      await value("select reviewer_snapshot is null v from delivery_control where id=$1", [c.id]),
    );
    assert((await register(await candidate({ id: c.id }))).technical_user === "USPOOF");
    assert((await decide(c, "business", "reject")).status === "rejected");
    assert(
      await value(
        "select count(*)::int v from delivery_outbox where kind='history' and event ? 'reviewers'",
      ) === 0,
      "legacy layout stays legacy",
    );
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: optional GitHub metadata can be added or renamed without changing frozen evidence", async () => {
  const { db, value, candidate, register, resolve } = await database();
  try {
    await db.query(
      "update delivery_reviewers set github_user_id=null,github_login=null where id=$1",
      [israel],
    );
    const c = await register(await candidate());
    assert(c.reviewer_snapshot.technical.github_user_id === null);
    assert(c.reviewer_snapshot.technical.github_login === null);
    await db.query(
      "update delivery_reviewers set github_user_id=18661493,github_login='israelhudson' where id=$1",
      [israel],
    );
    await db.query("update delivery_reviewers set github_login='israel-renamed' where id=$1", [
      israel,
    ]);
    const current = await resolve();
    assert(current.technical.github_user_id === 18661493);
    assert(current.technical.github_login === "israel-renamed");
    assert(current.technical.revision === c.reviewer_snapshot.technical.revision + 2);
    same(
      await value("select reviewer_snapshot v from delivery_control where id=$1", [c.id]),
      c.reviewer_snapshot,
    );
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: revocation after both approvals blocks dispatch effect and first publication claim", async () => {
  const { db, value, blocked, candidate, register, bind, decide } = await database();
  try {
    const c = await register(await candidate({ scope: "github_test" }));
    await bind(c.id);
    await decide(c, "technical");
    const approved = await decide(c, "business");
    assert(approved.status === "approved");
    await db.exec(
      "update delivery_outbox set state='done',receipt=repeat('e',40) where kind<>'dispatch'",
    );
    const lease = crypto.randomUUID();
    const work = await value("select delivery_take($1) v", [lease]);
    assert(work.task.kind === "dispatch");
    await db.query(
      "update delivery_reviewers set default_technical=false,default_business=false,active=false where id=$1",
      [israel],
    );
    await blocked("select delivery_begin($1,$2)", [work.task.id, lease], "inactive");
    await blocked("select delivery_publish($1,'123',false)", [c.id], "inactive");
    const state = await value("select to_jsonb(c) v from delivery_control c where id=$1", [c.id]);
    same(state, approved, "denied effect/claim preserves frozen approvals and state");
    assert(
      await value("select state v from delivery_outbox where id=$1", [work.task.id]) === "working",
    );
    assert(state.publication_run === null);
  } finally {
    await db.close();
  }
});

Deno.test("reviewers: default swap permits frozen dispatch and confirmed publication owner can finish after revocation", async () => {
  const { db, value, blocked, candidate, register, bind, decide, addSubstitute } = await database();
  try {
    const c = await register(await candidate({ scope: "github_test" }));
    await bind(c.id);
    await decide(c, "technical");
    await decide(c, "business");
    await addSubstitute();
    await db.exec("begin");
    await db.query(
      "update delivery_reviewers set default_technical=false,default_business=false where id=$1",
      [israel],
    );
    await db.query(
      "update delivery_reviewers set default_technical=true,default_business=true where id=$1",
      [substitute],
    );
    await db.exec("commit");
    await db.exec(
      "update delivery_outbox set state='done',receipt=repeat('e',40) where kind<>'dispatch'",
    );
    const lease = crypto.randomUUID();
    const work = await value("select delivery_take($1) v", [lease]);
    assert(work.task.kind === "dispatch");
    assert(
      (await value("select delivery_begin($1,$2) v", [work.task.id, lease])).task.state ===
        "effect",
    );
    const started = await value("select delivery_publish($1,'123',false) v", [c.id]);
    assert(started.status === "publishing" && started.publication_run === "123");
    await db.query("update delivery_reviewers set active=false where id=$1", [israel]);
    same(await value("select delivery_publish($1,'123',false) v", [c.id]), started);
    await blocked("select delivery_publish($1,'124',false)", [c.id], "Another run");
    const complete = await value("select delivery_publish($1,'123',true) v", [c.id]);
    assert(complete.status === "published");
    same(await value("select delivery_publish($1,'123',true) v", [c.id]), complete);
  } finally {
    await db.close();
  }
});
