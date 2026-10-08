import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
live = root.parent
final = root / 'output/workflow-lab-validado-v2.pptx'
validated = root / 'output/workflow-lab-validado-v2-rev5.pptx'
assert final.read_bytes() == validated.read_bytes()
validation = json.loads((root / 'build/validation-rev05.json').read_text())
assert validation['packageIntegrity']['status'] == 'pass'
assert validation['presentationLayout']['finding_count'] == 0
assert validation['firstPartyImport']['passed']
ns = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
with zipfile.ZipFile(final) as package:
    slides = [n for n in package.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
    notes = [n for n in package.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')]
    images = [n for n in package.namelist() if n.startswith('ppt/media/')]
    shapes = sum(len(ET.fromstring(package.read(n)).findall('.//p:sp',ns)) for n in slides)
    connectors = sum(len(ET.fromstring(package.read(n)).findall('.//p:cxnSp',ns)) for n in slides)
    for image in images:
        value = package.read(image)
        assert image.endswith('.png') and value.startswith(b'\x89PNG\r\n\x1a\n') or image.endswith('.jpeg') and value.startswith(b'\xff\xd8\xff')
    assert len(slides) == len(notes) == 13
sources = ['PASSO-A-PASSO-E-LICOES.md','MATRIZ-RESULTADOS.json','LIVE-SECURITY-AUDIT.md','FALHAS-E-PREVENCAO.md']
for source in sources:
    assert (live / source).is_file(), source
quality = {
    'schema':1,
    'created_at':datetime.now(timezone.utc).isoformat(),
    'status':'PASS',
    'deliverable':str(final),
    'sha256':hashlib.sha256(final.read_bytes()).hexdigest(),
    'bytes':final.stat().st_size,
    'slides':len(slides),
    'speaker_notes':len(notes),
    'native_tables':4,
    'native_diagrams':2,
    'native_shapes':shapes,
    'native_connectors':connectors,
    'embedded_source_images':len(images),
    'image_media_types_match_bytes':True,
    'font':'Helvetica Neue',
    'format':'16:9',
    'validation':'build/validation-rev05.json',
    'final_pptx_import_and_render':'build/render-final-13-slides.log',
    'all_final_slides_rendered':True,
    'all_final_slides_visually_reviewed_at_full_size':True,
    'unexpected_overlap_clipping_or_arrow_direction_errors_remaining':False,
    'powerpoint_application_opened':False,
    'template_picker_available':False,
    'preserves_previous_decks':True,
    'edited_scope':'apresentacao-v2 only; no code, previous decks, or GitHub mutations',
    'sources':[{'file':name,'sha256':hashlib.sha256((live/name).read_bytes()).hexdigest()} for name in sources],
    'factual_boundaries':{
        'github_release_real':'v1.5.0 from corrected v1.5.0-rc.2',
        'offline_scenarios_passed':9,
        'offline_scenarios_total':9,
        'remote_subcases_passed':15,
        'remote_subcases_total':20,
        'mobile_distribution':False,
        'independent_human_review_verified':False,
        'reviews':'Codex automated LAB test explicitly authorized by Israel',
        'unexpected_remote_promotion_failure_observed':False,
        'remote_partial_failure_recovery_exercised':False,
        'backport_to_main':'Confirmed by reviewed PR merge evidence',
    },
    'authoring_incidents_preserved':[
        'Missing runtime package environment made automatic font discovery fail on first attempt. Reused bundled runtime with RUNTIME_NODE_MODULES set.',
        'Visual review corrected the editable connector end direction and screenshot framing. Previous exports and authoring logs are preserved privately.',
        'Final late requirement added a dedicated slide distinguishing expected negative jobs from defects corrected and prevention.',
    ],
    'claim_boundary':'Package, geometry, import, rendered visual review, content traceability and media checks. Does not claim native Microsoft PowerPoint inspection, independent human approvals or mobile distribution.',
}
(root / 'QUALITY.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2)+'\n')
(root / 'QUALITY.md').write_text('''# Qualidade e escopo da apresentação V2

Entrega: `output/workflow-lab-validado-v2.pptx`, 13 slides em português, com
notas detalhadas e fontes por slide. A V2 preserva os decks anteriores.

As quatro tabelas e os dois diagramas são objetos nativos editáveis. Texto
do slide também permanece editável. Os cinco prints são imagens originais
embutidas, com recortes nativos que destacam o assunto e preservam os bytes.

## Verificações

- Pacote, geometria, heading fit e política de fonte: PASS, sem achados.
- Reimportação do PPTX final pelo Artifact Tool: PASS, 13 slides.
- Os 13 slides finais foram renderizados e inspecionados individualmente em
  tamanho completo. O contact sheet está em `renders-final/montage.webp`.
- Direção das setas, proporção e foco dos prints foram corrigidos durante a
  revisão. Versões intermediárias e logs permanecem em `build`.
- Tipos dos cinco arquivos de mídia correspondem aos bytes JPEG/PNG.
- A cópia final tem os mesmos bytes do export validado. Hash e fontes constam
  em `QUALITY.json`.
- O arquivo não foi aberto no aplicativo Microsoft PowerPoint. A revisão usa
  o Artifact Tool, seus verificadores e os renders do arquivo reimportado.

## Limites que aparecem na apresentação

A Release GitHub v1.5.0 é real, da RC2 corrigida. RC1/RC2 foram preservadas.
Os nove cenários offline PASS ficam separados das 15 de 20 verificações GitHub
PASS. A apresentação não infere os cinco subcasos pendentes no serviço real.
Os prints e as notas deixam explícita a automação autorizada por contas do LAB,
sem afirmar revisão humana independente. Nenhum aplicativo ou patch foi
distribuído. Os bloqueios vermelhos esperados ficam separados dos erros reais
corrigidos e dos limites de coleta apenas tratados.

## Reprodução local

As fontes estão em `build/create-deck.mjs` e `build/render-final.mjs`.
Use o Node e os pacotes do runtime oficial carregado para esta sessão, recriando
o symlink `build/node_modules` para os pacotes e definindo `RUNTIME_NODE_MODULES`.
Antes de uma nova exportação, escolha nomes novos de draft, final e receipt,
pois o finalizer não sobrescreve a saída existente.

Nenhum código do app, documento fora desta subpasta ou objeto GitHub foi
alterado por este agente de apresentação.
''')
# Keep a single user-facing file in output while preserving all validated revisions.
history = root / 'build/revisions'
history.mkdir(exist_ok=True)
for file in (root / 'output').glob('workflow-lab-validado-v2-rev*.pptx'):
    shutil.move(str(file),str(history / file.name))
symlink = root / 'build/node_modules'
if symlink.is_symlink():
    symlink.unlink()
print(json.dumps({'status':'PASS','final':str(final),'slides':13,'sha256':quality['sha256'],'quality':str(root/'QUALITY.json')},ensure_ascii=False))
