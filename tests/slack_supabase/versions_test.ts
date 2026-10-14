// deno-lint-ignore-file require-await
import {
  defaultRows,
  mobileRow,
  versionPresentation,
} from "../../supabase/functions/_shared/versions.ts";
import { canonical } from "../../supabase/functions/_shared/preview.ts";
import { digest } from "../../supabase/functions/_shared/poc.ts";
function assert(v: unknown) {
  if (!v) throw Error("assertion failed");
}
const c = {
  id: "poc-" + "a".repeat(32),
  version: "2.0.0",
  rc_tag: "poc-v2.0.0-rc.2",
  source_sha: "b".repeat(40),
  report_digest: "c".repeat(64),
  status: "published",
  report_text: JSON.stringify({ validation_mode: "controls_only" }),
};
function receipt(platform = "android") {
  return {
    kind: "platform_delivery_receipt_v1",
    candidate_id: c.id,
    delivery_version: c.version,
    rc_tag: c.rc_tag,
    github_tag: "poc-v2.0.0",
    source_sha: c.source_sha,
    report_digest: c.report_digest,
    target: { platform, release_version: "1.1.0+2" },
    patch_number: 4,
    provider_patch_id: 123,
    uploaded: true,
    track: "staging",
    device_validation: {
      kind: "Android emulator",
      base_version: "1.1.0+2",
      active_patch: 4,
      cold_restart_confirmed: true,
      successful_launch_confirmed: true,
    },
  };
}
Deno.test("Version rows distinguish Android and iOS build from patch; absent evidence is never success", () => {
  assert(mobileRow(c, receipt())[1] === "1.1.0+2 (patch 4)");
  const ios = receipt("ios");
  ios.target.release_version = "1.1.0+3";
  ios.patch_number = 23;
  assert(mobileRow(c, ios)[1] === "1.1.0+3 (patch 23)");
  assert(mobileRow(c, ios)[2].includes("não comprovada"));
  assert(defaultRows(c)[3][1] === "Não validada");
});
Deno.test("Mobile receipt from another candidate, SHA, base or failed upload cannot be displayed as delivered", () => {
  for (
    const delta of [
      { source_sha: "d".repeat(40) },
      { candidate_id: "other" },
      { report_digest: "0".repeat(64) },
      { rc_tag: "poc-v2.0.0-rc.1" },
      { uploaded: false },
      { patch_number: 0 },
      { patch_number: 1.5 },
      { target: { platform: "ios", release_version: "unverified" } },
      { track: "stable" },
      { kind: "unknown" },
    ]
  ) {
    let failed = false;
    try {
      mobileRow(c, { ...receipt(), ...delta });
    } catch {
      failed = true;
    }
    assert(failed);
  }
});
Deno.test("Controls-only table does not fetch Pages and never generates preview or patch", async () => {
  const io = {
    fetch: (() => {
      throw Error("Network forbidden");
    }) as typeof fetch,
  };
  const result = await versionPresentation(io, c, null);
  assert(result.rows[1][2] === "Não gerado nesta rodada");
  assert(result.sources.length === 0);
});
Deno.test("Table uses hashed preview metadata and matching release assets; changed evidence fails closed", async () => {
  const metadata = JSON.stringify({
    source_sha: c.source_sha,
    version: "1.1.0+2",
    web_content_sha256: "d".repeat(64),
  });
  const files = { "metadata.json": await digest(metadata) };
  const preview =
    `https://israelhudson.github.io/flutter_code_push_example/snapshots/${c.source_sha}/`;
  const candidate = {
    ...c,
    report_text: JSON.stringify({
      preview_url: preview,
      preview_sha: c.source_sha,
      snapshot_manifest_sha256: await digest(canonical(files)),
      web_content_sha256: "d".repeat(64),
    }),
  };
  const url =
    "https://github.com/israelhudson/flutter_code_push_example/releases/download/poc-v2.0.0/platform-receipt-android.json";
  const payload = JSON.stringify(receipt());
  const asset = {
    id: 12,
    name: "platform-receipt-android.json",
    browser_download_url: url,
    size: payload.length,
    digest: "sha256:" + await digest(payload),
  };
  const release = { tag_name: "poc-v2.0.0", draft: false, prerelease: false, assets: [asset] };
  const bodies: Record<string, string> = {
    [preview + "files.json"]: JSON.stringify(files),
    [preview + "metadata.json"]: metadata,
    [url]: payload,
  };
  const io = {
    fetch: (async (u, options) => {
      assert(!options?.headers);
      assert(!options?.method || options.method === "GET");
      const body = bodies[String(u)];
      if (!body) throw Error("Unexpected URL");
      return new Response(body);
    }) as typeof fetch,
  };
  const result = await versionPresentation(io, candidate, release);
  assert(result.rows[1][1] === "1.1.0+2");
  assert(result.rows[2][1] === "1.1.0+2 (patch 4)");
  assert(result.rows[3][1] === "Não validada");
  assert(result.sources.length === 2);
  for (const target of [preview + "metadata.json", url]) {
    const original = bodies[target];
    bodies[target] = original + " ";
    let failed = false;
    try {
      await versionPresentation(io, candidate, release);
    } catch {
      failed = true;
    }
    assert(failed);
    bodies[target] = original;
  }
  let failed = false;
  try {
    await versionPresentation(io, candidate, { ...release, assets: [asset, asset] });
  } catch {
    failed = true;
  }
  assert(failed);
});
