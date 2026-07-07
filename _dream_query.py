import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
c = conn.cursor()

# 1. List recent sessions
print("=== RECENT SESSIONS ===")
c.execute("SELECT id, project_id, title, time_created FROM session ORDER BY time_created DESC LIMIT 20")
for row in c.fetchall():
    print(json.dumps(row))

# 2. Get current project ID
print("\n=== CURRENT PROJECT ID ===")
c.execute("SELECT id FROM session WHERE directory LIKE '%Ilm Najot%' ORDER BY time_created DESC LIMIT 1")
row = c.fetchone()
if row:
    # Find the project_id from that session
    c.execute("SELECT project_id FROM session WHERE id = ?", (row[0],))
    proj = c.fetchone()
    if proj:
        project_id = proj[0]
        print(f"Project ID: {project_id}")
        
        # 3. List all sessions for this project
        print("\n=== ALL PROJECT SESSIONS (last 20) ===")
        c.execute("SELECT id, title, time_created FROM session WHERE project_id = ? ORDER BY time_created DESC LIMIT 20", (project_id,))
        for s in c.fetchall():
            print(json.dumps(s))
    else:
        print("No project_id found")
else:
    print("No sessions found for this directory")
    # Try all sessions
    c.execute("SELECT id, directory, project_id, time_created FROM session ORDER BY time_created DESC LIMIT 5")
    for row in c.fetchall():
        print(json.dumps(row))

conn.close()
