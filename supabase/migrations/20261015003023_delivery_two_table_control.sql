-- New lane only. No legacy row, tag, vote or message is changed.
create table public.delivery_control (
 id text primary key check (id ~ '^delivery-[a-f0-9]{32}$'),
 repository text not null check (repository = 'israelhudson/flutter_code_push_example'),
 version text not null check (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
 rc_number integer not null check (rc_number > 0),
 rc_tag text not null unique,
 source_sha text not null check (source_sha ~ '^[a-f0-9]{40}$'),
 manifest_commit text not null check (manifest_commit ~ '^[a-f0-9]{40}$'),
 manifest_digest text not null check (manifest_digest ~ '^[a-f0-9]{64}$'),
 team_id text not null check (team_id = 'T09CYB7AS77'),
 channel_id text not null check (channel_id = 'C0C8DUJB52L'),
 technical_user text not null check (technical_user ~ '^U[A-Z0-9]+$'),
 business_user text not null check (business_user ~ '^U[A-Z0-9]+$'),
 solo boolean not null default false,
 scope text not null check (scope in ('none', 'github_test')),
 previous_id text references public.delivery_control(id),
 status text not null default 'pending' check (status in ('pending','approved','rejected','publishing','published','cancelled')),
 revision integer not null default 0,
 technical_at timestamptz,
 business_at timestamptz,
 rejected_by text,
 rejected_role text check (rejected_role in ('technical','business')),
 rejected_at timestamptz,
 technical_channel text,
 technical_message text,
 business_channel text,
 business_message text,
 channel_message text,
 publication_run text check (publication_run ~ '^[0-9]+$'),
 created_at timestamptz not null default now(),
 check (solo or technical_user <> business_user),
 check (rc_tag = 'poc-v' || version || '-rc.' || rc_number),
 unique(version, rc_number)
);
create unique index delivery_one_active on public.delivery_control ((true))
 where status in ('pending','approved','publishing');
create table public.delivery_outbox (
 id bigint generated always as identity primary key,
 candidate_id text not null references public.delivery_control(id),
 kind text not null check (kind in ('history','channel','technical','business','dispatch')),
 revision integer not null,
 state text not null default 'pending' check (state in ('pending','working','effect','done','uncertain')),
 attempts integer not null default 0,
 lease text,
 leased_at timestamptz,
 receipt text,
 completed_at timestamptz,
 -- Only the minimal historical event, never a report, changelog or raw Slack payload.
 event jsonb not null default '{}'::jsonb check (jsonb_typeof(event) = 'object' and octet_length(event::text) <= 4096),
 created_at timestamptz not null default now(),
 unique(candidate_id,kind,revision)
);
create index delivery_outbox_pending on public.delivery_outbox(id) where state in ('pending','working');
alter table public.delivery_control enable row level security;
alter table public.delivery_outbox enable row level security;
revoke all on public.delivery_control, public.delivery_outbox from public, anon, authenticated;
grant select,insert,update on public.delivery_control,public.delivery_outbox to service_role;
grant usage,select on sequence public.delivery_outbox_id_seq to service_role;

create function public.delivery_enqueue(p_id text) returns void
language plpgsql security invoker set search_path = public as $$
declare c delivery_control;
begin
 select * into strict c from delivery_control where id=p_id;
 insert into delivery_outbox(candidate_id,kind,revision,event)
 values(c.id,'history',c.revision,jsonb_build_object(
 'candidate',c.id,'revision',c.revision,'status',c.status,'source_sha',c.source_sha,
 'technical_at',c.technical_at,'business_at',c.business_at,'rejected_role',c.rejected_role,
 'rejected_at',c.rejected_at,'solo',c.solo,'publication_run',c.publication_run))
 on conflict do nothing;
 insert into delivery_outbox(candidate_id,kind,revision)
 select c.id,k,c.revision from unnest(array['channel','technical','business']) k
 on conflict do nothing;
end $$;

create function public.delivery_register(p_candidate jsonb) returns jsonb
language plpgsql security invoker set search_path = public as $$
declare c delivery_control; prior delivery_control; incoming delivery_control;
begin
 -- Serializes RC sequence and one-active checks, including first registration.
 perform pg_advisory_xact_lock(1515002);
 incoming := jsonb_populate_record(null::delivery_control,p_candidate);
 select * into c from delivery_control where id=incoming.id;
 if found then
  if (c.manifest_commit,c.manifest_digest) is distinct from (incoming.manifest_commit,incoming.manifest_digest)
  then raise exception 'Immutable candidate differs'; end if;
  return to_jsonb(c);
 end if;
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
 manifest_digest,team_id,channel_id,technical_user,business_user,solo,scope,previous_id)
 values(incoming.id,incoming.repository,incoming.version,incoming.rc_number,incoming.rc_tag,
 incoming.source_sha,incoming.manifest_commit,incoming.manifest_digest,incoming.team_id,
 incoming.channel_id,incoming.technical_user,incoming.business_user,incoming.solo,incoming.scope,incoming.previous_id)
 returning * into c;
 perform delivery_enqueue(c.id);
 return to_jsonb(c);
