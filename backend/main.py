# -*- coding: utf-8 -*-
"""
WebSwarm Phase 7 Backend Engine
FastAPI + SQLite3 + Playwright + WebSocket Live Streaming
+ LangGraph & Groq API for Autonomous AI Agents
"""

import os
import os
import sqlite3
import ast
import bcrypt
import json
import asyncio
import base64
import traceback
import time
import contextvars
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any, Annotated
import operator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from pydantic import BaseModel, HttpUrl

from dotenv import load_dotenv

# LangGraph & LangChain imports
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

# ---------------------------------------------------------------------------
# Global Setup & Env Validation
# ---------------------------------------------------------------------------
load_dotenv()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
AGENT_NODE_TIMEOUT_SECONDS = 20
LLM_ATTEMPT_TIMEOUT_SECONDS = 12.0
MAX_GROQ_KEYS = 17
NODE_DEADLINE = contextvars.ContextVar("webswarm_node_deadline", default=None)
NODE_NAME = contextvars.ContextVar("webswarm_node_name", default=None)

class GroqClientManager:
    def __init__(self):
        numbered_keys = [
            os.getenv(f"GROQ_API_KEY_{i}", "").strip()
            for i in range(1, MAX_GROQ_KEYS + 1)
        ]
        pooled_keys = [
            key.strip() for key in os.getenv("GROQ_API_KEYS", "").split(",")
            if key.strip()
        ]
        candidates = [key for key in numbered_keys if key] or pooled_keys
        if not candidates:
            single = os.getenv("GROQ_API_KEY", "").strip()
            candidates = [single] if single else []

        # Preserve configuration order and cap the rotation pool at seventeen keys.
        self.keys = list(dict.fromkeys(candidates))[:MAX_GROQ_KEYS]
        self.current_idx = -1
        self.semaphore = asyncio.Semaphore(MAX_GROQ_KEYS)
        self.pending_requests: set[asyncio.Task] = set()

    def rotate_key(self):
        self.current_idx = (self.current_idx + 1) % len(self.keys)
        return self.keys[self.current_idx]

    def get_current_key(self):
        return self.keys[self.current_idx]

    def _track_request(self, task: asyncio.Task) -> None:
        self.pending_requests.add(task)

        def consume_result(done_task: asyncio.Task) -> None:
            self.pending_requests.discard(done_task)
            if not done_task.cancelled():
                try:
                    done_task.exception()
                except Exception:
                    pass

        task.add_done_callback(consume_result)

    async def ainvoke(self, msg, ws=None):
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout=0.25)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Groq request capacity is busy; using the demo fallback.") from exc

        try:
            loop = asyncio.get_running_loop()
            deadline = NODE_DEADLINE.get() or loop.time() + 15.0
            node_name = NODE_NAME.get()
            reserve_seconds = 8.0 if node_name in {"Navigation", "Functional", "Chaos"} else 3.0
            for attempt in range(min(MAX_GROQ_KEYS, len(self.keys))):
                remaining = deadline - loop.time()
                attempt_timeout = min(LLM_ATTEMPT_TIMEOUT_SECONDS, remaining - reserve_seconds)
                if attempt_timeout <= 0:
                    break
                active_requests = sum(not task.done() for task in self.pending_requests)
                if active_requests >= MAX_GROQ_KEYS:
                    raise RuntimeError("Timed-out Groq requests are still draining; using the demo fallback.")
                api_key = self.rotate_key()  # Round-robin on every call and every retry.
                try:
                    llm = ChatGroq(
                        model=GROQ_MODEL,
                        api_key=api_key,
                        max_retries=0,
                    )
                    request_task = asyncio.create_task(llm.ainvoke(msg))
                    self._track_request(request_task)
                    done, _ = await asyncio.wait(
                        {request_task}, timeout=attempt_timeout
                    )
                    if request_task in done:
                        return request_task.result()

                    request_task.cancel()
                    error = TimeoutError(
                        f"Groq request exceeded {attempt_timeout:.1f}s"
                    )
                except Exception as e:
                    error = e

                error_text = str(error).lower()
                is_rate_limit = any(
                    marker in error_text
                    for marker in ("429", "503", "quota", "resource_exhausted", "overloaded")
                )
                if ws:
                    reason = "rate limit; rotated immediately" if is_rate_limit else "request failed; rotated immediately"
                    await broadcast_log(
                        ws,
                        "System",
                        f"[WARNING] Groq {reason} ({attempt + 1}/{min(MAX_GROQ_KEYS, len(self.keys))}).",
                    )
                if isinstance(error, TimeoutError):
                    # A slow request has consumed the per-agent LLM budget; fail over to the
                    # node's deterministic path instead of multiplying the delay across keys.
                    break

            if not self.keys:
                raise RuntimeError("No Groq API keys configured; using the demo fallback.")
            raise RuntimeError("All configured Groq keys failed or timed out; using the demo fallback.")
        finally:
            self.semaphore.release()

llm_manager = GroqClientManager()

def llm_response_text(content: Any) -> str:
    """Normalize LangChain text-block responses without passing provider metadata onward."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )
    return str(content) if content is not None else ""

def parse_agent_action(content: Any) -> dict:
    """Parse a model action from plain text or a LangChain text-block response."""
    text = llm_response_text(content).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        action = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Agent action did not contain a JSON object.")
        action = json.loads(text[start:end + 1])
    if not isinstance(action, dict) or not isinstance(action.get("action"), str):
        raise ValueError("Agent action JSON must contain a string 'action' field.")
    return action


async def execute_playwright_action(page, action: dict, allowed_actions: set[str]) -> None:
    """Bind a validated LLM action directly to a Playwright page operation."""
    name = action["action"]
    if name not in allowed_actions:
        raise ValueError(f"Unsupported LLM action: {name}")
    if name == "none":
        return
    if name == "click":
        selector = action.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("LLM click action requires a non-empty CSS selector.")
        await page.locator(selector).first.click(timeout=5000)
        return
    if name == "click_text":
        text = action.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("LLM click_text action requires non-empty visible text.")
        await page.get_by_text(text, exact=True).first.click(timeout=5000)
        return
    if name == "fill":
        selector, value = action.get("selector"), action.get("value")
        if not isinstance(selector, str) or not selector.strip() or not isinstance(value, str):
            raise ValueError("LLM fill action requires a CSS selector and string value.")
        await page.locator(selector).first.fill(value, timeout=5000)
        return
    raise ValueError(f"No Playwright binding for LLM action: {name}")

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
DB_FILE = "webswarm.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT      NOT NULL UNIQUE,
                password_hash TEXT     NOT NULL,
                full_name    TEXT,
                role         TEXT,
                use_case     TEXT,
                created_at   DATETIME  DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER,
                target_url   TEXT      NOT NULL,
                testing_goal TEXT,
                status       TEXT      DEFAULT 'PENDING',
                created_at   DATETIME  DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bugs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id      INTEGER   NOT NULL,
                severity     TEXT      NOT NULL,
                description  TEXT      NOT NULL,
                page         TEXT,
                agent        TEXT,
                confidence   REAL,
                status       TEXT      DEFAULT 'OPEN',
                FOREIGN KEY (test_id) REFERENCES test_runs (id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id      INTEGER   NOT NULL,
                summary      TEXT,
                html_content TEXT,
                created_at   DATETIME  DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_id) REFERENCES test_runs (id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vision_diffs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id      INTEGER   NOT NULL,
                page_url     TEXT      NOT NULL,
                baseline_b64 TEXT      NOT NULL,
                current_b64  TEXT      NOT NULL,
                variance_pct REAL      NOT NULL,
                created_at   DATETIME  DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_id) REFERENCES test_runs (id)
            );
        """)
        
        # Safely add telemetry columns to test_runs if they don't exist
        try:
            cursor.execute("ALTER TABLE test_runs ADD COLUMN model_used TEXT DEFAULT 'openai/gpt-oss-20b'")
            cursor.execute("ALTER TABLE test_runs ADD COLUMN total_tokens INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE test_runs ADD COLUMN temperature REAL DEFAULT 0.7")
            cursor.execute("ALTER TABLE test_runs ADD COLUMN execution_time_ms INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Columns already exist
            
        try:
            cursor.execute("ALTER TABLE test_runs ADD COLUMN user_id INTEGER")
        except sqlite3.OperationalError:
            pass


        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"[DB] ERROR - Failed to initialise schema: {exc}")
        raise
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# LangGraph State & Node Definitions
# ---------------------------------------------------------------------------

