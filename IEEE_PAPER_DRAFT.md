# IEEE Paper Draft: WebSwarm

> **Draft status:** This is a research-paper starting point, not a submission-ready manuscript. Replace every author placeholder, verify all implementation details against the final code, and complete the evaluation before making claims about accuracy or general effectiveness. The preliminary observation below describes one exploratory scan only.

## Working title

**WebSwarm: A Multi-Agent Framework for Browser-Based Web Application Testing**

**Authors:** [Author names]

**Affiliations:** [Department, institution, city, country]

**Corresponding author:** [Email]

## Abstract

Web application testing must cover dynamic interactions, input boundaries, and responsive layouts, yet manually maintained browser scripts can be costly to adapt as interfaces change. This paper presents WebSwarm, a prototype that combines language-model-guided browser actions with deterministic interface checks in a five-stage agent workflow. A React dashboard submits a test goal to a FastAPI service, which coordinates planning, navigation, functional interaction, input stress testing, and finding validation through LangGraph. Playwright executes browser actions against a target application, while WebSocket messages stream progress and screenshots to the dashboard. Groq-hosted language models provide planning and analysis; SQLite stores run records and reports. In one exploratory run against an intentionally defective demonstration application, the workflow completed and reported three candidate issues: horizontal navigation overflow at a 375-pixel viewport and two buttons that remained enabled after a click. The run demonstrates end-to-end operation, but it does not establish detection accuracy: the button checks did not verify duplicate network submissions, and the study used only one target and one run. We describe the system, report this preliminary observation, and define a reproducible evaluation plan for measuring detection quality, repeatability, completion rate, and execution cost.

**Index Terms—** web application testing, browser automation, large language model agents, software quality assurance, responsive design testing.

## I. Introduction

Web applications expose behavior through changing page structures, client-side state, asynchronous requests, and responsive layouts. A test suite can check known workflows reliably, but it may miss behaviors that were not anticipated when the test was written. Browser automation can exercise those workflows, although selectors and scripted paths often need maintenance when the interface changes. Language-model-based agents offer a way to select actions from page context, but their outputs can be inconsistent and should not be treated as proof that a defect exists.

WebSwarm explores a hybrid approach. It uses a language model to help plan and choose browser actions, then combines those actions with observable checks implemented in the browser. A workflow graph separates planning, navigation, functional interaction, stress testing, and validation. This separation makes the scan trace visible and provides places to add deterministic assertions and collect evidence.

The system is intended as a prototype for assisted exploratory testing, not as a replacement for a project's regression suite or a security certification tool. Its output is a set of candidate findings that should be reviewed against the target application's behavior.

This paper makes the following implementation contributions:

1. It describes a browser-testing prototype that coordinates five specialized stages with LangGraph.
2. It documents an integration of model-assisted planning and actions with Playwright-based browser observations, plus live progress streaming and persistent reports.
3. It reports a bounded exploratory run on one intentionally defective application and distinguishes observed checks from conclusions that the run did not verify.
4. It specifies an evaluation protocol for testing detection accuracy and repeatability against known seeded defects.

The paper addresses two research questions:

- **RQ1:** Can the prototype execute its complete scan workflow against a target web application and produce a persisted report?
- **RQ2:** How accurately and consistently does the prototype identify known interface defects across repeated scans and target applications?

The current evidence addresses RQ1 for one run. RQ2 remains open and requires the controlled evaluation described in Section VI.

## II. Background and Related Work

Interactive web-agent research provides useful context for WebSwarm. WebArena introduced a realistic, reproducible environment with functional websites and tasks intended to measure agent behavior in interactive web settings [1]. WebVoyager studied end-to-end web interaction on real-world websites and presented a benchmark and automatic evaluation protocol for web-agent tasks [2]. AgentBench evaluated language-model agents across multiple interactive environments, illustrating the importance of measuring an agent through environment outcomes rather than model responses alone [3].

WebSwarm addresses a narrower task: exploratory quality checks on a target web interface. Its objective is to surface candidate UI and interaction defects, not to complete general-purpose tasks or to compete with the cited benchmarks. These works motivate controlled environments, outcome-based metrics, and explicit evaluation protocols. A final paper should deepen this section with additional peer-reviewed studies specifically about automated web testing, test-oracle design, visual testing, and LLM-based software testing. Each added claim should be supported by a source that has been read and verified.

