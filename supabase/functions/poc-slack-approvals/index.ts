import { runtime, slackHandler } from "../_shared/poc.ts";
Deno.serve(slackHandler(runtime()));
