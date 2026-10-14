import type { IO } from "./poc.ts";
import { canonical } from "./preview.ts";

export type VersionRow = [string, string, string];
const repo = "israelhudson/flutter_code_push_example";
const appVersion = /^\d+\.\d+\.\d+\+\d+(?:\.\d+)*$/;
async function sha(text: string) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)))]
    .map((v) => v.toString(16).padStart(2, "0")).join("");
}
export function defaultRows(c: any): VersionRow[] {
  const r = JSON.parse(c.report_text);
  return [
    [
      "GitHub",
      c.status === "published" ? `poc-v${c.version}` : c.rc_tag,
      c.status === "published" ? "Release publicada" : "Candidata; publicação pendente",
    ],
    [
      "Web",
      "Não verificada",
      r.validation_mode === "controls_only"
        ? "Não gerado nesta rodada"
        : "Versão do preview não conferida",
    ],
    ["Android", "Não validada", "Sem publicação comprovada nesta entrega"],
    ["iOS", "Não validada", "Sem publicação comprovada nesta entrega"],
  ];
}
// Receipts record an observed result. They never grant publication permission.
export function mobileRow(c: any, p: any): VersionRow {
  const platform = p.target?.platform;
  if (
    !["android", "ios"].includes(platform) ||
    !["local_operator_android_staging_receipt", "platform_delivery_receipt_v1"].includes(p.kind) ||
    (p.kind === "local_operator_android_staging_receipt" && platform !== "android") ||
    p.candidate_id !== c.id || p.delivery_version !== c.version || p.rc_tag !== c.rc_tag ||
    p.github_tag !== `poc-v${c.version}` || p.source_sha !== c.source_sha ||
    p.report_digest !== c.report_digest || p.uploaded !== true ||
    !appVersion.test(p.target.release_version) || !Number.isSafeInteger(p.patch_number) ||
    p.patch_number < 1 ||
    !Number.isSafeInteger(p.provider_patch_id) || p.provider_patch_id < 1 ||
    !["staging", "stable"].includes(p.track) ||
    (p.track === "stable" && p.promoted_to_stable !== true)
  ) throw Error("Platform receipt rejected");
  const d = p.device_validation;
  const device = d?.successful_launch_confirmed === true && d?.cold_restart_confirmed === true &&
    d?.active_patch === p.patch_number && d?.base_version === p.target.release_version;
  const observation = device
    ? (platform === "android" && d.kind === "Android emulator"
      ? "; execução confirmada no emulador"
      : "; execução confirmada em dispositivo")
    : "; execução em dispositivo não comprovada";
  return [
    platform === "android" ? "Android" : "iOS",
    `${p.target.release_version} (patch ${p.patch_number})`,
    `Patch em ${p.track}${observation}`,
  ];
}
export async function versionPresentation(io: Pick<IO, "fetch">, c: any, release: any) {
  const report = JSON.parse(c.report_text);
  const rows = defaultRows(c);
  const sources: any[] = [];
  const read = async (url: string, redirects: RequestRedirect = "error") => {
    const response = await io.fetch(url, {
      redirect: redirects,
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok || Number(response.headers.get("content-length")) > 262144) {
      throw Error("Evidence unavailable");
    }
    const text = await response.text();
    if (new TextEncoder().encode(text).length > 262144) throw Error("Evidence too large");
    return text;
  };
  if (report.validation_mode !== "controls_only") {
    const url =
      `https://israelhudson.github.io/flutter_code_push_example/snapshots/${c.source_sha}/`;
    if (
      !/^[a-f0-9]{40}$/.test(c.source_sha) || report.preview_url !== url ||
      report.preview_sha !== c.source_sha
    ) throw Error("Preview identity rejected");
    const files = JSON.parse(await read(url + "files.json"));
    const text = await read(url + "metadata.json");
    const m = JSON.parse(text);
    if (
      await sha(canonical(files)) !== report.snapshot_manifest_sha256 ||
      await sha(text) !== files["metadata.json"] || m.source_sha !== c.source_sha ||
      m.web_content_sha256 !== report.web_content_sha256 || !appVersion.test(m.version)
    ) throw Error("Preview version evidence rejected");
    rows[1] = ["Web", m.version, "Preview validado; não comprova produção"];
    sources.push({ url: url + "metadata.json", sha256: files["metadata.json"] });
  }
  if (release) {
    if (
      release.tag_name !== `poc-v${c.version}` || release.draft !== false ||
      release.prerelease !== false
    ) throw Error("Release evidence rejected");
    const seen = new Set<string>();
    for (const asset of release.assets ?? []) {
      if (
        ![
          "platform-receipt-android.json",
          "platform-receipt-ios.json",
          `shorebird-staging-receipt-${c.version}.json`,
        ].includes(asset.name)
      ) continue;
      const url = `https://github.com/${repo}/releases/download/poc-v${c.version}/${asset.name}`;
      if (
        asset.browser_download_url !== url || asset.size > 262144 ||
        !/^sha256:[a-f0-9]{64}$/.test(asset.digest ?? "")
      ) throw Error("Receipt asset rejected");
      // Public GitHub download; no bearer token is forwarded to redirects.
      const text = await read(url, "follow");
      if ("sha256:" + await sha(text) !== asset.digest) throw Error("Receipt digest changed");
      const row = mobileRow(c, JSON.parse(text));
      if (
        (asset.name === "platform-receipt-android.json" && row[0] !== "Android") ||
        (asset.name === "platform-receipt-ios.json" && row[0] !== "iOS")
      ) throw Error("Receipt filename platform mismatch");
      if (seen.has(row[0])) throw Error("Ambiguous platform receipts");
      seen.add(row[0]);
      rows[row[0] === "Android" ? 2 : 3] = row;
      sources.push({ url, sha256: asset.digest.slice(7), asset_id: asset.id });
    }
  }
  return { rows, sources };
}
