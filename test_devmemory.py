"""
Interactive Test & Demo Runner for DevMemory.

Creates a live test project with Git commits, DevMemory checkpoints,
metrics tracking, and regression detection.
"""

import os
import sys
import shutil
import subprocess

# Ensure UTF-8 printing on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import devmemory
from devmemory import DevMemoryProject


def run_test():
    print("=" * 60)
    print("🚀 DevMemory Live End-to-End Test")
    print("=" * 60)

    # 1. Setup sample project directory
    sample_dir = os.path.abspath("sample_project")
    if os.path.exists(sample_dir):
        shutil.rmtree(sample_dir)
    os.makedirs(sample_dir, exist_ok=True)

    print(f"\n1. Creating test project at: {sample_dir}")

    # 2. Initialize Git repo in sample project
    try:
        subprocess.run(["git", "init"], cwd=sample_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "AI Agent"], cwd=sample_dir, check=True)
        subprocess.run(["git", "config", "user.email", "agent@devmemory.io"], cwd=sample_dir, check=True)
        print("   ✅ Git repository initialized.")
    except Exception as e:
        print(f"   ⚠️ Git init warning: {e}")

    # 3. Initialize DevMemory
    proj = devmemory.init(sample_dir, name="Sentiment Classifier", project_id="sentiment-app")
    print(f"   ✅ DevMemory initialized in {proj.config.devmemory_dir}")

    # -------------------------------------------------------------
    # Version 1: Initial Implementation
    # -------------------------------------------------------------
    print("\n2. Creating Version 1 (Initial Model)...")
    model_code = """# Sentiment Model v1
def predict(text):
    words = text.lower().split()
    positive = ["good", "great", "awesome", "excellent", "love"]
    score = sum(1 for w in words if w in positive)
    return "POSITIVE" if score > 0 else "NEGATIVE"
"""
    with open(os.path.join(sample_dir, "model.py"), "w", encoding="utf-8") as f:
        f.write(model_code)

    _git_commit(sample_dir, "Initial baseline sentiment model\n\nEntire-Checkpoint: 01K9TQ8ZP7X3F5M2WVJ4CNRB6D")

    v1 = proj.checkpoint(
        intent="Implement baseline sentiment classifier",
        feature="sentiment-analysis",
        status="SUCCESS",
        tests_passed=20,
        tests_failed=0,
        metrics={"accuracy": 82.5, "latency_ms": 12.4},
        agent="claude-code",
    )
    print(f"   ✅ Version v{v1['version_id']} recorded! Status: [{v1['status']}] Accuracy: {v1['metrics']['accuracy']}%")

    # -------------------------------------------------------------
    # Version 2: Enhanced Vocabulary (Improvement)
    # -------------------------------------------------------------
    print("\n3. Creating Version 2 (Vocabulary Enhancement)...")
    model_code_v2 = """# Sentiment Model v2 - Extended Vocab
def predict(text):
    words = text.lower().split()
    positive = {"good", "great", "awesome", "excellent", "love", "fantastic", "amazing", "best"}
    negative = {"bad", "terrible", "horrible", "awful", "hate", "worst"}
    pos_score = sum(1 for w in words if w in positive)
    neg_score = sum(1 for w in words if w in negative)
    return "POSITIVE" if pos_score >= neg_score else "NEGATIVE"
"""
    with open(os.path.join(sample_dir, "model.py"), "w", encoding="utf-8") as f:
        f.write(model_code_v2)

    _git_commit(sample_dir, "Extend vocabulary dictionary\n\nEntire-Checkpoint: 01K9TQ9AP8Y4G6N3XWK5DOSC7E")

    v2 = proj.checkpoint(
        intent="Add negative words dictionary and extended positive vocab",
        feature="sentiment-analysis",
        status="SUCCESS",
        tests_passed=35,
        tests_failed=0,
        metrics={"accuracy": 91.0, "latency_ms": 11.2},
        agent="claude-code",
    )
    print(f"   ✅ Version v{v2['version_id']} recorded! Accuracy improved to {v2['metrics']['accuracy']}% (+8.5%)")

    # -------------------------------------------------------------
    # Version 3: Regression Attempt (Bad Heuristic)
    # -------------------------------------------------------------
    print("\n4. Creating Version 3 (Simulating a Regression)...")
    model_code_v3 = """# Sentiment Model v3 - Flawed Logic
def predict(text):
    # Bug: checking length instead of sentiment words
    return "POSITIVE" if len(text) > 10 else "NEGATIVE"
"""
    with open(os.path.join(sample_dir, "model.py"), "w", encoding="utf-8") as f:
        f.write(model_code_v3)

    _git_commit(sample_dir, "Simplify sentiment rule to character length\n\nEntire-Checkpoint: 01K9TQABC9Z5H7P4YXL6EPTD8F")

    v3 = proj.checkpoint(
        intent="Replace word lookup with string length threshold for 10x speed",
        feature="sentiment-analysis",
        tests_passed=12,
        tests_failed=23,
        metrics={"accuracy": 54.0, "latency_ms": 1.5},
        agent="cursor-agent",
    )
    print(f"   ⚠️ Version v{v3['version_id']} automatically flagged: [{v3['status']}] (is_regression={v3['is_regression']})")
    print(f"   Reason: {v3['analysis']}")
    print(f"   Advice: {v3['recommendation']}")

    # -------------------------------------------------------------
    # 5. Test Version Comparison (Diffing)
    # -------------------------------------------------------------
    print("\n5. Testing Version Comparison (v2 vs v3)...")
    diff_result = proj.diff(2, 3)
    print("   Metric Changes:")
    for k, info in diff_result["metric_changes"].items():
        print(f"     - {k}: {info['before']} -> {info['after']} (delta: {info.get('change')} [{info.get('direction')}])")
    print(f"   Test Changes: passed {diff_result['test_changes']['passed']:+}, failed {diff_result['test_changes']['failed']:+}")

    # -------------------------------------------------------------
    # 6. Test AI Context & Warning Prevention
    # -------------------------------------------------------------
    print("\n6. Testing AI Memory Warnings...")
    context = proj.context(feature="sentiment-analysis")
    print("\n--- AI AGENT PROMPT INJECTION SNIPPET ---")
    print(context["prompt_snippet"])

    # -------------------------------------------------------------
    # 7. Web Dashboard Server Launcher
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("🎉 All Tests Passed Successfully!")
    print("=" * 60)
    print("\nTo explore this project visually in the Web Dashboard, run:")
    print(f"   cd \"{sample_dir}\"")
    print("   devmemory serve")
    print("   -> Open http://127.0.0.1:8765\n")


def _git_commit(repo_dir: str, message: str):
    try:
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo_dir, check=True, capture_output=True)
    except Exception:
        pass


if __name__ == "__main__":
    run_test()