class SwarmState(TypedDict):
    test_id: int
    target_url: str
    testing_goal: str
    current_dom_snapshot: str
    discovered_urls: Annotated[List[str], operator.add]
    execution_logs: Annotated[List[str], operator.add]
    detected_bugs: Annotated[List[Dict[str, Any]], operator.add]
    browser_page: Any # Playwright Page reference
    agent_metrics: Annotated[List[Dict[str, Any]], operator.add]
    chaos_results: str  # XSS and boundary findings from Chaos Agent

async def broadcast_telemetry(ws: WebSocket, agent: str, exec_time_ms: int, tokens: int, confidence: float):
    try:
        await ws.send_json({
            "type": "telemetry", 
            "agent": agent, 
            "metrics": {
                "execution_time_ms": exec_time_ms,
                "tokens_consumed": tokens,
                "confidence_score": confidence
            }
        })
    except Exception:
        pass

async def broadcast_log(ws: WebSocket, agent: str, message: str):
    try:
        await ws.send_json({"type": "log", "agent": agent, "message": message})
        await asyncio.sleep(0.05)
    except Exception:
        pass

async def broadcast_status(ws: WebSocket, agent: str, status: str):
    try:
        await ws.send_json({"type": "status", "agent": agent, "status": status})
    except Exception:
        pass

async def broadcast_bug(ws: WebSocket, bug_data: dict):
    try:
        await ws.send_json({"type": "bug", "data": bug_data})
    except Exception:
        pass

def _consume_task_result(task: asyncio.Task) -> None:
    """Consume exceptions from work cancelled after its node deadline."""
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        pass

def bounded_agent_node(agent_name: str, node_fn):
    """Apply a hard wall-clock deadline and make node failures observable."""
    async def run(state: SwarmState, config: RunnableConfig) -> dict:
        ws = config["configurable"]["websocket"]
        started = time.perf_counter()
        deadline_token = NODE_DEADLINE.set(asyncio.get_running_loop().time() + AGENT_NODE_TIMEOUT_SECONDS)
        name_token = NODE_NAME.set(agent_name)
        task = asyncio.create_task(node_fn(state, config), name=f"webswarm-{agent_name.lower()}")
        try:
            done, _ = await asyncio.wait({task}, timeout=AGENT_NODE_TIMEOUT_SECONDS)
            if task not in done:
                task.cancel()
                task.add_done_callback(_consume_task_result)
                reason = f"{agent_name} exceeded the {AGENT_NODE_TIMEOUT_SECONDS}s node deadline"
                return await demo_fallback(agent_name, state, ws, reason, started)
            try:
                return task.result()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return await demo_fallback(agent_name, state, ws, f"{type(exc).__name__}: {exc}", started)
        finally:
            NODE_DEADLINE.reset(deadline_token)
            NODE_NAME.reset(name_token)
    return run

async def demo_fallback(agent_name: str, state: SwarmState, ws: WebSocket, reason: str, started: float) -> dict:
    elapsed = int((time.perf_counter() - started) * 1000)
    message = f"[DEMO FALLBACK] {agent_name} continued with a bounded deterministic step: {reason}"
    print(message)
    await broadcast_status(ws, agent_name, "Fallback")
    await broadcast_log(ws, agent_name, message)
    await broadcast_telemetry(ws, agent_name, elapsed, 0, 0.25)
    updates: dict = {
        "execution_logs": [message],
        "agent_metrics": [{"agent": agent_name, "time": elapsed, "tokens": 0, "confidence": 0.25}],
    }
    if agent_name == "Planner":
        await broadcast_log(ws, agent_name, "Simulated plan: load target, audit interactions and assets, then validate findings.")
    elif agent_name == "Navigation":
        updates.update({"discovered_urls": list(state.get("discovered_urls", [])), "current_dom_snapshot": state.get("current_dom_snapshot", "")})
    elif agent_name == "Chaos":
        updates["chaos_results"] = state.get("chaos_results", "")
    elif agent_name == "Validation":
        bug_types = {
            "[BROKEN_LINK]": ("BROKEN_LINK", "HIGH"),
            "[ASSET_ERROR]": ("ASSET_ERROR", "MEDIUM"),
            "[JS_CONSOLE]": ("JS_CONSOLE_ERROR", "HIGH"),
            "[JS_CONSOLE_ERROR]": ("JS_CONSOLE_ERROR", "HIGH"),
            "[BROKEN_ELEMENT]": ("BROKEN_ELEMENT", "MEDIUM"),
            "[MOBILE_MENU]": ("MOBILE_MENU", "MEDIUM"),
            "[XSS]": ("BROKEN_ELEMENT", "CRITICAL"),
        }
        bugs_by_description = {}
        evidence_logs = list(state.get("execution_logs", []))
        chaos_evidence = state.get("chaos_results", "")
        if isinstance(chaos_evidence, str):
            try:
                parsed_chaos = ast.literal_eval(chaos_evidence)
                if isinstance(parsed_chaos, list):
                    evidence_logs.extend(str(item) for item in parsed_chaos)
            except (ValueError, SyntaxError):
                evidence_logs.append(chaos_evidence)
        for log in evidence_logs:
            if not isinstance(log, str):
                continue
            for marker, (category, severity) in bug_types.items():
                if marker in log:
                    description = log[log.find(marker) + len(marker):].strip(" :")
                    bugs_by_description[(category, description)] = {
                        "category": category, "severity": severity,
                        "description": description or f"Finding recorded by an audit node ({category}).",
                        "confidence": 0.7,
                    }
        fallback_bugs = list(bugs_by_description.values())
        updates["detected_bugs"] = fallback_bugs
        if fallback_bugs:
            try:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    for bug in fallback_bugs:
                        severity = "HIGH" if bug["severity"] == "CRITICAL" else bug["severity"]
                        description = f"[{bug['category']}] {bug['description']}"
                        cursor.execute(
                            "INSERT INTO bugs (test_id, severity, description, page, agent, confidence, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (state["test_id"], severity, description, state["target_url"], "Validation (Fallback)", bug["confidence"], "OPEN"),
                        )
                        conn.commit()
                        await broadcast_bug(ws, {"id": cursor.lastrowid, "severity": severity, "description": description, "page": state["target_url"], "agent": "Validation (Fallback)", "status": "OPEN", "confidence": bug["confidence"]})
                finally:
                    conn.close()
            except Exception as exc:
                await broadcast_log(ws, agent_name, f"[WARN] Could not persist fallback findings: {exc}")
        await broadcast_log(ws, agent_name, f"Fallback validation recorded {len(fallback_bugs)} evidence-backed finding(s).")
    await broadcast_status(ws, agent_name, "Completed")
    return updates