## III. System Architecture

WebSwarm has four principal layers:

1. **Dashboard layer:** A React single-page application lets a user configure scans and view live status, findings, history, and reports.
2. **API and persistence layer:** FastAPI exposes REST endpoints for authentication, scan creation, bugs, reports, vision records, and history. SQLite stores application and scan data.
3. **Agent orchestration layer:** A LangGraph state graph executes five stages in sequence. A Groq-backed language-model client supports model-assisted planning, browser action selection, and validation analysis.
4. **Browser execution layer:** Playwright launches Chromium, loads the target URL, performs supported interactions, and supplies page and viewport observations to the agents.

The frontend creates a run through `POST /api/v1/start-swarm`. The backend records a pending test and returns its identifier. The live-testing page then opens `/api/v1/ws/live-testing/{test_id}` and sends a start message. The backend updates run status, creates the browser page, and invokes the graph. WebSocket events stream status, logs, telemetry, findings, and JPEG screenshots. On completion, the backend persists the report and metrics and sends a final status event.

The graph order is **Planner → Navigation → Functional → Chaos → Validation**. The planner turns the testing goal into a strategy. The navigation stage loads and explores the page, then checks discovered links and assets. The functional stage requests and executes a supported click or fill action and performs interface checks, including a narrow viewport check. The Chaos stage exercises visible inputs with boundary and security-test strings and checks visible buttons after interaction. The Validation stage reviews accumulated execution logs and findings and assigns severity labels.

A bounded wrapper places time limits around agent stages. The Groq client manager supports configured API-key rotation and bounded request attempts. If a model request fails or times out, fallback behavior can allow the graph to continue. Model confidence values and LLM-generated explanations are reported as telemetry or analysis; they are not calibrated probabilities and do not independently verify a finding.

### A. Data Flow

1. A user supplies a target URL and optional testing goal.
2. The REST API creates a run record in SQLite.
3. A WebSocket connection starts the run and receives streaming events.
4. Playwright loads the target and supplies page state to the agent graph.
5. Agents request model assistance where implemented and execute supported browser actions.
6. Findings, metrics, and report content are persisted; the frontend displays the results.

### B. Technology Stack

| Component | Technology | Role |
|---|---|---|
| User interface | React, Vite, Tailwind CSS | Scan configuration and result dashboard |
| UI routing and visualization | React Router, Recharts, Lucide React | Page routing, charts, and icons |
| API server | Python, FastAPI, Uvicorn | REST endpoints and WebSocket server |
| Workflow | LangGraph, LangChain Core | Stateful, ordered agent execution |
| Language-model integration | `langchain-groq`, Groq API | Model-assisted planning and analysis |
| Browser automation | Playwright, Chromium | Target-site navigation and interactions |
| Persistence | SQLite | Run, bug, report, user, and vision records |
| Configuration | `python-dotenv` | Local backend environment configuration |

## IV. Methodology

### A. Scan Inputs and State

A scan accepts a target URL and an optional natural-language testing goal. The graph state carries the run identifier, URL, goal, current page snapshot, discovered URLs, execution logs, detected findings, and browser page. Keeping these values in shared graph state allows later stages to use observations from earlier stages.

### B. Model-Assisted Actions

The planner and interactive stages use a Groq-hosted model configured by `GROQ_MODEL`. The model proposes actions from the testing goal and page context. The backend maps supported outputs to Playwright operations. A model-generated explanation is treated as guidance; the browser result and the implemented checks provide the observable evidence. If the model response is invalid or the requested action cannot be executed, the behavior should be recorded as an action failure rather than silently described as a successful test.

### C. Deterministic Checks

The current implementation includes structural checks for links and assets, browser console errors, button disabled state after a click, input handling, and horizontal overflow at a 375-pixel viewport. The Chaos stage fills visible controls with boundary and security-test values. These checks are deterministic only to the extent that the underlying browser observation and assertion are deterministic; they do not automatically establish application impact.

For example, observing that a button remains enabled after one click establishes that the button was not disabled at the observation time. It does **not**, by itself, establish that a second request was sent or that duplicate application state was created. A duplicate-submission claim requires an additional oracle, such as counting network requests or checking resulting server-side state after repeated submissions.

### D. Evidence and Reporting

