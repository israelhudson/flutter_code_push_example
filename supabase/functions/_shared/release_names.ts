// Names belong to the frozen candidate. New versions use the official namespace;
// historical candidates keep their original tags and branches through RC2/final.
export type ReleaseNamespace = "official" | "legacy";
const versionPattern = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
export function candidateNames(
  version: string,
  rcNumber: number,
  namespace: ReleaseNamespace = "official",
) {
  if (
    !versionPattern.test(version) || !Number.isSafeInteger(rcNumber) || rcNumber < 1 ||
    !["official", "legacy"].includes(namespace)
  ) throw Error("Release names rejected");
  const prefix = namespace === "legacy" ? "poc-" : "";
  return {
    namespace,
    rc_tag: `${prefix}v${version}-rc.${rcNumber}`,
    final_tag: `${prefix}v${version}`,
    branch: `${prefix}release/${version}`,
  };
}
export function releaseNames(c: any) {
  const match = /^(poc-)?v(.+)-rc\.([1-9]\d*)$/.exec(c.rc_tag ?? "");
  if (!match || match[2] !== c.version) throw Error("Frozen release names rejected");
  const rcNumber = Number(match[3]);
  if (c.rc_number != null && c.rc_number !== rcNumber) throw Error("Frozen RC number differs");
  const names = candidateNames(c.version, rcNumber, match[1] ? "legacy" : "official");
  if (c.branch != null && c.branch !== names.branch) throw Error("Frozen release branch differs");
  return names;
}
