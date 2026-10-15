import { CHANNEL, digest, type IO, REPOSITORY, requireReady, TEAM, validSignature } from "./poc.ts";
import { canonical, verifyCandidateEvidence } from "./preview.ts";
import { versionPresentation } from "./versions.ts";
const ID = /^delivery-[a-f0-9]{32}$/;
const SHA = /^[a-f0-9]{40}$/;
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
// This is a frozen selection, never a request-supplied grant of a role. The
// database resolves defaults for plan and compares them again while registering.
function reviewerSnapshot(value: any, solo: boolean) {
  if (
    !value || value.schema !== "delivery-reviewers-v1" || value.repository !== REPOSITORY ||
    value.team_id !== TEAM || typeof solo !== "boolean" || value.solo !== solo
  ) throw Error("Reviewer snapshot rejected");
  for (const role of ["technical", "business"]) {
    const person = value[role];
    if (
      !person || !UUID.test(person.id ?? "") || !Number.isSafeInteger(person.revision) ||
      person.revision < 1 || typeof person.name !== "string" || !person.name.trim() ||
      person.name.length > 120 || /[\u0000-\u001f]/.test(person.name) ||
      !/^U[A-Z0-9]+$/.test(person.slack_user ?? "") ||
      (person.github_user_id != null &&
        (!Number.isSafeInteger(person.github_user_id) || person.github_user_id < 1)) ||
      (person.github_login != null &&
        (typeof person.github_login !== "string" ||
          !/^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$/.test(person.github_login)))
    ) throw Error("Reviewer identity rejected");
  }
  const { technical, business } = value;
  if (
    !solo && (technical.id === business.id || technical.slack_user === business.slack_user ||
      (technical.github_user_id != null && technical.github_user_id === business.github_user_id))
  ) throw Error("Independent reviewers required");
  return value;
}
function verifyFrozenReviewers(candidate: any, manifest: any) {
  const hasSnapshot = candidate.reviewer_snapshot != null || manifest.reviewers != null ||
    candidate.technical_reviewer_id != null || candidate.business_reviewer_id != null;
  // Historical candidates predate the registry; never retroactively elect their reviewers.
  if (!hasSnapshot) return;
  const snapshot = reviewerSnapshot(candidate.reviewer_snapshot, candidate.solo);
  if (
    canonical(snapshot) !== canonical(manifest.reviewers) ||
    candidate.technical_reviewer_id !== snapshot.technical.id ||
    candidate.business_reviewer_id !== snapshot.business.id ||
    candidate.technical_user !== snapshot.technical.slack_user ||
    candidate.business_user !== snapshot.business.slack_user
  ) throw Error("Frozen reviewers differ");
}
function databaseReviewersRequired(policy: any) {
  if (
    policy.reviewer_source !== "database-v1" || typeof policy.solo !== "boolean" ||
    "technical" in policy || "business" in policy
  ) throw Error("Database reviewer policy required");
}
export function ready(io: IO) {
  requireReady(io);
  if (io.env("DELIVERY_V2_ENABLED") !== "true") throw Error("Delivery v2 disabled");
}
export async function github(io: IO, path: string) {
  const r = await io.fetch(`https://api.github.com/repos/${REPOSITORY}/${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${io.env("POC_GITHUB_DISPATCH_TOKEN")}`,
    },
    redirect: "error",
    signal: AbortSignal.timeout(3000),
  });
  if (r.status === 404) return null;
  if (!r.ok) throw Error("GitHub verification unavailable");
  return r.json();
}
async function file(io: IO, path: string, commit: string) {
  if (!SHA.test(commit)) throw Error("Immutable commit required");
  const r = await github(io, `contents/${path}?ref=${commit}`);
  if (r?.encoding !== "base64" || r.size > 65536) throw Error("Invalid GitHub file");
  return new TextDecoder().decode(
    Uint8Array.from(atob(r.content.replaceAll("\n", "")), (x) => x.charCodeAt(0)),
  );
}
async function state(io: IO, id: string) {
  if (!ID.test(id)) throw Error("Invalid candidate");
  const c = await io.db("rpc/delivery_state", { p_id: id });
  if (!c) throw Error("Unknown candidate");
  const text = await file(io, `candidates/${id}/manifest.json`, c.manifest_commit);
  if (await digest(text) !== c.manifest_digest) throw Error("Manifest changed");
  const report = JSON.parse(text);
  if (report.id !== c.id || report.source_sha !== c.source_sha || report.rc_tag !== c.rc_tag) {
    throw Error("Manifest identity differs");
  }
  verifyFrozenReviewers(c, report);
  return {
    ...c,
    report_text: text,
    report_digest: c.manifest_digest,
    publication_scope: c.scope,
    mode: c.solo ? "solo_test" : "two_reviewers",
    is_lab: true,
    approvals: [
      ...(c.technical_at ? [{ role: "technical", approved_at: c.technical_at }] : []),
      ...(c.business_at ? [{ role: "business", approved_at: c.business_at }] : []),
    ],
  };
}
export function deliveryCard(c: any, kind: string) {
  const label = c.status === "cancelled"
    ? `Versão ${c.version} cancelada`
    : c.status === "published"
    ? `Versão ${c.version} publicada`
    : c.status === "publishing"
    ? `Publicando ${c.version}`
    : c.status === "rejected"
    ? `Versão ${c.version} negada`
    : `Release Candidate ${c.version} · RC${c.rc_number}`;
  const tag = c.status === "published" ? `poc-v${c.version}` : c.rc_tag;
  const links = `<https://github.com/${REPOSITORY}/releases/tag/${tag}|Ver versão no GitHub>` +
    (c.publication_run
      ? `\n<https://github.com/${REPOSITORY}/actions/runs/${c.publication_run}|Acompanhar publicação>`
      : "");
  const roleName = kind === "technical" ? "técnico" : "de negócio";
  const blocks: any[] = [{ type: "section", text: { type: "plain_text", text: label } }, {
    type: "section",
    text: {
      type: "mrkdwn",
      text: `${c.technical_at ? "✅" : "🕒"} Técnico · <@${c.technical_user}>\n${
        c.business_at ? "✅" : "🕒"
      } Negócio · <@${c.business_user}>`,
    },
  }, { type: "section", text: { type: "mrkdwn", text: links } }];
  if (c.status === "published" && Array.isArray(c.versionRows)) {
    blocks.push({
      type: "section",
      text: {
        type: "plain_text",
        text: c.versionRows.map((r: string[]) => r.join(" · ")).join("\n"),
      },
    });
  }
  if (c.solo) {
    blocks.push({
      type: "context",
      elements: [{
        type: "plain_text",
        text: "Ensaio solo: a mesma pessoa representa os dois papéis.",
      }],
    });
  }
  if (kind !== "channel" && c.status === "pending" && !c[`${kind}_at`]) {
    blocks.push({
      type: "actions",
      elements: [
        {
          type: "button",
          action_id: `delivery_${kind}_accept`,
          text: { type: "plain_text", text: `Aceite ${roleName}` },
          value: c.id,
          style: "primary",
        },
        {
          type: "button",
          action_id: `delivery_${kind}_reject`,
          text: { type: "plain_text", text: "Negar versão" },
          value: c.id,
          style: "danger",
        },
      ],
    });
  }
  return { text: label, blocks };
}
export function deliverySlackHandler(io: IO) {
  return async (request: Request) => {
    try {
      ready(io);
      if (request.method !== "POST") return new Response("", { status: 405 });
      const raw = await request.text();
      if (
        raw.length > 65536 ||
        !await validSignature(
          raw,
          request.headers.get("x-slack-request-timestamp") ?? "",
          request.headers.get("x-slack-signature") ?? "",
          io.env("POC_SLACK_SIGNING_SECRET") ?? "",
        )
      ) return new Response("", { status: 401 });
      const p = JSON.parse(new URLSearchParams(raw).get("payload") ?? "{}");
      const a = p.actions?.[0],
        match = /^delivery_(technical|business)_(accept|reject)$/.exec(a?.action_id ?? "");
      if (
        p.type !== "block_actions" || p.actions?.length !== 1 || !match || !ID.test(a.value) ||
        p.api_app_id !== io.env("POC_SLACK_APP_ID") || p.team?.id !== TEAM ||
        p.channel?.id !== p.container?.channel_id || p.message?.ts !== p.container?.message_ts
      ) throw Error("Invalid interaction");
      // Commit the decision AND outbox before ACK. DB deadline is 1.8 s; no external calls here.
      await io.db("rpc/delivery_decide", {
        p_id: a.value,
        p_role: match[1],
        p_action: match[2],
        p_user: p.user?.id,
        p_team: p.team.id,
        p_channel: p.channel.id,
        p_message: p.message.ts,
      });
      // Wake-up is best effort only: the committed outbox survives a lost dispatch.
      io.wait(
        io.fetch(
          `https://api.github.com/repos/${REPOSITORY}/actions/workflows/delivery-worker.yml/dispatches`,
          {
            method: "POST",
            redirect: "error",
            signal: AbortSignal.timeout(2000),
            headers: {
              Authorization: `Bearer ${io.env("POC_GITHUB_DISPATCH_TOKEN")}`,
              Accept: "application/vnd.github+json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ ref: io.env("DELIVERY_SOURCE_BRANCH") ?? "main" }),
          },
        ).then((r) => {
          if (r.status !== 204) io.log("delivery_worker_wakeup_pending");
        }).catch(() => io.log("delivery_worker_wakeup_pending")),
      );
      return new Response("");
    } catch {
      io.log("delivery_action_not_confirmed");
      return new Response(
        "Não foi possível confirmar a ação. Atualize a mensagem e tente novamente.",
        { status: 503 },
      );
    }
  };
}
export function deliveryControlHandler(io: IO) {
  return async (request: Request) => {
    try {
      ready(io);
      if (request.method !== "POST") return new Response("", { status: 405 });
      const raw = await request.text();
      if (raw.length > 65536) throw Error("Too large");
      const p = JSON.parse(raw),
        publication = ["state", "claim", "complete", "presentation"].includes(p.operation);
      const secret = io.env(publication ? "POC_PUBLICATION_SECRET" : "POC_REGISTRATION_SECRET");
      if (
        !secret ||
        await digest(request.headers.get("authorization") ?? "") !==
          await digest(`Bearer ${secret}`)
      ) return new Response("", { status: 401 });
      if (!/^\d+$/.test(String(p.run_id))) throw Error("Run required");
      const run = await github(io, `actions/runs/${p.run_id}`);
      const workflow = publication
        ? "delivery-publish.yml"
        : ["take", "finish", "send", "cancel", "compact"].includes(p.operation)
        ? "delivery-worker.yml"
        : "delivery-prepare.yml";
      const workerOperation = ["take", "finish", "send", "cancel", "compact"].includes(p.operation);
      const allowedPath = workerOperation
        ? ["delivery-worker.yml", "delivery-prepare.yml", "delivery-publish.yml"].some((w) =>
          run?.path === `.github/workflows/${w}`
        )
        : run?.path === `.github/workflows/${workflow}`;
      const sourceBranch = io.env("DELIVERY_SOURCE_BRANCH") ?? "main";
      const scheduled = run?.event === "schedule" &&
        run?.path === ".github/workflows/delivery-worker.yml" && run?.head_branch === "main";
      if (
        !run || !allowedPath ||
        (!scheduled && (run.head_branch !== sourceBranch || run.event !== "workflow_dispatch")) ||
        run.status !== "in_progress"
      ) throw Error("Wrong workflow");
      const cfg = JSON.parse(await file(io, "delivery/delivery-policy.json", run.head_sha));
      if (
        cfg.repository !== REPOSITORY || cfg.team_id !== TEAM || cfg.channel_id !== CHANNEL ||
        cfg.history_branch !== "codex/delivery-history" || cfg.source_branch !== sourceBranch ||
        cfg.schema !== "delivery-policy-v2"
      ) throw Error("Policy rejected");
      if (p.operation === "plan") databaseReviewersRequired(cfg);
      if (
        run.event !== "schedule" &&
        (run.actor?.id !== cfg.operator_github_id ||
          run.triggering_actor?.id !== cfg.operator_github_id)
      ) throw Error("Operator rejected");
      if (run.event === "schedule" && workflow !== "delivery-worker.yml") {
        throw Error("Unexpected schedule");
      }
      if (p.operation === "cancel") {
        if (
          run.event !== "workflow_dispatch" ||
          run.path !== ".github/workflows/delivery-worker.yml" || !ID.test(p.candidate)
        ) throw Error("Manual cancellation required");
        return Response.json(await io.db("rpc/delivery_cancel", { p_id: p.candidate }));
      }
      if (p.operation === "send") {
        const bot = await io.slack("auth.test", {});
        if (
          bot.team_id !== TEAM || bot.user_id !== io.env("POC_SLACK_BOT_USER_ID") ||
          bot.user_id === "U0C750FTCS3"
        ) throw Error("Dedicated bot required");
        const work = await io.db("rpc/delivery_begin", { p_id: p.task_id, p_lease: p.lease });
        const t = work.task, c = work.candidate;
        let receipt: string, channel: string | null = null, message: string | null = null;
        if (t.kind === "dispatch") {
          if (
            c.status !== "approved" || c.scope !== "github_test" ||
            io.env("POC_PUBLICATION_ENABLED") !== "true"
          ) throw Error("Dispatch blocked");
          const r = await io.fetch(
            `https://api.github.com/repos/${REPOSITORY}/actions/workflows/delivery-publish.yml/dispatches`,
            {
              method: "POST",
              redirect: "error",
              signal: AbortSignal.timeout(3000),
              headers: {
                Authorization: `Bearer ${io.env("POC_GITHUB_DISPATCH_TOKEN")}`,
                Accept: "application/vnd.github+json",
                "Content-Type": "application/json",
              },
              body: JSON.stringify({ ref: cfg.source_branch, inputs: { candidate: c.id } }),
            },
          );
          if (r.status !== 204) throw Error("Dispatch outcome not confirmed");
          receipt = "github-dispatch-204";
        } else if (["channel", "technical", "business"].includes(t.kind)) {
          if (c.status === "published") {
            const frozen = await state(io, c.id);
            const release = await github(io, `releases/tags/poc-v${c.version}`);
            if (!release) throw Error("Published release missing");
            c.versionRows = (await versionPresentation(io, frozen, release)).rows;
          }
          const isChannel = t.kind === "channel";
          const ts = isChannel ? c.channel_message : c[`${t.kind}_message`];
          const target = isChannel ? c.channel_id : (c[`${t.kind}_channel`] ?? c[`${t.kind}_user`]);
          const sent = await io.slack(ts ? "chat.update" : "chat.postMessage", {
            channel: target,
            ...(ts ? { ts } : {}),
            ...deliveryCard(c, t.kind),
          });
          channel = sent.channel;
          message = sent.ts;
          receipt = `slack:${channel}:${message}`;
        } else throw Error("Effect rejected");
        await io.db("rpc/delivery_finish", {
          p_id: t.id,
          p_lease: p.lease,
          p_receipt: receipt,
          p_channel: channel,
          p_message: message,
        });
        return Response.json({ task_id: t.id, receipt });
      }
      if (p.operation === "compact") {
        return Response.json({ removed: await io.db("rpc/delivery_compact", {}) });
      }
      if (p.operation === "take") {
        return Response.json(await io.db("rpc/delivery_take", { p_lease: p.lease }));
      }
      if (p.operation === "finish") {
        const task = await io.db("rpc/delivery_task", { p_id: p.task_id, p_lease: p.lease });
        if (!task || task.kind !== "history" || !SHA.test(p.receipt)) {
          throw Error("History receipt required");
        }
        const saved = JSON.parse(
          await file(io, `candidates/${task.candidate_id}/event-${task.revision}.json`, p.receipt),
        );
        if (canonical(saved) !== canonical(task.event)) throw Error("GitHub evidence differs");
        return Response.json(
          await io.db("rpc/delivery_finish", {
            p_id: p.task_id,
            p_lease: p.lease,
            p_receipt: p.receipt,
          }),
        );
      }
      if (p.operation === "plan") {
        if (
          !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(p.version) ||
          !["none", "github_test"].includes(p.publication_scope) ||
          !["full", "controls_only"].includes(p.validation_mode)
        ) throw Error("Invalid plan");
        if (p.publication_scope === "github_test" && io.env("POC_PUBLICATION_ENABLED") !== "true") {
          throw Error("Publication disabled");
        }
        const reviewers = reviewerSnapshot(
          await io.db("rpc/delivery_resolve_reviewers", {
            p_repository: REPOSITORY,
            p_team: TEAM,
            p_solo: cfg.solo,
          }),
          cfg.solo,
        );
        const tags = await github(io, "git/matching-refs/tags/poc-v");
        const requested = p.version.split(".").map(Number);
        const atLeast = (v: number[]) =>
          v[0] > requested[0] ||
          v[0] === requested[0] &&
            (v[1] > requested[1] || v[1] === requested[1] && v[2] >= requested[2]);
        if (
          !Array.isArray(tags) || tags.some((t: any) => {
            const m = /^refs\/tags\/poc-v(\d+)\.(\d+)\.(\d+)$/.exec(t.ref);
            return m && atLeast(m.slice(1).map(Number));
          })
        ) throw Error("Version already promoted or obsolete");
        const rows = await io.db("rpc/delivery_state", {});
        if (rows.some((c: any) => ["pending", "approved", "publishing"].includes(c.status))) {
          throw Error("Active evaluation");
        }
        const previous = rows.find((c: any) => c.version === p.version);
        if (previous && !["rejected", "cancelled"].includes(previous.status)) {
          throw Error("Version closed");
        }
        // Never reuse a legacy namespace or overwrite its tags/branch.
        const branch = await github(io, `git/ref/heads/poc-release/${p.version}`);
        if (branch && !previous) throw Error("Version already exists in legacy lane");
        const rc = (previous?.rc_number ?? 0) + 1;
        if (await github(io, `git/ref/tags/poc-v${p.version}-rc.${rc}`)) {
          throw Error("Existing orphan tag requires reconciliation");
        }
        return Response.json({
          id: "delivery-" + crypto.randomUUID().replaceAll("-", ""),
          version: p.version,
          rc_number: rc,
          rc_tag: `poc-v${p.version}-rc.${rc}`,
          source_sha: branch?.object?.sha ?? run.head_sha,
          branch: `poc-release/${p.version}`,
          creator: cfg.operator_github_login,
          publication_scope: p.publication_scope,
          validation_mode: p.validation_mode,
          previous_candidate: previous?.id ?? null,
          reviewers,
        });
      }
      if (p.operation === "register") {
        if (
          !ID.test(p.candidate) || !SHA.test(p.manifest_commit) ||
          !/^[a-f0-9]{64}$/.test(p.manifest_digest)
        ) throw Error("Manifest reference required");
        const text = await file(io, `candidates/${p.candidate}/manifest.json`, p.manifest_commit);
        if (await digest(text) !== p.manifest_digest) throw Error("Manifest digest differs");
        const r = JSON.parse(text);
        if (
          r.id !== p.candidate || r.repository !== REPOSITORY ||
          r.run_url !== `https://github.com/${REPOSITORY}/actions/runs/${p.run_id}` ||
          r.tooling_sha !== run.head_sha
        ) throw Error("Manifest provenance differs");
        const existing = await io.db("rpc/delivery_state", { p_id: r.id });
        if (existing) {
          // Retry an already-frozen manifest without electing anyone again. Old
          // manifests are allowed only here, never to create a new candidate.
          if (
            existing.id !== r.id || existing.manifest_commit !== p.manifest_commit ||
            existing.manifest_digest !== p.manifest_digest ||
            existing.source_sha !== r.source_sha ||
            existing.rc_tag !== r.rc_tag
          ) throw Error("Existing registration differs");
          verifyFrozenReviewers(existing, r);
        } else databaseReviewersRequired(cfg);
        const reviewers = r.reviewers != null
          ? reviewerSnapshot(r.reviewers, existing ? existing.solo : cfg.solo)
          : null;
        if (!existing && !reviewers) throw Error("Reviewer snapshot required");
        const tag = await github(io, `git/ref/tags/${r.rc_tag}`);
        if (tag?.object?.type !== "commit" || tag.object.sha !== r.source_sha) {
          throw Error("Tag differs");
        }
        if (existing) return Response.json(existing);
        await verifyCandidateEvidence(io, r);
        const auth = await io.slack("auth.test", {});
        if (
          auth.team_id !== TEAM || auth.user_id !== io.env("POC_SLACK_BOT_USER_ID") ||
          auth.user_id === "U0C750FTCS3"
        ) throw Error("Dedicated bot required");
        const registered = await io.db("rpc/delivery_register", {
          p_candidate: {
            id: r.id,
            repository: REPOSITORY,
            version: r.version,
            rc_number: r.rc_number,
            rc_tag: r.rc_tag,
            source_sha: r.source_sha,
            manifest_commit: p.manifest_commit,
            manifest_digest: p.manifest_digest,
            team_id: TEAM,
            channel_id: CHANNEL,
            reviewers,
            solo: cfg.solo,
            scope: r.publication_scope,
            previous_id: r.previous_candidate,
          },
        });
        verifyFrozenReviewers(registered, r);
        return Response.json(registered);
      }
      const c = await state(io, p.candidate);
      if (p.operation === "delivery") {
        return Response.json({
          id: c.id,
          delivery: c.channel_message ? "sent" : "pending",
          message_ts: c.channel_message,
        });
      }
      if (p.operation === "state") return Response.json(c);
      if (p.operation === "presentation") {
        return Response.json(
          await versionPresentation(io, c, await github(io, `releases/tags/poc-v${c.version}`)),
        );
      }
      if (["claim", "complete"].includes(p.operation)) {
        if (io.env("POC_PUBLICATION_ENABLED") !== "true") throw Error("Publication disabled");
        const tag = await github(io, `git/ref/tags/${c.rc_tag}`);
        if (tag?.object?.type !== "commit" || tag.object.sha !== c.source_sha) {
          throw Error("Candidate tag differs");
        }
        if (p.operation === "claim") await verifyCandidateEvidence(io, JSON.parse(c.report_text));
        else {
          const finalTag = `poc-v${c.version}`,
            ref = await github(io, `git/ref/tags/${finalTag}`),
            release = await github(io, `releases/tags/${finalTag}`);
          if (
            ref?.object?.type !== "commit" || ref.object.sha !== c.source_sha ||
            release?.id !== p.receipt?.release_id || release.draft !== false ||
            release.prerelease !== false
          ) throw Error("Publication unproven");
        }
        const result = await io.db("rpc/delivery_publish", {
          p_id: c.id,
          p_run: String(p.run_id),
          p_complete: p.operation === "complete",
        });
        const published = c.status === "published"
          ? await github(io, `releases/tags/poc-v${c.version}`)
          : null;
        return Response.json({
          ...result,
          already_published: c.status === "published",
          receipt: published
            ? {
              tag: published.tag_name,
              release_id: published.id,
              release_url: published.html_url,
              source_sha: c.source_sha,
              report_digest: c.manifest_digest,
              distribution_performed: false,
            }
            : undefined,
        });
      }
      throw Error("Unknown operation");
    } catch {
      io.log("delivery_control_rejected");
      return new Response("Delivery operation not confirmed", { status: 409 });
    }
  };
}
