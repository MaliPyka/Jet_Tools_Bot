import re

LINE_RE = re.compile(
    r"^S\.\S+,\s*(?:eVin:\s*\S+,\s*)?(.+)$",
    re.IGNORECASE | re.MULTILINE,
)

NEW_KEYWORDS = ["l 60", "l60", "s100"]
OLD_KEYWORDS = ["max plus", "max pro"]


def classify(model: str) -> tuple[str, bool]:
    text = model.lower()
    if any(k in text for k in NEW_KEYWORDS):
        return "new", True
    if any(k in text for k in OLD_KEYWORDS):
        return "old", True
    return "old", False


def parse_scooter_report(text: str) -> tuple[int, int, list[str]]:
    old = new = 0
    unknown = []

    for match in LINE_RE.finditer(text):
        model = match.group(1).strip()
        category, recognized = classify(model)

        if category == "new":
            new += 1
        else:
            old += 1

        if not recognized:
            unknown.append(model)

    return old, new, unknown