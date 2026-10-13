// deno-lint-ignore-file require-await
import { verifyPreview } from "../../supabase/functions/_shared/preview.ts";
import { digest } from "../../supabase/functions/_shared/poc.ts";
function assert(v: unknown) {
  if (!v) throw Error("assertion failed");
}
Deno.test("Preview só aceita manifest, metadados e bytes do SHA congelado", async () => {
  const sha = "a".repeat(40);
  const app = {
    "flutter_bootstrap.js": "bootstrap",
    "index.html": "app",
    "main.dart.js": "program",
  };
  const appHashes: Record<string, string> = {};
  for (const [path, bytes] of Object.entries(app)) appHashes[path] = await digest(bytes);
  const contentHash = await digest(JSON.stringify(appHashes));
  const metadata = JSON.stringify({
    schema: "pages-preview-v1",
    source_sha: sha,
    snapshot_path: `snapshots/${sha}/`,
    web_content_sha256: contentHash,
  });
  const files: Record<string, string> = { "index.html": "wrapper", "metadata.json": metadata };
  for (const [p, b] of Object.entries(app)) files["app/" + p] = b;
  const manifest: Record<string, string> = {};
  for (const p of Object.keys(files).sort()) manifest[p] = await digest(files[p]);
  files["files.json"] = JSON.stringify(manifest);
  const base = `https://israelhudson.github.io/flutter_code_push_example/snapshots/${sha}/`;
  const report = {
    source_sha: sha,
    preview_sha: sha,
    preview_url: base,
    web_content_sha256: contentHash,
    snapshot_manifest_sha256: await digest(JSON.stringify(manifest)),
  };
  const io = {
    fetch: (async (url) => new Response(files[String(url).slice(base.length)])) as typeof fetch,
  };
  await verifyPreview(io, report);
  files["app/main.dart.js"] = "different program";
  let failed = false;
  try {
    await verifyPreview(io, report);
  } catch {
    failed = true;
  }
  assert(failed);
  failed = false;
  try {
    await verifyPreview(io, { ...report, preview_sha: "b".repeat(40) });
  } catch {
    failed = true;
  }
  assert(failed);
});
