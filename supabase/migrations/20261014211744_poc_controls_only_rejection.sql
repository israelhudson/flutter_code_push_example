-- Explicit controls-only exercise and reason-free rejection in the dedicated POC.
-- Existing frozen reports keep full preview verification by default.
create or replace function public.poc_register(p_report text,p_digest text,p_creator text,p_scope text default 'none')
returns jsonb language plpgsql security invoker set search_path='' as $$
declare cfg public.poc_config%rowtype; r jsonb:=p_report::jsonb; c public.poc_candidates%rowtype;
 prior public.poc_candidates%rowtype; creator text; expected integer;
begin
 select * into cfg from public.poc_config where flow='flutter-code-push' for update;
 if not cfg.enabled or p_creator is distinct from cfg.operator_github then raise exception 'disabled_or_operator'; end if;
 if encode(sha256(convert_to(p_report,'UTF8')),'hex') is distinct from p_digest
 or r->>'repository' is distinct from cfg.repository or r->>'source_sha' !~ '^[a-f0-9]{40}$'
 or coalesce(r->>'validation_mode','full') not in ('full','controls_only')
 or (coalesce(r->>'validation_mode','full')='full' and (
  r->>'preview_url' is distinct from 'https://israelhudson.github.io/flutter_code_push_example/snapshots/'||(r->>'source_sha')||'/'
  or r->>'preview_sha' is distinct from r->>'source_sha'
  or coalesce(r->>'web_content_sha256','') !~ '^[a-f0-9]{64}$'
  or coalesce(r->>'snapshot_manifest_sha256','') !~ '^[a-f0-9]{64}$'))
 or (r->>'validation_mode'='controls_only' and (
  r->'preview_performed' is distinct from 'false'::jsonb
  or r->'distribution_performed' is distinct from 'false'::jsonb
  or r->'preview_url' is distinct from 'null'::jsonb
  or r->'preview_sha' is distinct from 'null'::jsonb
  or r->'web_content_sha256' is distinct from 'null'::jsonb
  or r->'snapshot_manifest_sha256' is distinct from 'null'::jsonb
  or r#>'{platforms,android,base_release_version}' is distinct from 'null'::jsonb
  or r#>'{platforms,android,effective_patch}' is distinct from 'null'::jsonb
  or r#>'{platforms,ios,base_release_version}' is distinct from 'null'::jsonb
  or r#>'{platforms,ios,effective_patch}' is distinct from 'null'::jsonb)) or coalesce(r->>'run_url','') !~ '^https://github.com/israelhudson/flutter_code_push_example/actions/runs/[0-9]+$'
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

create or replace function public.poc_action(p_id text,p_action text,p_user text,p_team text,p_channel text,p_ts text,p_reason text default null,p_token text default null)
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
 elsif p_action='reject' then
  update public.poc_candidates set status='adjustment_requested',revision=revision+1,
   adjustment_reason=null,adjustment_author=p_user,adjustment_at=now()
  where id=c.id returning * into c;
  update public.poc_adjustment_tokens set consumed=true where candidate_id=c.id and not consumed;
  changed:=true;
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

revoke all on function public.poc_register(text,text,text,text) from public,anon,authenticated;
revoke all on function public.poc_action(text,text,text,text,text,text,text,text) from public,anon,authenticated;
grant execute on function public.poc_register(text,text,text,text) to service_role;
grant execute on function public.poc_action(text,text,text,text,text,text,text,text) to service_role;
