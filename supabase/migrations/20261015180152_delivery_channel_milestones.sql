-- Channel milestones use the existing outbox, one external effect per task.
-- No historical row/event is rewritten or backfilled by this migration.
alter table public.delivery_outbox drop constraint delivery_outbox_kind_check;
alter table public.delivery_outbox add constraint delivery_outbox_kind_check
 check (kind in ('history','channel','technical','business','dispatch','notice'));
create unique index delivery_notice_milestone
 on public.delivery_outbox(candidate_id,(event->>'status')) where kind='notice';
-- This tombstone survives outbox compaction: only the digest already announced,
-- never a second receipt/report or a new history table. Historical rows stay null.
alter table public.delivery_control add column android_staging_notice_digest text
 check (android_staging_notice_digest ~ '^[a-f0-9]{64}$');

create or replace function public.delivery_immutable() returns trigger
language plpgsql set search_path=public as $$
begin
 if (to_jsonb(old)-array['status','revision','technical_at','business_at','rejected_by','rejected_role','rejected_at','technical_channel','technical_message','business_channel','business_message','channel_message','publication_run','android_staging_notice_digest'])
 is distinct from
 (to_jsonb(new)-array['status','revision','technical_at','business_at','rejected_by','rejected_role','rejected_at','technical_channel','technical_message','business_channel','business_message','channel_message','publication_run','android_staging_notice_digest'])
 then raise exception 'Frozen candidate cannot change'; end if;
 if (old.technical_at is not null and new.technical_at is distinct from old.technical_at)
 or (old.business_at is not null and new.business_at is distinct from old.business_at)
 or (old.publication_run is not null and new.publication_run is distinct from old.publication_run)
 or (old.android_staging_notice_digest is not null and new.android_staging_notice_digest is distinct from old.android_staging_notice_digest)
 or (new.android_staging_notice_digest is not null and (old.status<>'published' or new.status<>'published'))
 then raise exception 'Decision or publication identity cannot change'; end if;
 return new;
end $$;

create or replace function public.delivery_enqueue(p_id text) returns void
language plpgsql security invoker set search_path=public as $$
declare c delivery_control; evidence jsonb; new_history bigint; previous_status text;
begin
 select * into strict c from delivery_control where id=p_id;
 select event->>'status' into previous_status from delivery_outbox
 where candidate_id=c.id and kind='history' and revision<c.revision order by revision desc limit 1;
 -- Preserve the exact existing journal event shape, including legacy candidates.
 evidence := jsonb_build_object(
  'candidate',c.id,'revision',c.revision,'status',c.status,'source_sha',c.source_sha,
  'technical_at',c.technical_at,'business_at',c.business_at,'rejected_role',c.rejected_role,
  'rejected_at',c.rejected_at,'solo',c.solo,'publication_run',c.publication_run);
 if c.reviewer_snapshot is not null then
  evidence := evidence || jsonb_build_object('reviewers',c.reviewer_snapshot);
 end if;
 insert into delivery_outbox(candidate_id,kind,revision,event)
 values(c.id,'history',c.revision,evidence) on conflict do nothing returning id into new_history;
 insert into delivery_outbox(candidate_id,kind,revision)
 select c.id,k,c.revision from unnest(array['channel','technical','business']) k
 on conflict do nothing;
 -- Only a newly recorded transition may create a notice. A repeated enqueue
 -- cannot retroactively announce a milestone from before this migration.
 if new_history is not null and c.status is distinct from previous_status
  and c.status in ('publishing','published','rejected','cancelled') then
  insert into delivery_outbox(candidate_id,kind,revision,event)
  values(c.id,'notice',c.revision,jsonb_build_object(
   'schema','delivery-channel-notice-v1','candidate',c.id,'revision',c.revision,
   'status',c.status,'source_sha',c.source_sha,'version',c.version,
   'rc_number',c.rc_number,'rc_tag',c.rc_tag,'publication_run',c.publication_run))
  on conflict do nothing;
 end if;
end $$;

-- Refresh the presentation after attaching verified platform receipts. It cannot
-- publish, change decisions, or rewrite the immutable history already in GitHub.
create function public.delivery_refresh(p_id text,p_mobile jsonb default null) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare c delivery_control; evidence jsonb; announce_mobile boolean := false;
begin
 select * into strict c from delivery_control where id=p_id for update;
 if c.status<>'published' then raise exception 'Published candidate required'; end if;
 -- Server-only input extracted from a hash-verified Release asset by the Edge
 -- Function; the HTTP caller never supplies this authorization/evidence object.
 if p_mobile is not null then
  if jsonb_typeof(p_mobile)<>'object' or octet_length(p_mobile::text)>1024
   or (p_mobile->>'schema') is distinct from 'delivery-android-staging-notice-v1'
   or (p_mobile->>'asset_digest') is null or (p_mobile->>'asset_digest') !~ '^[a-f0-9]{64}$'
   or (p_mobile->>'release_version') is null
   or (p_mobile->>'release_version') !~ '^[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+(\.[0-9]+)*$'
   or jsonb_typeof(p_mobile->'patch_number') is distinct from 'number'
   or (p_mobile->>'patch_number') !~ '^[1-9][0-9]*$'
   or (p_mobile->>'patch_number')::numeric>2147483647
  then raise exception 'Verified Android staging receipt required'; end if;
  if c.android_staging_notice_digest is not null
   and c.android_staging_notice_digest is distinct from p_mobile->>'asset_digest'
  then raise exception 'Android staging milestone already frozen'; end if;
  announce_mobile := c.android_staging_notice_digest is null;
 end if;
 update delivery_control set revision=revision+1,
  android_staging_notice_digest=coalesce(android_staging_notice_digest,p_mobile->>'asset_digest')
 where id=p_id returning * into c;
 -- Presentation refresh enqueues only history/card work. Explicitly avoid the
 -- milestone path even if old operational notices were compacted after 7 days.
 evidence := jsonb_build_object(
  'candidate',c.id,'revision',c.revision,'status',c.status,'source_sha',c.source_sha,
  'technical_at',c.technical_at,'business_at',c.business_at,'rejected_role',c.rejected_role,
  'rejected_at',c.rejected_at,'solo',c.solo,'publication_run',c.publication_run);
 if c.reviewer_snapshot is not null then
  evidence := evidence || jsonb_build_object('reviewers',c.reviewer_snapshot);
 end if;
 if p_mobile is not null then
  evidence := evidence || jsonb_build_object('android_staging',p_mobile);
 end if;
 insert into delivery_outbox(candidate_id,kind,revision,event)
 values(c.id,'history',c.revision,evidence);
 insert into delivery_outbox(candidate_id,kind,revision)
 select c.id,k,c.revision from unnest(array['channel','technical','business']) k;
 if announce_mobile then
  insert into delivery_outbox(candidate_id,kind,revision,event)
  values(c.id,'notice',c.revision,(p_mobile-'schema')||jsonb_build_object(
   'schema','delivery-channel-notice-v1','candidate',c.id,'revision',c.revision,
   'status','android_staging','source_sha',c.source_sha,'version',c.version,
   'rc_number',c.rc_number,'rc_tag',c.rc_tag,'publication_run',c.publication_run))
  on conflict do nothing;
 end if;
 return to_jsonb(c);
