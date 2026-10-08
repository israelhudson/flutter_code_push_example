import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FileBlob, PresentationFile } from '@oai/artifact-tool';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const finalPath=path.join(root,'output','workflow-lab-validado-v2.pptx');
const presentation=await PresentationFile.importPptx(await FileBlob.load(finalPath));
const target=path.join(root,'renders-final');await fs.mkdir(target,{recursive:true});
for(let i=0;i<presentation.slides.items.length;i++){
 const slide=presentation.slides.items[i];
 const png=await presentation.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(target,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
}
const webp=await presentation.export({format:'webp',montage:true});
await fs.writeFile(path.join(target,'montage.webp'),new Uint8Array(await webp.arrayBuffer()));
const inspected=await presentation.inspect({kind:'slide,textbox,shape,image,table,notes',maxChars:100000});
await fs.writeFile(path.join(target,'inspection.ndjson'),inspected.ndjson);
console.log(JSON.stringify({imported_file:finalPath,slide_count:presentation.slides.items.length,rendered_slides:presentation.slides.items.length,status:'PASS'}));
