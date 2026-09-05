"""
Development Version Control Testing Script for test_app.

Simulates an AI-assisted development workflow with DevMemory:
- Version 1: Baseline model
- Version 2: Feature improvement
- Version 3: AI Regression turn
- Version 4: Recovery turn guided by DevMemory context
"""

import os
import sys
import shutil
import subprocess

# Add parent directory to path so devmemory can be imported directly
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import devmemory
from devmemory import DevMemoryProject


def _git(cmd_args, cwd):
    try:
        subprocess.run(["git"] + cmd_args, cwd=cwd, check=True, capture_output=True)
    except Exception:
        pass


def execute_version_control_demo():
    print("=" * 65)
    print("⚡ DevMemory Version Control Testing Environment")
    print("   Project: test_app")
    print("=" * 65)

    # 1. Initialize Git in test_app
    _git(["init"], current_dir)
    _git(["config", "user.name", "AI Assistant"], current_dir)
    _git(["config", "user.email", "agent@devmemory.io"], current_dir)
    print("\n✅ Step 1: Initialized Git repository in test_app/")

    # Reset existing database if present so version numbers always start cleanly at v1..v4
    db_path = os.path.join(current_dir, ".devmemory", "devmemory.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

    # 2. Initialize DevMemory
    proj = devmemory.init(current_dir, name="TextClassifier App", project_id="text-classifier-app")
    print(f"✅ Step 2: DevMemory tracking active in .devmemory/")

    # -------------------------------------------------------------
    # ITERATION 1: Baseline Classifier
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("📌 Iteration 1: Baseline Naive Bayes Classifier")
    print("-" * 50)
    _git(["add", "."], current_dir)
    _git(["commit", "-m", "Initial baseline classifier\n\nEntire-Checkpoint: 01K9TQ8ZP7X3F5M2WVJ4CNRB6D"], current_dir)

    v1 = proj.checkpoint(
        intent="Implement baseline sentiment classifier using positive vocabulary lookup",
        feature="sentiment-model",
        status="SUCCESS",
        tests_passed=3,
        tests_failed=2,
        metrics={"accuracy": 60.0, "latency_ms": 15.2},
        agent="claude-code",
    )
    print(f"   [v{v1['version_id']}] Status: [{v1['status']}] | Accuracy: {v1['metrics']['accuracy']}% | Tests: {v1['tests_passed']} passed, {v1['tests_failed']} failed")

    # -------------------------------------------------------------
    # ITERATION 2: Add Negative Vocabulary & Weighted Scoring
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("📌 Iteration 2: Feature Engineering & Negative Vocab")
    print("-" * 50)

    v2_code = """class TextClassifier:
    def __init__(self):
        self.positive = {"good", "great", "awesome", "excellent", "love", "fantastic"}
        self.negative = {"bad", "terrible", "horrible", "awful", "hate", "worst"}

    def predict(self, text: str) -> str:
        words = text.lower().split()
        pos_score = sum(1 for w in words if w in self.positive)
        neg_score = sum(1 for w in words if w in self.negative)
        return "POSITIVE" if pos_score >= neg_score else "NEGATIVE"
"""
    with open(os.path.join(current_dir, "classifier.py"), "w", encoding="utf-8") as f:
        f.write(v2_code)

    _git(["add", "."], current_dir)
    _git(["commit", "-m", "Add negative vocabulary and weighted scoring\n\nEntire-Checkpoint: 01K9TQ9AP8Y4G6N3XWK5DOSC7E"], current_dir)

    v2 = proj.checkpoint(
        intent="Add negative words dictionary and balance scoring logic",
        feature="sentiment-model",
        status="SUCCESS",
        tests_passed=5,
        tests_failed=0,
        metrics={"accuracy": 100.0, "latency_ms": 12.0},
        agent="claude-code",
    )
    print(f"   [v{v2['version_id']}] Status: [{v2['status']}] | Accuracy: {v2['metrics']['accuracy']}% (+40.0%) | Tests: {v2['tests_passed']} passed, {v2['tests_failed']} failed")

    # -------------------------------------------------------------
    # ITERATION 3: Flawed Prompt Turn (Simulating AI Regression)
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("📌 Iteration 3: Flawed AI Edit (Simulating Regression)")
    print("-" * 50)

    v3_code = """class TextClassifier:
    def __init__(self):
        pass

    def predict(self, text: str) -> str:
        # Flawed shortcut: checking string length instead of sentiment
        return "POSITIVE" if len(text) > 15 else "NEGATIVE"
"""
    with open(os.path.join(current_dir, "classifier.py"), "w", encoding="utf-8") as f:
        f.write(v3_code)

    _git(["add", "."], current_dir)
    _git(["commit", "-m", "Replace vocab lookup with character length rule\n\nEntire-Checkpoint: 01K9TQABC9Z5H7P4YXL6EPTD8F"], current_dir)

    v3 = proj.checkpoint(
        intent="Optimize inference speed by evaluating string character count instead of set lookup",
        feature="sentiment-model",
        tests_passed=2,
        tests_failed=3,
        metrics={"accuracy": 40.0, "latency_ms": 1.2},
        agent="cursor-agent",
    )
    print(f"   ⚠️ [v{v3['version_id']}] Status: [{v3['status']}] (is_regression={v3['is_regression']})")
    print(f"   Analysis: {v3['analysis']}")
    print(f"   Advice:   {v3['recommendation']}")

    # -------------------------------------------------------------
    # ITERATION 4: Recovery Turn Guided by DevMemory AI Context
    # -------------------------------------------------------------
    print("\n" + "-" * 50)
    print("📌 Iteration 4: Recovery Turn (Using DevMemory Context)")
    print("-" * 50)

    ctx = proj.context(feature="sentiment-model")
    print(f"   DevMemory Context Warning fetched for AI Agent:\n   -> '{ctx['warnings'][0]['recommendation']}'")

    v4_code = """class TextClassifier:
    def __init__(self):
        self.positive = {"good", "great", "awesome", "excellent", "love", "fantastic", "amazing"}
        self.negative = {"bad", "terrible", "horrible", "awful", "hate", "worst", "poor"}

    def predict(self, text: str) -> str:
        words = text.lower().replace("!", "").replace(".", "").split()
        pos_score = sum(1 for w in words if w in self.positive)
        neg_score = sum(1 for w in words if w in self.negative)
        return "POSITIVE" if pos_score >= neg_score else "NEGATIVE"
"""
    with open(os.path.join(current_dir, "classifier.py"), "w", encoding="utf-8") as f:
        f.write(v4_code)

    _git(["add", "."], current_dir)
    _git(["commit", "-m", "Restore vocabulary lookup and punctuation stripping\n\nEntire-Checkpoint: 01K9TQBDE0A6J8Q5ZYM7FQVE9G"], current_dir)

    v4 = proj.checkpoint(
        intent="Restore vocabulary lookup, add punctuation stripping, and expand sentiment sets",
        feature="sentiment-model",
        status="SUCCESS",
        tests_passed=5,
        tests_failed=0,
        metrics={"accuracy": 100.0, "latency_ms": 10.5},
        agent="claude-code",
    )
    print(f"   [v{v4['version_id']}] Status: [{v4['status']}] | Accuracy: {v4['metrics']['accuracy']}% | Tests: {v4['tests_passed']} passed, {v4['tests_failed']} failed")

    # -------------------------------------------------------------
    # Compare & Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 65)
    print("📊 DevMemory Version Control Test Summary")
    print("=" * 65)

    status = proj.status()
    print(f"Project:          {status['project_name']}")
    print(f"Current Version:  v{status['current_version']}")
    print(f"Total Iterations: {status['total_versions']}")
    print(f"Active Metrics:   {status['latest_metrics']}")

    diff = proj.diff(2, 3)
    print("\nComparing v2 -> v3 (Regression Step):")
    for k, info in diff["metric_changes"].items():
        print(f"   Metric '{k}': {info['before']} -> {info['after']} (change: {info['change']} [{info['direction']}])")

    print("\nLaunch the dashboard to view this test project interactively:")
    print(f"   python test_app/start_dashboard.py")
    print("   -> http://127.0.0.1:8765\n")


if __name__ == "__main__":
    execute_version_control_demo()
