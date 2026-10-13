import { controlHandler, runtime } from "../_shared/poc.ts";
Deno.serve(controlHandler(runtime()));
