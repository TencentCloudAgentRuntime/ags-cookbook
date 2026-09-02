import "dotenv/config";

import { mysqlConfigFromEnv } from "./config.js";
import { runMigrations } from "./migrations.js";

const result = await runMigrations(mysqlConfigFromEnv());
console.log(`MySQL schema ready: ${result.applied.length} applied, ${result.skipped.length} already current`);
