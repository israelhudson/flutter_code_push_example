-- Automatic reviewers for new candidates only. No historical row is backfilled.
-- Catalog administration stays in audited SQL/migrations; runtime cannot edit it.
create table public.delivery_reviewers (
 id uuid primary key default gen_random_uuid(),
 repository text not null check (repository ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
 name text not null check (length(btrim(name)) between 1 and 120 and name !~ '[[:cntrl:]]'),
 slack_team_id text not null check (slack_team_id ~ '^T[A-Z0-9]+$'),
 slack_user_id text not null check (slack_user_id ~ '^U[A-Z0-9]+$'),
 github_user_id bigint check (github_user_id > 0),
 github_login text check (github_login ~ '^[A-Za-z0-9]([A-Za-z0-9-]{0,37}[A-Za-z0-9])?$'),
 can_technical boolean not null default false,
 can_business boolean not null default false,
 default_technical boolean not null default false,
 default_business boolean not null default false,
 active boolean not null default true,
 revision bigint not null default 1 check (revision > 0),
 created_at timestamptz not null default now(),
 check (not default_technical or (active and can_technical)),
 check (not default_business or (active and can_business)),
 unique (repository, slack_team_id, slack_user_id)
);
create unique index delivery_reviewers_default_technical
 on public.delivery_reviewers(repository) where default_technical;
create unique index delivery_reviewers_default_business
 on public.delivery_reviewers(repository) where default_business;
create unique index delivery_reviewers_github_identity
 on public.delivery_reviewers(repository,github_user_id) where github_user_id is not null;
alter table public.delivery_reviewers enable row level security;
revoke all on public.delivery_reviewers from public,anon,authenticated,service_role;
grant select on public.delivery_reviewers to service_role;

-- A statement-level lock is obtained before row locks, sharing one lock order with
-- registration and decisions. It also covers inserts and atomic default swaps.
create function public.delivery_reviewers_lock() returns trigger
language plpgsql security invoker set search_path=public as $$
begin
 perform pg_advisory_xact_lock(1515003);
 return null;
end $$;
create trigger delivery_reviewers_lock before insert or update or delete
 on public.delivery_reviewers for each statement execute function public.delivery_reviewers_lock();

create function public.delivery_reviewers_identity() returns trigger
language plpgsql security invoker set search_path=public as $$
begin
 if tg_op='UPDATE' then
  if (new.id,new.repository,new.slack_team_id,new.slack_user_id,new.created_at)
   is distinct from
   (old.id,old.repository,old.slack_team_id,old.slack_user_id,old.created_at)
  then raise exception 'Reviewer identity is immutable; register another person'; end if;
  new.revision := old.revision+1;
 else
  new.revision := 1;
 end if;
 return new;
end $$;
create trigger delivery_reviewers_identity before insert or update on public.delivery_reviewers
 for each row execute function public.delivery_reviewers_identity();
revoke all on function public.delivery_reviewers_lock(),public.delivery_reviewers_identity()
 from public,anon,authenticated,service_role;

insert into public.delivery_reviewers(id,repository,name,slack_team_id,slack_user_id,
 github_user_id,github_login,can_technical,can_business,default_technical,default_business)
values('1b2c3d4e-1515-4000-8000-000000000001','israelhudson/flutter_code_push_example',
 'Israel','T09CYB7AS77','U0BMFQKC001',18661493,'israelhudson',true,true,true,true);

create function public.delivery_resolve_reviewers(p_repository text,p_team text,p_solo boolean)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare t delivery_reviewers; b delivery_reviewers;
begin
 perform pg_advisory_xact_lock(1515003);
 if p_repository is null or p_team is null or p_solo is null then
  raise exception 'Repository, workspace and solo policy are required'; end if;
 select * into strict t from delivery_reviewers where repository=p_repository
  and slack_team_id=p_team and default_technical and active and can_technical;
 select * into strict b from delivery_reviewers where repository=p_repository
  and slack_team_id=p_team and default_business and active and can_business;
 if not p_solo and (t.id=b.id or t.slack_user_id=b.slack_user_id
  or (t.github_user_id is not null and t.github_user_id=b.github_user_id)) then
  raise exception 'Distinct technical and business reviewers required outside solo mode'; end if;
 return jsonb_build_object('schema','delivery-reviewers-v1','repository',p_repository,
  'team_id',p_team,'solo',p_solo,
  'technical',jsonb_build_object('id',t.id,'revision',t.revision,'name',t.name,
   'slack_user',t.slack_user_id,'github_user_id',t.github_user_id,'github_login',t.github_login),
  'business',jsonb_build_object('id',b.id,'revision',b.revision,'name',b.name,
   'slack_user',b.slack_user_id,'github_user_id',b.github_user_id,'github_login',b.github_login));
end $$;
revoke all on function public.delivery_resolve_reviewers(text,text,boolean) from public,anon,authenticated;
grant execute on function public.delivery_resolve_reviewers(text,text,boolean) to service_role;

alter table public.delivery_control
 add column technical_reviewer_id uuid references public.delivery_reviewers(id) on delete restrict,
 add column business_reviewer_id uuid references public.delivery_reviewers(id) on delete restrict,
 add column reviewer_snapshot jsonb,
 add constraint delivery_reviewer_snapshot_shape check (
  (technical_reviewer_id is null and business_reviewer_id is null and reviewer_snapshot is null)
  or (technical_reviewer_id is not null and business_reviewer_id is not null
   and reviewer_snapshot is not null and jsonb_typeof(reviewer_snapshot)='object'
   and (reviewer_snapshot->>'schema') is not distinct from 'delivery-reviewers-v1'
   and octet_length(reviewer_snapshot::text)<=4096));

-- The original legacy event shape is kept; only newly assigned candidates carry
-- the frozen reviewer evidence. Past outbox events are not rewritten.
create or replace function public.delivery_enqueue(p_id text) returns void
language plpgsql security invoker set search_path=public as $$
declare c delivery_control; evidence jsonb;
begin
 select * into strict c from delivery_control where id=p_id;
 evidence := jsonb_build_object(
  'candidate',c.id,'revision',c.revision,'status',c.status,'source_sha',c.source_sha,
  'technical_at',c.technical_at,'business_at',c.business_at,'rejected_role',c.rejected_role,
  'rejected_at',c.rejected_at,'solo',c.solo,'publication_run',c.publication_run);
 if c.reviewer_snapshot is not null then
  evidence := evidence || jsonb_build_object('reviewers',c.reviewer_snapshot);
 end if;
 insert into delivery_outbox(candidate_id,kind,revision,event)
 values(c.id,'history',c.revision,evidence) on conflict do nothing;
 insert into delivery_outbox(candidate_id,kind,revision)
 select c.id,k,c.revision from unnest(array['channel','technical','business']) k
 on conflict do nothing;
end $$;

create or replace function public.delivery_register(p_candidate jsonb) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare c delivery_control; prior delivery_control; incoming delivery_control; reviewers jsonb;
begin
 perform pg_advisory_xact_lock(1515002);
 incoming := jsonb_populate_record(null::delivery_control,p_candidate);
 select * into c from delivery_control where id=incoming.id;
 if found then
  -- Retrying an already-frozen manifest does not reinterpret historical reviewers.
  if (c.manifest_commit,c.manifest_digest) is distinct from (incoming.manifest_commit,incoming.manifest_digest)
  then raise exception 'Immutable candidate differs'; end if;
  return to_jsonb(c);
 end if;
 reviewers := delivery_resolve_reviewers(incoming.repository,incoming.team_id,incoming.solo);
 if p_candidate->'reviewers' is distinct from reviewers then
  raise exception 'Reviewer selection changed; prepare a new manifest before registration'; end if;
 if incoming.previous_id is not null then
  select * into strict prior from delivery_control where id=incoming.previous_id for update;
  if prior.status not in ('rejected','cancelled') or prior.version <> incoming.version
    or incoming.rc_number <> prior.rc_number+1
    or exists(select 1 from delivery_control where previous_id=prior.id)
  then raise exception 'RC2 requires the last closed candidate'; end if;
 elsif incoming.rc_number <> 1 then raise exception 'First RC must be RC1'; end if;
 if exists(select 1 from delivery_control where status='published' and
  string_to_array(version,'.')::int[] >= string_to_array(incoming.version,'.')::int[])
 then raise exception 'Version already published or obsolete'; end if;
 insert into delivery_control(id,repository,version,rc_number,rc_tag,source_sha,manifest_commit,
 manifest_digest,team_id,channel_id,technical_user,business_user,solo,scope,previous_id,
 technical_reviewer_id,business_reviewer_id,reviewer_snapshot)
 values(incoming.id,incoming.repository,incoming.version,incoming.rc_number,incoming.rc_tag,
 incoming.source_sha,incoming.manifest_commit,incoming.manifest_digest,incoming.team_id,
 incoming.channel_id,reviewers#>>'{technical,slack_user}',reviewers#>>'{business,slack_user}',
 incoming.solo,incoming.scope,incoming.previous_id,(reviewers#>>'{technical,id}')::uuid,
 (reviewers#>>'{business,id}')::uuid,reviewers) returning * into c;
 perform delivery_enqueue(c.id);
 return to_jsonb(c);
end $$;

-- Reusable authorization barrier for new decisions and irreversible dispatch /
-- publication claims. Default swaps do not reassign frozen candidates; explicit
-- active/role revocation prevents beginning a new publication for those candidates.
create function public.delivery_assert_reviewers(p_candidate public.delivery_control)
returns void language plpgsql security invoker set search_path=public as $$
begin
 perform pg_advisory_xact_lock(1515003);
 if p_candidate.reviewer_snapshot is null then return; end if;
 if not exists(select 1 from delivery_reviewers where id=p_candidate.technical_reviewer_id
   and repository=p_candidate.repository and slack_team_id=p_candidate.team_id
   and slack_user_id=p_candidate.technical_user and active and can_technical)
  or not exists(select 1 from delivery_reviewers where id=p_candidate.business_reviewer_id
   and repository=p_candidate.repository and slack_team_id=p_candidate.team_id
   and slack_user_id=p_candidate.business_user and active and can_business)
 then raise exception 'Assigned reviewer is inactive or no longer authorized for this role'; end if;
end $$;
revoke all on function public.delivery_assert_reviewers(public.delivery_control) from public,anon,authenticated;
grant execute on function public.delivery_assert_reviewers(public.delivery_control) to service_role;

create or replace function public.delivery_decide(p_id text,p_role text,p_action text,p_user text,
 p_team text,p_channel text,p_message text) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare c delivery_control;
begin
 -- Match catalog writers' lock order before taking the candidate row lock.
 perform pg_advisory_xact_lock(1515003);
 select * into strict c from delivery_control where id=p_id for update;
 if p_role is null or p_action is null or p_role not in ('technical','business') or p_action not in ('accept','reject')
 or p_team is distinct from c.team_id or p_channel !~ '^D[A-Z0-9]+$'
 or p_message !~ '^[0-9]+\.[0-9]+$'
 or (p_role='technical' and (p_user,p_channel,p_message) is distinct from
    (c.technical_user,c.technical_channel,c.technical_message))
 or (p_role='business' and (p_user,p_channel,p_message) is distinct from
    (c.business_user,c.business_channel,c.business_message))
 then raise exception 'Wrong reviewer, role or private message'; end if;
 -- Already-committed decisions remain idempotent, including historical callbacks.
 if p_action='reject' and c.status='rejected' and c.rejected_by=p_user and c.rejected_role=p_role
 then return to_jsonb(c); end if;
 if p_action='accept' and ((p_role='technical' and c.technical_at is not null)
   or (p_role='business' and c.business_at is not null)) then return to_jsonb(c); end if;
 if c.status <> 'pending' then raise exception 'Evaluation closed'; end if;
 perform delivery_assert_reviewers(c);
 if p_action='reject' then
  update delivery_control set status='rejected',rejected_by=p_user,rejected_role=p_role,
   rejected_at=clock_timestamp(),revision=revision+1 where id=p_id;
 else
  update delivery_control set
   technical_at=case when p_role='technical' then clock_timestamp() else technical_at end,
   business_at=case when p_role='business' then clock_timestamp() else business_at end,
   revision=revision+1 where id=p_id;
  update delivery_control set status='approved' where id=p_id and technical_at is not null and business_at is not null;
 end if;
 perform delivery_enqueue(p_id);
 insert into delivery_outbox(candidate_id,kind,revision)
 select id,'dispatch',revision from delivery_control where id=p_id and status='approved' and scope='github_test'
 on conflict do nothing;
 select * into c from delivery_control where id=p_id;
 return to_jsonb(c);
end $$;
revoke all on function public.delivery_register(jsonb),public.delivery_decide(text,text,text,text,text,text,text)
 from public,anon,authenticated;
grant execute on function public.delivery_register(jsonb),public.delivery_decide(text,text,text,text,text,text,text)
 to service_role;


create or replace function public.delivery_begin(p_id bigint,p_lease text) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare o delivery_outbox; c delivery_control;
begin
 select * into strict o from delivery_outbox where id=p_id;
 if o.kind='dispatch' then
  -- Lock catalog before the control row; another reviewer may have been revoked
  -- after both approvals but before this worker starts the external dispatch.
  perform pg_advisory_xact_lock(1515003);
  select * into strict c from delivery_control where id=o.candidate_id for update;
  perform delivery_assert_reviewers(c);
 end if;
 update delivery_outbox set state='effect' where id=p_id and lease=p_lease and state='working'
  and kind<>'history' returning * into o;
 if not found then raise exception 'Effect already started or lease changed'; end if;
 return jsonb_build_object('task',to_jsonb(o),'candidate',
  (select to_jsonb(candidate) from delivery_control candidate where candidate.id=o.candidate_id));
end $$;

create or replace function public.delivery_publish(p_id text,p_run text,p_complete boolean default false)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare c delivery_control;
begin
 perform pg_advisory_xact_lock(1515003);
 select * into strict c from delivery_control where id=p_id for update;
 if p_run is null or p_run !~ '^[0-9]+$' or c.scope<>'github_test'
 then raise exception 'Publication scope rejected'; end if;
 if c.status in ('publishing','published') then
  -- The same established publication owner can finish/retry even after a catalog
  -- change. Revocation is a barrier to starting work, not a fictitious rollback.
  if c.publication_run is distinct from p_run then raise exception 'Another run owns publication'; end if;
 elsif c.status<>'approved' or c.technical_at is null or c.business_at is null then
  raise exception 'Both approvals required';
 else
  perform delivery_assert_reviewers(c);
 end if;
 if exists(select 1 from delivery_outbox where candidate_id=p_id and kind='history'
  and event->>'status' in ('pending','approved') and state<>'done')
 then raise exception 'GitHub evidence pending'; end if;
 if p_complete and c.status not in ('publishing','published') then raise exception 'Claim required'; end if;
 if c.status='published' then return to_jsonb(c); end if;
 update delivery_control set status=case when p_complete then 'published' else 'publishing' end,
  publication_run=p_run,revision=revision+1 where id=p_id
  and (status<>'publishing' or p_complete) returning * into c;
 if found then perform delivery_enqueue(p_id); end if;
 return (select to_jsonb(t) from delivery_control t where id=p_id);
end $$;
revoke all on function public.delivery_begin(bigint,text),public.delivery_publish(text,text,boolean)
 from public,anon,authenticated;
grant execute on function public.delivery_begin(bigint,text),public.delivery_publish(text,text,boolean)
 to service_role;
