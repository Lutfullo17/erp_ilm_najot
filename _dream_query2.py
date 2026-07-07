import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
c = conn.cursor()

# Check the most recent work session: "To'lov tarixida o'quvchi ismi formatlash"
session_id = 'ses_0c4e6e9a8ffelH9wn6qr8AbB7z'
print(f"=== SESSION: {session_id} ===")
c.execute("""
    SELECT m.id, m.agent_id,
           json_extract(p.data, '$.type') as part_type,
           json_extract(p.data, '$.tool') as tool,
           substr(p.data, 1, 600) as preview
    FROM message m
    JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
      AND json_extract(m.data, '$.role') = 'user'
    ORDER BY m.time_created
    LIMIT 5
""", (session_id,))
for row in c.fetchall():
    print(json.dumps(row, default=str))

# Also check assistant responses with tool calls
print("\n=== ASSISTANT ACTIONS ===")
c.execute("""
    SELECT m.id,
           json_extract(p.data, '$.type') as part_type,
           json_extract(p.data, '$.tool') as tool,
           substr(json_extract(p.data, '$.text'), 1, 300) as text_preview,
           substr(json_extract(p.data, '$.state.output'), 1, 300) as output_preview
    FROM message m
    JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
      AND json_extract(m.data, '$.role') = 'assistant'
    ORDER BY m.time_created
    LIMIT 20
""", (session_id,))
for row in c.fetchall():
    print(json.dumps(row, default=str))

conn.close()
