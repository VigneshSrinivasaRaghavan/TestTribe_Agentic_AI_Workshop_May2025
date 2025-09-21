# 📘 Day 8 – Capstone Project

Welcome to the **Capstone Day** of our Agentic AI for Testers workshop! 🚀
Today, you’ll work in teams to design and implement your **own QA Agent** using everything we learned over the past 7 days:

* LangGraph for orchestration
* Memory & persistence
* Logs & reporting
* LLM integration (OpenAI, Ollama, Gemini, etc.)

At the end of this session, 1–2 teams will showcase their work live.

---

## 🎯 Objective

Each team will **pick one project** from the 3 options below. The goal is **not** to write perfect production code, but to show that you can:

* Break down a QA use case into an **agent flow** (inputs → processing → outputs).
* Use LangGraph to connect nodes.
* Save results into a report (CSV/JSON/Markdown).
* Log execution steps for traceability.
* (Optional) Add stretch goals like Jira/Slack integration.

👉 **Even if you’re new to Python, don’t worry.**
You can **leverage GenAI tools** like ChatGPT, Gemini, or Cursor AI to help generate boilerplate code. For example:

* Ask ChatGPT: *“Write a Python function that reads a CSV and extracts column X.”*
* Or: *“Convert this test case description into JSON format using Python.”*

Your creativity + AI assistance = working agent! 💡

---

## 🛠 Capstone Agent Options

### 1️⃣ Bug Report Summarizer Agent

**Input:** Raw defect logs or a bug export file (`bugs_raw.txt`).
**Task:** Convert messy/unstructured bug details into a **clean summary** with:

* Bug ID / Title
* Steps to Reproduce
* Expected vs Actual behavior
* Severity

**Must-Have Outcome:** A `bugs_summary.csv` file with structured bug reports.
**Stretch Goal:** Auto-create a Jira issue via API.

---

### 2️⃣ Requirement Coverage Agent

**Input:**

* Requirements file (`requirements.txt`)
* Test cases file (`testcases.csv`)

**Task:** Check whether every requirement has at least one mapped test.

**Must-Have Outcome:** A `coverage_report.json` with:

* Coverage percentage
* List of covered vs uncovered requirements

**Stretch Goal:** Auto-generate missing test case drafts using LLM.

---

### 3️⃣ Test Data Generator Agent

**Input:** Requirement or test description file (`testdata_prompt.txt`).

**Task:** Generate sample test input data. For example:

* Valid & invalid emails
* Edge-case phone numbers
* Date ranges (past/future)

**Must-Have Outcome:** A `testdata.csv` with at least 5 rows of generated test data.
**Stretch Goal:** Separate into *positive* vs *negative* test data.

---

## ⏱️ Suggested Timeline (2.5 hours)

1. **15 min** – Read capstone brief, form teams, pick one agent.
2. **90 min** – Build phase (use Day 1–7 code + GenAI for help).
3. **15 min** – Wrap up, prepare report files for demo.
4. **30 min** – Showcase (1–2 teams present live run).

---

## ✅ Expectations

* Every team must submit:

  * Input file(s) they worked on
  * Final output report (`.csv` / `.json`)
  * Logs showing the agent run

* Showcase focus:

  * Clear explanation of **what problem your agent solved**
  * Quick run-through of **code + final output**

Remember: **done is better than perfect.**
Aim for a working demo, not 100% polished code.

---

## 💡 Tips

* Use your Day 1–7 code as **reference templates**.
* Split team roles: *one drives coding, one researches prompts, one documents, one tests output, one preps for demo*.
* Don’t get stuck on syntax — use ChatGPT/Gemini to fill gaps.
* Focus on the **flow** (agent pipeline + useful output), not deep technical perfection.

---

🔥 That’s your Capstone! Good luck — can’t wait to see your QA agents in action.