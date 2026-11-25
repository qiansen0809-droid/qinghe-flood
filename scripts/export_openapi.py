"""Run python -m scripts.export_openapi from the project root."""
import json
from pathlib import Path
from app.api import ROOT, app

def main():
    path = ROOT/'docs'/'openapi.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(path)

if __name__=='__main__':
    main()

