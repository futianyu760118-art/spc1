import re, os

versions_dir = os.path.join(os.path.dirname(__file__), 'alembic', 'versions')
revisions = {}
down_revisions = set()

for fn in os.listdir(versions_dir):
    if not fn.endswith('.py') or fn.startswith('__'):
        continue
    with open(os.path.join(versions_dir, fn), 'r', encoding='utf-8') as f:
        content = f.read()
    
    rev_match = re.search(r'^revision[:\s]+[=:]\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    down_match = re.search(r'^down_revision[:\s]+[=:]\s*(.+)', content, re.MULTILINE)
    
    if rev_match:
        rev = rev_match.group(1)
        revisions[rev] = fn
        
        if down_match:
            down_val = down_match.group(1).strip()
            # Extract revision IDs from tuple or string
            ids = re.findall(r'["\']([^"\']+)["\']', down_val)
            for d in ids:
                down_revisions.add(d)

# Heads = revisions not referenced as down_revision by any other
heads = set(revisions.keys()) - down_revisions
print("Heads:")
for h in sorted(heads):
    print(f"  {h} -> {revisions[h]}")
