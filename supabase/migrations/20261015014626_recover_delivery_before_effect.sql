-- A reserved task has not sent anything until delivery_begin commits `effect`.
-- Recover that safe window automatically; uncertain effects still require evidence.
create or replace function public.delivery_take(p_lease text) returns jsonb
language plpgsql security invoker set search_path = public as $$
declare o delivery_outbox;
begin
 if p_lease is null or p_lease !~ '^[a-f0-9-]{36}$' then raise exception 'Invalid lease'; end if;
 update delivery_outbox
 set state=case when state='working' or kind='history' then 'pending' else 'uncertain' end,
     lease=null,leased_at=null
 where state in ('working','effect') and leased_at < now()-interval '5 minutes';
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

create or replace function public.delivery_decide(p_id text,p_role text,p_action text,p_user text,
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
 -- Validate the original account, role and DM before acknowledging a retry.
 if p_action='reject' and c.status='rejected' and c.rejected_by=p_user and c.rejected_role=p_role
 then return to_jsonb(c); end if;
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

revoke all on function public.delivery_take(text),public.delivery_decide(text,text,text,text,text,text,text)
 from public,anon,authenticated;
grant execute on function public.delivery_take(text),public.delivery_decide(text,text,text,text,text,text,text)
 to service_role;