end $$;

create function public.delivery_decide(p_id text,p_role text,p_action text,p_user text,
 p_team text,p_channel text,p_message text) returns jsonb
language plpgsql security invoker set search_path = public as $$
declare c delivery_control;
begin
 select * into strict c from delivery_control where id=p_id for update;
 if p_role is null or p_action is null or p_role not in ('technical','business') or p_action not in ('accept','reject')
 or p_team is distinct from c.team_id or p_channel !~ '^D[A-Z0-9]+$'
 or p_message !~ '^[0-9]+\.[0-9]+$'
 or (p_role='technical' and (p_user,p_channel,p_message) is distinct from
    (c.technical_user,c.technical_channel,c.technical_message))
 or (p_role='business' and (p_user,p_channel,p_message) is distinct from
    (c.business_user,c.business_channel,c.business_message))
 then raise exception 'Wrong reviewer, role or private message'; end if;
 -- Repeated accepted callback is harmless even after closure; never reopens voting.
 if p_action='accept' and ((p_role='technical' and c.technical_at is not null)
   or (p_role='business' and c.business_at is not null)) then return to_jsonb(c); end if;
 if c.status <> 'pending' then raise exception 'Evaluation closed'; end if;
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

create function public.delivery_take(p_lease text) returns jsonb
language plpgsql security invoker set search_path = public as $$
declare o delivery_outbox;
begin
 if p_lease is null or p_lease !~ '^[a-f0-9-]{36}$' then raise exception 'Invalid lease'; end if;
 -- Expired sends/dispatches have ambiguous outcomes: NEVER blindly retry them.
 update delivery_outbox set state=case when kind='history' then 'pending' else 'uncertain' end,
 lease=null where state in ('working','effect') and leased_at < now()-interval '5 minutes';
 select q.* into o from delivery_outbox q where q.state='pending'
 and not exists(select 1 from delivery_outbox older where older.candidate_id=q.candidate_id
  and older.kind=q.kind and older.id<q.id and older.state<>'done')
 and (q.kind<>'dispatch' or not exists(select 1 from delivery_outbox h
  where h.candidate_id=q.candidate_id and h.kind='history' and h.revision<=q.revision and h.state<>'done'))
 order by q.id for update skip locked limit 1;
 if not found then return null; end if;
 perform 1 from delivery_control where id=o.candidate_id for update;
 update delivery_outbox set state='working',attempts=attempts+1,lease=p_lease,leased_at=now()
 where id=o.id returning * into o;
 return jsonb_build_object('task',to_jsonb(o),'candidate',
 (select to_jsonb(c) from delivery_control c where c.id=o.candidate_id));
end $$;

