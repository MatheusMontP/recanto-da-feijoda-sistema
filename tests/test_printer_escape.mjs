import assert from "node:assert/strict";

import { escapeHtml } from "../frontend/js/modules/printer.js";

assert.equal(
  escapeHtml("<img src=x onerror=alert(1)>"),
  "&lt;img src=x onerror=alert(1)&gt;",
);
