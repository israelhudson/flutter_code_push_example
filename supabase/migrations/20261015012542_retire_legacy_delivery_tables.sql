-- Dedicated delivery project only. Apply after verified private backup + GitHub archive,
-- retired Edge routes and disabled legacy workflows. No CASCADE: unknown dependencies abort.
do $$ begin
 if exists(select 1 from public.poc_config where enabled or publication_enabled) then
  raise exception 'Disable legacy config before retirement'; end if;
 if exists(select 1 from public.poc_candidates where status not in ('published','adjustment_requested','rejected','cancelled')) then
  raise exception 'Legacy candidate still active'; end if;
 if exists(select 1 from public.poc_publications where state<>'published') then
  raise exception 'Legacy publication not reconciled'; end if;
 if exists(select 1 from public.poc_private_notices where state<>'sent') then
  raise exception 'Legacy notice not reconciled'; end if;
 if to_regclass('public.delivery_control') is null or to_regclass('public.delivery_outbox') is null then
  raise exception 'New schema missing'; end if;
end $$;
drop function public.poc_register(text,text,text,text);
drop function public.poc_action(text,text,text,text,text,text,text,text);
drop function public.poc_state(text);
drop function public.poc_notice(text,text,boolean);
drop function public.poc_finish_notice(text,text,text,text,text,text,jsonb);
drop function public.poc_publish(text,text,text,jsonb);
drop table public.poc_adjustment_tokens;
drop table public.poc_private_notices;
drop table public.poc_events;
drop table public.poc_publications;
drop table public.poc_approvals;
drop table public.poc_candidates;
drop function public.poc_immutable();
drop table public.poc_config;
drop table public.poc_user_directory;