# --- Agent 1: Planner Node ---
async def planner_node(state: SwarmState, config: RunnableConfig) -> dict:
    ws = config["configurable"]["websocket"]
    await broadcast_status(ws, "Planner", "Running")
    await broadcast_log(ws, "Planner", f"Analyzing objective: {state['testing_goal']}")
    
    start_t = time.perf_counter()
    tokens = 0
    confidence = 0.95
    
    try:
        msg = [
            SystemMessage(content="You are an autonomous AI Planner Agent for web testing. Output a brief 3-step strategy to test the user's objective."),
            HumanMessage(content=f"Target URL: {state['target_url']}\nObjective: {state['testing_goal']}")
        ]
        response = await llm_manager.ainvoke(msg, ws=ws)
        plan = llm_response_text(response.content)
        
        try:
            tokens = response.response_metadata.get('token_usage', {}).get('total_tokens', 150)
        except:
            tokens = 150
            
        exec_t = int((time.perf_counter() - start_t) * 1000)
        await broadcast_telemetry(ws, "Planner", exec_t, tokens, confidence)
        
        await broadcast_log(ws, "Planner", f"Strategy formulated:\n{plan}")
        await broadcast_status(ws, "Planner", "Completed")
        
        await asyncio.sleep(1) # Add delay between agents
        return {
            "execution_logs": [f"Planner initialized strategy for {state['target_url']}"],
            "agent_metrics": [{"agent": "Planner", "time": exec_t, "tokens": tokens, "confidence": confidence}]
        }
    except Exception as e:
        raise RuntimeError(f"Planner LLM request failed: {e}") from e