end $$;

create or replace function public.delivery_take(p_lease text) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare o delivery_outbox;
begin
 if p_lease is null or p_lease !~ '^[a-f0-9-]{36}$' then raise exception 'Invalid lease'; end if;
 -- A reservation is safe to retry; an external effect of unknown outcome is not.
 update delivery_outbox
 set state=case when state='working' or kind='history' then 'pending' else 'uncertain' end,
     lease=null,leased_at=null
 where state in ('working','effect') and leased_at < now()-interval '5 minutes';
 select q.* into o from delivery_outbox q where q.state='pending'
 and not exists(select 1 from delivery_outbox older where older.candidate_id=q.candidate_id
  and older.kind=q.kind and older.id<q.id and older.state<>'done')
 and (q.kind not in ('dispatch','notice') or not exists(select 1 from delivery_outbox h
  where h.candidate_id=q.candidate_id and h.kind='history' and h.revision<=q.revision and h.state<>'done'))
 -- Broadcast only after the canonical card has a confirmed ts and the channel
 -- updates through this revision have finished. The notice never replaces its ts.
 and (q.kind<>'notice' or (
  exists(select 1 from delivery_control c where c.id=q.candidate_id and c.channel_message is not null)
  and not exists(select 1 from delivery_outbox card where card.candidate_id=q.candidate_id
   and card.kind='channel' and card.revision<=q.revision and card.state<>'done')))
 order by q.id for update skip locked limit 1;
 if not found then return null; end if;
 perform 1 from delivery_control where id=o.candidate_id for update;
 update delivery_outbox set state='working',attempts=attempts+1,lease=p_lease,leased_at=now()
 where id=o.id returning * into o;
 return jsonb_build_object('task',to_jsonb(o),'candidate',
 (select to_jsonb(c) from delivery_control c where c.id=o.candidate_id));
end $$;

create or replace function public.delivery_finish(p_id bigint,p_lease text,p_receipt text,
 p_channel text default null,p_message text default null) returns void
language plpgsql security invoker set search_path=public as $$
declare o delivery_outbox; c delivery_control;
begin
 select * into strict o from delivery_outbox where id=p_id for update;
 if o.state='done' and o.receipt=p_receipt then return; end if;
 if o.state not in ('working','effect') or o.lease is distinct from p_lease or coalesce(length(p_receipt),0)=0
 or length(p_receipt)>512 then raise exception 'Invalid task receipt or lease'; end if;
 select * into strict c from delivery_control where id=o.candidate_id for update;
 if o.kind in ('channel','technical','business','notice') then
  if p_message is null or p_message !~ '^[0-9]+\.[0-9]+$'
   or p_channel is null or (o.kind in ('channel','notice') and p_channel<>c.channel_id)
   or (o.kind in ('technical','business') and p_channel !~ '^D[A-Z0-9]+$')
  then raise exception 'Invalid Slack receipt'; end if;
  if o.kind='notice' then
   if o.state<>'effect' or c.channel_message is null or p_message=c.channel_message
    or p_receipt is distinct from 'slack:'||p_channel||':'||p_message
   then raise exception 'Invalid notice receipt'; end if;
  elsif o.kind='channel' then update delivery_control set channel_message=p_message where id=c.id;
  elsif o.kind='technical' then update delivery_control set technical_message=p_message,technical_channel=p_channel where id=c.id;
  else update delivery_control set business_message=p_message,business_channel=p_channel where id=c.id; end if;
 end if;
 update delivery_outbox set state='done',receipt=p_receipt,lease=null,completed_at=clock_timestamp() where id=o.id;
end $$;

-- delivery_begin already makes every non-history effect single-use, and the
-- existing compactor waits for every kind before deleting operational receipts.
revoke all on function public.delivery_enqueue(text),public.delivery_take(text),
 public.delivery_finish(bigint,text,text,text,text),public.delivery_refresh(text,jsonb)
 from public,anon,authenticated;
grant execute on function public.delivery_enqueue(text),public.delivery_take(text),
 public.delivery_finish(bigint,text,text,text,text),public.delivery_refresh(text,jsonb) to service_role;
