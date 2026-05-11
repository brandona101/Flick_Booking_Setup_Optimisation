# Getting Started - Flick BSO Project

This guide gets you set up to contribute to the Booking Setup Optimisation repo and use it with Claude Code. No prior git or coding experience needed.

---

## 1. Install the tools

### GitHub account
Create a free account at [github.com](https://github.com) if you don't have one. Let Brandon know your username so he can add you as a collaborator.

### Claude Code (desktop app)
Claude Code is the AI assistant used to work on this project.

1. Download the Claude Code desktop app from [claude.ai/download](https://claude.ai/download) and install it
2. Open the app and log in - a Claude Pro or Team subscription is required (sign up at [claude.ai](https://claude.ai) if needed)

---

## 2. Get the repo onto your machine

Open Claude Code desktop, then ask it:

> "Clone the Flick BSO repo from https://github.com/brandona101/Flick_Booking_Setup_Optimisation.git into my Documents folder"

Claude will handle the clone. Once done, open the `Flick_Booking_Setup_Optimisation` folder from within the app - it will read the project context automatically.

The folder structure looks like this:

```
Flick_Booking_Setup_Optimisation/
├── docs/                    Project proposal and scheduling logic docs
├── run-diagnostic/          Run Diagnostic tool (HTML) + user guides
├── run-maintenance/         Planned - run tuning tooling
├── run-builder/             Planned - visual run builder
└── ml-optimisation/
    └── pest/
        └── melbourne-commercial/   Active ML clustering scripts + SQL
```

---

## 3. Data handling - Important

**Never commit data files to this repo.** Customer and operational data must stay off GitHub.

- Working data (CSV exports from Dynamics 365) goes in the `data/` subfolder inside each component - these are automatically excluded and will never be uploaded
- If Claude ever lists a `.csv` file as a pending change, stop and check with Brandon before committing
- The same applies to any file containing site names, addresses, or customer details

**Saving local files you don't want uploaded.** If you want to keep notes, working files, or personal scripts inside the project folder without them going to GitHub, just ask Claude:

> "Add [filename] to the gitignore so it stays local only"

Claude will update the `.gitignore` file so git never picks it up. Useful for scratch files, local exports, or anything else that's useful to you but not relevant to the shared repo.

---

## 4. Working with Claude and commits - Read this before you start

Claude Code is powerful but will sometimes make changes beyond what you asked for, or suggest commits more frequently than needed. To keep the repo clean and changes easy to review:

**Before committing anything, ask Claude:**
> "Show me a full list of every file that has changed and explain the major modifications in each"

Review that list. If anything looks unrelated to your task, ask Claude to revert those specific files before committing.

**One commit per task.** Don't commit after every small step - finish the task, review all changes together, then commit once with a clear summary of what was done and why.

**Do not set Claude to "Always Allow" for commits or pushes.** Approve each one individually so you stay in control of what goes to the shared repo. This makes it significantly easier to review history and revert if something goes wrong.

All changes go to your own branch first (covered below) - Pushes will then be reviewed prior to merging to main. 

---

## 5. Daily workflow

### Starting work - sync and create a branch

Always start by getting the latest version of the repo and creating a branch for your work. Ask Claude:

> "Fetch and pull the latest changes from the remote, then create a new branch called [your-branch-name]"

Use a short, descriptive branch name - e.g. `brisbane-pest-phase0` or `diagnostic-tool-update`.

Working on your own branch means your changes stay separate until they are reviewed and merged to main. Never work directly on master.

**Tell Claude which part of the repo your task relates to before you start.** This repo will grow to cover multiple tools and service lines, and Claude reads project context broadly by default. If your task only involves the Melbourne Commercial ML scripts, say so - e.g.:

> "I'm working in ml-optimisation/pest/melbourne-commercial/ only - please focus on that area for this task"

This keeps Claude's context focused on what's relevant, avoids it touching unrelated parts of the repo, and reduces unnecessary credit usage.

### Making and committing changes

Work through your task with Claude's help. When you're ready to commit:

1. Ask Claude for a full list of changed files and what was modified in each
2. Review the list - anything unrelated to your task should be questioned or reverted before committing
3. Once you're happy, ask Claude to commit with a clear summary message
4. Claude will ask for your approval before committing - review and confirm

### Pushing and requesting a merge

When your task is complete and committed, ask Claude to push your branch:

> "Push my branch to the remote"

### If there's a conflict

If two people have edited the same file, git will flag a conflict. Don't try to resolve it yourself - I (Brandon) am happy to review this to make sure that the changes do not overlap.

---

## 6. Using Claude Code

Claude reads the project context automatically when you open the folder - including the algorithm reference and decision log in `ml-optimisation/pest/melbourne-commercial/`.

### Things to keep in mind
- Claude works with files on your local machine - it cannot access GitHub, Dynamics 365, or Databricks directly
- Never paste raw customer data (names, addresses, site details) into the Claude chat
- Always review changes before committing - see section 4

---

## Coming soon

- **Jira integration** - tickets for each component will link directly to this repo once the Jira board is set up.
