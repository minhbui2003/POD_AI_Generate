import json
import os
import time


def append_generation_audit(output_folder, record):
    os.makedirs(output_folder, exist_ok=True)
    audit_path = os.path.join(output_folder, "generation_audit.jsonl")
    data = dict(record)
    data.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))

    with open(audit_path, "a", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=True) + "\n")

    return audit_path
