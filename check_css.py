import re, os, glob

with open(os.path.join('templates', 'base.html'), 'r', encoding='utf-8') as f:
    content = f.read()

defined = set(re.findall(r'\.([\w-]+)\s*\{', content))

used = set()
for tpl in glob.glob('templates/**/*.html', recursive=True):
    with open(tpl, 'r', encoding='utf-8') as f:
        for m in re.findall(r'class="([^"]+)"', f.read()):
            used.update(m.split())

skip = {'fas', 'fab', 'far'}
missing = used - defined - skip
missing = {c for c in missing if not c.startswith('fa-')}

for c in sorted(missing):
    print(f'  .{c}')