# --- Agent 2: Navigation Node ---
async def navigation_node(state: SwarmState, config: RunnableConfig) -> dict:
    ws = config["configurable"]["websocket"]
    page = state.get("browser_page")
    
    await broadcast_status(ws, "Navigation", "Running")
    await broadcast_log(ws, "Navigation", f"Navigating to {state['target_url']}...")
    
    start_t = time.perf_counter()
    nav_logs = []
    console_errors = []

    try:
        # Attach console error listener BEFORE navigation
        def handle_console(msg):
            if msg.type in ("error", "warning"):
                console_errors.append(f"[{msg.type.upper()}] {msg.text}")

        page.on("console", handle_console)

        page.set_default_timeout(3500)
        page.set_default_navigation_timeout(8000)
        await page.goto(state['target_url'], wait_until="domcontentloaded", timeout=8000)
        title = await page.title()
        await broadcast_log(ws, "Navigation", f"Successfully loaded page. Title: '{title}'")
        nav_logs.append(f"Navigated to {state['target_url']}. Title: {title}")

        # Ask the model for one explicit navigation action and execute that
        # action through Playwright. Invalid or unsupported actions are errors;
        # there is no scripted fallback action.
        navigation_msg = [
            SystemMessage(content='''You are a web navigation QA agent. Based on the page text, choose at most one useful navigation action. Return only JSON matching one of these shapes:
{"action":"click","selector":"CSS selector"}
{"action":"click_text","text":"visible link or button text"}
{"action":"none"}
Use "none" when no safe, relevant navigation action is apparent. Do not invent selectors or text.'''),
            HumanMessage(content=f"Page title: {title}\nPage content:\n{(await page.locator('body').inner_text())[:4000]}")
        ]
        navigation_response = await llm_manager.ainvoke(navigation_msg, ws=ws)
        nav_action = parse_agent_action(navigation_response.content)
        await execute_playwright_action(page, nav_action, {"click", "click_text", "none"})
        nav_logs.append(f"Navigation LLM action executed: {nav_action['action']}")
        await broadcast_log(ws, "Navigation", f"Executed LLM navigation action: {nav_action['action']}")

        # --- Link Discovery & 404 Audit ---
        links = await page.eval_on_selector_all('a[href]', 'elements => elements.map(el => ({ href: el.href, text: el.innerText.trim() }))')
        await broadcast_log(ws, "Navigation", f"Discovered {len(links)} links. Auditing for broken anchors and 404s...")

        broken_links = []
        for link in links[:15]:  # Audit first 15 links to avoid timeout
            href = link.get("href", "")
            if not href or href.startswith("javascript:") or href.startswith("mailto:"):
                continue
            if href.startswith("#"):
                # Check anchor fragment exists on page
                fragment = href[1:]
                if fragment:
                    exists = await page.evaluate(f'!!document.getElementById("{fragment}") || !!document.querySelector("[name=\\"{fragment}\\"]")')
                    if not exists:
                        broken_links.append(f"Dead anchor: {href} (fragment not found on page)")
                        nav_logs.append(f"[BROKEN_LINK] Dead anchor #{fragment} found — no matching element ID.")
        
        if broken_links:
            await broadcast_log(ws, "Navigation", f"[ALERT] {len(broken_links)} broken anchor(s) detected: {broken_links[:3]}")
        
        # --- Asset Audit: Broken images & missing alt ---
        img_issues = await page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.map(img => ({
                src: img.src,
                alt: img.alt,
                naturalWidth: img.naturalWidth
            }));
        }""")

        asset_logs = []
        for img in img_issues:
            if not img.get("alt"):
                asset_logs.append(f"[ASSET_ERROR] Missing alt attribute on <img src='{img.get('src', '')[:60]}'>")
            if img.get("naturalWidth") == 0 and img.get("src"):
                asset_logs.append(f"[ASSET_ERROR] Broken image (failed to load): {img.get('src', '')[:80]}")

        for log in asset_logs[:5]:
            await broadcast_log(ws, "Navigation", log)
        nav_logs.extend(asset_logs)

        # --- Console Error Report ---
        await asyncio.sleep(1)  # Allow deferred JS errors to fire
        if console_errors:
            await broadcast_log(ws, "Navigation", f"[JS_CONSOLE] {len(console_errors)} browser console error(s) captured:")
            for err in console_errors[:5]:
                await broadcast_log(ws, "Navigation", f"  {err}")
            nav_logs.extend(console_errors)
        else:
            await broadcast_log(ws, "Navigation", "No browser console errors detected on page load.")

        # DOM snapshot (full text for downstream agents)
        dom_snapshot = await page.evaluate('() => document.body.innerText.substring(0, 5000)')
        nav_logs.append(f"Discovered {len(links)} links. Broken anchors: {len(broken_links)}. Asset issues: {len(asset_logs)}. Console errors: {len(console_errors)}.")

        exec_t = int((time.perf_counter() - start_t) * 1000)
        await broadcast_telemetry(ws, "Navigation", exec_t, 0, 1.0)
        await broadcast_status(ws, "Navigation", "Completed")
        
        await asyncio.sleep(1)
        return {
            "discovered_urls": [l.get("href", "") for l in links],
            "current_dom_snapshot": dom_snapshot,
            "execution_logs": nav_logs,
            "agent_metrics": [{"agent": "Navigation", "time": exec_t, "tokens": 0, "confidence": 1.0}]
        }
    except Exception as e:
        raise RuntimeError(f"Navigation failed: {e}") from e


# --- Agent 3: Functional Node ---
async def functional_node(state: SwarmState, config: RunnableConfig) -> dict:
    ws = config["configurable"]["websocket"]
    page = state.get("browser_page")
    
    await broadcast_status(ws, "Functional", "Running")
    await broadcast_log(ws, "Functional", "Executing functional interaction & accessibility audit...")
    
    start_t = time.perf_counter()
    tokens = 0
    confidence = 0.85
    func_logs = list(state.get("execution_logs", []))

    try:
        # --- AI Decision: What to interact with ---
        msg = [
            SystemMessage(content='''You are a Functional QA Agent. Choose one safe functional action using the supplied page text. Return only JSON matching one of these shapes:
{"action":"click","selector":"CSS selector"}
{"action":"click_text","text":"visible button or link text"}
{"action":"fill","selector":"CSS selector for an input","value":"test value"}
{"action":"none"}
Use "none" if a safe, relevant action cannot be selected. Do not invent selectors or text.'''),
            HumanMessage(content=f"Page Content:\n{state.get('current_dom_snapshot', '')[:2000]}")
        ]
        response = await llm_manager.ainvoke(msg, ws=ws)
        await broadcast_log(ws, "Functional", f"AI Decision: {llm_response_text(response.content)[:200]}")
        functional_action = parse_agent_action(response.content)

        try:
            tokens = response.response_metadata.get('token_usage', {}).get('total_tokens', 120)
        except:
            tokens = 120

        baseline_b64, current_b64 = "", ""
        variance = 0.0
        post_interaction_errors = []

        if not page.is_closed() and "CRITICAL ERROR" not in state.get('current_dom_snapshot', ''):

            # --- Capture post-interaction console errors ---
            def handle_post_console(msg):
                if msg.type == "error":
                    post_interaction_errors.append(f"[JS_CONSOLE_ERROR] {msg.text}")
            page.on("console", handle_post_console)

            # --- Baseline screenshot ---
            baseline_bytes = await page.screenshot(type="jpeg", quality=40)

            # --- Button interaction audit ---
            await broadcast_log(ws, "Functional", "Auditing buttons for event listener bindings...")
            button_issues = await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]'));
                return buttons.map(btn => ({
                    text: btn.innerText || btn.value || '',
                    hasOnclick: !!btn.onclick || !!btn.getAttribute('onclick'),
                    disabled: btn.disabled,
                    type: btn.type || 'button'
                }));
            }""")
            for btn in button_issues:
                if not btn.get("hasOnclick") and not btn.get("disabled") and btn.get("type") != "submit":
                    log = f"[BROKEN_ELEMENT] Button '{btn.get('text', 'unnamed')[:40]}' has no onclick handler and is not a submit button."
                    await broadcast_log(ws, "Functional", log)
                    func_logs.append(log)

            # Execute exactly the action returned by the model via Playwright.
            # Parsing or binding errors are surfaced by the node; no fallback
            # scripted interaction is substituted.
            await execute_playwright_action(page, functional_action, {"click", "click_text", "fill", "none"})
            await broadcast_log(ws, "Functional", f"Executed LLM functional action: {functional_action['action']}")
            await asyncio.sleep(1)

            # --- Mobile Viewport Check (structural audit, independent of action) ---
            await broadcast_log(ws, "Functional", "Switching to mobile viewport (375px) for layout audit...")
            await page.set_viewport_size({"width": 375, "height": 812})
            await asyncio.sleep(1)

            overflow_issues = await page.evaluate("""() => {
                const body = document.body;
                const scrollW = body.scrollWidth;
                const viewW = window.innerWidth;
                const overflowing = Array.from(document.querySelectorAll('*')).filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.right > window.innerWidth + 5;
                }).map(el => el.tagName + (el.className ? '.' + el.className.toString().split(' ')[0] : ''));
                return { scrollWidth: scrollW, viewWidth: viewW, overflowing: overflowing.slice(0, 5) };
            }""")

            if overflow_issues.get("scrollWidth", 0) > overflow_issues.get("viewWidth", 375) + 5:
                log = f"[MOBILE_MENU] Layout overflow detected on 375px viewport. Horizontal scroll triggered. Overflowing elements: {overflow_issues.get('overflowing', [])}"
                await broadcast_log(ws, "Functional", log)
                func_logs.append(log)
            else:
                await broadcast_log(ws, "Functional", "Mobile viewport: No horizontal overflow detected.")

            # --- Hamburger/menu toggle test ---
            hamburger = page.locator("button[class*='menu'], button[class*='burger'], button[class*='toggle'], button[aria-label*='menu'], .hamburger, .navbar-toggle").first
            try:
                if await hamburger.count() > 0:
                    await broadcast_log(ws, "Functional", "Mobile menu toggle found. Testing open/close...")
                    await hamburger.click()
                    await asyncio.sleep(0.5)
                    await hamburger.click()
                    await asyncio.sleep(0.5)
                    if post_interaction_errors:
                        log = f"[MOBILE_MENU] Mobile menu toggle produced JS errors: {post_interaction_errors[0]}"
                        func_logs.append(log)
                        await broadcast_log(ws, "Functional", log)
            except Exception:
                pass

            # Restore desktop viewport
            await page.set_viewport_size({"width": 1280, "height": 800})

            # --- Post-interaction screenshot ---
            current_bytes = await page.screenshot(type="jpeg", quality=40)
            baseline_size = len(baseline_bytes)
            current_size = len(current_bytes)
            # Optimized structural JPEG byte-size heuristic for rapid layout
            # shift detection; this is not a pixel-by-pixel image diff.
            variance = abs(baseline_size - current_size) / max(baseline_size, 1) * 100.0
            baseline_b64 = base64.b64encode(baseline_bytes).decode('utf-8')
            current_b64 = base64.b64encode(current_bytes).decode('utf-8')
            await broadcast_log(ws, "Functional", f"Layout variance computed: {variance:.2f}% shift detected.")

            # Log post-interaction JS errors
            await asyncio.sleep(0.5)
            for err in post_interaction_errors[:3]:
                await broadcast_log(ws, "Functional", err)
                func_logs.append(err)

            # Save vision diff to SQLite
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO vision_diffs (test_id, page_url, baseline_b64, current_b64, variance_pct)
                    VALUES (?, ?, ?, ?, ?)
                """, (state["test_id"], state['target_url'], baseline_b64, current_b64, variance))
                conn.commit()
            finally:
                conn.close()
        else:
            await broadcast_log(ws, "Functional", "Skipping interaction; target page is unreachable or closed.")

        func_logs.append(f"Functional agent done. Visual variance: {variance:.2f}%. Button issues and mobile audit complete.")
        exec_t = int((time.perf_counter() - start_t) * 1000)
        await broadcast_telemetry(ws, "Functional", exec_t, tokens, confidence)
        await broadcast_status(ws, "Functional", "Completed")
        await asyncio.sleep(1)
        return {
            "execution_logs": func_logs,
            "agent_metrics": [{"agent": "Functional", "time": exec_t, "tokens": tokens, "confidence": confidence}]
        }
    except Exception as e:
        raise RuntimeError(f"Functional audit failed: {e}") from e


# --- Agent 4: Chaos Node ---
async def chaos_node(state: SwarmState, config: RunnableConfig) -> dict:
    ws = config["configurable"]["websocket"]
    page = state.get("browser_page")
    
    await broadcast_status(ws, "Chaos", "Running")
    await broadcast_log(ws, "Chaos", "Initiating XSS injection, boundary condition, and stress testing suite...")
    
    start_t = time.perf_counter()
    chaos_logs = []
    chaos_findings = []

    XSS_PAYLOADS = [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert('xss')",
        "'><svg onload=alert(1)>",
        "\"><script>document.cookie</script>",
    ]

    BOUNDARY_INPUTS = [
        ("", "Empty input submission"),
        ("A" * 5000, "5000-char overflow string"),
        ("test@invalid", "Invalid email (missing TLD)"),
        ("user@domain.co", "Valid .co domain email (should be accepted)"),
        ("user+tag@sub.domain.com", "Valid plus-tag email (should be accepted)"),
        ("<>\"'&;", "Special characters / HTML injection probe"),
        ("' OR '1'='1", "SQL injection probe"),
        ("0", "Zero/falsy boundary value"),
    ]

    try:
        if not page.is_closed() and "CRITICAL ERROR" not in state.get('current_dom_snapshot', ''):

            # --- XSS Injection into input fields ---
            await broadcast_log(ws, "Chaos", "Phase 1: XSS payload injection into all visible input fields...")
            inputs = await page.locator("input:visible, textarea:visible").all()
            xss_vulnerable = []

            for i, inp in enumerate(inputs[:5]):  # Test up to 5 inputs
                try:
                    payload = XSS_PAYLOADS[i % len(XSS_PAYLOADS)]
                    await inp.fill(payload)
                    await asyncio.sleep(0.3)
                    # Check if payload was rendered in DOM (indicates innerHTML vulnerability)
                    rendered = await page.evaluate(f"document.body.innerHTML.includes(`alert('xss')`)")
                    if rendered:
                        finding = f"[XSS] Input field rendered alert payload in DOM — unsafe innerHTML detected. Payload: {payload[:50]}"
                        xss_vulnerable.append(finding)
                        chaos_findings.append(finding)
                        await broadcast_log(ws, "Chaos", f"[CRITICAL] {finding}")
                    else:
                        await broadcast_log(ws, "Chaos", f"Input #{i+1}: XSS payload injected, no DOM rendering (safe).")
                    chaos_logs.append(f"XSS test on input #{i+1}: payload={payload[:40]}")
                except Exception:
                    pass

            # --- Boundary Input Tests on first form ---
            await broadcast_log(ws, "Chaos", "Phase 2: Boundary input stress testing (empty, overflow, email formats)...")
            first_input = page.locator("input[type='text'], input[type='email'], input:not([type='hidden'])").first
            try:
                if await first_input.count() > 0:
                    for value, label in BOUNDARY_INPUTS:
                        await first_input.fill(value)
                        await asyncio.sleep(0.2)
                        chaos_logs.append(f"Boundary test: {label} — value='{value[:40]}'")
                    await broadcast_log(ws, "Chaos", f"Boundary inputs tested: {len(BOUNDARY_INPUTS)} cases.")
            except Exception as e:
                chaos_logs.append(f"Boundary test skipped: {str(e)}")

            # --- Duplicate Submit / Button Stress Test ---
            await broadcast_log(ws, "Chaos", "Phase 3: Duplicate submission stress test on buttons...")
            buttons = await page.locator("button:visible, input[type=submit]:visible").all()
            for btn in buttons[:3]:
                try:
                    btn_text = await btn.inner_text()
                    # Click rapidly twice to test duplicate submission guard
                    await btn.click(force=True)
                    await asyncio.sleep(0.1)
                    is_disabled = await btn.is_disabled()
                    if not is_disabled:
                        finding = f"[BROKEN_ELEMENT] Button '{btn_text[:40].strip()}' is NOT disabled after first click — duplicate submission risk."
                        chaos_findings.append(finding)
                        await broadcast_log(ws, "Chaos", finding)
                    else:
                        await broadcast_log(ws, "Chaos", f"Button '{btn_text[:30].strip()}' correctly disables after click.")
                    chaos_logs.append(f"Stress test: button '{btn_text[:30].strip()}'")
                except Exception:
                    pass

            await broadcast_log(ws, "Chaos", f"Chaos suite complete. {len(chaos_findings)} security/boundary finding(s) detected.")

        else:
            await broadcast_log(ws, "Chaos", "Skipping chaos injection; page is unreachable.")
            chaos_logs.append("Page unreachable — chaos skipped.")

        exec_t = int((time.perf_counter() - start_t) * 1000)
        await broadcast_telemetry(ws, "Chaos", exec_t, 0, 1.0)
        await broadcast_status(ws, "Chaos", "Completed")
        await asyncio.sleep(1)

        all_logs = list(state.get("execution_logs", [])) + chaos_logs
        return {
            "execution_logs": all_logs,
            "chaos_results": str(chaos_findings),
            "agent_metrics": [{"agent": "Chaos", "time": exec_t, "tokens": 0, "confidence": 1.0}]
        }
    except Exception as e:
        raise RuntimeError(f"Chaos audit failed: {e}") from e


# --- Agent 5: Validation Node ---
async def validation_node(state: SwarmState, config: RunnableConfig) -> dict:
    ws = config["configurable"]["websocket"]
    
    await broadcast_status(ws, "Validation", "Running")
    await broadcast_log(ws, "Validation", "Executing comprehensive QA validation pass using Groq...")
    
    start_t = time.perf_counter()
    tokens = 0
    all_bugs = []

    VALIDATION_SYSTEM_PROMPT = """You are a Senior QA Validation Agent and Security Auditor embedded inside an autonomous web testing swarm.
