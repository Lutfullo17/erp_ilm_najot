import sqlite3, json

conn = sqlite3.connect(r'C:\Users\user\.local\share\mimocode\mimocode.db')
c = conn.cursor()

# Check session: "Bot xabaridagi to'lov balanslarini tuzatish"
session_id = 'ses_0c8fca787ffe7vw98xZTOUzkak'
print(f"=== SESSION: Bot payment balance fix ===")
c.execute("""
    SELECT m.id,
           json_extract(m.data, '$.role') as role,
           json_extract(p.data, '$.type') as part_type,
           json_extract(p.data, '$.tool') as tool,
           substr(json_extract(p.data, '$.text'), 1, 500) as text_preview,
           substr(json_extract(p.data, '$.state.output'), 1, 500) as output_preview
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
        print(f"  [{role}] TEXT: {text[:400]}")

# Check session: "Dars jadvali yaxshilash va o'zgartirish cheklovlari"
session_id2 = 'ses_0dc4fe4faffepsoBgeVz5CRLf3'
print(f"\n=== SESSION: Dars jadvali yaxshilash ===")
c.execute("""
    SELECT m.id,
           json_extract(m.data, '$.role') as role,
           json_extract(p.data, '$.type') as part_type,
           json_extract(p.data, '$.tool') as tool,
           substr(json_extract(p.data, '$.text'), 1, 500) as text_preview,
           substr(json_extract(p.data, '$.state.output'), 1, 500) as output_preview
    FROM message m
    JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
    ORDER BY m.time_created, p.time_created
""", (session_id2,))
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
        print(f"  [{role}] TEXT: {text[:400]}")

conn.close()
