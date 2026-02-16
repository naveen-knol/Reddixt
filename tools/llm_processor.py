"""
LLM Processor for the AI Intelligence System.
Uses Claude to extract structured insights from Reddit content.
"""

import os
import json
import hashlib
from datetime import datetime

import anthropic
from dotenv import load_dotenv

from database import Database

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

EXTRACTION_PROMPT = """You are an intelligence analyst extracting actionable insights from online discussions.

Analyze this Reddit post and extract ALL relevant insights. For each insight, classify it into exactly one type:

- **problem**: A pain point, frustration, or unmet need expressed by the user
- **tool**: A specific tool, product, or service being discussed (positive or negative)
- **idea**: A product/business idea mentioned or implied
- **trend**: A broader pattern, shift, or emerging behavior

For EACH insight found, return a JSON object with these fields:
- type: "problem" | "tool" | "idea" | "trend"
- summary: One clear sentence describing the insight
- entities: List of specific tools, products, or technologies mentioned (empty list if none)
- sentiment: Float from -1.0 (very negative) to 1.0 (very positive)
- urgency_signals: List of urgency indicators found (e.g., "need this yesterday", "critical", "blocking me")
- confidence: Float from 0.0 to 1.0 — how confident you are this is a real, actionable insight (not noise)
- has_solution: Boolean — whether a solution/tool was mentioned for this problem (only relevant for "problem" type)

Focus on SIGNAL, not noise. Skip generic opinions, memes, or off-topic tangents.
Look for: real frustrations from builders, tools gaining genuine traction, unmet needs with no existing solution, and concrete business opportunities.

Return a JSON array of insights. If no actionable insights found, return an empty array [].

---

**Subreddit**: {source_name}
**Title**: {title}
**Content**:
{body}
"""

MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 2000


def get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY must be set in .env")
    return anthropic.Anthropic(api_key=api_key)


def make_embedding(text):
    """Hash-based pseudo-embedding for MVP clustering."""
    h = hashlib.sha256(text.lower().encode()).hexdigest()
    return h


def extract_insights(client, content_row):
    """Send a single piece of content to Claude and parse structured insights."""
    title = content_row["title"] or ""
    body = content_row["body"] or ""
    source_name = content_row["source_name"]

    # Truncate very long posts to control token usage
    if len(body) > 4000:
        body = body[:4000] + "\n\n[...truncated]"

    prompt = EXTRACTION_PROMPT.format(
        source_name=source_name, title=title, body=body
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        insights = json.loads(text)

        if not isinstance(insights, list):
            insights = [insights]

        return insights

    except json.JSONDecodeError as e:
        print(f"    JSON parse error for content {content_row['id']}: {e}")
        return []
    except anthropic.APIError as e:
        print(f"    API error for content {content_row['id']}: {e}")
        return []


def process_batch(batch_size=50):
    """Process a batch of unprocessed content through Claude."""
    db = Database()
    client = get_client()

    content_rows = db.get_unprocessed_content(limit=batch_size)

    if not content_rows:
        print("No unprocessed content found. Run collection first.")
        db.close()
        return 0

    print(f"Processing {len(content_rows)} posts through Claude...")

    total_insights = 0

    for i, row in enumerate(content_rows):
        safe_title = row['title'][:60].encode('ascii', errors='replace').decode('ascii')
        print(f"  [{i+1}/{len(content_rows)}] {row['source_name']}: {safe_title}...", end=" ", flush=True)

        insights = extract_insights(client, row)

        for insight in insights:
            insight_type = insight.get("type", "trend")
            if insight_type not in ("problem", "tool", "idea", "trend"):
                insight_type = "trend"

            summary = insight.get("summary", "")
            if not summary:
                continue

            entities = insight.get("entities", [])
            sentiment = float(insight.get("sentiment", 0.0))
            urgency_signals = insight.get("urgency_signals", [])
            confidence = float(insight.get("confidence", 0.5))

            embedding = make_embedding(summary)

            db.add_insight(
                content_id=row["id"],
                insight_type=insight_type,
                summary=summary,
                entities=entities,
                sentiment=sentiment,
                urgency_signals=urgency_signals,
                confidence=confidence,
                embedding=embedding,
            )
            total_insights += 1

        db.mark_content_processed(row["id"])
        print(f"-> {len(insights)} insights")

    print(f"\nDone. Extracted {total_insights} insights from {len(content_rows)} posts.")
    db.close()
    return total_insights


if __name__ == "__main__":
    process_batch()
