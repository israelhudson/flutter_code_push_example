// deno-lint-ignore-file require-await
import { dispatch, IO } from "../../supabase/functions/_shared/poc.ts";
function assert(value: unknown) {
  if (!value) throw Error("assertion failed");
}
function fixture(
  options: { token?: boolean; claim?: boolean; live?: boolean; status?: number; fail?: boolean } =
    {},
) {
  const calls: any[] = [], requests: any[] = [];
  const io: IO = {
    env: (key) =>
      key === "POC_GITHUB_DISPATCH_TOKEN"
        ? (options.token === false ? undefined : "offline-fixture")
        : key === "POC_SOURCE_BRANCH"
        ? "slack-main"
        : undefined,
    db: async (path, data) => {
      calls.push({ path, data });
      if (path === "rpc/poc_notice") {
        return {
          send: data?.p_claim ? options.claim !== false : options.live !== false,
          recipient: "israelhudson",
        };
      }
      return {};
    },
    fetch: (async (url: any, init: any) => {
      requests.push({ url, body: JSON.parse(init.body) });
      if (options.fail) throw Error("offline network uncertainty");
      return new Response(null, { status: options.status ?? 204 });
    }) as typeof fetch,
    slack: async () => {
      throw Error("dispatch must not call Amulets or Slack");
    },
    wait: () => {},
    log: () => {},
  };
  return { io, calls, requests };
}
Deno.test("Dispatch absent token does not reserve or send", async () => {
  const f = fixture({ token: false });
  await dispatch(f.io, "poc-test");
  assert(f.calls.length === 0 && f.requests.length === 0);
});
Deno.test("Dispatch denied reservation never sends", async () => {
  const f = fixture({ claim: false });
  await dispatch(f.io, "poc-test");
  assert(f.requests.length === 0 && f.calls.length === 1);
});
Deno.test("Dispatch rechecks live decision before sending", async () => {
  const f = fixture({ live: false });
  await dispatch(f.io, "poc-test");
  assert(f.requests.length === 0);
  assert(f.calls.at(-1).data.p_state === "skipped");
});
Deno.test("Dispatch targets only POC workflow and frozen candidate", async () => {
  const f = fixture();
  await dispatch(f.io, "poc-test");
  assert(f.requests.length === 1);
  assert(
    f.requests[0].url ===
      "https://api.github.com/repos/israelhudson/flutter_code_push_example/actions/workflows/poc-slack-publish.yml/dispatches",
  );
  assert(
    JSON.stringify(f.requests[0].body) ===
      JSON.stringify({ ref: "slack-main", inputs: { candidate: "poc-test" } }),
  );
  assert(f.calls.at(-1).data.p_state === "sent" && f.calls.at(-1).data.p_receipt.acknowledged);
});
for (const options of [{ status: 403 }, { fail: true }]) {
  Deno.test("Dispatch uncertainty records without retry " + JSON.stringify(options), async () => {
    const f = fixture(options);
    let failed = false;
    try {
      await dispatch(f.io, "poc-test");
    } catch {
      failed = true;
    }
    assert(failed && f.requests.length === 1 && f.calls.at(-1).data.p_state === "uncertain");
  });
}
