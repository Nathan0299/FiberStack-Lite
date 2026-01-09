#!/usr/bin/env python3
"""
Documentation Verification Script
- Checks for broken local file links in Markdown files.
- Checks for leftover TODO/FIXME markers.
"""

import os
import re
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent / "docs"
ROOT_DIR = Path(__file__).parent.parent

# Regex for Markdown links: [text](link)
LINK_PATTERN = re.compile(r'\[.*?\]\((.*?)\)')

def verify_file(filepath):
    errors = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    lines = content.splitlines()
    for i, line in enumerate(lines):
        # 1. Check for TODO/FIXME
        if "TODO" in line or "FIXME" in line:
             # Ignore if it's in this script or specific exclusions
             if "verify_docs.py" not in str(filepath):
                 errors.append(f"Line {i+1}: Found TODO/FIXME")

        # 2. Check Links
        matches = LINK_PATTERN.findall(line)
        for link in matches:
            if link.startswith("http") or link.startswith("#") or link.startswith("mailto:"):
                continue
            
            # Handle absolute file:// paths (common in this project's context)
            if link.startswith("file://"):
                path_str = link.replace("file://", "")
                # Remove anchor
                if "#" in path_str:
                    path_str = path_str.split("#")[0]
                
                target_path = Path(path_str)
            else:
                # Relative paths
                # Remove anchor
                if "#" in link:
                    link = link.split("#")[0]
                    
                target_path = (filepath.parent / link).resolve()
            
            if not target_path.exists():
                errors.append(f"Line {i+1}: Broken link to '{link}'")

    return errors

def main():
    print(f"Verifying docs in {DOCS_DIR}...")
    failure = False
    
    # Walk through docs dir
    for root, _, files in os.walk(DOCS_DIR):
        for file in files:
            if file.endswith(".md"):
                path = Path(root) / file
                errors = verify_file(path)
                if errors:
                    print(f"\n❌ {path.name}:")
                    for e in errors:
                        print(f"  - {e}")
                    failure = True
                else:
                    print(f"✅ {path.name}")
                    
    if failure:
        sys.exit(1)
    else:
        print("\nAll documentation verified successfully.")
        sys.exit(0)

if __name__ == "__main__":
    main()
