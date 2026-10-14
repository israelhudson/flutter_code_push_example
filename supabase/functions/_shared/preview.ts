import type { IO } from "./poc.ts";

function canonical(value: any): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    const ordered = Object.keys(value).sort((a, b) => {
      const left = [...a].map((c) => c.codePointAt(0)!);
      const right = [...b].map((c) => c.codePointAt(0)!);
      for (let i = 0; i < Math.min(left.length, right.length); i++) {
        if (left[i] !== right[i]) return left[i] - right[i];
      }
      return left.length - right.length;
    });
    return "{" + ordered.map((k) => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}
async function sha(bytes: Uint8Array) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes as BufferSource))].map(
    (x) => x.toString(16).padStart(2, "0"),
  ).join("");
}
export async function verifyPreview(io: Pick<IO, "fetch">, report: any) {
  if (
    !/^[a-f0-9]{40}$/.test(report.source_sha ?? "") || report.preview_sha !== report.source_sha ||
    report.preview_url !==
      `https://israelhudson.github.io/flutter_code_push_example/snapshots/${report.source_sha}/`
  ) throw Error("Preview source rejected");
  const get = async (path: string) => {
    const response = await io.fetch(report.preview_url + path, {
      redirect: "error",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok || Number(response.headers.get("content-length")) > 32 * 1024 * 1024) {
      throw Error("Preview unavailable");
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length > 32 * 1024 * 1024) throw Error("Preview resource too large");
    return bytes;
  };
  const manifest = JSON.parse(
    new TextDecoder("utf-8", { fatal: true }).decode(await get("files.json")),
  );
  const app: Record<string, string> = {};
  for (const [name, hash] of Object.entries(manifest)) {
    if (
      typeof hash !== "string" || !/^[a-f0-9]{64}$/.test(hash) || name.startsWith("/") ||
      /[\\%?#:]/.test(name) || [...name].some((c) =>
        c.codePointAt(0)! < 32 || c.codePointAt(0) === 127
      ) || name.split("/").some((p) => !p || p.startsWith("."))
    ) throw Error("Preview manifest rejected");
    if (name.startsWith("app/")) app[name.slice(4)] = hash;
    else if (!["metadata.json", "index.html"].includes(name)) {
      throw Error("Preview file scope rejected");
    }
  }
  if (
    await sha(new TextEncoder().encode(canonical(manifest))) !== report.snapshot_manifest_sha256 ||
    await sha(new TextEncoder().encode(canonical(app))) !== report.web_content_sha256
  ) throw Error("Preview digest changed");
  const bytes = await get("metadata.json");
  const metadata = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  if (
    metadata.schema !== "pages-preview-v1" || metadata.source_sha !== report.source_sha ||
    metadata.snapshot_path !== `snapshots/${report.source_sha}/` ||
    metadata.web_content_sha256 !== report.web_content_sha256 ||
    await sha(bytes) !== manifest["metadata.json"]
  ) throw Error("Preview metadata changed");
  await Promise.all(
    ["index.html", "app/index.html", "app/flutter_bootstrap.js", "app/main.dart.js"].map(
      async (path) => {
        if (await sha(await get(path)) !== manifest[path]) throw Error("Preview bytes changed");
      },
    ),
  );
}

// The alternative is a frozen, explicitly labelled GitHub-only exercise.
// Missing preview evidence in the normal flow must still fail closed.
export async function verifyCandidateEvidence(io: Pick<IO, "fetch">, report: any) {
  const mode = report.validation_mode ?? "full";
  if (mode === "full") return await verifyPreview(io, report);
  if (
    mode !== "controls_only" || !/^[a-f0-9]{40}$/.test(report.source_sha ?? "") ||
    !["none", "github_test"].includes(report.publication_scope) ||
    report.preview_performed !== false || report.distribution_performed !== false ||
    ["preview_url", "preview_sha", "web_content_sha256", "snapshot_manifest_sha256"].some(
      (key) => report[key] !== null,
    ) ||
    ["android", "ios"].some((platform) =>
      report.platforms?.[platform]?.base_release_version !== null ||
      report.platforms?.[platform]?.effective_patch !== null
    )
  ) throw Error("Controls-only evidence rejected");
}