create function public.delivery_finish(p_id bigint,p_lease text,p_receipt text,
 p_channel text default null,p_message text default null) returns void
language plpgsql security invoker set search_path = public as $$
declare o delivery_outbox; c delivery_control;
begin
 select * into strict o from delivery_outbox where id=p_id for update;
 if o.state='done' and o.receipt=p_receipt then return; end if;
 if o.state not in ('working','effect') or o.lease is distinct from p_lease or coalesce(length(p_receipt),0)=0
 or length(p_receipt)>512 then raise exception 'Invalid task receipt or lease'; end if;
 select * into strict c from delivery_control where id=o.candidate_id for update;
 if o.kind in ('channel','technical','business') then
  if p_message is null or p_message !~ '^[0-9]+\.[0-9]+$'
   or p_channel is null or (o.kind='channel' and p_channel<>c.channel_id)
   or (o.kind<>'channel' and p_channel !~ '^D[A-Z0-9]+$') then raise exception 'Invalid Slack receipt'; end if;
  if o.kind='channel' then update delivery_control set channel_message=p_message where id=c.id;
  elsif o.kind='technical' then update delivery_control set technical_message=p_message,technical_channel=p_channel where id=c.id;
  else update delivery_control set business_message=p_message,business_channel=p_channel where id=c.id; end if;
 end if;
 update delivery_outbox set state='done',receipt=p_receipt,lease=null,completed_at=clock_timestamp() where id=o.id;
end $$;

create function public.delivery_publish(p_id text,p_run text,p_complete boolean default false) returns jsonb
language plpgsql security invoker set search_path = public as $$
declare c delivery_control;
begin
 select * into strict c from delivery_control where id=p_id for update;
 if p_run is null or p_run !~ '^[0-9]+$' or c.scope<>'github_test' then raise exception 'Publication scope rejected'; end if;
 if c.status in ('publishing','published') then
  if c.publication_run is distinct from p_run then raise exception 'Another run owns publication'; end if;
 elsif c.status<>'approved' or c.technical_at is null or c.business_at is null then
  raise exception 'Both approvals required';
 end if;
 if exists(select 1 from delivery_outbox where candidate_id=p_id and kind='history' and event->>'status' in ('pending','approved') and state<>'done')
 then raise exception 'GitHub evidence pending'; end if;
 if p_complete and c.status not in ('publishing','published') then raise exception 'Claim required'; end if;
 if c.status='published' then return to_jsonb(c); end if;
 update delivery_control set status=case when p_complete then 'published' else 'publishing' end,
 publication_run=p_run,revision=revision+1 where id=p_id
 and (status<>'publishing' or p_complete) returning * into c;
 if found then perform delivery_enqueue(p_id); end if;
 return (select to_jsonb(t) from delivery_control t where id=p_id);
end $$;

-- All entrypoints are server-only, SECURITY INVOKER; no public API policy.
revoke all on function public.delivery_enqueue(text), public.delivery_register(jsonb),
 public.delivery_decide(text,text,text,text,text,text,text),public.delivery_take(text),
 public.delivery_finish(bigint,text,text,text,text),public.delivery_publish(text,text,boolean)
 from public,anon,authenticated;
grant execute on function public.delivery_enqueue(text),public.delivery_register(jsonb),
 public.delivery_decide(text,text,text,text,text,text,text),public.delivery_take(text),
 public.delivery_finish(bigint,text,text,text,text),public.delivery_publish(text,text,boolean) to service_role;

create function public.delivery_state(p_id text default null) returns jsonb
language sql security invoker set search_path=public as $$
 select case when p_id is null then coalesce((select jsonb_agg(to_jsonb(c) order by created_at desc) from delivery_control c),'[]'::jsonb)
 else (select to_jsonb(c) from delivery_control c where id=p_id) end
$$;
revoke all on function public.delivery_state(text) from public,anon,authenticated;
grant execute on function public.delivery_state(text) to service_role;

