import os
import re
from pathlib import Path

root_dir = Path(__file__).resolve().parent
frontend_dir = root_dir / "mobile" / "src"
backend_dir = root_dir / "backend" / "app" / "routers"

api_pattern = re.compile(r'(apiGet|apiPost|apiPut|apiPatch|apiDelete)\s*(?:<[^>]+>)?\s*\(\s*[`"\']([^"\'`]+)[`"\']')

calls = []
for root, _, files in os.walk(frontend_dir):
    for f in files:
        if f.endswith(('.ts', '.tsx')):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fl:
                for method, path in api_pattern.findall(fl.read()):
                    clean_path = path.split('?')[0]
                    norm_path = re.sub(r'\$\{[^}]+\}', '{param}', clean_path)
                    verb = method.replace("api", "").upper()
                    calls.append((verb, norm_path, f))

backend_routes = []
route_pattern = re.compile(r'@router\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']*)["\']')
prefix_pattern = re.compile(r'router\s*=\s*APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']')

for f in os.listdir(backend_dir):
    if f.endswith('.py') and f != '__init__.py':
        p = os.path.join(backend_dir, f)
        with open(p, 'r', encoding='utf-8', errors='ignore') as fl:
            content = fl.read()
            pfx_match = prefix_pattern.search(content)
            pfx = pfx_match.group(1) if pfx_match else ""
            for method, path in route_pattern.findall(content):
                full_path = pfx + path
                stripped = re.sub(r'^/v1', '', full_path)
                if not stripped.startswith('/'):
                    stripped = '/' + stripped
                norm_full = re.sub(r'\{[^}]+\}', '{param}', stripped)
                backend_routes.append((method.upper(), norm_full, f))

backend_set = set((m, norm) for m, norm, _ in backend_routes)
frontend_set = set((m, norm) for m, norm, _ in calls)

print(f"Total Unique Frontend Calls: {len(frontend_set)}")
print(f"Total Unique Backend Routes: {len(backend_set)}")

unmatched_fe = []
for m, norm in sorted(frontend_set):
    if (m, norm) not in backend_set:
        unmatched_fe.append((m, norm))

if unmatched_fe:
    print(f"\n[!] FRONTEND CALLS NOT MATCHING BACKEND ({len(unmatched_fe)}):")
    for m, norm in unmatched_fe:
        files = [f for verb, path, f in calls if verb == m and path == norm]
        print(f"  {m:6} {norm:35} in {set(files)}")
else:
    print("\n[OK] ALL FRONTEND CALLS PERFECTLY MATCH BACKEND ENDPOINTS!")
