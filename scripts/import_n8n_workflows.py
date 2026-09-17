#!/usr/bin/env python3
"""
Imports and activates all 9 Agency OS n8n workflow templates into the local n8n container.
Ensures active=True and proper n8n schema compatibility.
"""
import glob
import json
import os
import subprocess
import sys

def main():
    templates_dir = "/opt/agency/n8n/templates"
    if not os.path.isdir(templates_dir):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        templates_dir = os.path.join(base_dir, "n8n", "templates")
    dest_dir = "/opt/n8n/data/workflows"
    
    os.makedirs(dest_dir, exist_ok=True)
    for old_f in glob.glob(os.path.join(dest_dir, "*.json")):
        try:
            os.remove(old_f)
        except Exception:
            pass
    
    pattern = os.path.join(templates_dir, "**", "workflow.json")
    files = sorted(glob.glob(pattern, recursive=True))
    print(f"[Import] Found {len(files)} workflow templates to import into n8n from {templates_dir}.")

    imported_names = []
    for idx, fpath in enumerate(files):
        with open(fpath, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        
        data["active"] = True
        data.pop("tags", None)
        if "settings" not in data:
            data["settings"] = {}
        
        wf_name = data.get("name", f"workflow_{idx}")
        imported_names.append(wf_name)
        
        clean_name = f"wf_{idx}_{clean_filename(wf_name)}"
        dest_file = os.path.join(dest_dir, f"{clean_name}.json")
        with open(dest_file, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2)
        print(f"  [+] Prepared [{idx+1}/{len(files)}]: {wf_name} -> {clean_name}.json")

    # Set permissions for node user in docker
    try:
        subprocess.run(["sudo", "chown", "-R", "1000:1000", "/opt/n8n/data"], check=True)
    except Exception as e:
        print(f"[Warn] Chown failed: {e}")

    # Run n8n import CLI inside docker container
    cmd = [
        "sudo", "docker", "exec", "-u", "node", "n8n",
        "n8n", "import:workflow", "--separate", "--input=/home/node/.n8n/workflows/"
    ]
    print(f"[Import] Executing n8n CLI: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:\n", res.stdout)
    if res.stderr:
        print("STDERR:\n", res.stderr)

    # List workflows in n8n and publish each one
    list_cmd = ["sudo", "docker", "exec", "-u", "node", "n8n", "n8n", "list:workflow"]
    lres = subprocess.run(list_cmd, capture_output=True, text=True)
    print("[Import] Workflows in n8n after import:\n", lres.stdout)

    # Parse workflow IDs and publish them
    for line in lres.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Usually format is: <id>|<name> or similar table
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if parts:
            wf_id = parts[0]
            if wf_id.isdigit() or len(wf_id) > 1:
                try:
                    pub_cmd = ["sudo", "docker", "exec", "-u", "node", "n8n", "n8n", "publish:workflow", f"--id={wf_id}"]
                    pub_res = subprocess.run(pub_cmd, capture_output=True, text=True)
                    print(f"Published workflow {wf_id}: {pub_res.stdout.strip()}")
                except Exception as ex:
                    print(f"Failed publishing workflow {wf_id}: {ex}")

def clean_filename(name: str) -> str:
    import re
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)


if __name__ == "__main__":
    main()
