# 🐝 WebSwarm

> **An Autonomous Multi-Agent AI Testing Platform**
> WebSwarm allows developers and QA teams to unleash a hive of AI agents against any web application to autonomously navigate, test functionality, inject chaos, and validate UI stability, all streamed live to a vibrant dashboard.

---

## 🏗 Architecture & Tech Stack

WebSwarm is built with a modern, high-performance architecture:

- **Frontend:** React, Vite, Tailwind CSS (Glassmorphism UI), Recharts, Lucide Icons.
- **Backend:** FastAPI (Python), WebSockets, SQLite.
- **AI & Automation:** Google Gemini 2.5 Flash, LangGraph, Playwright.
- **Resilience Engine:** Custom `GeminiClientManager` featuring automatic API key rotation (round-robin), `asyncio.Semaphore` concurrency throttling, and exponential backoff retry loops to completely bypass rate limits.

---

## ✨ Core Features

- **🧠 LangGraph 5-Agent Swarm:** A coordinated team of distinct AI agents working autonomously:
  1. **Planner Agent:** Analyzes the objective and strategizes the test path.
  2. **Navigation Agent:** Controls Playwright, scrapes links, and navigates.
  3. **Functional Agent:** Dynamically interacts with forms, buttons, and DOM elements.
  4. **Chaos Agent:** Injects extreme boundary tests, multi-click stress, and XSS payloads.
  5. **Validation Agent:** Acts as the Senior QA to evaluate the logs, confirm bugs, and assign severities.
- **📺 Live Visual Test Streaming:** Watch the AI test your app in real-time. Playwright captures and streams Base64 JPEG DOM states over WebSockets directly into the frontend canvas.
- **📊 Real-time Telemetry:** Granular monitoring of Token Usage, Model Confidence Scores, and Execution Time (ms) per agent.
- **🐞 Smart Bug Tracker:** An interactive data table that logs every discovered vulnerability with severity levels (Critical, High, Medium, Low).
- **👁️ Vision Diffs Engine:** Side-by-side snapshot comparison calculating pixel-level variance and layout shifts caused by AI interactions.
- **📈 Historical Regression Analytics:** Beautiful Recharts Area and Bar graphs showing bug regression trends and severity spikes over time across different target URLs.
- **📄 Executive HTML Reports:** Generate and download gorgeous, print-ready HTML reports containing executive summaries, metrics, and deep-dive technical root-cause analyses written by the AI.

---

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- SQLite (pre-installed on most systems)

### 2. Configure Environment Keys
Navigate to the `backend` directory and edit the `.env` file to include your Google Gemini API key(s). 
*Note: WebSwarm supports a multi-key pool. If one key hits a rate limit, the system will automatically rotate to the next key to prevent crashes.*

Create `backend/.env`:
```env
# Single Key
GEMINI_API_KEY="your_google_ai_studio_api_key_here"

# OR Multi-Key Pool (Highly Recommended for free tiers)
GEMINI_API_KEY_1="key_one..."
GEMINI_API_KEY_2="key_two..."
GEMINI_API_KEY_3="key_three..."
```

### 3. Automated Startup (Recommended)
You can boot the entire stack (install dependencies, setup virtual environments, and start servers) with a single command!

**Windows:**
```bat
start.bat
```

**Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

### 4. Manual Startup (Alternative)

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
playwright install chromium
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### 5. Access the Platform
Once booted, access the beautiful WebSwarm dashboard at: **http://localhost:5173**

---

## 🗄️ Database Inspection (VS Code)
WebSwarm stores everything perfectly offline in a local SQLite database (`backend/webswarm.db`).
If you are using Visual Studio Code, we have pre-configured workspace settings. 
1. Install the recommended extension (`alexcvzz.vscode-sqlite`).
2. Open the Command Palette (`Ctrl+Shift+P`) and search for **"SQLite: Open Database"**.
3. Select `backend/webswarm.db` to instantly browse `test_runs`, `bugs`, `users`, and `vision_diffs` directly in your editor!
