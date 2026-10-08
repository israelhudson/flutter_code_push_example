import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const workspaceDir = path.dirname(HERE);
const liveDir = path.dirname(workspaceDir);
const SKILL_DIR = '/Users/israelhudson/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations';
const RUNTIME_PYTHON = '/Users/israelhudson/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')).href);
const FONT = resolvePresentationFont();
const P = Presentation.create({ slideSize: { width: 1600, height: 900 } });
const C = { bg:'#F5F7FA', navy:'#12243A', muted:'#4A6076', green:'#087F71', red:'#AB3744', blue:'#165FCC', white:'#FFFFFF', line:'#CFD9E3' };
const sourceBase = 'https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/';
const run = 'https://github.com/israelhudson/flutter_code_push_example/actions/runs/37851607911';
const release = 'https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.5.0';
const preview = 'https://israelhudson.github.io/flutter_code_push_example/snapshots/b8763ec5adc5e24ce34f474a66a079b48a9ffa0f/';
const summary = JSON.parse(await fs.readFile(path.join(liveDir, 'MATRIZ-RESULTADOS.json'), 'utf8'));
let backport = { status:'PENDENTE', label:'PR de retorno à main em validação' };
try {
  const merged = JSON.parse(await fs.readFile(path.join(liveDir, 'backport-pr-merged.json'), 'utf8'));
  if (merged.state === 'MERGED' || merged.merged_at || merged.mergedAt || merged.merged === true) backport = {status:'PASS',label:'Correção também integrada à main por PR'};
} catch {}
const outline = [];
const notesCommon = '\n\nEscopo do ensaio: GitHub Release e tags reais. Nenhum app, patch Shorebird, loja ou TestFlight foi distribuído. As reviews foram operações automatizadas por Codex, autorizadas por Israel, usando as contas GitHub configuradas. Não comprovam revisão humana independente ou aceite de negócio. Evidências locais primárias: PASSO-A-PASSO-E-LICOES.md, MATRIZ-RESULTADOS.json e LIVE-SECURITY-AUDIT.md na pasta do ensaio. Os links da branch de estado ficam acessíveis após a preservação do pacote de evidências pelo executor.\n';

function text(slide, value, x, y, w, h, size=30, opts={}) {
  const box = slide.shapes.add({ geometry:'textbox', position:{left:x,top:y,width:w,height:h}, fill:'none', line:{fill:'none',width:0} });
  box.text = value;
  box.text.style = { fontSize:size, typeface:FONT, color:opts.color??C.navy, bold:opts.bold??false, alignment:opts.align??'left', verticalAlignment:'top', wrap:'square', autoFit:'none', insets:0 };
  if (opts.link) box.text.get(value).link = {uri:opts.link,isExternal:true};
  return box;
}
function slide(title, note, dark=false) {
  const s = P.slides.add(); s.background.fill=dark?C.navy:C.bg;
  text(s,title,88,62,1424,100,56,{bold:true,color:dark?C.white:C.navy});
  text(s,`${P.slides.items.length.toString().padStart(2,'0')}`,1445,844,67,28,20,{color:dark?'#B8CCD9':C.muted,align:'right'});
  s.speakerNotes.text = note+notesCommon;
  outline.push({slide:P.slides.items.length,title,note});
  return s;
}
function node(s,label,x,y,w,h,color=C.navy) {
  const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:C.white,line:{style:'solid',fill:color,width:2}});
  n.text=label; n.text.style={typeface:FONT,fontSize:30,bold:true,color,alignment:'center',verticalAlignment:'middle',insets:20,wrap:'square',autoFit:'none'};
  return n;
}
function connect(s,a,b,from='right',to='left',color=C.muted) {
  s.shapes.connect(a,b,{kind:from==='right'&&to==='left'?'straight':'elbow',fromSide:from,toSide:to,line:{fill:color,width:2,style:'solid'},tail:{type:'triangle',width:'med',length:'med'}});
}
function table(s,values,x,y,w,h,widths,size=27) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
  t.styleOptions={headerRow:true,bandedRows:false};
  t.borders.assign({style:'solid',fill:C.line,width:1});
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({fill:C.white,textStyle:{fontSize:size,typeface:FONT,color:C.navy},margins:{left:18,right:18,top:12,bottom:12},anchor:'center'});
  for(let c=0;c<values[0].length;c++){const cell=t.getCell(0,c);cell.fill=C.navy;cell.text.style={fontSize:size,typeface:FONT,bold:true,color:C.white};}
  return t;
}
async function image(s,name,x,y,w,h,crop) {
  const imagePath=path.isAbsolute(name)?name:path.join(liveDir,name);
  const bytes=await fs.readFile(imagePath);
  return s.images.add({blob:bytes,contentType:imagePath.toLowerCase().endsWith('.png')?'image/png':'image/jpeg',alt:`Captura original do ensaio: ${name}`,fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{} )});
}
function reference(names) {return names.map(n=>`${sourceBase}${n}`).join('\n');}

