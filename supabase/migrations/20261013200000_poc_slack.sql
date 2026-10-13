-- Independent project only. No lab_* table, shared function or Mobile policy is changed.
create table public.poc_user_directory (
 github_login text primary key,
 github_id bigint not null unique,
 slack_user_id text not null unique check(slack_user_id ~ '^U[A-Z0-9]+$'),
 display_name text not null,
 verified_at timestamptz not null
);
insert into public.poc_user_directory values
 ('israelhudson',18661493,'U0BMFQKC001','Israel',now());
create table public.poc_config (
 flow text primary key check(flow='flutter-code-push'),
 repository text not null check(repository='israelhudson/flutter_code_push_example'),
 team_id text not null check(team_id='T09CYB7AS77'),
 channel_id text not null check(channel_id='C0C8DUJB52L'),
 enabled boolean not null default false,
 publication_enabled boolean not null default false,
 mode text not null check(mode in ('solo_test','two_reviewers')),
 operator_github text not null references public.poc_user_directory(github_login),
 technical_reviewer text not null references public.poc_user_directory(slack_user_id),
 business_reviewer text not null references public.poc_user_directory(slack_user_id),
 check(mode='solo_test' or technical_reviewer<>business_reviewer),
 check(mode<>'solo_test' or (technical_reviewer='U0BMFQKC001' and business_reviewer='U0BMFQKC001'))
);
insert into public.poc_config values
 ('flutter-code-push','israelhudson/flutter_code_push_example','T09CYB7AS77','C0C8DUJB52L',false,false,'solo_test','israelhudson','U0BMFQKC001','U0BMFQKC001');
