import { runtime } from "../_shared/poc.ts";
import { deliveryControlHandler } from "../_shared/delivery.ts";
Deno.serve(deliveryControlHandler(runtime()));