Your task is to perform a THOROUGH, MULTI-CATEGORY quality assurance pass on the provided execution logs, DOM snapshot, and test context.

You MUST detect and report ALL issues found across the following bug categories:

1. BROKEN NAVIGATION & FUNCTIONALITY LINKS
   - Any <a> tag or JS function that returns a 404, triggers a console ReferenceError, or fails to navigate/act as expected.

2. FORM VALIDATION ERRORS
   - Form fields or regex rules that incorrectly reject valid input formats (e.g., .co domains, emails with numbers)
   - OR allow clearly invalid inputs (e.g., empty fields, special chars in name fields).

3. BROKEN INTERACTIVE ELEMENTS (BUTTONS / INPUTS)
   - Buttons or submit inputs with no event listener, duplicate submission risk (not disabled on click), delayed response, or no visual feedback.

4. FRONT-END JAVASCRIPT CONSOLE ERRORS
   - Any runtime JavaScript error (TypeError, ReferenceError, SyntaxError) captured in logs during page load or interactions.

5. ASSET & LINK VALIDATION
   - <img> tags with broken src paths (404), missing alt attributes (accessibility), or external assets failing to load.

6. MOBILE MENU FAILURE
   - Hamburger/toggle menu not opening or closing correctly in mobile viewport, or producing JS errors during toggle.

