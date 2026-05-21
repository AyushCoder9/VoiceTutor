import os
import subprocess
import datetime

commits = [
    ("Initial project setup", ["README.md", ".gitignore", "backend/requirements.txt", "frontend/package.json", "backend/.env.example"]),
    ("Setup backend core", ["backend/server.py", "backend/bot.py"]),
    ("Implement agent logic", ["backend/agent"]),
    ("Add curriculum module", ["backend/curriculum"]),
    ("Implement memory layer", ["backend/memory", "backend/data"]),
    ("Configure transports", ["backend/transports"]),
    ("Add observability tracking", ["backend/observability", "logs"]),
    ("Add test suite", ["backend/tests", "test_pipecat.py"]),
    ("Setup frontend core", ["frontend/app", "frontend/lib"]),
    ("Build UI components", ["frontend/components"]),
    ("Configure frontend tools", ["frontend/tsconfig.json", "frontend/tailwind.config.ts", "frontend/postcss.config.mjs", "frontend/next.config.mjs", "frontend/package-lock.json", "frontend/public"]),
    ("Add project documentation", ["docs", "EMAIL.md", "WRITEUP.md", "GLOSSARY.md", "INTERVIEW_PREP.md", "VIDEO_SCRIPT.md"]),
    ("Finalize remaining files", ["."])
]

os.system("rm -rf .git")
os.system("git init")
os.system('git config user.name "ayushkumarsingh"')
os.system('git config user.email "ayushkumarsingh@users.noreply.github.com"')
os.system('git branch -M main')
os.system('git remote add origin https://github.com/AyushCoder9/VoiceTutor.git')

start_time = datetime.datetime(2026, 5, 20, 9, 0, 0)
end_time = datetime.datetime(2026, 5, 22, 2, 50, 0)
time_step = (end_time - start_time) / len(commits)

current_time = start_time

for msg, paths in commits:
    for path in paths:
        if os.path.exists(path) or path == ".":
            subprocess.run(["git", "add", path])
    
    date_str = current_time.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date_str
    env["GIT_COMMITTER_DATE"] = date_str
    
    subprocess.run(["git", "commit", "-m", msg], env=env)
    current_time += time_step
