-- Official delivery names for new versions. All existing rows/tags/events keep
-- their frozen namespace, including another RC of an existing legacy version.
do $$
declare tag_constraint text;
begin
 select conname into strict tag_constraint from pg_constraint
 where conrelid='public.delivery_control'::regclass and contype='c'
 and pg_get_constraintdef(oid) like '%rc_tag =%';
 execute format('alter table public.delivery_control drop constraint %I',tag_constraint);
end $$;
alter table public.delivery_control add constraint delivery_candidate_tag_identity
 check (rc_tag in ('v'||version||'-rc.'||rc_number,'poc-v'||version||'-rc.'||rc_number));

create function public.delivery_namespace() returns trigger
language plpgsql security invoker set search_path=public as $$
begin
 if exists(select 1 from delivery_control c where c.version=new.version
  and (c.rc_tag like 'poc-v%') is distinct from (new.rc_tag like 'poc-v%'))
 then raise exception 'Version namespace is frozen; keep the existing RC tag family'; end if;
 return new;
end $$;
create trigger delivery_namespace before insert on public.delivery_control
 for each row execute function public.delivery_namespace();
revoke all on function public.delivery_namespace() from public,anon,authenticated,service_role;
