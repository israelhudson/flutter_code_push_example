import { runtime } from "../_shared/poc.ts";
import { routerHandler } from "../_shared/router.ts";
Deno.serve(routerHandler(runtime()));
