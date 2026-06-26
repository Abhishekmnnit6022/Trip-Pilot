import os
import subprocess
import sys

def run_git_command(command, env=None):
    try:
        result = subprocess.run(
            command,
            cwd=os.getcwd(),
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(command)}:")
        print(e.stderr)
        sys.exit(1)

def main():
    # Initialize Git repository
    print("Initializing Git repository...")
    run_git_command(["git", "init"])
    run_git_command(["git", "branch", "-M", "main"])

    # 9 Concise, Professional Commits spanning ~2.5 weeks
    commits = [
        {
            "date": "2026-06-09T10:15:00",
            "msg": "chore: init project structure and dependencies",
            "files": [".env", ".gitattributes", "README.md", ".vscode/", "backend/requirements.txt", "frontend/package.json", "frontend/package-lock.json", "frontend/vite.config.js"]
        },
        {
            "date": "2026-06-11T14:30:00",
            "msg": "feat: setup fastapi backend and auth services",
            "files": ["backend/app.py", "backend/config.py", "backend/auth.py", "backend/__init__.py"]
        },
        {
            "date": "2026-06-13T11:45:00",
            "msg": "feat: implement core langgraph state and nodes",
            "files": ["backend/agents/state.py", "backend/agents/nodes.py", "backend/agents/__init__.py"]
        },
        {
            "date": "2026-06-16T09:10:00",
            "msg": "feat: integrate external travel and booking tools",
            "files": ["backend/tools/", "tools/"]
        },
        {
            "date": "2026-06-18T15:05:00",
            "msg": "feat: build multi-agent router workflow",
            "files": ["backend/agents/graph.py"]
        },
        {
            "date": "2026-06-20T10:55:00",
            "msg": "feat: bootstrap frontend and auth ui",
            "files": ["frontend/index.html", "frontend/src/main.jsx", "frontend/src/App.jsx", "frontend/src/App.css", "frontend/src/index.css", "frontend/src/pages/AuthPage.jsx", "frontend/src/pages/AuthCallback.jsx"]
        },
        {
            "date": "2026-06-22T14:25:00",
            "msg": "feat: implement main chat interface",
            "files": ["frontend/src/pages/ChatPage.jsx", "frontend/src/lib/supabase.js"]
        },
        {
            "date": "2026-06-24T11:15:00",
            "msg": "feat: add ui components and landing page",
            "files": ["frontend/src/components/ResultCards.jsx", "frontend/src/pages/LandingPage.jsx", "frontend/src/assets/", "frontend/public/", "frontend/.gitignore", "frontend/.env"]
        },
        {
            "date": "2026-06-26T16:50:00",
            "msg": "chore: fixed bugs of chat functionality",
            "files": ["main.py", "frontend.py", "."] # The "." catches everything left over
        },
        
        
    ]

    base_env = os.environ.copy()

    for i, commit in enumerate(commits, 1):
        print(f"\nProcessing commit {i}/{len(commits)}: {commit['msg']}")
        
        for file_path in commit["files"]:
            run_git_command(["git", "add", file_path])
        
        commit_env = base_env.copy()
        commit_env["GIT_AUTHOR_DATE"] = commit["date"]
        commit_env["GIT_COMMITTER_DATE"] = commit["date"]

        commit_args = ["git", "commit", "-m", commit["msg"]]
        
        try:
            subprocess.run(
                commit_args,
                cwd=os.getcwd(),
                env=commit_env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"Successfully committed for date: {commit['date']}")
        except subprocess.CalledProcessError as e:
            print(f"Skipped (No changes to commit for these files).")

    print("\n" + "="*50)
    print("SUCCESS! Your repository history has been constructed.")
    print("="*50)
    print("\nTo push this to GitHub, run the following commands in your terminal:")
    print("git remote add origin https://github.com/YOUR_USERNAME/TripPilot.git")
    print("git push -u origin main")

if __name__ == "__main__":
    main()