import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from notify.telegram_bot import _chunk_text, build_approval_request_text

if __name__ == "__main__":
    mock_job = {
        "title": "Director Digital Sales Benelux",
        "company": "Mock Retail Group",
        "location": "Amsterdam, Netherlands",
        "relevance_score": 0.85,
        "url": "https://example.com/vacature/123",
    }

    text = build_approval_request_text(mock_job)

    assert mock_job["title"] in text
    assert mock_job["company"] in text
    assert "0.85" in text
    assert mock_job["url"] in text

    chunks = _chunk_text("A" * 100, max_len=40)
    assert all(len(c) <= 40 for c in chunks)
    assert "".join(chunks) == "A" * 100

    print(text)
    print("\nTest passed (message formatting only, nothing sent)")