create table public.poc_candidates (
 id text primary key check(id ~ '^poc-[a-f0-9]{32}$'),
 flow text not null references public.poc_config(flow),
 version text not null check(version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'),
 rc_number integer not null check(rc_number>0),
 rc_tag text not null unique,
 source_sha text not null check(source_sha ~ '^[a-f0-9]{40}$'),
 report_text text not null,
 report_digest text not null check(report_digest ~ '^[a-f0-9]{64}$'),
 creator_github text not null references public.poc_user_directory(github_login),
 creator_slack text not null references public.poc_user_directory(slack_user_id),
 technical_reviewer text not null references public.poc_user_directory(slack_user_id),
 business_reviewer text not null references public.poc_user_directory(slack_user_id),
 mode text not null check(mode in ('solo_test','two_reviewers')),
 team_id text not null check(team_id='T09CYB7AS77'),
 channel_id text not null check(channel_id='C0C8DUJB52L'),
 is_lab boolean not null check(is_lab),
 publication_scope text not null check(publication_scope in ('none','github_test')),
 previous_candidate text references public.poc_candidates(id),
 created_at timestamptz not null default now(),
 expires_at timestamptz not null default now()+interval '36 hours',
 status text not null default 'pending' check(status in ('pending','approved','adjustment_requested','expired','publishing','published','cancelled')),
 message_ts text check(message_ts ~ '^[0-9]+\.[0-9]+$'),
 revision integer not null default 0,
 adjustment_reason text,
 adjustment_author text,
 adjustment_at timestamptz,
 unique(version,rc_number),
 check(rc_tag='poc-v'||version||'-rc.'||rc_number::text),
 check(mode='solo_test' or technical_reviewer<>business_reviewer)
);
create unique index poc_one_active on public.poc_candidates(flow)
 where status in ('pending','approved','publishing');
create table public.poc_approvals (
 candidate_id text not null references public.poc_candidates(id),
 role text not null check(role in ('technical','business')),
 slack_user_id text not null,
 approved_at timestamptz not null default now(),
 mode text not null,
 primary key(candidate_id,role)
);
create table public.poc_private_notices (
 candidate_id text not null references public.poc_candidates(id),
 event text not null,
 recipient text not null,
 state text not null default 'reserved' check(state in ('reserved','sent','skipped','uncertain')),
 slack_channel text,
 slack_ts text,
 delivery_receipt jsonb,
 created_at timestamptz not null default now(),
 finished_at timestamptz,
 primary key(candidate_id,event,recipient)
);
create table public.poc_adjustment_tokens (
 token text primary key,
 candidate_id text not null references public.poc_candidates(id),
 slack_user_id text not null,
 message_ts text not null,
 created_at timestamptz not null default now(),
 expires_at timestamptz not null default now()+interval '5 minutes',
 consumed boolean not null default false
);
create table public.poc_publications (
 candidate_id text primary key references public.poc_candidates(id),
 intent_id text not null,
 run_id text not null,
 state text not null check(state in ('publishing','published')),
 created_at timestamptz not null default now(),
 receipt jsonb,
 finished_at timestamptz
);
create table public.poc_events (
 id bigint generated always as identity primary key,
 candidate_id text not null references public.poc_candidates(id),
 event text not null,
 actor text,
 at timestamptz not null default now(),
 detail jsonb not null default '{}'
);

create function public.poc_immutable() returns trigger language plpgsql set search_path='' as $$
begin
 if (to_jsonb(new)-array['status','message_ts','revision','adjustment_reason','adjustment_author','adjustment_at'])
 is distinct from (to_jsonb(old)-array['status','message_ts','revision','adjustment_reason','adjustment_author','adjustment_at']) then
  raise exception 'immutable_candidate';
 end if;
 return new;
end; $$;
create trigger poc_candidate_immutable before update on public.poc_candidates
 for each row execute function public.poc_immutable();

create function public.poc_register(p_report text,p_digest text,p_creator text,p_scope text default 'none')
returns jsonb language plpgsql security invoker set search_path='' as $$
declare cfg public.poc_config%rowtype; r jsonb:=p_report::jsonb; c public.poc_candidates%rowtype;
 prior public.poc_candidates%rowtype; creator text; expected integer;
begin
 select * into cfg from public.poc_config where flow='flutter-code-push' for update;
 if not cfg.enabled or p_creator is distinct from cfg.operator_github then raise exception 'disabled_or_operator'; end if;
 if encode(sha256(convert_to(p_report,'UTF8')),'hex') is distinct from p_digest
 or r->>'repository' is distinct from cfg.repository or r->>'source_sha' !~ '^[a-f0-9]{40}$'
 or r->>'preview_url' is distinct from 'https://israelhudson.github.io/flutter_code_push_example/snapshots/'||(r->>'source_sha')||'/'
 or r->>'preview_sha' is distinct from r->>'source_sha'
 or coalesce(r->>'web_content_sha256','') !~ '^[a-f0-9]{64}$'
 or coalesce(r->>'snapshot_manifest_sha256','') !~ '^[a-f0-9]{64}$'
 or coalesce(r->>'run_url','') !~ '^https://github.com/israelhudson/flutter_code_push_example/actions/runs/[0-9]+$'
 or p_scope not in ('none','github_test') or p_scope is null or r->>'publication_scope' is distinct from p_scope
 or (p_scope='github_test' and not cfg.publication_enabled) then raise exception 'invalid_frozen_report'; end if;
 select * into c from public.poc_candidates where rc_tag=r->>'rc_tag';
 if found then
  if c.report_digest<>p_digest or c.creator_github<>p_creator or c.publication_scope<>p_scope then raise exception 'immutable_retry'; end if;
  return to_jsonb(c);
 end if;
 update public.poc_candidates set status='expired',revision=revision+1
 where flow=cfg.flow and status in ('pending','approved') and expires_at<=now();
 if exists(select 1 from public.poc_candidates where flow=cfg.flow and status in ('pending','approved','publishing')) then raise exception 'one_candidate_at_a_time'; end if;
 select * into prior from public.poc_candidates where version=r->>'version' order by rc_number desc limit 1;
 expected:=coalesce(prior.rc_number,0)+1;
 if exists(select 1 from public.poc_candidates where status='published'
 and string_to_array(version,'.')::numeric[]>=string_to_array(r->>'version','.')::numeric[]) then raise exception 'version_already_published_or_older'; end if;
 if (r->>'rc_number')::integer<>expected or r->>'rc_tag' is distinct from 'poc-v'||(r->>'version')||'-rc.'||expected::text
 or (expected>1 and (prior.status<>'adjustment_requested' or r->>'previous_candidate' is distinct from prior.id))
 or (expected=1 and r->>'previous_candidate' is not null) then raise exception 'invalid_rc_sequence'; end if;
 if exists(select 1 from public.poc_candidates where version=r->>'version' and status='published') then raise exception 'version_already_published'; end if;
 select slack_user_id into creator from public.poc_user_directory where github_login=p_creator;
 insert into public.poc_candidates(id,flow,version,rc_number,rc_tag,source_sha,report_text,report_digest,creator_github,creator_slack,
 technical_reviewer,business_reviewer,mode,team_id,channel_id,is_lab,publication_scope,previous_candidate)
 values(r->>'id',cfg.flow,r->>'version',expected,r->>'rc_tag',r->>'source_sha',p_report,p_digest,p_creator,creator,
 cfg.technical_reviewer,cfg.business_reviewer,cfg.mode,cfg.team_id,cfg.channel_id,true,p_scope,r->>'previous_candidate') returning * into c;
 insert into public.poc_events(candidate_id,event,actor,detail) values(c.id,'registered',p_creator,jsonb_build_object('digest',p_digest,'mode',cfg.mode));
 return to_jsonb(c);
end; $$;

create function public.poc_action(p_id text,p_action text,p_user text,p_team text,p_channel text,p_ts text,p_reason text default null,p_token text default null)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare c public.poc_candidates%rowtype; n integer; changed boolean:=false; expected_user text; tok public.poc_adjustment_tokens%rowtype;
begin
 if not (select enabled from public.poc_config where flow='flutter-code-push') then raise exception 'disabled'; end if;
 select * into c from public.poc_candidates where id=p_id for update;
 if not found or p_team is distinct from c.team_id or p_channel is distinct from c.channel_id or c.message_ts is null
 or p_ts is distinct from c.message_ts or p_user is null or p_user not in(c.technical_reviewer,c.business_reviewer)
 then raise exception 'unauthorized_context'; end if;
 if c.expires_at<=now() or c.status not in('pending','approved') then raise exception 'closed_candidate'; end if;
 if p_action in('technical','business') then
  expected_user:=case when p_action='technical' then c.technical_reviewer else c.business_reviewer end;
  if p_user<>expected_user then raise exception 'unauthorized_role'; end if;
  insert into public.poc_approvals(candidate_id,role,slack_user_id,mode) values(c.id,p_action,p_user,c.mode)
  on conflict(candidate_id,role) do nothing;
  changed:=found;
  select count(*) into n from public.poc_approvals where candidate_id=c.id;
  update public.poc_candidates set status=case when n=2 then 'approved' else 'pending' end,revision=revision+case when changed then 1 else 0 end
  where id=c.id returning * into c;
 elsif p_action='open_adjustment' then
  if coalesce(p_token,'') !~ '^[a-f0-9]{64}$' then raise exception 'invalid_token'; end if;
  insert into public.poc_adjustment_tokens(token,candidate_id,slack_user_id,message_ts) values(p_token,c.id,p_user,c.message_ts);
 elsif p_action in('adjust','cancel_adjustment') then
  select * into tok from public.poc_adjustment_tokens where token=p_token for update;
  if not found or tok.candidate_id<>c.id or tok.slack_user_id<>p_user or tok.message_ts<>p_ts or tok.consumed or tok.expires_at<=now()
  then raise exception 'invalid_modal'; end if;
  update public.poc_adjustment_tokens set consumed=true where token=p_token;
  if p_action='adjust' then
   if p_reason is null or length(trim(p_reason))<3 or length(p_reason)>1000 then raise exception 'invalid_reason'; end if;
   update public.poc_candidates set status='adjustment_requested',revision=revision+1,
    adjustment_reason=trim(p_reason),adjustment_author=p_user,adjustment_at=now() where id=c.id returning * into c;
   changed:=true;
  end if;
 else raise exception 'invalid_action'; end if;
 if changed then insert into public.poc_events(candidate_id,event,actor,detail) values(c.id,p_action,p_user,jsonb_build_object('mode',c.mode)); end if;
 return to_jsonb(c)||jsonb_build_object('approvals',coalesce((select jsonb_agg(to_jsonb(a)) from public.poc_approvals a where candidate_id=c.id),'[]'::jsonb),'changed',changed);
end; $$;

create function public.poc_state(p_id text) returns jsonb language sql security invoker set search_path='' as $$
 select to_jsonb(c)||jsonb_build_object('approvals',coalesce((select jsonb_agg(to_jsonb(a)) from public.poc_approvals a where a.candidate_id=c.id),'[]'::jsonb))
 from public.poc_candidates c where c.id=p_id;
$$;
create function public.poc_notice(p_id text,p_event text,p_claim boolean default true) returns jsonb language plpgsql security invoker set search_path='' as $$
declare c public.poc_candidates%rowtype; n integer; target_role text; recipient text;
begin
 select * into c from public.poc_candidates where id=p_id for update;
 if not found or not (select enabled from public.poc_config where flow=c.flow) then raise exception 'disabled_or_unknown'; end if;
 select count(*) into n from public.poc_approvals where candidate_id=c.id;
 if p_event='card' and c.message_ts is null and c.status='pending' and c.expires_at>now() then recipient:=c.channel_id;
 elsif p_event like 'review_pending:%' and n=1 and c.status='pending' and c.expires_at>now() then
  target_role:=split_part(p_event,':',2);
  if target_role not in('technical','business') or exists(select 1 from public.poc_approvals a where a.candidate_id=c.id and a.role=target_role)
  then return jsonb_build_object('send',false); end if;
  recipient:=case when target_role='technical' then c.technical_reviewer else c.business_reviewer end;
 elsif p_event='approved' and n=2 and c.status in('approved','publishing','published') and c.expires_at>now() then recipient:=c.creator_slack;
 elsif p_event='dispatch' and n=2 and c.status='approved' and c.publication_scope='github_test'
 and (select publication_enabled from public.poc_config where flow=c.flow) and c.expires_at>now()
 and not exists(select 1 from public.poc_adjustment_tokens where candidate_id=c.id and not consumed and expires_at>now()) then recipient:=c.creator_github;
 elsif p_event='published' and c.status='published' then recipient:=c.channel_id;
 else return jsonb_build_object('send',false); end if;
 if p_claim then
  insert into public.poc_private_notices(candidate_id,event,recipient) values(c.id,p_event,recipient) on conflict do nothing;
  if not found then return jsonb_build_object('send',false); end if;
 end if;
 return jsonb_build_object('send',true,'recipient',recipient,'event',p_event,'pending_role',target_role);
end; $$;

create function public.poc_finish_notice(p_id text,p_event text,p_recipient text,p_state text,p_channel text default null,p_ts text default null,p_receipt jsonb default null)
returns void language plpgsql security invoker set search_path='' as $$
begin
 if p_state not in('sent','uncertain','skipped') or (p_state='sent' and p_event<>'dispatch' and (p_channel is null or p_ts is null))
 or (p_state='sent' and p_event='dispatch' and p_receipt->>'acknowledged' is distinct from 'true') then raise exception 'invalid_receipt'; end if;
 update public.poc_private_notices set state=p_state,slack_channel=p_channel,slack_ts=p_ts,delivery_receipt=p_receipt,finished_at=now()
 where candidate_id=p_id and event=p_event and recipient=p_recipient and state='reserved';
 if not found then raise exception 'notice_not_reserved'; end if;
 if p_event='card' and p_state='sent' then
  if p_channel<>'C0C8DUJB52L' or p_ts !~ '^[0-9]+\.[0-9]+$' then raise exception 'invalid_card_receipt'; end if;
  update public.poc_candidates set message_ts=p_ts where id=p_id and message_ts is null;
 end if;
end; $$;

create function public.poc_publish(p_id text,p_operation text,p_run text,p_receipt jsonb default null) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare c public.poc_candidates%rowtype; pub public.poc_publications%rowtype;
begin
 select * into c from public.poc_candidates where id=p_id for update;
 if not found then raise exception 'unknown_candidate'; end if;
 select * into pub from public.poc_publications where candidate_id=c.id;
 if pub.state='published' then return jsonb_build_object('receipt',pub.receipt,'already_published',true); end if;
 if not (select enabled and publication_enabled from public.poc_config where flow=c.flow)
 or c.publication_scope<>'github_test' or c.expires_at<=now() or c.status not in('approved','publishing')
 or (select count(*) from public.poc_approvals where candidate_id=c.id)<>2
 or exists(select 1 from public.poc_adjustment_tokens where candidate_id=c.id and not consumed and expires_at>now())
 then raise exception 'publication_not_authorized'; end if;
 if p_operation='claim' then
  if pub.run_id is not null and pub.run_id<>p_run then raise exception 'original_run_required'; end if;
  insert into public.poc_publications(candidate_id,intent_id,run_id,state) values(c.id,c.id||':'||p_run,p_run,'publishing') on conflict do nothing;
  update public.poc_candidates set status='publishing',revision=revision+1 where id=c.id and status='approved';
 elsif p_operation='complete' then
  if pub.run_id is distinct from p_run or p_receipt->>'source_sha' is distinct from c.source_sha
  or p_receipt->>'report_digest' is distinct from c.report_digest or p_receipt->>'tag' is distinct from 'poc-v'||c.version
  or p_receipt->>'release_url' is distinct from 'https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v'||c.version
  or coalesce((p_receipt->>'release_id')::bigint,0)<=0 or p_receipt->>'distribution_performed' is distinct from 'false'
  then raise exception 'invalid_publication_receipt'; end if;
  update public.poc_publications set state='published',receipt=p_receipt,finished_at=now() where candidate_id=c.id;
  update public.poc_candidates set status='published',revision=revision+1 where id=c.id;
  insert into public.poc_events(candidate_id,event,detail) values(c.id,'published',p_receipt);
 else raise exception 'invalid_publication_operation'; end if;
 return jsonb_build_object('candidate',public.poc_state(c.id),'publication',(select to_jsonb(p) from public.poc_publications p where candidate_id=c.id));
end; $$;

-- Every table is private to the service. No client-facing policy or secret in Flutter.
do $$ declare t text; begin
 foreach t in array array['poc_user_directory','poc_config','poc_candidates','poc_approvals','poc_private_notices','poc_adjustment_tokens','poc_publications','poc_events'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated',t);
  execute format('grant select,insert,update on public.%I to service_role',t);
 end loop;
end $$;
grant usage on sequence public.poc_events_id_seq to service_role;
revoke update on public.poc_approvals,public.poc_events from service_role;
do $$ declare f record; begin
 for f in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and left(p.proname,4)='poc_' loop
  execute format('revoke all on function %s from public,anon,authenticated',f.sig);
  execute format('grant execute on function %s to service_role',f.sig);
 end loop;
end $$;