The system streams logs, screenshots, statuses, and telemetry to the dashboard and stores run results in SQLite. A final report includes candidate findings and model-generated technical analysis. In an evaluated version, every finding should include a reproducible action sequence, browser and viewport configuration, supporting screenshot or DOM/network evidence, and a clear distinction between observed facts and inferred impact.

## V. Preliminary Evaluation

### A. Evaluation Setting

One exploratory scan was run against a deliberately defective demonstration web application. The scan goal targeted duplicate-submission behavior and mobile navigation overflow at a 375-pixel viewport. The run used the five-stage workflow and completed with a persisted report. It recorded 32 agent actions and three findings, all assigned High severity by the validation stage.

### B. Observations

| Observation | Reported evidence | Interpretation limit |
|---|---|---|
| Mobile navigation overflow | Functional stage reported horizontal scroll at 375px and named `UL.nav-links`, `LI`, and `A` elements as overflowing. | One viewport and one application were tested; this does not establish responsive correctness across devices. |
| “Get Started” remains enabled | Chaos stage observed the button was not disabled after a click. | A repeated submission or duplicate network request was not measured. Treat duplicate submission as a risk, not a verified outcome. |
| “Subscribe” remains enabled | Chaos stage observed the button was not disabled after a click. | A repeated submission or duplicate network request was not measured. Treat duplicate submission as a risk, not a verified outcome. |

This run demonstrates that the application can complete the scan path, execute browser checks, call the validation model, stream findings, and save a report. It is a feasibility observation, not a measurement of precision, recall, generalization, or comparative performance. The three reported findings cannot be counted as three confirmed bugs without comparing them against an independently established ground truth.

### C. Evaluation Metrics for the Full Study

A controlled study should establish a defect ground-truth set before running WebSwarm. For each target and defect class, reviewers should record whether the defect is present and what observable evidence confirms it. Findings should then be matched to ground truth using a documented matching rule.

Recommended metrics are:

- **Precision:** `TP / (TP + FP)`, the proportion of reported findings that match a seeded or independently confirmed defect.
- **Recall:** `TP / (TP + FN)`, the proportion of known defects found by the system.
- **Completion rate:** completed scans divided by initiated scans.
- **Repeatability:** pairwise Jaccard similarity of findings across repeated runs on the same unchanged target: `|F_i ∩ F_j| / |F_i ∪ F_j|`.
- **Execution cost:** scan duration, model-request count, token usage, and monetary cost where available.
- **Evidence completeness:** proportion of findings with all required reproduction steps and supporting evidence.

Report denominators and confidence intervals where appropriate. Keep severity assignment quality separate from defect detection quality: a correctly detected defect can still receive an incorrect severity.

### D. Recommended Experimental Protocol

1. Build or select several test applications with documented, seeded defects across interaction, form, navigation, and responsive-layout categories.
2. Define ground truth before testing. Include both defective and clean controls to measure false positives.
3. Freeze each application version and record its commit, deployment URL, browser version, viewport, and test data.
4. Run each configuration multiple times. Record model name, prompt/goal, API configuration category (without storing secrets), scan time, token usage, and completion status.
5. Compare each finding with ground truth using two independent reviewers or a documented adjudication process.
6. Include a baseline, such as a manually authored Playwright suite or deterministic checks alone, to evaluate the value added by model-assisted stages.
7. Publish anonymized logs, test definitions, matching rules, and scripts where licensing and target-site permission allow.

## VI. Discussion

The prototype combines language-model flexibility with browser-based observation and a structured execution trace. Its current exploratory result shows that this architecture can reach a target site, run the agent sequence, surface a viewport overflow observation, and save a report. The value of this combination depends on whether the checks are reproducible and whether reported findings match real defects. Neither a polished report nor a high model confidence value substitutes for independent validation.

The division into stages can help diagnose failures. A model may select an inappropriate action, Playwright may fail to locate an element, the deterministic check may measure an incomplete condition, or the validation stage may overstate the evidence. Recording these events separately is necessary to evaluate each subsystem and identify where false positives or false negatives originate.

The screenshot-size comparison described by the implementation is a coarse heuristic based on compressed JPEG size. It is not a pixel-level visual diff and may change with compression or image content. It should be described as a structural signal unless the implementation is replaced with a validated visual comparison method.

## VII. Limitations and Threats to Validity

