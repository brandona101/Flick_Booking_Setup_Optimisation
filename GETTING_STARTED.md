# Getting Started — Flick BSO Project

This guide gets you set up to contribute to the Booking Setup Optimisation repo and use it with Claude Code. No prior git experience needed — follow the steps in order.

---

## 1. Install the tools

### Git
Git tracks changes to files and syncs your work with the shared repo.

1. Download from [git-scm.com/downloads](https://git-scm.com/downloads) — pick the Windows installer
2. Run the installer, accepting all defaults
3. When done, open **Git Bash** (search for it in the Start menu) and run:
   ```bash
   git --version
   ```
   You should see something like `git version 2.x.x`. If so, you're good.

### GitHub account
If you don't already have one, create a free account at [github.com](https://github.com). Let Brandon know your username so he can add you as a collaborator on the repo.

### Claude Code (desktop app)
Claude Code is the AI assistant used to work on this project. We use the desktop app — no terminal setup required.

1. Download the Claude Code desktop app from [claude.ai/download](https://claude.ai/download) and install it
2. Open the app and log in with your Anthropic account. If you don't have one, sign up at [claude.ai](https://claude.ai) — a Claude Pro or Team subscription is required
3. That's it. You'll open the project folder from within the app (covered in step 5 below)

---

## 2. Clone the repo

"Cloning" downloads a full copy of the project to your machine.

1. Open **Git Bash**
2. Navigate to where you want to keep the project. For example, to put it in your Documents folder:
   ```bash
   cd ~/Documents
   ```
3. Clone the repo:
   ```bash
   git clone https://github.com/brandona101/Flick_Booking_Setup_Optimisation.git
   ```
4. Move into the project folder:
   ```bash
   cd Flick_Booking_Setup_Optimisation
   ```

You now have a local copy of the project. The folder structure looks like this:

```
Flick_Booking_Setup_Optimisation/
├── docs/                    Project proposal and scheduling logic docs
├── run-diagnostic/          Run Diagnostic tool (HTML) + user guides
├── run-maintenance/         Planned — run tuning tooling
├── run-builder/             Planned — visual run builder
└── ml-optimisation/
    └── pest/
        └── melbourne-commercial/   Active ML clustering scripts + SQL
```

---

## 3. Data handling — important

**Never commit data files to this repo.** Customer and operational data must stay off GitHub.

- Working data (CSV exports from Dynamics 365) goes in the `data/` subfolder inside each component — these are gitignored and will never be uploaded
- The `.gitignore` file automatically blocks `*.csv`, generated dashboards, and zip files
- If git ever asks you to commit a `.csv` file, stop and check with Brandon before proceeding

---

## 4. Daily workflow

### Before you start work — pull the latest changes
Always sync before starting to avoid conflicts with others' work:
```bash
git pull
```

### Making changes
Work on files as normal using your editor of choice. When you're ready to save your changes to the shared repo:

1. **Check what's changed:**
   ```bash
   git status
   ```

2. **Stage the files you want to commit** (be specific — don't use `git add .` blindly):
   ```bash
   git add path/to/your/file.py
   ```

3. **Commit with a clear message:**
   ```bash
   git commit -m "Brief description of what changed and why"
   ```

4. **Push to GitHub:**
   ```bash
   git push
   ```

### If two people edit the same file
Git will flag a **merge conflict**. Don't panic — reach out to Brandon and resolve it together before pushing. Don't force-push or overwrite someone else's work.

---

## 5. Using Claude Code

Claude Code is an AI assistant that understands the full project — its history, scripts, docs, and design decisions — and helps you build and iterate faster.

### Starting a session
1. Open the **Claude Code desktop app**
2. Click **Open Folder** (or similar — it may prompt you on first launch) and navigate to your cloned `Flick_Booking_Setup_Optimisation` folder
3. Claude will read the project context automatically — including `CLAUDE.md` files that contain project-specific guidance on the algorithm, data structure, and business rules

You can now chat with Claude directly about anything in the project.

### What Claude can help with
- **Running and modifying scripts** — ask it to adjust clustering parameters, add a new branch to the ML pipeline, or debug a script
- **Explaining code** — paste a section and ask what it does
- **Generating outputs** — run Phase 0/1 scripts against a new branch's data export with Claude's help
- **Writing and editing docs** — update READMEs, draft notes for branch reviews, summarise run outputs
- **SQL** — modify the AGB export queries for a new branch or data requirement

### Example prompts to get started
> "Run the Phase 0 distribution analysis against the data I've placed in ml-optimisation/pest/melbourne-commercial/data/"

> "Explain what the tabu-search rebalance step in phase1_clustering.py is doing"

> "I'm adding Brisbane Commercial Pest — what do I need to set up for a new branch?"

> "The diagnostic tool flagged 14 overloaded slots for this branch. What are the options for fixing that?"

### Things to keep in mind
- Claude cannot access GitHub, Dynamics 365, or Databricks directly — it works with files you have locally
- Never paste raw customer data (names, addresses, site details) into the Claude chat — work at the level of exported CSVs in the `data/` folder
- If Claude makes a code change you're unsure about, use `git diff` to review it before committing

---

## 6. Getting help

| Problem | Who to ask |
|---|---|
| Git / repo access issues | Brandon Atkinson |
| Claude Code login / billing | [claude.ai/support](https://claude.ai/support) |
| Dynamics 365 data exports | Your branch ops or the national team |
| Script errors / algorithm questions | Brandon Atkinson |

---

## Coming soon

- **Jira integration** — tickets for each component will link directly to this repo once the Jira board is set up. Branch naming and commit message conventions will be updated at that point.