create function public.delivery_begin(p_id bigint,p_lease text) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare o delivery_outbox;
begin
 update delivery_outbox set state='effect' where id=p_id and lease=p_lease and state='working' and kind<>'history' returning * into o;
 if not found then raise exception 'Effect already started or lease changed'; end if;
 return jsonb_build_object('task',to_jsonb(o),'candidate',(select to_jsonb(c) from delivery_control c where c.id=o.candidate_id));
end $$;
revoke all on function public.delivery_begin(bigint,text) from public,anon,authenticated;
grant execute on function public.delivery_begin(bigint,text) to service_role;

create function public.delivery_task(p_id bigint,p_lease text) returns jsonb
language sql security invoker set search_path=public as $$
 select to_jsonb(o) from delivery_outbox o where id=p_id and lease=p_lease and state='working'
$$;
revoke all on function public.delivery_task(bigint,text) from public,anon,authenticated;
grant execute on function public.delivery_task(bigint,text) to service_role;

create function public.delivery_immutable() returns trigger language plpgsql set search_path=public as $$
begin
 if (to_jsonb(old)-array['status','revision','technical_at','business_at','rejected_by','rejected_role','rejected_at','technical_channel','technical_message','business_channel','business_message','channel_message','publication_run'])
 is distinct from
 (to_jsonb(new)-array['status','revision','technical_at','business_at','rejected_by','rejected_role','rejected_at','technical_channel','technical_message','business_channel','business_message','channel_message','publication_run'])
 then raise exception 'Frozen candidate cannot change'; end if;
 if (old.technical_at is not null and new.technical_at is distinct from old.technical_at)
 or (old.business_at is not null and new.business_at is distinct from old.business_at)
 or (old.publication_run is not null and new.publication_run is distinct from old.publication_run)
 then raise exception 'Decision or publication identity cannot change'; end if;
 return new;
end $$;
create trigger delivery_immutable before update on public.delivery_control
for each row execute function public.delivery_immutable();
revoke all on function public.delivery_immutable() from public,anon,authenticated;

create function public.delivery_cancel(p_id text) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare c delivery_control;
begin
 select * into strict c from delivery_control where id=p_id for update;
 if c.status='cancelled' then return to_jsonb(c); end if;
 if c.status not in ('pending','approved') or exists(select 1 from delivery_outbox where candidate_id=p_id and kind='dispatch' and state<>'pending')
 then raise exception 'Cannot cancel after dispatch starts'; end if;
 update delivery_control set status='cancelled',revision=revision+1 where id=p_id returning * into c;
 update delivery_outbox set state='done',receipt='cancelled-before-dispatch',completed_at=clock_timestamp() where candidate_id=p_id and kind='dispatch' and state='pending';
 perform delivery_enqueue(p_id);
 return to_jsonb(c);
end $$;
revoke all on function public.delivery_cancel(text) from public,anon,authenticated;
grant execute on function public.delivery_cancel(text) to service_role;

-- Keep only operational work after terminal evidence is confirmed and observed for 7 days.
-- The control tombstone remains, so old signed messages cannot create a new evaluation.
create function public.delivery_compact() returns integer
language plpgsql security invoker set search_path=public as $$
declare removed integer;
begin
 delete from delivery_outbox o using delivery_control c
 where o.candidate_id=c.id and c.status in ('published','rejected','cancelled')
 and not exists(select 1 from delivery_outbox q where q.candidate_id=c.id and
    (q.state<>'done' or q.completed_at is null or q.completed_at>now()-interval '7 days'))
 and exists(select 1 from delivery_outbox h where h.candidate_id=c.id and h.kind='history'
    and h.revision=c.revision and h.state='done' and h.receipt ~ '^[a-f0-9]{40}$');
 get diagnostics removed=row_count;
 return removed;
end $$;
revoke all on function public.delivery_compact() from public,anon,authenticated;
grant execute on function public.delivery_compact() to service_role;
grant delete on public.delivery_outbox to service_role;
