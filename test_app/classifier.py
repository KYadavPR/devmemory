class TextClassifier:
    def __init__(self):
        self.positive = {"good", "great", "awesome", "excellent", "love", "fantastic", "amazing"}
        self.negative = {"bad", "terrible", "horrible", "awful", "hate", "worst", "poor"}

    def predict(self, text: str) -> str:
        words = text.lower().replace("!", "").replace(".", "").split()
        pos_score = sum(1 for w in words if w in self.positive)
        neg_score = sum(1 for w in words if w in self.negative)
        return "POSITIVE" if pos_score >= neg_score else "NEGATIVE"