- **Small evaluation sample:** The current reported run covers one application and one execution. It does not support general claims about effectiveness.
- **No independent ground truth:** Findings have not been adjudicated against a labeled defect set; precision and recall are unknown.
- **Incomplete duplicate-submission oracle:** The button check observes disabled state after a click but does not establish duplicate requests or duplicate server-side effects.
- **Model variability:** Model outputs may vary by prompt, model release, page content, and API availability. Key rotation and fallbacks improve continuity but do not guarantee equivalent outputs.
- **Validation dependence:** The validation stage uses model-generated judgments and may share failure modes with earlier model-assisted stages.
- **Scope of checks:** Visible controls and a 375-pixel viewport do not represent all browser states, devices, accessibility requirements, or application workflows.
- **External-site instability:** Network, authentication, rate limiting, content changes, and third-party scripts can alter scan behavior.
- **Potential side effects:** Browser actions and boundary inputs can submit forms or change data. Testing should be limited to owned or explicitly authorized targets, preferably in a staging environment with disposable data.
- **Cost and latency:** The paper needs measured latency and model usage across repeated scans before discussing scalability or cost effectiveness.

## VIII. Ethics and Reproducibility

Only scan applications that the researchers own or have explicit permission to test. Use staging systems and synthetic accounts where possible. Avoid collecting personal data, submitting real purchases, or sending destructive inputs to production systems. Redact API keys, cookies, credentials, personal information, and sensitive target details from logs and artifacts before sharing them.

For reproducibility, archive the source revision, dependency versions, model identifier, prompt, browser version, viewport settings, test application revision, seeded defect list, raw event logs, and result-matching procedure. Do not publish `.env` files or API credentials. If target applications cannot be redistributed, provide a controlled local reproduction environment or detailed setup instructions.

## IX. Conclusion and Future Work

This paper describes WebSwarm, a prototype that coordinates model-assisted planning and browser interaction with deterministic interface checks in a five-stage workflow. A single exploratory scan completed against an intentionally defective demonstration application and produced candidate findings related to mobile overflow and button state. This establishes end-to-end feasibility for that run, but it does not establish defect-detection accuracy or prove that the button observations caused duplicate submissions.

The next research step is a controlled, repeated evaluation against applications with known defects and clean controls. The implementation should add a network- or state-based oracle for duplicate submissions, preserve evidence for every reported issue, and separate observed facts from model-generated impact explanations. Only after such a study should the paper make broader claims about effectiveness or reliability.

## References

[1] S. Zhou et al., “WebArena: A Realistic Web Environment for Building Autonomous Agents,” *arXiv preprint arXiv:2307.13854*, 2023. [Online]. Available: https://arxiv.org/abs/2307.13854

[2] H. He et al., “WebVoyager: Building an End-to-End Web Agent with Large Multimodal Models,” *arXiv preprint arXiv:2401.13919*, 2024. [Online]. Available: https://arxiv.org/abs/2401.13919

[3] X. Liu et al., “AgentBench: Evaluating LLMs as Agents,” *arXiv preprint arXiv:2308.03688*, 2023. [Online]. Available: https://arxiv.org/abs/2308.03688

> Verify the final bibliographic fields and citation formatting against the versions you actually read and the target venue’s instructions. Add primary sources on automated web testing, test oracles, visual testing, and LLM-based software testing before submission.

## IEEE Preparation Checklist

- Select a specific IEEE conference or journal and use its current Word or LaTeX template; requirements and page limits vary by venue.
- IEEE conference guidance recommends a single-paragraph abstract of at most 250 words and 3–5 keywords. The abstract above is a draft and should be revised after the evaluation is complete.
- Replace author, affiliation, funding, and contact placeholders with accurate information.
- Add the completed evaluation, comparison baseline, tables, figures, and reproducibility details.
- Confirm that each technical claim is supported by an appropriate citation or a reported experiment; verify references and remove uncited entries.
- Remove template instructions and placeholder text, check figure readability and PDF compliance, and follow the target venue's submission policies.

IEEE author guidance: [Structure Your Paper](https://conferences.ieeeauthorcenter.ieee.org/write-your-paper/structure-your-paper/) and [Authoring Tools and Templates](https://conferences.ieeeauthorcenter.ieee.org/write-your-paper/authoring-tools-and-templates/).
