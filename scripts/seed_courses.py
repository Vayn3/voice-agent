"""Run after git pull to synchronize the versioned course catalog."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.database import init_database
from backend.app.course_catalog import seed_courses

if __name__ == "__main__":
    init_database()
    print("课程已同步：" + ", ".join(seed_courses()))