// 1. A cover stays simple. Its native diagram is an editable process definition.
{
const s=slide('Workflow do LAB','Apresentação V2 nova, preservando apresentações anteriores. Laboratório de 8 de outubro de 2026. A validação evoluiu do resultado simulado para criação real de tag estável e Release GitHub, mantendo a distribuição mobile como aceite futuro. O usuário pediu cenários de rejeição, correção e RC2, logs e lições para o Amulets.\n'+release,true);
text(s,'Candidata, aprovação e promoção\nno GitHub',88,235,1330,190,68,{color:C.white,bold:true});
text(s,'Release real v1.5.0',88,526,950,70,42,{color:'#7CE0CF',bold:true});
text(s,'Validação e lições para o Amulets\n8 de outubro de 2026',88,670,1200,100,30,{color:'#D4E1EB'});
}
// 2. Actual terminal result, supported by GETs and receipts rather than screen only.
{
const s=slide('Resultado comprovado','O run da RC2 terminou completed/success. Todos os oito jobs concluíram com sucesso. A API confirmou v1.5.0 no commit b8763ec5adc5e24ce34f474a66a079b48a9ffa0f, igual à RC2. Release ID 407306454, published_at 2026-10-08T22:16:37Z, 19h16 de Fortaleza, draft=false, prerelease=false. A intenção, API e receipt coincidem nos objetos e nas três decisões. RC1/RC2 ficaram preservadas.\n'+reference(['rc2-verified-result-stable-release.json','rc2-verified-result-stable-ref.json','rc2-verified-result-state.json','rc2-verified-result-run.json','12-release-estavel-publicada.jpg']));
text(s,'v1.5.0',88,200,460,86,72,{bold:true,color:C.green,link:release});
text(s,'Tag estável e Release reais\nno código aprovado da RC2',88,324,490,130,35,{bold:true});
text(s,'RC1 e RC2 continuam no histórico.\nO recibo confirma a publicação.',88,518,490,130,29);
await image(s,'12-release-estavel-publicada.jpg',610,230,902,389,{left:0.03,top:0.18,right:0.025,bottom:0.08});
text(s,'Escopo: catálogo GitHub. Aplicativo e patch não distribuídos.',88,768,1330,45,27,{color:C.muted});
text(s,'Ensaio automatizado autorizado. Independência de revisão humana não verificada.',88,814,1390,35,23,{color:C.muted});
}
// 3. Editable diagram, required process evidence rather than decorative shapes.
{
const s=slide('Percurso da candidata','O operador usa main revisada para iniciar o fluxo e informa versão/título legíveis. O helper mantém release/<versão> e cria uma RC imutável. A avaliação usa exatamente a fonte selecionada da release, executa analyze/test/build web, publica bytes verificados e confirma HTTP/changelog antes dos gates. Israel e Fabrícia registram avais em Environments exclusivos. Os dois jobs e receipts precisam passar. Depois, uma das duas contas autoriza PUBLICAR no terceiro Environment. Só o runner final com permissão cria a tag estável/Release e confere o resultado.\n'+run+'\n'+reference(['rc2-verified-result-state.json','rc2-verified-result-jobs.json']));
const a=node(s,'Main revisada\nRelease e RC',88,208,365,114);
const b=node(s,'Testes e build web\nPreview confirmado',568,208,440,114);
const c=node(s,'Israel E Fabrícia\nDois avais',1130,208,382,114,C.green);
connect(s,a,b);connect(s,b,c);
const d=node(s,'Israel OU Fabrícia\nComando PUBLICAR',1130,466,382,126,C.blue);
const e=node(s,'Tag estável\nRelease e recibo',568,466,440,126,C.green);
connect(s,c,d,'bottom','top');connect(s,d,e,'left','right');
text(s,'Uma correção na release cria outra RC e reinicia a avaliação.',88,682,1390,65,33,{bold:true});
text(s,'Cada decisão pertence ao mesmo código, preview e changelog.',88,770,1390,44,27,{color:C.muted});
}
// 4. The native AND requirement and OR final command are different operations.
{
const s=slide('Duas aprovações e um comando final','A interface do GitHub permite que um Environment com vários required reviewers seja liberado por um reviewer elegível. Para exigir ambas as contas no LAB, a implementação usa dois Environments exclusivos e jobs dependentes de ambos. aprovacao-israel aceita somente israelhudson, aprovacao-fahnassau30 somente fahnassau30. autorizar-publicacao aceita uma das duas contas, após sucesso dos dois jobs. Permissões de main/release e review técnico do PR são diferentes do aceite da candidata.\n'+reference(['rc2-two-approvals-awaiting-final-pending.json','rc2-two-approvals-awaiting-final-reviews.json','rc2-two-approvals-awaiting-final-state.json']));
table(s,[['Etapa','Conta elegível','Efeito'],['Aval de Israel','Israel','Registra uma aprovação'],['Aval de Fabrícia','Fabrícia','Registra a outra aprovação'],['PUBLICAR','Israel ou Fabrícia','Autoriza a promoção']],88,192,1424,342,[390,390,644],30);
text(s,'0/2 ou 1/2',88,590,330,65,38,{bold:true,color:C.red});
text(s,'Publicação bloqueada',470,598,1020,60,32);
text(s,'2/2',88,683,330,65,38,{bold:true,color:C.green});
text(s,'Libera somente o comando final',470,691,1020,60,32);
text(s,'Os dois avais não publicam automaticamente.',88,785,1380,44,28,{bold:true,color:C.blue});
}
// 5. Original screenshot remains embedded. Native label cannot be renamed.
{
const s=slide('O botão “Approve and deploy”','O texto do botão pertence à interface nativa do GitHub e não pode ser renomeado pelo workflow. Seu efeito depende do Environment selecionado. Em aprovacao-israel ou aprovacao-fahnassau30, o job apenas confere a conta oficial, valida a identidade e grava o receipt de aval. Depois da aprovação da Fabrícia na RC1, Gate second teria apenas registrado aval, mas no ensaio ela rejeitou RC1. Na RC2 ambos os jobs de aval passaram, e a captura mostra que autorizar-publicacao ainda aguardava o terceiro clique. No terceiro Environment o clique autoriza efeitos reais GitHub-only.\nhttps://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments\n'+reference(['09-rc2-dois-avais-aguardando-publicar.jpg','rc2-two-approvals-awaiting-final-jobs.json','rc2-two-approvals-awaiting-final-stable-release.json']));
await image(s,'09-rc2-dois-avais-aguardando-publicar.jpg',88,204,431,600,{left:0.015,top:0.35,right:0.765,bottom:0.07});
text(s,'Gate de aprovação',650,203,862,54,33,{bold:true,color:C.green});
text(s,'Registra só o aval da conta selecionada.',650,270,862,78,31);
await image(s,'/var/folders/d3/3vkjpdv15gj03tx9g9xssxrc0000gn/T/codex-clipboard-f0ce0f67-ff6a-4fd3-beb8-fdcb0d7e7706.png',650,390,700,170,{left:0.62,top:0.90,right:0.025,bottom:0.002});
s.speakerNotes.text+='\nFonte do detalhe do botão: imagem original anexada por Israel na conversa, codex-clipboard-f0ce0f67-ff6a-4fd3-beb8-fdcb0d7e7706.png. O recorte exibe o label nativo do GitHub. A captura da lista de jobs é do ensaio RC2 e comprova o estado do comando final aguardando.\n';
text(s,'Gate PUBLICAR',650,620,862,54,33,{bold:true,color:C.blue});
text(s,'Autoriza os efeitos após os dois avais.',650,687,862,78,31);
text(s,'Dois gates verdes. Comando final aguardando.',650,790,862,46,26,{color:C.muted});
}
// 6. Delivery version and native app version remain distinct.
{
const s=slide('Identidade congelada da candidata','Antes dos avais, RC2 fixa versão de entrega 1.5.0, tag v1.5.0-rc.2, stable v1.5.0, source b8763ec5adc5e24ce34f474a66a079b48a9ffa0f, tooling 9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0, run/tentativa 1, título, política, modo github_release_only, preview e relatório/changelog. Report digest f322ac38d3d87747dc7a29642a19d9892476bcb642a34f9602ddc910a9624334. Ambos os receipts e comando final vinculam essa identidade. O preview mostra pubspec 1.1.0+2, distinto da versão GitHub 1.5.0. Um preview web não valida Android/iOS ou release-base Shorebird. Alterar fonte/conteúdo exige outra candidata e novos avais.\n'+preview+'\n'+reference(['07-preview-rc2-corrigido.jpg','rc2-zero-approvals-state.json','rc2-verified-result-state.json']));
text(s,'Preview da RC2 corrigida',720,204,792,53,31,{bold:true,color:C.green});
await image(s,'07-preview-rc2-corrigido.jpg',720,312,792,218,{left:0.20,top:0.47,right:0.20,bottom:0.23});
text(s,'Versão da entrega: 1.5.0\nVersão do app no preview: 1.1.0+2',720,589,792,109,28,{color:C.muted});
text(s,'Código selecionado',88,214,540,52,33,{bold:true});
text(s,'RC imutável e commit exato',88,278,540,68,29);
text(s,'Conteúdo da revisão',88,393,540,52,33,{bold:true});
text(s,'Preview, changelog e relatório\nligados à mesma fonte',88,457,540,116,29);
text(s,'Destino e modo',88,622,540,52,33,{bold:true});
text(s,'GitHub Release v1.5.0',88,686,540,67,29,{color:C.green});
text(s,'Preview web confirma este snapshot. Mobile tem validação própria.',88,798,1380,43,25,{color:C.muted});
}
// 7. RC rejection actually observed, correction then fresh candidate.
{
const s=slide('Rejeição da RC1 e correção','Cenário controlado real. RC1 teve um aval Israel e a conta Fabrícia rejeitou, via Safari em automação autorizada, porque a mensagem inicial precisava identificar o laboratório em português. Gate second failure, final e promoção skipped, nenhum stable/Release. O journal ainda mostrava awaiting_approvals porque o helper não roda em gate rejeitado. A conclusão deve conciliar run/reviews, não esse campo isolado. PR 15 mudou só headline para Laboratório de atualizações e expectativa do widget test, target release/1.5.0, CI/review técnica automatizada passaram e merge b8763ec. Novo corte criou RC2, preservou RC1 como superseded, gerou novo preview/report e zero receipts herdados. Novos avais e terceiro comando promoveram RC2. Backport: '+backport.label+'.\nhttps://github.com/israelhudson/flutter_code_push_example/pull/15\nhttps://github.com/israelhudson/flutter_code_push_example/pull/16\n'+reference(['04-rc1-rejeitada-sem-promocao.jpg','correction-pr-merged.json','rc2-cut-state.json','rc2-zero-approvals-state.json']));
await image(s,'04-rc1-rejeitada-sem-promocao.jpg',88,260,879,356,{left:0,top:0.24,right:0,bottom:0.025});
text(s,'1  RC1 rejeitada',1040,205,472,64,34,{bold:true,color:C.red});
text(s,'2  Correção revisada\n    na release',1040,314,472,105,33,{bold:true});
text(s,'3  RC2 começa\n    com zero avais',1040,457,472,111,33,{bold:true,color:C.green});
text(s,'4  Novos dois avais\n    e comando final',1040,606,472,111,33,{bold:true});
text(s,backport.label,88,780,1424,47,28,{color:backport.status==='PASS'?C.green:C.muted});
}
// 8. Native editable table describes actual references, avoiding renaming RC.
{
const s=slide('Tags candidatas e tag estável','A promoção preserva tags RC e cria outro ref estável no mesmo commit aprovado. Nenhuma tag é renomeada, apagada, movida ou force-pushed. Fonte RC1 9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0, RC2 e stable b8763ec5adc5e24ce34f474a66a079b48a9ffa0f. Regras de proteção bloqueiam updates/deletes tanto no namespace RC como no novo namespace v* estável. A Release final não é draft nem prerelease, e título/corpo/changelog correspondem à intenção congelada. Um GET da tag isolado ainda não comprova a Release ou conclusão do workflow.\n'+reference(['rc2-verified-result-rc-refs.json','rc2-verified-result-stable-ref.json','rc2-verified-result-stable-release.json','rc2-verified-result-state.json']));
table(s,[['Referência','Código','Papel no histórico'],['v1.5.0-rc.1','9c4ad37','Candidata rejeitada, preservada'],['v1.5.0-rc.2','b8763ec','Candidata corrigida e aprovada'],['v1.5.0','b8763ec','Versão estável publicada']],88,200,1424,350,[370,290,764],30);
text(s,'RC2 e estável compartilham o código aprovado',88,612,1350,78,40,{bold:true,color:C.green});
text(s,'A Release mantém a ligação com o preview, changelog e execução.',88,720,1400,75,31);
}
// 9. Only observed remote subcases, never nine entire remote fault scenarios.
{
const s=slide('Cenários observados no GitHub','Resultados primários do ensaio remoto. Os testes negativos são PASS quando o GitHub recusa ou bloqueia sem efeitos. Zero e um aval não publicaram. Dois avais liberaram somente terceiro gate. RC1 rejection skip de final. Conta Israel no gate Fabrícia recebeu 422 e não criou review. Rerun da RC1 tentativa 2 falhou prepare antes da avaliação. Versão igual 1.5.0 run 37852613605 e antiga 1.4.0 run 37852617201 falharam prepare por versão já usada/reservada ou anterior à estável, evaluate skipped. Assessments compararam journal exatamente ao baseline completed, sem mudança de tags, Release, ID, corpo, flags ou candidata. Promoção RC2 final concluída em GitHub. Backport consta no slide de correção quando houver merge comprovado.\n'+reference(['MATRIZ-RESULTADOS.json','LIVE-SECURITY-AUDIT.md','same-version-blocked-assessment.json','old-version-blocked-assessment.json','rc2-verified-result-state.json']));
text(s,`${summary.remote_subcases_passed} de ${summary.remote_subcases_total} verificações PASS. Os ramos restantes seguem pendentes remotamente.`,88,146,1424,39,27,{color:C.green});
table(s,[['Teste','Resultado observado'],['0/2 e 1/2','Publicação bloqueada'],['2/2 sem comando','Terceiro gate aguardando'],['Rejeição da RC1','Promoção não iniciou'],['Correção e RC2','Novo código, preview e zero avais'],['Conta no gate errado','GitHub recusou a aprovação'],['Rerun da RC1','Preparação recusou reexecução'],['Versão igual ou antiga','Preparação recusou novo corte'],['Comando final na RC2','Tag estável e Release confirmadas']],88,203,1424,588,[500,924],28);
text(s,'Provas: APIs, logs e recibos. Reviews automatizadas por contas autorizadas.',88,813,1390,35,23,{color:C.muted});
}
// 10. Native table lists all nine local fault scenarios and their boundary.
{
const s=slide('Nove cenários offline','Suíte final v3: 9 de 9 cenários passaram, 24 testes de promoção e 5 de configuração passaram. Helper real e Git temporário real, com GitHub APIs/reviews/HTTP sintéticos. Isso não efetua rede, Pages, approvals humanas ou Release real. Cenários VAL-01 zero/um/dois sem final, VAL-02 rejeição/correção/RC2, VAL-03 deriva identidade, VAL-04 conflitos, VAL-05 falha parcial/POST perdido/recovery, VAL-06 versão/ator/bot/rerun, VAL-07 CAS concorrente, VAL-08 preview falho, VAL-09 retirada de proteções. Snapshot integrado teve 273 contratos passando no GitHub além de Flutter analyze/test. Nem todos os ramos/falhas desses nove cenários foram executados no serviço GitHub.\nhttps://github.com/israelhudson/flutter_code_push_example/actions/runs/37850097988\nhttps://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/summary.json');
table(s,[['Caso','Condição validada localmente'],['01','Aprovações incompletas e comando separado'],['02','RC1 rejeitada, correção e RC2 sem herança'],['03','Fonte, relatório ou política divergentes'],['04','Tag estável ou Release conflitantes'],['05','Falha parcial, resposta perdida e recuperação'],['06','Versão, conta, bot ou tentativa inválidos'],['07','Atualizações concorrentes do journal'],['08','Falha na confirmação do preview'],['09','Proteções removidas antes ou entre efeitos']],88,177,1424,600,[200,1224],26);
text(s,'9/9 PASS local. No GitHub: 273 testes, Flutter analyze e test passaram.',88,807,1424,46,27,{bold:true,color:C.green});
}
// 11. Transaction intent, reconciled GETs, and fresh authorization for recovery.
{
const s=slide('Falha parcial e recuperação','Fluxo de efeitos usa intenção persistida antes de chamada externa, depois tag exact GET, Release exact GET e receipt final. O publisher reconfere identidade, reviews oficiais, jobs, proteções e attempt1. Tag/Release usam create-only, sem editar/remover objeto existente ou alterar source para contornar erro. Se POST perder resposta, o GET reconcilia objeto esperado. Se somente tag existir, journal registra parcial/failed e não emite recibo completed. Recovery workflow manual em tentativa nova, com tooling original, decisões originais revalidadas e autorização final nova, termina somente o que falta. Nenhuma recuperação foi necessária na promoção real, recovery_authorizations vazio. Falhas parciais/conflicting tags/protections removidas/CAS remain offline. Concurrency release-lab-mutation serializa prepare/effects/recovery, sem lock durante espera humana. Runner do app é readonly, Pages/publisher isolados.\n'+reference(['LIVE-SECURITY-AUDIT.md','rc2-verified-result-state.json'])+'\nhttps://github.com/israelhudson/flutter_code_push_example/blob/main/.github/workflows/release-lab-recover.yml');
const a=node(s,'Intenção salva',88,213,300,115);
const b=node(s,'Tag conferida',460,213,300,115);
const c=node(s,'Release conferida',832,213,300,115);
const d=node(s,'Recibo concluído',1204,213,308,115,C.green);
connect(s,a,b);connect(s,b,c);connect(s,c,d);
text(s,'Se um efeito falhar',88,420,648,61,38,{bold:true,color:C.red});
text(s,'Preserva o estado parcial.\nMantém o código aprovado.\nExige nova autorização para recuperar.',88,511,668,170,31);
text(s,'Proteções durante a espera',844,420,668,61,38,{bold:true});
text(s,'O publicador reconfere as regras.\nUm runner novo executa os efeitos.\nO build do app usa permissão de leitura.',844,511,668,170,31);
text(s,'Falhas e recuperação: evidência offline. Promoção real concluiu sem recuperação.',88,790,1400,55,26,{color:C.muted});
}
// 12. Distinguish expected negative runs from corrected defects and collectors.
{
const s=slide('Jobs vermelhos e prevenção','Quatro conclusões vermelhas do Actions são negativas esperadas: rejeição da RC1, rerun da RC1 e versões igual/antiga. A API 422 no gate errado é recusa externa esperada, não um job falho. Zero/um/dois avais antes do comando são estados waiting e não erros. Todos os oito jobs RC2 passaram, sem recovery. Erros evitáveis corrigidos: configuração rejeitou defaults seguros required_reviewers=[] e require_extra_approval_for_unattributed_changes=true, normalização explícita e 5 testes resolveram sem bypass. Auditoria encontrou lacuna de reconferir proteções após espera, corrigida em finish_real/live_intent e coberta VAL-09 offline, sem induzir falha destrutiva remota. Fixture de lost-response contava tag histórica entrega-0100-rc.1 no namespace errado, assertion corrigida e histórico preservado. Coletor 422 olhava só stderr/string-int, corrigiu parsing e verificou zero reviews sem repetir request. Exportação do log RC1 devolveu exit1 porque job rejeitado não tinha etapas, preservou 391589 bytes, não alegar que todos os logs exportaram completos. Snapshot promotion-completed-* ainda era in_progress, usar família rc2-verified-result-* como prova terminal. Prevenção: preflight de versão/permissão/ambiente, validação explícita de defaults seguros, regras rechecadas após espera, coletores com tipos normalizados e run_attempt, evidência terminal composta por GET/receipt/jobs.\n'+reference(['FALHAS-E-PREVENCAO.md','rc1-log-collection.json','rc2-wrong-account-assessment.json','rc2-verified-result-run.json','same-version-blocked-assessment.json','old-version-blocked-assessment.json']));
text(s,'Bloqueios esperados',88,203,652,61,38,{bold:true,color:C.red});
text(s,'RC1 rejeitada\nReexecução da RC1\nVersão igual à publicada\nVersão anterior à publicada',88,293,652,240,32);
text(s,'Versões recusadas preservaram a Release.\nConta errada: a API recusou o aval.',88,626,652,112,28,{color:C.muted});
text(s,'Erros corrigidos',844,203,668,61,38,{bold:true,color:C.green});
text(s,'Configuração rígida',844,294,668,46,31,{bold:true});
text(s,'Normalização segura e cinco testes.',844,348,668,52,29);
text(s,'Proteções após a espera',844,437,668,46,31,{bold:true});
text(s,'Reconferência antes dos efeitos.',844,491,668,52,29);
text(s,'Coleta e leitura das evidências',844,580,668,46,31,{bold:true});
text(s,'JSON normalizado e prova terminal.\nLogs parciais continuam preservados.',844,634,668,97,29);
text(s,'Próximo ensaio: pré-check de versão e permissões, com coleta de evidências conferida.',88,793,1400,57,26,{color:C.blue,bold:true});
}
// 13. Transfer lessons and explicitly separate future mobile end capability.
{
const s=slide('Aplicação ao Amulets','Lições a transportar, sem executar comandos no código Amulets nesta tarefa. Confirmar atores: plano histórico propõe Samuel E Vinícius para aprovação e um dos dois para PUBLICAR, não comprova política final atual. Conferir suporte de required reviewers no repositório privado/plano, revisores técnicos elegíveis, permissões App/token e preview privado. Preservar RC imutável, correction PR release e backport separado main, nova fonte/report/preview/avais. Sem reutilização de approvals. Restringir writers do journal, porque proteção contra force-push/exclusão não impede writer malicioso. Registros devem distinguir operador, conta e aceite humano. Artefatos Actions duram 90 dias neste workflow, exportar logs/reviews/GET/receipts/prints sem segredos. Para mobile, definir versão/build/release-base por plataforma, toolchain e compatibilidade nativa/assets/dependências, adaptador/store/Shorebird, credenciais assinadas e destinos corretos. Depois comprovar upload, testers, instalação no dispositivo, monitoramento/rollback. Nenhum desses resultados foi validado pelo preview ou Release GitHub.\n'+reference(['PASSO-A-PASSO-E-LICOES.md','MATRIZ-RESULTADOS.json','LIVE-SECURITY-AUDIT.md'])+'\nhttps://github.com/israelhudson/flutter_code_push_example/blob/main/docs/delivery/FLUXO-DOIS-APROVADORES.md\nhttps://github.com/israelhudson/flutter_code_push_example/blob/main/docs/delivery/VALIDACAO-E-PROMOCAO.md\nhttps://docs.shorebird.dev/code-push/patch/');
text(s,'Política de aprovação',88,205,666,61,37,{bold:true});
text(s,'Duas pessoas aprovam a mesma RC.\nUma delas autoriza o comando final.',88,293,666,117,31);
text(s,'Histórico preservado',88,487,666,61,37,{bold:true});
text(s,'Correção passa pela release e main.\nNova RC exige preview e novos avais.',88,575,666,117,31);
text(s,'Evidências por resultado',844,205,668,61,37,{bold:true});
text(s,'Logs, reviews, GETs e recibos\nmostram exatamente o que aconteceu.',844,293,668,117,31);
text(s,'Aceite mobile separado',844,487,668,61,37,{bold:true,color:C.blue});
text(s,'Base exata, build e destino corretos.\nDistribuição e uso no dispositivo.',844,575,668,117,31);
text(s,'Próxima validação: adaptador mobile autorizado e prova de entrega por plataforma.',88,790,1390,58,27,{bold:true,color:C.blue});
}

