# Day 6 — API Executor Agent


You’ll implement an **API test execution agent** that mirrors the UI executor you just built.
The agent will run a RestAssured + TestNG suite (Maven), parse results, ask an LLM to triage failures (**transient vs real**), and decide whether to retry based on policy.

> You can treat the **UI Executor** as your “reference implementation.”
> Your job is to adapt it for the API repo and TestNG/Surefire outputs.

---

## 📦 What you’re given / can assume

* An API automation repo already set up (from class notes):

  * Maven + Surefire + TestNG
  * Tests: `ApiSmokeTest` (pass), `ApiFlakyTest` (sometimes 503), `ApiDefectTest` (always wrong expectation)
  * Expected artifacts per run:

    ```
    target/surefire-reports/
      testng-results.xml
      TEST-com.example.tests.ApiSmokeTest.xml
      TEST-com.example.tests.ApiFlakyTest.xml
      TEST-com.example.tests.ApiDefectTest.xml
    ```
  * CLI knobs:

    * `-Dgroups=...` for TestNG groups
    * `-DBASE_URL=...` and `-DFLAKE_P=...` passed via Surefire `systemPropertyVariables`

> If you need the API setup steps again, check the class notes. (You don’t need to change the API repo for this assignment.)

---

## 🎯 Learning goals

* Reuse a **LangGraph** agent structure (state → nodes → graph → driver) for a different test stack.
* Parse **TestNG/Surefire XML** (not JUnit) and normalize results.
* Add a small **LLM triage** step (summary + `transient|real` labels).
* Implement **retry policies** (`none | always | flaky_only`) and keep behavior explainable.
* Produce a **unified JSON report** similar to the UI executor.

---

## 🗂️ Target folder structure (mirror the UI executor)

```
src/
  graph/
    api_executor/
      state.py
      nodes.py
      graph.py
    drivers/
      run_api_executor.py
  core/
    prompts/
      api_exec_system.txt      # NEW prompts for API triage
      api_exec_user.txt
```

> Keep function names and flow consistent with the UI executor. Students should be able to diff the two agents side-by-side.

---

## 🧱 Step-by-step tasks

### 1) `state.py`

Create `APIExecState` mirroring `UIExecState`, with API-specific defaults:

* `project: Literal["api"]`
* `cwd: str` (API repo path)
* `cmd: List[str]` (default: `["mvn", "-q", "-DskipTests=false", "test"]`)
* `junit_path: str` (use the Surefire/TestNG file: `target/surefire-reports/testng-results.xml`)
* `env: Dict[str,str]` (forwarded to Maven as system properties via Surefire)
* Attempts/approval: `attempt`, `max_attempts`, `approved`
* Process outputs: `run_rc`, `stdout`, `stderr`
* Results/summary/errors: same structure as UI executor
* Policy knobs: `policy: "always" | "flaky_only" | "none"`, `retry_scope: "full" | "failed_only"`
* LLM: `llm_summary: str`

### 2) `nodes.py`

Reuse the UI nodes but adapt for Maven + TestNG:

* **`prepare_config`**: set API defaults (cmd, junit path).
* **`execute_tests`**: run `subprocess.run(cmd, cwd=cwd, env=merged_env)`.

  * Map `state["env"]` to Maven system properties if you want (e.g., merge `{"BASE_URL": "...", "FLAKE_P": "1"}` into the environment; Surefire will read them).
* **`parse_results`** (API version): parse **`testng-results.xml`**.
  Hints for TestNG structure:

  * Root is `<testng-results>` with `<suite>` → `<test>` → `<class>` → `<test-method>` entries.
  * For failures, you’ll typically see:

    ```xml
    <test-method status="FAIL" name="...">
      <exception class="...">
        <message>...</message>
        <full-stacktrace>...</full-stacktrace>
      </exception>
    </test-method>
    ```
  * Normalize each case as:

    ```json
    {
      "name": "<method name>",
      "suite": "<class name>",
      "time_s": <float seconds if available>,
      "status": "passed|failed|skipped",
      "message": "<exception/message>",
      "details": "<full-stacktrace or combined long text>",
      "attempt": <int>,
      "project": "API"
    }
    ```
* **LLM triage** (`llm_triage`): copy the UI pattern, but load **API prompts** (see below).

  * Output: per-case `llm_label` (`transient|real`) and `llm_reason`, plus run-level `llm_summary`.
  * **Transient** signals (API): `5xx`, timeouts, connection reset, DNS issues, “read timed out”, “socket timeout”, rate limits, eventual consistency.
  * **Real** signals: assertion mismatches, contract errors (expected 201 got 200), `4xx` indicating client/test issue, schema mismatches, bad test data.
* **Approval checkpoint**: re-use the polished version (skip when failed=0, policy=none, or at last attempt).
* **Router**: same logic—prefer **LLM** labels under `flaky_only`, otherwise fall back to simple rules (e.g., message/details containing `5xx`, `timeout`, `connect`, `reset`, `temporarily unavailable`).

### 3) `graph.py`

Wire the same flow:

```
prepare → run → parse → llm_triage → approve → (retry → run … | END)
```

### 4) `run_api_executor.py` (driver)

Mirror the UI driver:

