import { verifyPreview } from "./preview.ts";

export const REPOSITORY = "israelhudson/flutter_code_push_example";
export const CHANNEL = "C0C8DUJB52L";
export const TEAM = "T09CYB7AS77";
export const SHARED_PROJECT = "uvfwvplcziehxrkidrxh";
export const ID = /^poc-[a-f0-9]{32}$/;
export type Data = Record<string, unknown>;
export type IO = {
  env: (key: string) => string | undefined;
  db: (path: string, data?: Data, method?: string) => Promise<any>;
  slack: (method: string, data: Data) => Promise<any>;
  fetch: typeof fetch;
  wait: (task: Promise<unknown>) => void;
  log: (event: string) => void;
};

export async function digest(text: string): Promise<string> {
  return [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)),
    ),
  ]
    .map((v) => v.toString(16).padStart(2, "0")).join("");
}
// Signature routine ported from amulets-release-lab 68941a3; routing is POC-only.
export async function validSignature(
  raw: string,
  ts: string,
  signature: string,
  secret: string,
  now = Date.now(),
) {
  if (
    !/^\d+$/.test(ts) || Math.abs(now / 1000 - Number(ts)) > 300 ||
    !/^v0=[a-f0-9]{64}$/.test(signature) || !secret
  ) return false;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
  return crypto.subtle.verify(
    "HMAC",
    key,
    Uint8Array.from(signature.slice(3).match(/../g)!, (v) => parseInt(v, 16)),
    new TextEncoder().encode(`v0:${ts}:${raw}`),
  );
}
export function isolated(url: string): string {
  const parsed = new URL(url);
  if (
    parsed.protocol !== "https:" ||
    !/^[a-z]{20}\.supabase\.co$/.test(parsed.hostname) ||
    parsed.hostname.startsWith(SHARED_PROJECT + ".") || parsed.username ||
    parsed.password || parsed.search || parsed.hash || parsed.port ||
    parsed.pathname !== "/"
  ) throw Error("Dedicated Supabase project required");
  return parsed.origin;
}
export function requireReady(io: IO) {
  isolated(io.env("SUPABASE_URL") ?? "");
  if (!["main", "slack-main"].includes(io.env("POC_SOURCE_BRANCH") ?? "slack-main")) {
    throw Error("Source lane rejected");
  }
  if (io.env("POC_ENABLED") !== "true") throw Error("POC disabled");
}
export function slackRequest(method: string, data: Record<string, unknown>, token: string) {
  const read = ["auth.test", "conversations.info", "conversations.members", "users.info"].includes(
    method,
  );
  if (!read && !["chat.postMessage", "chat.update", "views.open"].includes(method)) {
    throw Error("Slack method rejected");
  }
  const query = new URLSearchParams(Object.entries(data).map(([k, v]) => [k, String(v)]));
  return new Request(`https://slack.com/api/${method}${read ? "?" + query : ""}`, {
    method: read ? "GET" : "POST",
    redirect: "error",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json; charset=utf-8",
    },
    body: read ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(1600),
  });
}
export function runtime(): IO {
  return {
    env: (k) => Deno.env.get(k),
    fetch,
    wait: (task) => {
      const edge = (globalThis as unknown as {
        EdgeRuntime: { waitUntil: (p: Promise<unknown>) => void };
      }).EdgeRuntime;
      edge.waitUntil(task);
    },
    log: (event) => console.error(event),
    db: async (path, data, method = "POST") => {
      const base = isolated(Deno.env.get("SUPABASE_URL") ?? "");
      const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
      if (!key || !/^(rpc\/poc_[a-z_]+|poc_[a-z_]+(?:\?.*)?)$/.test(path)) {
        throw Error("Database scope rejected");
      }
      const r = await fetch(`${base}/rest/v1/${path}`, {
        method,
        redirect: "error",
        headers: {
          apikey: key,
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
        body: data ? JSON.stringify(data) : undefined,
        signal: AbortSignal.timeout(1800),
      });
      if (!r.ok) throw Error("Database rejected operation");
      const text = await r.text();
      return text ? JSON.parse(text) : null;
    },
    slack: async (method, data) => {
      if (
        ![
          "auth.test",
          "conversations.info",
          "conversations.members",
          "users.info",
          "chat.postMessage",
          "chat.update",
          "views.open",
        ].includes(method)
      ) throw Error("Slack method rejected");
      const token = Deno.env.get("POC_SLACK_BOT_TOKEN");
      if (!token) throw Error("POC bot missing");
      const r = await fetch(slackRequest(method, data, token));
      const result = await r.json();
      if (!r.ok || result.ok !== true) throw Error("Slack rejected operation");
      return result;
    },
  };
}
export async function state(io: IO, id: string) {
  if (!ID.test(id)) throw Error("Candidate ID rejected");
  const c = await io.db("rpc/poc_state", { p_id: id });
  if (
    !c || c.channel_id !== CHANNEL || c.team_id !== TEAM || c.is_lab !== true ||
    !["none", "github_test"].includes(c.publication_scope)
  ) throw Error("Candidate scope rejected");
  return c;
}
export function card(c: any, now = Date.now()) {
  const report = JSON.parse(c.report_text);
  const roles = new Set(c.approvals?.map((a: any) => a.role) ?? []);
  const expired = Date.parse(c.expires_at) <= now;
  const published = c.status === "published";
  const finalTag = published ? "poc-v" + c.version : null;
  const blocked = !published && (expired ||
    ["adjustment_requested", "cancelled", "expired"].includes(c.status));
  const title = published
    ? `✅ Versão ${c.version} publicada · GitHub TESTE`
    : blocked
    ? "Ajuste ou prazo encerrado · candidata bloqueada"
    : `Flutter POC · ${roles.size}/2 aceites`;
  const section = (text: string) => ({
    type: "section",
    text: { type: "plain_text", text },
  });
  const solo = c.mode === "solo_test"
    ? "Solo: Israel representa os dois papéis; não são dois revisores reais."
    : "Dois revisores independentes.";
  const elements: any[] = [{
    type: "button",
    action_id: "poc_preview",
    value: c.id,
    text: { type: "plain_text", text: published ? "Preview aprovado" : "Preview da RC" },
    url: report.preview_url,
  }, {
    type: "button",
    action_id: "poc_changelog",
    value: c.id,
    text: { type: "plain_text", text: "Changelog e execução" },
    url: report.run_url,
  }];
  if (published) {
    elements.unshift({
      type: "button",
      action_id: "poc_release",
      value: c.id,
      text: { type: "plain_text", text: "Abrir Release" },
      url: `https://github.com/israelhudson/flutter_code_push_example/releases/tag/${finalTag}`,
    });
  }
  if (!blocked && c.status === "pending") {
    for (
      const [role, label] of [["technical", "Aceite técnico"], [
        "business",
        "Aceite de negócio",
      ]]
    ) {
      if (!roles.has(role)) {
        elements.push({
          type: "button",
          action_id: `poc_${role}`,
          value: c.id,
          text: { type: "plain_text", text: label },
        });
      }
    }
  }
  if (!blocked && ["pending", "approved"].includes(c.status)) {
    elements.push({
      type: "button",
      action_id: "poc_adjust",
      value: c.id,
      text: { type: "plain_text", text: "Solicitar ajuste" },
    });
  }
  return {
    channel: CHANNEL,
    text: published ? `${title} · ${finalTag}` : `${c.rc_tag} · ${title}`,
    parse: "none",
    link_names: false,
    unfurl_links: false,
    unfurl_media: false,
    blocks: [
      { type: "header", text: { type: "plain_text", text: title } },
      section(
        `${published ? finalTag + "\nPromovida de: " + c.rc_tag : c.rc_tag}\n${report.title}\n${
          (report.changelog || "Consulte o changelog completo na execução.")
            .slice(0, 1400)
        }`,
      ),
      section(
        `Técnico: ${
          roles.has("technical") ? "aceito" : "pendente"
        } (${c.technical_reviewer})\nNegócio: ${
          roles.has("business") ? "aceito" : "pendente"
        } (${c.business_reviewer})\n${solo}\nEstado: ${
          published ? "Publicada no GitHub (teste)" : c.status
        }\n${c.adjustment_reason ? "Motivo: " + c.adjustment_reason : ""}`,
      ),
      {
        type: "context",
        elements: [{
          type: "plain_text",
          text: `SHA ${c.source_sha.slice(0, 12)} · ${
            published
              ? "Aprovações concluídas; RC preservada como histórico"
              : "validade 36h · encerra " + c.expires_at
          }\nPublicação: ${
            c.publication_scope === "none" ? "desligada" : "somente GitHub TESTE"
          }. A thread fica livre para conversa.`,
        }],
      },
      { type: "actions", elements },
    ],
  };
}
export async function updateCard(io: IO, id: string) {
  let c = await state(io, id);
  if (!c.message_ts) return;
  for (let i = 0; i < 4; i++) {
    const message = card(c);
    await io.slack("chat.update", { ...message, ts: c.message_ts });
    const next = await state(io, id);
    if (JSON.stringify(message) === JSON.stringify(card(next))) return;
    c = next;
  }
  throw Error("Card requires reconciliation");
}
export async function sendNotice(io: IO, id: string, event: string) {
  const claim = await io.db("rpc/poc_notice", {
    p_id: id,
    p_event: event,
    p_claim: true,
  });
  if (!claim.send) return;
  const finish = (value: Data) =>
    io.db("rpc/poc_finish_notice", {
      p_id: id,
      p_event: event,
      p_recipient: claim.recipient,
      ...value,
    });
  try {
    const live = await io.db("rpc/poc_notice", {
      p_id: id,
      p_event: event,
      p_claim: false,
    });
    if (!live.send || live.recipient !== claim.recipient) {
      await finish({ p_state: "skipped" });
      return;
    }
    const c = await state(io, id);
    let message: Data;
    if (event === "card") message = card(c);
    else if (event === "published") {
      message = {
        channel: CHANNEL,
        text:
          `${c.rc_tag}: Release de TESTE publicada no GitHub. SHA ${c.source_sha}. Nenhum patch distribuído.`,
        unfurl_links: false,
      };
    } else {
      if (!/^U[A-Z0-9]+$/.test(live.recipient) || !c.message_ts) {
        throw Error("Private recipient rejected");
      }
      const url = `https://amuletsworkspace.slack.com/archives/${CHANNEL}/p${
        c.message_ts.replace(".", "")
      }`;
      message = {
        channel: live.recipient,
        text: event === "approved"
          ? `${c.rc_tag}: 2/2 aceites. A candidata que você criou foi aprovada. Publicação: ${c.publication_scope}.`
          : `${c.rc_tag}: 1/2 aceites. Falta sua avaliação ${
            live.pending_role === "technical" ? "técnica" : "de negócio"
          }.`,
        unfurl_links: false,
        unfurl_media: false,
        blocks: [{
          type: "section",
          text: {
            type: "plain_text",
            text: event === "approved"
              ? `${c.rc_tag}: dois papéis aceitos. ${
                c.mode === "solo_test" ? "Ensaio solo." : "Revisores independentes."
              }`
              : `${c.rc_tag}: sua avaliação ${
                live.pending_role === "technical" ? "técnica" : "de negócio"
              } está pendente.`,
          },
        }, {
          type: "actions",
          elements: [{
            type: "button",
            text: { type: "plain_text", text: "Abrir candidata" },
            url,
          }],
        }],
      };
    }
    const sent = await io.slack("chat.postMessage", message);
    if (
      !/^\d+\.\d+$/.test(sent.ts ?? "") ||
      (event === "card" || event === "published"
        ? sent.channel !== CHANNEL
        : !/^D[A-Z0-9]+$/.test(sent.channel ?? ""))
    ) throw Error("Slack receipt rejected");
    await finish({ p_state: "sent", p_channel: sent.channel, p_ts: sent.ts });
  } catch {
    await finish({ p_state: "uncertain" });
    throw Error("Notice uncertain; reconcile before retry");
  }
}
export async function dispatch(io: IO, id: string) {
  const token = io.env("POC_GITHUB_DISPATCH_TOKEN");
  if (!token) return; // Missing credential must not reserve an event that was never attempted.
  const event = "dispatch";
  const claim = await io.db("rpc/poc_notice", {
    p_id: id,
    p_event: event,
    p_claim: true,
  });
  if (!claim.send) return;
  try {
    const live = await io.db("rpc/poc_notice", {
      p_id: id,
      p_event: event,
      p_claim: false,
    });
    if (!live.send) {
      await io.db("rpc/poc_finish_notice", {
        p_id: id,
        p_event: event,
        p_recipient: claim.recipient,
        p_state: "skipped",
      });
      return;
    }
    const r = await io.fetch(
      `https://api.github.com/repos/${REPOSITORY}/actions/workflows/poc-slack-publish.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: io.env("POC_SOURCE_BRANCH") ?? "slack-main",
          inputs: { candidate: id },
        }),
        signal: AbortSignal.timeout(5000),
      },
    );
    if (r.status !== 204) throw Error("Dispatch not acknowledged");
    await io.db("rpc/poc_finish_notice", {
      p_id: id,
      p_event: event,
      p_recipient: claim.recipient,
      p_state: "sent",
      p_receipt: { acknowledged: true, workflow: "poc-slack-publish.yml" },
    });
  } catch {
    await io.db("rpc/poc_finish_notice", {
      p_id: id,
      p_event: event,
      p_recipient: claim.recipient,
      p_state: "uncertain",
    });
    throw Error("Dispatch uncertain; reconcile");
  }
}
async function progress(io: IO, id: string) {
  await updateCard(io, id);
  const c = await state(io, id);
  const roles = new Set(c.approvals.map((a: any) => a.role));
  if (roles.size === 1 && c.status === "pending") {
    await sendNotice(
      io,
      id,
      `review_pending:${roles.has("technical") ? "business" : "technical"}`,
    );
  }
  if (roles.size === 2 && c.status === "approved") {
    await sendNotice(io, id, "approved");
    await dispatch(io, id);
  }
}
async function feedback(io: IO, payload: any, text: string) {
  try {
    const url = new URL(payload.response_url);
    if (
      url.protocol !== "https:" || url.hostname !== "hooks.slack.com" || url.port || url.username ||
      url.password || !url.pathname.startsWith("/actions/")
    ) return;
    await io.fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response_type: "ephemeral", replace_original: false, text }),
      signal: AbortSignal.timeout(1500),
    });
  } catch {
    io.log("poc_private_feedback_unavailable");
  }
}
export function slackHandler(io: IO) {
  return async (request: Request): Promise<Response> => {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }
    const raw = await request.text();
    if (raw.length > 65536) {
      return new Response("Payload too large", { status: 413 });
    }
    if (
      !await validSignature(
        raw,
        request.headers.get("x-slack-request-timestamp") ?? "",
        request.headers.get("x-slack-signature") ?? "",
        io.env("POC_SLACK_SIGNING_SECRET") ?? "",
      )
    ) return new Response("Unauthorized", { status: 401 });
    try {
      requireReady(io);
      const p = JSON.parse(new URLSearchParams(raw).get("payload") ?? "null");
      if (
        p?.api_app_id !== io.env("POC_SLACK_APP_ID") || p.team?.id !== TEAM ||
        !/^U[A-Z0-9]+$/.test(p.user?.id ?? "")
      ) throw Error("Invalid app context");
      if (
        ["view_submission", "view_closed"].includes(p.type) &&
        p.view?.callback_id === "poc_adjustment"
      ) {
        const meta = JSON.parse(p.view.private_metadata);
        if (!ID.test(meta.id) || !/^[a-f0-9]{64}$/.test(meta.token)) {
          throw Error("Invalid modal");
        }
        const c = await state(io, meta.id);
        const reason = p.view.state?.values?.adjustment?.reason?.value;
        if (
          p.type === "view_submission" &&
          (typeof reason !== "string" || reason.trim().length < 3 ||
            reason.length > 1000)
        ) {
          return Response.json({
            response_action: "errors",
            errors: { adjustment: "Informe o motivo, de 3 a 1000 caracteres." },
          });
        }
        await io.db("rpc/poc_action", {
          p_id: c.id,
          p_action: p.type === "view_closed" ? "cancel_adjustment" : "adjust",
          p_user: p.user.id,
          p_team: TEAM,
          p_channel: CHANNEL,
          p_ts: c.message_ts,
          p_reason: reason ?? null,
          p_token: meta.token,
        });
        io.wait(
          progress(io, c.id).catch(() => io.log("poc_adjustment_refresh_failed")),
        );
        return Response.json({ response_action: "clear" });
      }
      const a = p.actions?.[0];
      if (
        p.type !== "block_actions" || p.actions.length !== 1 ||
        ![
          "poc_technical",
          "poc_business",
          "poc_adjust",
          "poc_preview",
          "poc_changelog",
          "poc_release",
          "poc_workflow_link",
        ].includes(
          a?.action_id,
        ) || !ID.test(a?.value ?? "") || p.channel?.id !== CHANNEL ||
        (p.container?.channel_id && p.container.channel_id !== CHANNEL) ||
        !/^\d+\.\d+$/.test(p.container?.message_ts ?? "")
      ) throw Error("Invalid interaction");
      // URL buttons still produce callbacks. ACK navigation without voting,
      // creating notices, or granting any publication capability.
      if (
        ["poc_preview", "poc_changelog", "poc_release", "poc_workflow_link"].includes(a.action_id)
      ) {
        return new Response("");
      }
      const input = {
        p_id: a.value,
        p_user: p.user.id,
        p_team: TEAM,
        p_channel: CHANNEL,
        p_ts: p.container.message_ts,
      };
      io.wait(
        (async () => {
          if (a.action_id === "poc_adjust") {
            const token = await digest(raw);
            await io.db("rpc/poc_action", {
              ...input,
              p_action: "open_adjustment",
              p_token: token,
            });
            await io.slack("views.open", {
              trigger_id: p.trigger_id,
              view: {
                type: "modal",
                callback_id: "poc_adjustment",
                notify_on_close: true,
                private_metadata: JSON.stringify({ id: a.value, token }),
                title: { type: "plain_text", text: "Solicitar ajuste" },
                submit: { type: "plain_text", text: "Registrar" },
                close: { type: "plain_text", text: "Voltar" },
                blocks: [{
                  type: "input",
                  block_id: "adjustment",
                  label: { type: "plain_text", text: "O que precisa mudar?" },
                  element: {
                    type: "plain_text_input",
                    action_id: "reason",
                    multiline: true,
                    min_length: 3,
                    max_length: 1000,
                  },
                }],
              },
            });
          } else {
            const result = await io.db("rpc/poc_action", {
              ...input,
              p_action: a.action_id.slice(4),
            });
            await feedback(
              io,
              p,
              `${result.approvals.length}/2 aceites registrados. ${
                result.mode === "solo_test"
                  ? "Ensaio solo: os dois papéis são seus."
                  : "Revisores independentes."
              } Consulte o cartão para acompanhar a candidata.`,
            );
            await progress(io, a.value).catch(() => io.log("poc_vote_saved_notification_failed"));
          }
        })().catch(async () => {
          io.log("poc_action_not_confirmed");
          await feedback(
            io,
            p,
            "Não foi possível confirmar esta operação. Confira seu papel e a validade da candidata. A publicação não é autorizada por este aviso.",
          );
        }),
      );
      return new Response(""); // ACK precedes DB/card/DM work; logs never contain payload or credentials.
    } catch {
      return new Response("Interação indisponível ou fora da POC", {
        status: 403,
      });
    }
  };
}

async function github(io: IO, path: string) {
  const r = await io.fetch(
    `https://api.github.com/repos/${REPOSITORY}/${path}`,
    {
      redirect: "error",
      headers: {
        Accept: "application/vnd.github+json",
        ...(io.env("POC_GITHUB_DISPATCH_TOKEN")
          ? { Authorization: `Bearer ${io.env("POC_GITHUB_DISPATCH_TOKEN")}` }
          : {}),
      },
      signal: AbortSignal.timeout(3000),
    },
  );
  if (r.status === 404) return null;
  if (!r.ok) throw Error("GitHub verification unavailable");
  return r.json();
}
export function controlHandler(io: IO) {
  return async (request: Request): Promise<Response> => {
    if (request.method === "GET") {
      return Response.json({
        protocol: 1,
        repository: REPOSITORY,
        channel: CHANNEL,
        enabled: io.env("POC_ENABLED") === "true",
        publication_enabled: io.env("POC_PUBLICATION_ENABLED") === "true",
      });
    }
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }
    try {
      requireReady(io);
      const raw = await request.text();
      if (raw.length > 65536) return new Response("Too large", { status: 413 });
      const input = JSON.parse(raw);
      const publication = ["claim", "complete", "state"].includes(
        input.operation,
      );
      const secret = io.env(
        publication ? "POC_PUBLICATION_SECRET" : "POC_REGISTRATION_SECRET",
      );
      if (
        !secret ||
        await digest(request.headers.get("authorization") ?? "") !==
          await digest(`Bearer ${secret}`)
      ) return new Response("Unauthorized", { status: 401 });
      if (!/^\d+$/.test(String(input.run_id))) throw Error("Run required");
      const run = await github(io, `actions/runs/${input.run_id}`);
      const cfg = (await io.db("poc_config?flow=eq.flutter-code-push", undefined, "GET"))[
        0
      ];
      const operator = (await io.db(
        `poc_user_directory?github_login=eq.${cfg.operator_github}`,
        undefined,
        "GET",
      ))[0];
      const expectedWorkflow = publication ? "poc-slack-publish.yml" : "poc-slack-prepare.yml";
      if (
        !cfg.enabled || !run ||
        run.head_branch !== (io.env("POC_SOURCE_BRANCH") ?? "slack-main") ||
        run.event !== "workflow_dispatch" ||
        run.path !== `.github/workflows/${expectedWorkflow}` ||
        run.actor?.id !== operator.github_id ||
        run.triggering_actor?.id !== operator.github_id
      ) throw Error("Trusted workflow/operator required");
      if (input.operation === "plan") {
        if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(input.version)) {
          throw Error("Version required");
        }
        const scope = input.publication_scope ?? "none";
        if (
          !["none", "github_test"].includes(scope) ||
          (scope === "github_test" &&
            (!cfg.publication_enabled || io.env("POC_PUBLICATION_ENABLED") !== "true"))
        ) throw Error("Publication scope disabled");
        const rows = await io.db(
          "poc_candidates?order=created_at.desc",
          undefined,
          "GET",
        );
        const wanted = input.version.split(".").map((n: string) => BigInt(n));
        if (
          rows.some((c: any) => {
            if (c.status !== "published") return false;
            const published = c.version.split(".").map((n: string) => BigInt(n));
            for (let i = 0; i < 3; i++) {
              if (published[i] !== wanted[i]) return published[i] > wanted[i];
            }
            return true;
          })
        ) throw Error("Version already published or older");
        const retry = rows.find((c: any) =>
          c.version === input.version && c.status === "pending" && !c.message_ts &&
          JSON.parse(c.report_text).run_url ===
            `https://github.com/${REPOSITORY}/actions/runs/${input.run_id}` &&
          JSON.parse(c.report_text).title === input.title && c.publication_scope === scope
        );
        if (retry) {
          return Response.json({
            id: retry.id,
            version: retry.version,
            rc_number: retry.rc_number,
            rc_tag: retry.rc_tag,
            source_sha: retry.source_sha,
            branch: `poc-release/${retry.version}`,
            previous_candidate: retry.previous_candidate,
            creator: retry.creator_github,
            publication_scope: retry.publication_scope,
          });
        }
        if (
          rows.some((c: any) =>
            ["pending", "approved", "publishing"].includes(c.status) &&
            Date.parse(c.expires_at) > Date.now()
          )
        ) throw Error("One active RC per flow");
        const prior = rows.filter((c: any) =>
          c.version === input.version
        ).sort((a: any, b: any) => b.rc_number - a.rc_number)[0];
        if (prior && prior.status !== "adjustment_requested") {
          throw Error("New RC requires adjustment");
        }
        const branch = `poc-release/${input.version}`;
        const ref = await github(
          io,
          `git/ref/heads/${encodeURIComponent(branch)}`,
        );
        return Response.json({
          id: `poc-${crypto.randomUUID().replaceAll("-", "")}`,
          version: input.version,
          rc_number: (prior?.rc_number ?? 0) + 1,
          rc_tag: `poc-v${input.version}-rc.${(prior?.rc_number ?? 0) + 1}`,
          source_sha: ref?.object?.sha ?? run.head_sha,
          branch,
          previous_candidate: prior?.id ?? null,
          creator: operator.github_login,
          publication_scope: scope,
        });
      }
      if (input.operation === "register") {
        const r = JSON.parse(input.report_text);
        const ref = await github(
          io,
          `git/ref/tags/${encodeURIComponent(r.rc_tag)}`,
        );
        if (
          !ID.test(r.id) ||
          r.run_url !==
            `https://github.com/${REPOSITORY}/actions/runs/${input.run_id}` ||
          ref?.object?.type !== "commit" || ref.object.sha !== r.source_sha
        ) throw Error("Tag/report diverged");
        const bot = await io.slack("auth.test", {});
        if (
          bot.team_id !== TEAM || !io.env("POC_SLACK_BOT_USER_ID") ||
          bot.user_id !== io.env("POC_SLACK_BOT_USER_ID") ||
          (bot.user_id === "U0C750FTCS3" && io.env("POC_SHARED_APP_ROUTING") !== "true")
        ) throw Error("POC bot/routing configuration rejected");
        let cursor = "", members: string[] = [];
        for (let page = 0; page < 20; page++) {
          const result = await io.slack("conversations.members", {
            channel: CHANNEL,
            limit: 200,
            ...(cursor ? { cursor } : {}),
          });
          members = members.concat(result.members ?? []);
          cursor = result.response_metadata?.next_cursor ?? "";
          if (!cursor) break;
        }
        if (
          cursor ||
          ![
            bot.user_id,
            cfg.technical_reviewer,
            cfg.business_reviewer,
            operator.slack_user_id,
          ].every((u) => members.includes(u))
        ) throw Error("Bot/reviewers must belong to lab channel");
        if (r.publication_scope === "github_test" && io.env("POC_PUBLICATION_ENABLED") !== "true") {
          throw Error("Publication scope disabled");
        }
        await verifyPreview(io, r);
        const c = await io.db("rpc/poc_register", {
          p_report: input.report_text,
          p_digest: input.report_digest,
          p_creator: operator.github_login,
          p_scope: r.publication_scope,
        });
        io.wait(
          sendNotice(io, c.id, "card").catch(() => io.log("poc_card_send_uncertain")),
        );
        return Response.json({
          id: c.id,
          status: c.status,
          message_delivery: "check persisted receipt",
        });
      }
      if (input.operation === "delivery" && ID.test(input.candidate ?? "")) {
        const c = await state(io, input.candidate);
        if (
          JSON.parse(c.report_text).run_url !==
            `https://github.com/${REPOSITORY}/actions/runs/${input.run_id}`
        ) throw Error("Original preparation run required");
        const notices = await io.db(
          `poc_private_notices?candidate_id=eq.${c.id}&event=eq.card`,
          undefined,
          "GET",
        );
        return Response.json({
          candidate: c.id,
          status: c.status,
          message_ts: c.message_ts,
          delivery: notices[0]?.state ?? "pending",
        });
      }
      if (publication && ID.test(input.candidate ?? "")) {
        const c = await state(io, input.candidate);
        if (input.operation === "state") return Response.json(c);
        if (io.env("POC_PUBLICATION_ENABLED") !== "true") {
          throw Error("Publication disabled");
        }
        const ref = await github(
          io,
          `git/ref/tags/${encodeURIComponent(c.rc_tag)}`,
        );
        if (ref?.object?.type !== "commit" || ref.object.sha !== c.source_sha) {
          throw Error("Frozen tag changed");
        }
        if (input.operation === "claim") await verifyPreview(io, JSON.parse(c.report_text));
        if (input.operation === "complete") {
          const release = await github(
            io,
            `releases/tags/${encodeURIComponent("poc-v" + c.version)}`,
          );
          const final = await github(
            io,
            `git/ref/tags/${encodeURIComponent("poc-v" + c.version)}`,
          );
          if (
            release?.id !== input.receipt?.release_id || release?.draft ||
            release?.prerelease !== true || final?.object?.type !== "commit" ||
            final.object.sha !== c.source_sha
          ) throw Error("Publication receipt not independently verified");
        }
        const result = await io.db("rpc/poc_publish", {
          p_id: c.id,
          p_operation: input.operation,
          p_run: String(input.run_id),
          p_receipt: input.receipt ?? null,
        });
        if (input.operation === "complete") {
          io.wait(
            (async () => {
              await updateCard(io, c.id);
              await sendNotice(io, c.id, "published");
            })().catch(() => io.log("poc_publication_notice_uncertain")),
          );
        }
        return Response.json(result);
      }
      throw Error("Operation unavailable");
    } catch {
      io.log("poc_control_not_confirmed");
      return new Response(
        "Operation unavailable; inspect safe server logs and persisted state",
        { status: 409 },
      );
    }
  };
}