await fs.writeFile(path.join(workspaceDir,'outline-and-notes.json'),JSON.stringify({created_at:new Date().toISOString(),font:FONT,slide_count:P.slides.items.length,source_matrix_timestamp:summary.generated_at,backport,slides:outline},null,2));
await fs.writeFile(path.join(workspaceDir,'source-snapshot.json'),JSON.stringify(summary,null,2));
const candidatePath=path.join(HERE,'draft-rev05.pptx');
await (await PresentationFile.exportPptx(P)).save(candidatePath);
const finalPath=path.join(workspaceDir,'output','workflow-lab-validado-v2-rev5.pptx');
const validationPath=path.join(HERE,'validation-rev05.json');
const result=await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','15240000,8572500','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','4','--require-native-table-slide','8','--require-native-table-slide','9','--require-native-table-slide','10'],requiredNativeTableOwnerSlides:[4,8,9,10],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:validationPath});
for(let i=0;i<P.slides.items.length;i++){
 const s=P.slides.items[i]; const png=await P.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(workspaceDir,'renders',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 const layout=await s.export({format:'layout'}); await fs.writeFile(path.join(workspaceDir,'renders',`slide-${String(i+1).padStart(2,'0')}.layout.json`),await layout.text());
}
const montage=await P.export({format:'webp',montage:true}); await fs.writeFile(path.join(workspaceDir,'renders','montage.webp'),new Uint8Array(await montage.arrayBuffer()));
console.log(JSON.stringify({finalPath,font:FONT,slides:P.slides.items.length,validationPath,backport,result},null,2));