* CLI:

  * `--cwd` (API repo)
  * `--junit` (`target/surefire-reports/testng-results.xml`)
  * `--max-retries` (2)
  * `--policy` (`none|always|flaky_only`)
  * `--retry-scope` (keep `"full"` for v1)
  * `--env` (repeatable; e.g., `--env FLAKE_P=1 --env BASE_URL=https://httpbin.org`)
* Build the graph, invoke, print the final numeric summary, and **print LLM summary** if present.
* Save `outputs/api/api_execution_report.json` with `summary`, `results`, `errors`, and `llm_summary`.

### 5) Prompts (API-specific)

Create:

* `src/core/prompts/api_exec_system.txt`

  * Role: “API test failure triage assistant.”
  * Inputs: same payload shape as UI (attempt, policy, failed\_cases with name/suite/message/details).
  * Labeling rubric tailored for API (see transient/real above).
  * Strict JSON response with:

    ```json
    {
      "summary": "string",
      "labels": [{"name":"string","label":"transient|real","reason":"string"}]
    }
    ```
  * If unclear, default to `real`.

* `src/core/prompts/api_exec_user.txt`

  * Short instructions mirroring the UI user prompt: output strict JSON only, insert `{payload}` somewhere; your node should safely replace that token with `json.dumps(payload)` (do **not** use `.format(...)` on the template).

> Tip: You can copy the UI prompt texts and adapt the **LABELING GUIDELINES** section for API failures.

---

## ▶️ How to run (after you implement)

**macOS / Linux**

```bash
export API_REPO="/path/to/your/api-repo"

# Scenario A — flaky_only, force a flake
python -m src.graph.drivers.run_api_executor \
  --cwd "$API_REPO" \
  --junit target/surefire-reports/testng-results.xml \
  --max-retries 2 \
  --policy flaky_only \
  --env FLAKE_P=1

# Scenario B — none (no retry)
python -m src.graph.drivers.run_api_executor \
  --cwd "$API_REPO" \
  --junit target/surefire-reports/testng-results.xml \
  --max-retries 2 \
  --policy none \
  --env FLAKE_P=1

# Scenario C — always (force retry)
python -m src.graph.drivers.run_api_executor \
  --cwd "$API_REPO" \
  --junit target/surefire-reports/testng-results.xml \
  --max-retries 2 \
  --policy always
```

**Windows (PowerShell)**

```powershell
$env:API_REPO="C:\path\to\api-repo"

python -m src.graph.drivers.run_api_executor `
  --cwd "$env:API_REPO" `
  --junit target/surefire-reports/testng-results.xml `
  --max-retries 2 `
  --policy flaky_only `
  --env FLAKE_P=1

python -m src.graph.drivers.run_api_executor `
  --cwd "$env:API_REPO" `
  --junit target/surefire-reports/testng-results.xml `
  --max-retries 2 `
  --policy none `
  --env FLAKE_P=1

python -m src.graph.drivers.run_api_executor `
  --cwd "$env:API_REPO" `
  --junit target/surefire-reports/testng-results.xml `
  --max-retries 2 `
  --policy always
```

**What to expect** (mirrors UI):

* Console: numeric summary + **🧠 LLM summary** when failures exist.
* JSON report: `outputs/api/api_execution_report.json`

  * `llm_summary` (string), and per-failed case `llm_label` + `llm_reason`.
* Exit code: `0` only if the final summary has `failed=0`.

---

## ✅ Acceptance criteria

* Same graph shape as UI (`prepare → run → parse → llm_triage → approve → retry|END`).
* Parses **TestNG** XML correctly:

  * Each case normalized with `name`, `suite`, `status`, `time_s`, `message`, `details`.
* LLM triage:

  * Produces run-level `llm_summary`.
  * Adds per-case `llm_label` + `llm_reason` for current attempt’s failures.
  * Router prefers LLM under `flaky_only` and falls back to rules.
* Driver prints and saves a report to `outputs/api/api_execution_report.json`.
* Scenario A/B/C behave like the UI executor with analogous outcomes.

---

## 💡 Hints & pitfalls

* **Don’t use `str.format`** on prompt templates that contain `{`…`}` (JSON). Use `.replace("{payload}", json.dumps(payload))`.
* TestNG “long text” is usually inside `<full-stacktrace>`. Combine with `<message>` for `details`.
* For a simple **rule fallback**, treat `5xx`, “timeout”, “connect”, “reset”, “temporarily unavailable” as **transient**; treat `4xx`, assertion mismatches, schema errors as **real**.
* Keep `retry_scope="full"` for v1 (full suite rerun). “Failed-only” rerun is extra credit (see below).

---

## ⭐ Extra credit (optional)

* **Failed-only reruns:** parse failed class/methods and run:

  * `mvn -q -Dtest=ClassName#method test`, or
  * `-Dgroups=flaky` to rerun only transient-labeled tests, or
  * use TestNG’s generated `testng-failed.xml` if present.
* **Slack/Jira integration:** post `llm_summary` and attach the JSON report.
* **Guardrails:** automatically **deny retry** if `llm_label == "real"` on all failures.

---

## 📦 Deliverables

* Files:
  `src/graph/api_executor/state.py`, `nodes.py`, `graph.py`, `drivers/run_api_executor.py`,
  `src/core/prompts/api_exec_system.txt`, `api_exec_user.txt`.
* A sample run’s `outputs/api/api_execution_report.json`.
* A short note (or screenshot) showing Scenario A/B/C console output.

---