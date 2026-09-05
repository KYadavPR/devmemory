"""Main entry point for Test App."""

from classifier import TextClassifier

def run():
    clf = TextClassifier()
    samples = [
        "I love this software, it is excellent!",
        "Terrible experience, very bad performance.",
        "Good overall, but needs work."
    ]
    for text in samples:
        print(f"Text: '{text}' -> Sentiment: {clf.predict(text)}")

if __name__ == "__main__":
    run()
