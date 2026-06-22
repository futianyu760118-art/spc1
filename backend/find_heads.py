import re, os

versions_dir = r'd:\wanghuazheng\project\SPC-v2\backend\alembic\versions'
revisions = {}
down_revs = set()

for f in os.listdir(versions_dir):
    if not f.endswith('.py'):
        continue
    content = open(os.path.join(versions_dir, f)).read()
    rev_m = re.search(r"revision\s*[:=]\s*['\"]([^'\"]+)['\"]", content)
    down_m = re.search(r"down_revision\s*[:=]\s*(.+?)$", content, re.MULTILINE)
    if rev_m:
        rev = rev_m.group(1)
        revisions[rev] = f
        if down_m:
            down_text = down_m.group(1).strip()
            for d in re.findall(r"['\"]([^'\"]+)['\"]", down_text):
                down_revs.add(d)

heads = [r for r in revisions if r not in down_revs]
print("Heads:")
for h in heads:
    print(f"  {h} -> {revisions[h]}")
