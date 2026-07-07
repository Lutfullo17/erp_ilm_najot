import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
c = conn.cursor()

# Get ALL parts from this session to see the full story
session_id = 'ses_0c4e6e9a8ffelH9wn6qr8AbB7z'
print(f"=== ALL PARTS SESSION: {session_id} ===")
c.execute("""
    SELECT m.id,
           json_extract(m.data, '$.role') as role,
           json_extract(p.data, '$.type') as part_type,
           json_extract(p.data, '$.tool') as tool,
           substr(json_extract(p.data, '$.text'), 1, 400) as text_preview,
           substr(json_extract(p.data, '$.state.output'), 1, 400) as output_preview
    FROM message m
    JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
    ORDER BY m.time_created, p.time_created
""", (session_id,))
for row in c.fetchall():
    role = row[1]
    ptype = row[2]
    tool = row[3]
    text = row[4] or ''
    output = row[5] or ''
    if ptype == 'tool' and tool:
        print(f"  [{role}] TOOL: {tool}")
        if output:
            print(f"    OUTPUT: {output[:300]}")
    elif ptype == 'text' and text:
        print(f"  [{role}] TEXT: {text[:300]}")
    elif ptype in ('step-start', 'step-finish'):
        pass  # skip step markers
    elif ptype == 'actor':
        pass  # skip actor calls

conn.close()