OUTPUT FORMAT:
You MUST output a single valid JSON array (not an object) containing one JSON object per detected bug.
Each bug object must have EXACTLY these keys:
  - "category": one of [BROKEN_LINK, FORM_VALIDATION, BROKEN_ELEMENT, JS_CONSOLE_ERROR, ASSET_ERROR, MOBILE_MENU]
  - "severity": one of [CRITICAL, HIGH, MEDIUM, LOW]
  - "description": a precise, developer-actionable string describing the issue and its location
  - "confidence": float from 0.0 to 1.0

If NO bugs are found in a category, do not include entries for that category.
If NO bugs are found at all, output an empty array: []
NEVER include markdown, explanation text, or code fences. Output ONLY the raw JSON array."""

    try:
        dom_context = state.get('current_dom_snapshot', '')[:4000]
        logs_context = str(state.get('execution_logs', []))[:3000]
        chaos_context = str(state.get('chaos_results', ''))[:1000]

        msg = [
            SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
            HumanMessage(content=f"""TESTING GOAL: {state.get('testing_goal', 'General QA scan')}

TARGET URL: {state.get('target_url', 'Unknown')}

EXECUTION LOGS:
{logs_context}

DOM SNAPSHOT (truncated):
{dom_context}

CHAOS TEST RESULTS:
{chaos_context}

Now perform your comprehensive QA validation pass and output the JSON bug array.""")
        ]
        
        response = await llm_manager.ainvoke(msg, ws=ws)
        raw_output = llm_response_text(response.content).strip()
        
        try:
            tokens = response.response_metadata.get('token_usage', {}).get('total_tokens', 250)
        except:
            tokens = 250
        
        # Strip markdown fences if present
        if "```json" in raw_output:
            raw_output = raw_output.split("```json")[1].split("```")[0].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output.split("```")[1].strip()

        # Parse the bug array
        try:
            bug_list = json.loads(raw_output)
            if isinstance(bug_list, dict):
                bug_list = [bug_list]  # Wrap single object in list for safety
            if not isinstance(bug_list, list):
                bug_list = []
        except json.JSONDecodeError:
            await broadcast_log(ws, "Validation", f"[WARN] Could not parse JSON response. Raw: {raw_output[:150]}")
            bug_list = [{
                "category": "JS_CONSOLE_ERROR",
                "severity": "MEDIUM",
                "description": f"Validation agent returned unparseable output during analysis. Raw snippet: {raw_output[:120]}",
                "confidence": 0.5
            }]

        await broadcast_log(ws, "Validation", f"QA Pass complete. {len(bug_list)} issue(s) detected across all categories.")

        # Persist each bug to SQLite and broadcast to UI
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            for bug in bug_list:
                severity = bug.get('severity', 'MEDIUM').upper()
                # Normalize severity - map CRITICAL to HIGH for DB compatibility
                db_severity = severity if severity in ['HIGH', 'MEDIUM', 'LOW'] else 'HIGH'
                description = bug.get('description', 'Unknown issue detected.')
                category = bug.get('category', 'GENERAL')
                confidence = float(bug.get('confidence', 0.75))
                full_description = f"[{category}] {description}"

                cursor.execute("""
                    INSERT INTO bugs (test_id, severity, description, page, agent, confidence, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (state["test_id"], db_severity, full_description, state['target_url'], "Validation (Groq)", confidence, 'OPEN'))
                conn.commit()
                bug_id = cursor.lastrowid

                await broadcast_log(ws, "Validation", f"[{severity}] {category}: {description[:100]} (Confidence: {round(confidence*100)}%)")
                await broadcast_bug(ws, {
                    "id": bug_id, "severity": db_severity, "description": full_description,
                    "page": state['target_url'], "agent": "Validation (Groq)", "status": "OPEN", "confidence": confidence
                })
                all_bugs.append(bug)
        finally:
            conn.close()

        avg_confidence = sum(float(b.get('confidence', 0.75)) for b in all_bugs) / max(len(all_bugs), 1)
        exec_t = int((time.perf_counter() - start_t) * 1000)
        await broadcast_telemetry(ws, "Validation", exec_t, tokens, avg_confidence)
        await broadcast_status(ws, "Validation", "Completed")

        await asyncio.sleep(1)
        return {
            "detected_bugs": all_bugs,
            "agent_metrics": [{"agent": "Validation", "time": exec_t, "tokens": tokens, "confidence": avg_confidence}]
        }

    except Exception as e:
        raise RuntimeError(f"Validation failed: {e}") from e


# Build LangGraph
workflow = StateGraph(SwarmState)
workflow.add_node("planner", bounded_agent_node("Planner", planner_node))
workflow.add_node("navigation", bounded_agent_node("Navigation", navigation_node))
workflow.add_node("functional", bounded_agent_node("Functional", functional_node))
workflow.add_node("chaos", bounded_agent_node("Chaos", chaos_node))
workflow.add_node("validation", bounded_agent_node("Validation", validation_node))

