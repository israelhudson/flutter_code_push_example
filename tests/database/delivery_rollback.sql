-- Dedicated POC only. All synthetic rows roll back; no external effects.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
set local role service_role;
do $$
declare
 c jsonb; r jsonb; denied boolean; id1 text := 'delivery-'||repeat('1',32); id2 text := 'delivery-'||repeat('2',32);
begin
 if exists(select 1 from delivery_control) then raise exception 'Requires empty v2 controls'; end if;
 assert not has_table_privilege('anon','public.delivery_control','SELECT');
 assert not has_table_privilege('authenticated','public.delivery_outbox','INSERT');
 assert not has_function_privilege('anon','public.delivery_register(jsonb)','EXECUTE');
 assert (select relrowsecurity from pg_class where oid='public.delivery_control'::regclass);
 assert (select relrowsecurity from pg_class where oid='public.delivery_outbox'::regclass);
 c := jsonb_build_object('id',id1,'repository','israelhudson/flutter_code_push_example','version','99.0.0','rc_number',1,'rc_tag','poc-v99.0.0-rc.1','source_sha',repeat('a',40),'manifest_commit',repeat('b',40),'manifest_digest',repeat('c',64),'team_id','T09CYB7AS77','channel_id','C0C8DUJB52L','technical_user','UTECH','business_user','UBIZ','solo',false,'scope','github_test');
 perform delivery_register(c);
 update delivery_control set technical_channel='DTECH',technical_message='100.1',business_channel='DBIZ',business_message='100.2' where id=id1;
 denied:=false;
 begin perform delivery_decide(id1,'technical','accept','UBIZ','T09CYB7AS77','DTECH','100.1'); exception when others then denied:=true; end;
 assert denied, 'wrong reviewer must fail';
 r:=delivery_decide(id1,'technical','accept','UTECH','T09CYB7AS77','DTECH','100.1');
 assert r->>'status'='pending';
 r:=delivery_decide(id1,'technical','accept','UTECH','T09CYB7AS77','DTECH','100.1');
 assert (r->>'revision')::int=1, 'duplicate acceptance';
 denied:=false;
 begin perform delivery_publish(id1,'100'); exception when others then denied:=true; end;
 assert denied, 'one approval cannot publish';
 r:=delivery_decide(id1,'business','reject','UBIZ','T09CYB7AS77','DBIZ','100.2');
 assert r->>'status'='rejected';
 c:=c||jsonb_build_object('id',id2,'rc_number',2,'rc_tag','poc-v99.0.0-rc.2','previous_id',id1);
 r:=delivery_register(c);
 assert r->>'technical_at' is null and r->>'business_at' is null, 'RC2 resets votes';
 update delivery_control set technical_channel='DTECH',technical_message='200.1',business_channel='DBIZ',business_message='200.2' where id=id2;
 perform delivery_decide(id2,'business','accept','UBIZ','T09CYB7AS77','DBIZ','200.2');
 r:=delivery_decide(id2,'technical','accept','UTECH','T09CYB7AS77','DTECH','200.1');
 assert r->>'status'='approved';
 denied:=false;
 begin perform delivery_publish(id2,'100'); exception when others then denied:=true; end;
 assert denied, 'history gate';
 -- Synthetic evidence receipt, not proof of a real GitHub publication.
 update delivery_outbox set state='done',receipt=repeat('f',40),completed_at=now() where kind='history';
 r:=delivery_publish(id2,'100'); assert r->>'status'='publishing';
 denied:=false;
 begin perform delivery_publish(id2,'101'); exception when others then denied:=true; end;
 assert denied, 'publication owner';
 update delivery_outbox set state='done',receipt=repeat('f',40),completed_at=now() where kind='history';
 r:=delivery_publish(id2,'100',true); assert r->>'status'='published';
 update delivery_outbox set state='done',receipt=repeat('f',40),completed_at=now() where kind='history';
 r:=delivery_publish(id2,'100',true); assert r->>'status'='published', 'idempotency';
 update delivery_outbox set state='working',lease='old',leased_at=now()-interval '6 minutes' where kind='technical';
 perform delivery_take('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
 assert exists(select 1 from delivery_outbox where kind='technical' and state='uncertain');
 assert delivery_compact()=0, 'pending effects must survive';
end $$;
rollback;
select 'rollback_scenarios_passed' as result,(select count(*) from public.delivery_control) as controls,(select count(*) from public.delivery_outbox) as outbox;
