# tree.py
import os
from pathlib import Path

# Корень проекта — на уровень выше, чем src
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = Path(__file__).parent / "PROJECT_STRUCTURE.md"

# Что включаем в анализ
INCLUDE_DIRS = ["src", "data", "backups", "logs", "assets", "docs"]
INCLUDE_EXTS = [".py", ".md", ".db", ".json", ".txt", ".sql"]

# Что исключаем
EXCLUDE_NAMES = [
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".vscode",
    "venv",
    "env",
    "*.pyc",
    "*.log",  # логи не включаем в структуру
    "logs/",  # сами логи — нет, но папку упоминаем
]

def should_include(path: Path) -> bool:
    if any(ex in str(path) for ex in EXCLUDE_NAMES):
        return False
    if path.is_file():
        return path.suffix in INCLUDE_EXTS
    return True

def generate_tree(root: Path, prefix: str = "", is_last: bool = True) -> str:
    try:
        items = sorted([p for p in root.iterdir() if should_include(p)], key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        return f"{prefix}{'└── ' if is_last else '├── '}[Ошибка доступа]\n"
    
    if not items:
        return ""

    tree_str = ""
    for i, item in enumerate(items):
        is_last_item = i == len(items) - 1
        connector = "└── " if is_last_item else "├── "
        
        tree_str += f"{prefix}{connector}{item.name}\n"
        
        if item.is_dir():
            extension = "    " if is_last_item else "│   "
            tree_str += generate_tree(item, prefix + extension, is_last_item)
    
    return tree_str

def main():
    print("🔄 Генерация структуры проекта...")
    
    tree = f"📁 {PROJECT_ROOT.name}/\n"
    tree += generate_tree(PROJECT_ROOT)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(tree)
    
    print(f"✅ Структура сохранена: {OUTPUT_FILE}")
    print("\n📋 Пример структуры:\n")
    print(tree[:500] + "..." if len(tree) > 500 else tree)

if __name__ == "__main__":
    main()