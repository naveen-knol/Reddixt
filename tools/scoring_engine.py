"""
Scoring Engine for the AI Intelligence System.
Calculates momentum, buildability, urgency scores. Detects gap patterns. Clusters insights into ideas.
"""

import json
import math
import re
from collections import defaultdict
from datetime import datetime

from database import Database

# Keywords that suggest buildability
API_KEYWORDS = ["api", "sdk", "library", "package", "npm", "pip", "endpoint", "webhook", "integration"]
SIMPLE_KEYWORDS = ["wrapper", "bot", "script", "automation", "chrome extension", "slack bot", "discord bot", "cli tool"]
COMPLEX_KEYWORDS = ["platform", "marketplace", "infrastructure", "enterprise", "ml model", "training", "fine-tune"]

# Urgency signal keywords
URGENCY_KEYWORDS = [
    "need this", "desperately", "frustrated", "painful", "broken",
    "no solution", "nothing works", "can't find", "doesn't exist",
    "blocking", "critical", "urgent", "asap", "help me",
    "struggling", "impossible", "waste of time", "hours wasted",
]


def calculate_momentum_score(insights):
    """
    Momentum (0-10): How much attention is this topic getting?
    Factors: mention count, recency, engagement, cross-subreddit validation.
    """
    if not insights:
        return 0.0

    mention_count = len(insights)
    mention_score = min(mention_count / 5.0, 1.0) * 10

    # Recency: average age in days, newer = higher
    now = datetime.utcnow()
    ages = []
    for ins in insights:
        try:
            created = datetime.strptime(ins["created_at"], "%Y-%m-%d %H:%M:%S")
            age_days = (now - created).total_seconds() / 86400
            ages.append(age_days)
        except (ValueError, KeyError):
            ages.append(7.0)
    avg_age = sum(ages) / len(ages) if ages else 7.0
    recency_score = max(0, 10 - avg_age)

    # Engagement: average engagement score from source posts
    engagements = [float(ins.get("engagement_score", 0)) for ins in insights]
    avg_engagement = sum(engagements) / len(engagements) if engagements else 0
    engagement_score = min(avg_engagement / 5.0, 1.0) * 10

    # Cross-subreddit validation
    subreddits = set(ins.get("source_name", "") for ins in insights)
    cross_score = min(len(subreddits) / 3.0, 1.0) * 10

    momentum = (
        mention_score * 0.3
        + recency_score * 0.3
        + engagement_score * 0.2
        + cross_score * 0.2
    )
    return round(min(momentum, 10.0), 2)


def calculate_buildability_score(summary, entities):
    """
    Buildability (0-10): How feasible is it to build this?
    Higher = easier to build. Also returns effort estimate.
    """
    text = (summary + " " + " ".join(entities)).lower()

    score = 5.0  # baseline

    # Boost if APIs/existing tools are mentioned
    api_matches = sum(1 for kw in API_KEYWORDS if kw in text)
    score += min(api_matches * 0.8, 2.0)

    # Boost if it's a simple project type
    simple_matches = sum(1 for kw in SIMPLE_KEYWORDS if kw in text)
    score += min(simple_matches * 1.0, 2.0)

    # Penalize if it's complex
    complex_matches = sum(1 for kw in COMPLEX_KEYWORDS if kw in text)
    score -= min(complex_matches * 1.0, 3.0)

    score = max(0, min(score, 10.0))

    # Effort estimate
    if score >= 7.5:
        effort = "weekend"
    elif score >= 5.5:
        effort = "week"
    elif score >= 3.0:
        effort = "month"
    else:
        effort = "complex"

    return round(score, 2), effort


def calculate_urgency_score(insights):
    """
    Urgency (0-10): How pressing is this need?
    Factors: negative sentiment, urgency keywords, problem age.
    """
    if not insights:
        return 0.0

    # Sentiment: more negative = more urgent
    sentiments = [float(ins.get("sentiment", 0)) for ins in insights]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
    sentiment_score = max(0, (1 - avg_sentiment) * 5)  # -1 sentiment -> 10, 0 -> 5, 1 -> 0

    # Urgency keyword presence
    all_text = " ".join(
        (ins.get("summary", "") + " " + json.dumps(ins.get("urgency_signals", [])))
        for ins in insights
    ).lower()

    keyword_hits = sum(1 for kw in URGENCY_KEYWORDS if kw in all_text)
    keyword_score = min(keyword_hits / 3.0, 1.0) * 10

    # Recency of problem mentions
    now = datetime.utcnow()
    ages = []
    for ins in insights:
        try:
            created = datetime.strptime(ins["created_at"], "%Y-%m-%d %H:%M:%S")
            age_days = (now - created).total_seconds() / 86400
            ages.append(age_days)
        except (ValueError, KeyError):
            ages.append(7.0)
    avg_age = sum(ages) / len(ages) if ages else 7.0
    recency_score = max(0, 10 - avg_age * 1.5)

    urgency = (
        sentiment_score * 0.4
        + keyword_score * 0.35
        + recency_score * 0.25
    )
    return round(min(urgency, 10.0), 2)


