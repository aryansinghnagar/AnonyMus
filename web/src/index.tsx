/* src/index.tsx — Solid.js application entry point */

import { render } from "solid-js/web";
import { Suspense } from "solid-js";
import "./index.css";
import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

render(
  () => (
    <Suspense fallback={<div class="auth-page"><div class="skeleton" style="width:120px;height:24px;"></div></div>}>
      <App />
    </Suspense>
  ),
  root
);