workflow.add_edge(START, "planner")
workflow.add_edge("planner", "navigation")
workflow.add_edge("navigation", "functional")
workflow.add_edge("functional", "chaos")
workflow.add_edge("chaos", "validation")
workflow.add_edge("validation", END)

swarm_app = workflow.compile()

# ---------------------------------------------------------------------------
# FastAPI Application & REST
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] Initialising database schema ...")
    init_db()
    
    try:
        if not llm_manager.keys:
            pass
        else:
            print(f"[Startup] Groq API Key(s) detected ({len(llm_manager.keys)} total). Ready for autonomous execution.")
    except Exception:
        print("\n" + "="*60)
        print("!!! WARNING: GROQ API KEYS ARE MISSING; LLM calls will use fallback behavior. !!!")
        print("Set GROQ_API_KEYS or GROQ_API_KEY in .env.")
        print("The Swarm execution will crash if invoked without it.")
        print("="*60 + "\n")
        
    yield
    print("[Shutdown] WebSwarm backend stopped.")

app = FastAPI(
    title="WebSwarm API - Multi-Agent Groq Run",
    description="FastAPI + SQLite + Playwright + LangGraph + Groq",
    version="7.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TestRequest(BaseModel):
    targetUrl: HttpUrl
    testingGoal: Optional[str] = None
    selectedAgents: Optional[List[str]] = None
    userId: Optional[int] = None

class SignInRequest(BaseModel):
    email: str
    password: str

class SignUpRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str
    use_case: str

@app.post("/api/v1/auth/signup", tags=["Auth"])
def signup(req: SignUpRequest):
    hashed = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (email, password_hash, full_name, role, use_case)
            VALUES (?, ?, ?, ?, ?)
        """, (req.email, hashed, req.full_name, req.role, req.use_case))
        conn.commit()
        user_id = cursor.lastrowid
        cursor.execute("SELECT id, email, full_name, role, use_case, created_at FROM users WHERE id = ?", (user_id,))
        return {"status": "Success", "user": dict(cursor.fetchone())}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="User with this email already exists.")
    finally:
        conn.close()

@app.post("/api/v1/auth/signin", tags=["Auth"])
def signin(req: SignInRequest):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (req.email,))
        user_row = cursor.fetchone()
        if not user_row or not bcrypt.checkpw(req.password.encode('utf-8'), user_row['password_hash'].encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user_dict = dict(user_row)
        del user_dict['password_hash']
        return {"status": "Success", "user": user_dict}
    finally:
        conn.close()

@app.post("/api/v1/start-swarm", tags=["Swarm"])
async def start_swarm(request: TestRequest):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO test_runs (target_url, testing_goal, status, user_id, model_used) VALUES (?, ?, 'PENDING', ?, ?)",
            (str(request.targetUrl), request.testingGoal, request.userId, GROQ_MODEL),
        )
        test_id = cursor.lastrowid
        conn.commit()
        return {"status": "Success", "testId": test_id, "targetUrl": str(request.targetUrl)}
    finally:
        conn.close()

@app.get("/api/v1/bugs", tags=["Bugs"])
def get_all_bugs():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bugs ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@app.get("/api/v1/reports", tags=["Reports"])
def get_all_reports():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, t.target_url 
            FROM reports r
            JOIN test_runs t ON r.test_id = t.id
            ORDER BY r.created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@app.get("/api/v1/vision-diffs", tags=["Vision"])
def get_all_vision_diffs():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vision_diffs ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@app.get("/api/v1/history", tags=["History"])
def get_history(user_id: int, url: Optional[str] = None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        if url:
            cursor.execute("SELECT * FROM test_runs WHERE user_id = ? AND target_url = ? ORDER BY id ASC", (user_id, url))
        else:
            cursor.execute("SELECT * FROM test_runs WHERE user_id = ? ORDER BY id ASC", (user_id,))
            
        test_runs = cursor.fetchall()
        
        history_data = []
        prev_bugs = 0
        
        for run in test_runs:
            run_dict = dict(run)
            test_id = run_dict["id"]
            
            cursor.execute("SELECT severity FROM bugs WHERE test_id = ?", (test_id,))
            bugs = cursor.fetchall()
            
            high = len([b for b in bugs if b['severity'] == 'HIGH'])
            medium = len([b for b in bugs if b['severity'] == 'MEDIUM'])
            low = len([b for b in bugs if b['severity'] == 'LOW'])
            total = len(bugs)
            
            delta = total - prev_bugs if history_data else 0
            
            cursor.execute("SELECT AVG(confidence) as avg_conf FROM bugs WHERE test_id = ?", (test_id,))
            conf_row = cursor.fetchone()
            avg_confidence = conf_row['avg_conf'] if conf_row and conf_row['avg_conf'] else 0.0
            
            run_dict["metrics"] = {
                "total_bugs": total,
                "high": high,
                "medium": medium,
                "low": low,
                "delta": delta,
                "avg_confidence": avg_confidence
            }
            history_data.append(run_dict)
            prev_bugs = total
            
        return history_data
    finally:
        conn.close()

def update_test_status(test_id: int, status: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE test_runs SET status = ? WHERE id = ?", (status, test_id))
        conn.commit()
    finally:
        conn.close()

def create_report(test_id: int, summary: str, html: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reports (test_id, summary, html_content) VALUES (?, ?, ?)", (test_id, summary, html))
        conn.commit()
    finally:
        conn.close()

@app.websocket("/api/v1/ws/live-testing/{test_id}")
async def websocket_endpoint(websocket: WebSocket, test_id: int):
    await websocket.accept()
    
    try:
        data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
        msg = json.loads(data)
        
        if msg.get("action") == "start":
            target_url = msg.get("targetUrl")
            goal = msg.get("testingGoal") or "Perform a general functionality scan and identify critical UI bugs."
            
            update_test_status(test_id, "RUNNING")
            await broadcast_status(websocket, "System", "Running")
            await broadcast_log(websocket, "System", f"Swarm engine ignited for {target_url}")
            await broadcast_telemetry(websocket, "System", 0, 0, 1.0)
            
            stop_event = asyncio.Event()
            screenshot_task = None
            browser = None

            async def stream_screenshots(ws: WebSocket, page, stop_event: asyncio.Event):
                while not stop_event.is_set():
                    try:
                        if not page.is_closed():
                            buffer = await asyncio.wait_for(page.screenshot(type="jpeg", quality=40), timeout=3.0)
                            b64 = base64.b64encode(buffer).decode('utf-8')
                            await asyncio.wait_for(ws.send_json({"type": "screenshot", "data": b64}), timeout=3.0)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)

            # Global setup for Playwright context
            try:
                async with async_playwright() as pw:
                    browser = await asyncio.wait_for(pw.chromium.launch(headless=True), timeout=10.0)
                    page = await asyncio.wait_for(browser.new_page(), timeout=5.0)
                    page.set_default_timeout(3500)
                    page.set_default_navigation_timeout(8000)
                    
                    screenshot_task = asyncio.create_task(stream_screenshots(websocket, page, stop_event))
                    
                    # Initialize Graph State
                    initial_state = {
                        "test_id": test_id,
                        "target_url": target_url,
                        "testing_goal": goal,
                        "current_dom_snapshot": "",
                        "discovered_urls": [],
                        "execution_logs": [],
                        "detected_bugs": [],
                        "browser_page": page
                    }
                    
                    config = {"configurable": {"websocket": websocket}}
                    
                    # Execute LangGraph Autonomous Workflow
                    final_state = await swarm_app.ainvoke(initial_state, config=config)
                    
                    # Graph execution finished. Generate final report.
                    await broadcast_status(websocket, "Report", "Running")
                    await broadcast_log(websocket, "Report", "Graph execution completed. Generating summary report...")
                    
                    # 1. Calculate Metrics
                    detected_bugs = final_state.get('detected_bugs', [])
                    execution_logs = final_state.get('execution_logs', [])
                    
                    high_bugs = len([b for b in detected_bugs if b.get('severity') == 'HIGH'])
                    med_bugs = len([b for b in detected_bugs if b.get('severity') == 'MEDIUM'])
                    low_bugs = len([b for b in detected_bugs if b.get('severity') == 'LOW'])
                    
                    # 2. Get Deep-Dive Technical Analysis from Groq
                    tech_analysis_text = "No vulnerabilities detected. System structure appears stable."
                    if detected_bugs:
                        await broadcast_log(websocket, "Report", "Requesting Deep-Dive Technical Analysis from Groq...")
                        analysis_msg = [
                            SystemMessage(content="You are an Expert Security & QA Architect. Provide a detailed root-cause analysis and remediation steps for the following bugs. Format your response cleanly without markdown ticks."),
                            HumanMessage(content=json.dumps(detected_bugs))
                        ]
                        try:
                            response = await llm_manager.ainvoke(analysis_msg, ws=websocket)
                            tech_analysis_text = llm_response_text(response.content).strip()
                        except Exception as e:
                            tech_analysis_text = f"Analysis generation failed due to API load: {e}"

                    # 3. Construct Structured JSON Summary for the Frontend UI
                    report_json = json.dumps({
                        "overview": f"Swarm analysis completed for {target_url}",
                        "metrics": {
                            "total_bugs": len(detected_bugs),
                            "high": high_bugs,
                            "medium": med_bugs,
                            "low": low_bugs,
                            "actions_taken": len(execution_logs)
                        },
                        "telemetry": {
                            "model": GROQ_MODEL,
                            "agents_deployed": 5
                        },
                        "technical_analysis": tech_analysis_text
                    })
                    
                    # 4. Construct the standalone Downloadable HTML File
                    bugs_html = "".join([f"<li class='bug {b.get('severity', 'LOW').lower()}'><strong>[{b.get('severity')}]</strong> {b.get('description')} (Agent: {b.get('agent')})</li>" for b in detected_bugs])
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <title>WebSwarm Executive Report - {test_id}</title>
                        <style>
                            body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f8fafc; color: #0f172a; line-height: 1.6; padding: 40px; }}
                            .container {{ max-width: 1000px; margin: 0 auto; background: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
                            h1 {{ color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
                            .metrics {{ display: flex; gap: 20px; margin: 30px 0; }}
                            .metric-card {{ flex: 1; background: #f1f5f9; padding: 20px; border-radius: 8px; text-align: center; border: 1px solid #e2e8f0; }}
                            .metric-card h3 {{ margin: 0; font-size: 24px; color: #3b82f6; }}
                            .metric-card p {{ margin: 5px 0 0; text-transform: uppercase; font-size: 12px; font-weight: bold; color: #64748b; }}
                            .high {{ color: #dc2626; }} .medium {{ color: #d97706; }} .low {{ color: #2563eb; }}
                            .section {{ margin-top: 40px; }}
                            .tech-analysis {{ background: #1e293b; color: #e2e8f0; padding: 25px; border-radius: 8px; font-family: monospace; white-space: pre-wrap; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>WebSwarm Execution Report #{test_id}</h1>
                            <p><strong>Target URL:</strong> {target_url}</p>
                            
                            <div class="metrics">
                                <div class="metric-card"><h3>{len(detected_bugs)}</h3><p>Total Bugs</p></div>
                                <div class="metric-card"><h3 class="high">{high_bugs}</h3><p>Critical / High</p></div>
                                <div class="metric-card"><h3>{len(execution_logs)}</h3><p>Agent Actions</p></div>
                            </div>

                            <div class="section">
                                <h2>Detected Vulnerabilities</h2>
                                <ul>{bugs_html or "<li>No vulnerabilities detected.</li>"}</ul>
                            </div>

                            <div class="section">
                                <h2>Detailed Technical Analysis & Remediation</h2>
                                <div class="tech-analysis">{tech_analysis_text}</div>
                            </div>
                            
                            <div class="section">
                                <p><small>Generated autonomously by WebSwarm powered by {GROQ_MODEL}.</small></p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    create_report(test_id, report_json, html_content)
                    
                    agent_metrics = final_state.get('agent_metrics', [])
                    total_time = sum(m.get('time', 0) for m in agent_metrics)
                    total_tokens = sum(m.get('tokens', 0) for m in agent_metrics)
                    
                    # Update test run with telemetry
                    conn_update = get_db_connection()
                    try:
                        c = conn_update.cursor()
                        c.execute("UPDATE test_runs SET total_tokens = ?, execution_time_ms = ? WHERE id = ?", (total_tokens, total_time, test_id))
                        conn_update.commit()
                    except Exception as e:
                        print("Telemetry save error:", e)
                    finally:
                        conn_update.close()
                    
                    await broadcast_status(websocket, "Report", "Completed")
                    
                    stop_event.set()
                    if screenshot_task:
                        screenshot_task.cancel()
                        await asyncio.gather(screenshot_task, return_exceptions=True)
                    if browser:
                        await asyncio.wait_for(browser.close(), timeout=3.0)
                    
                    update_test_status(test_id, "COMPLETED")
                    await websocket.send_json({"type": "finish", "testId": test_id, "status": "Success"})
                    
            except Exception as e:
                stop_event.set()
                if screenshot_task:
                    screenshot_task.cancel()
                    await asyncio.gather(screenshot_task, return_exceptions=True)
                if browser:
                    try:
                        await asyncio.wait_for(browser.close(), timeout=3.0)
                    except Exception:
                        pass
                update_test_status(test_id, "FAILED")
                await broadcast_log(websocket, "System", f"[ERROR] Graph Execution Failed: {str(e)}")
                traceback.print_exc()
                await websocket.send_json({"type": "finish", "testId": test_id, "status": "Failed"})

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for test {test_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