def detect_gap_pattern(insights):
    """
    Gap pattern: problem mentioned in 2+ subreddits with no solution referenced.
    Returns True if this is a gap.
    """
    problem_insights = [i for i in insights if i.get("insight_type") == "problem"]
    if len(problem_insights) < 2:
        return False

    subreddits = set(i.get("source_name", "") for i in problem_insights)
    if len(subreddits) < 2:
        return False

    # Check if any insight mentions a solution
    for ins in insights:
        # If urgency_signals is stored as JSON string, parse it
        signals = ins.get("urgency_signals", [])
        if isinstance(signals, str):
            try:
                signals = json.loads(signals)
            except json.JSONDecodeError:
                signals = []

        entities = ins.get("entities", [])
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except json.JSONDecodeError:
                entities = []

        # If there are tool/product entities alongside a problem, it might have a solution
        if ins.get("insight_type") == "tool" and entities:
            return False

    return True


def cluster_insights(insights, similarity_threshold=0.70):
    """
    Group related insights by entity/keyword overlap.
    MVP approach: cluster by shared entities and keyword overlap in summaries.
    """
    if not insights:
        return []

    clusters = []
    used = set()

    for i, ins_a in enumerate(insights):
        if i in used:
            continue

        cluster = [ins_a]
        used.add(i)

        entities_a = _get_entities(ins_a)
        words_a = _get_keywords(ins_a.get("summary", ""))

        for j, ins_b in enumerate(insights):
            if j in used:
                continue

            entities_b = _get_entities(ins_b)
            words_b = _get_keywords(ins_b.get("summary", ""))

            # Entity overlap
            entity_overlap = len(entities_a & entities_b) > 0 if entities_a and entities_b else False

            # Keyword overlap (Jaccard similarity)
            if words_a and words_b:
                intersection = len(words_a & words_b)
                union = len(words_a | words_b)
                keyword_sim = intersection / union if union > 0 else 0
            else:
                keyword_sim = 0

            if entity_overlap or keyword_sim >= similarity_threshold:
                cluster.append(ins_b)
                used.add(j)

        clusters.append(cluster)

    return clusters


def _get_entities(insight):
    entities = insight.get("entities") or []
    if isinstance(entities, str):
        try:
            entities = json.loads(entities)
        except json.JSONDecodeError:
            entities = []
    if not entities or not isinstance(entities, list):
        return set()
    return set(e.lower() for e in entities if e and isinstance(e, str))


def _get_keywords(text):
    """Extract meaningful keywords from text."""
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "and", "or", "but", "in", "on", "at", "to", "for", "of",
                  "with", "by", "from", "it", "this", "that", "i", "we",
                  "you", "they", "my", "your", "not", "no", "so", "if",
                  "can", "do", "just", "like", "use", "using", "have", "has"}
    words = set(re.findall(r'\b[a-z]{3,}\b', text.lower()))
    return words - stop_words


def run_scoring(days=7):
    """Main scoring pipeline: fetch insights, cluster, score, create ideas."""
    db = Database()

    insights = db.get_insights(days=days)
    if not insights:
        print("No insights found. Run processing first.")
        db.close()
        return 0

    # Convert sqlite3.Row to dict for easier manipulation
    insights_list = [dict(ins) for ins in insights]

    print(f"Scoring {len(insights_list)} insights from the last {days} days...")

    # Cluster insights
    clusters = cluster_insights(insights_list)
    print(f"Found {len(clusters)} insight clusters.")

    ideas_created = 0

    for cluster in clusters:
        if not cluster:
            continue

        # Build idea from cluster
        # Title: use the most confident insight's summary
        best = max(cluster, key=lambda x: float(x.get("confidence", 0)))
        title = best.get("summary", "Untitled")
        if len(title) > 100:
            title = title[:97] + "..."

        # Description: combine unique summaries
        summaries = list(dict.fromkeys(ins.get("summary", "") for ins in cluster))
        description = " | ".join(summaries[:5])

        # Collect all entities
        all_entities = set()
        for ins in cluster:
            all_entities.update(_get_entities(ins))

        insight_ids = [ins.get("id") for ins in cluster if ins.get("id")]
        source_subs = list(set(ins.get("source_name", "") for ins in cluster))

        # Calculate scores
        momentum = calculate_momentum_score(cluster)
        buildability, effort = calculate_buildability_score(
            description, list(all_entities)
        )
        urgency = calculate_urgency_score(cluster)
        gap = detect_gap_pattern(cluster)

        db.add_idea(
            title=title,
            description=description,
            insight_ids=insight_ids,
            momentum_score=momentum,
            buildability_score=buildability,
            urgency_score=urgency,
            effort_estimate=effort,
            gap_pattern=gap,
            source_subreddits=source_subs,
        )
        ideas_created += 1

        flag = " ** GAP PATTERN **" if gap else ""
        safe_title = title[:60].encode('ascii', errors='replace').decode('ascii')
        print(f"  Idea: {safe_title}... [M:{momentum} B:{buildability} U:{urgency} E:{effort}]{flag}")

    print(f"\nDone. Created {ideas_created} ideas.")
    db.close()
    return ideas_created


if __name__ == "__main__":
    run_scoring()
