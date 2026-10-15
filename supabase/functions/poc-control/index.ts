import { controlHandler, runtime } from "../_shared/poc.ts";
const io = runtime();
Deno.serve((request: Request) => {
  if (io.env("POC_LEGACY_RETIRED") === "true") {
    return new Response("Fluxo legado encerrado; histórico preservado no GitHub.", { status: 410 });
  }
  return controlHandler(io)(request);
});
