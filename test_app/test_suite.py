"""Automated test suite for TextClassifier in test_app."""

from classifier import TextClassifier

def run_tests():
    clf = TextClassifier()
    test_cases = [
        ("I love this!", "POSITIVE"),
        ("Awesome feature!", "POSITIVE"),
        ("This is terrible.", "NEGATIVE"),
        ("Very bad experience.", "NEGATIVE"),
        ("Excellent and great!", "POSITIVE"),
    ]
    passed = 0
    failed = 0
    for text, expected in test_cases:
        pred = clf.predict(text)
        if pred == expected:
            passed += 1
        else:
            failed += 1
    accuracy = (passed / len(test_cases)) * 100.0
    return {"passed": passed, "failed": failed, "total": len(test_cases), "accuracy": accuracy}

if __name__ == "__main__":
    res = run_tests()
    print(f"Test Results: {res['passed']}/{res['total']} passed ({res['accuracy']:.1f}% accuracy)")
