import os
path = r'C:\Users\user\.local\share\mimocode\memory\projects\5d7f797e-ee56-47f8-b50b-0e753109bd11\MEMORY.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
lines = content.split('\n')
print(f'Lines: {len(lines)}')
print(f'Size: {len(content.encode("utf-8"))} bytes')
