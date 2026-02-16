"""
Briefing Generator for the AI Intelligence System.
Creates weekly intelligence reports from scored ideas.
"""

import os
import json
from datetime import datetime

from database import Database

BRIEFINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".tmp", "briefings")


def ensure_briefings_dir():
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)


def format_idea(idea, rank=None):
    """Format a single idea as a markdown block."""
    prefix = f"**{rank}.** " if rank else "- "
    title = idea["title"]
    effort = idea["effort_estimate"]
    momentum = idea["momentum_score"]
    buildability = idea["buildability_score"]
    urgency = idea["urgency_score"]
    combined = idea["combined_score"]

    subreddits = idea["source_subreddits"]
    if isinstance(subreddits, str):
        try:
            subreddits = json.loads(subreddits)
        except json.JSONDecodeError:
            subreddits = []

    sub_str = ", ".join(subreddits) if subreddits else "N/A"

    lines = [
        f"{prefix}**{title}**",
        f"  - Scores: Momentum {momentum:.1f} | Buildability {buildability:.1f} | Urgency {urgency:.1f} | Combined {combined:.1f}",
        f"  - Effort: {effort}",
        f"  - Sources: {sub_str}",
    ]

    if idea["gap_pattern"]:
        lines.append("  - 🔥 **Gap Pattern Detected** — no existing solution found")

    description = idea.get("description", "")
    if description:
        # Show first 200 chars of description
        desc_short = description[:200] + "..." if len(description) > 200 else description
        lines.append(f"  - Context: {desc_short}")

    lines.append("")
    return "\n".join(lines)


def generate_briefing():
    """Generate a full weekly intelligence briefing."""
    db = Database()
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")

    stats = db.get_stats()

    # Fetch ideas by category
    all_ideas = db.get_ideas(min_score=0.0, limit=100)
    gap_ideas = db.get_gap_patterns(limit=10)

    if not all_ideas:
        print("No ideas found. Run the scoring engine first.")
        db.close()
        return None

    all_ideas = [dict(i) for i in all_ideas]
    gap_ideas = [dict(i) for i in gap_ideas]

    # Categorize
    weekend_projects = [i for i in all_ideas if i["effort_estimate"] == "weekend" and i["buildability_score"] >= 6.0]
    weekend_projects.sort(key=lambda x: x["combined_score"], reverse=True)

    trending_tools = [i for i in all_ideas if any(
        kw in (i.get("description", "") or "").lower()
        for kw in ["tool", "app", "platform", "service", "software"]
    )]
    trending_tools.sort(key=lambda x: x["momentum_score"], reverse=True)

    high_urgency = [i for i in all_ideas if i["urgency_score"] >= 5.0]
    high_urgency.sort(key=lambda x: x["urgency_score"], reverse=True)

    product_opps = [i for i in all_ideas if i["combined_score"] >= 3.0 and i["effort_estimate"] in ("week", "month")]
    product_opps.sort(key=lambda x: x["combined_score"], reverse=True)

    # Build briefing
    sections = []

    sections.append(f"# AI Intelligence Briefing — {date_str}")
    sections.append("")
    sections.append(f"*Generated at {now.strftime('%Y-%m-%d %H:%M UTC')}*")
    sections.append(f"*Database: {stats['content']} posts collected, {stats['insights']} insights extracted, {stats['ideas']} ideas scored*")
    sections.append("")

    # --- Section 1: Quick Wins ---
    sections.append("## 🚀 Quick Wins: Weekend Projects")
    sections.append("")
    if weekend_projects:
        for rank, idea in enumerate(weekend_projects[:5], 1):
            sections.append(format_idea(idea, rank))
    else:
        sections.append("*No weekend-sized projects found this cycle.*\n")

    # --- Section 2: Trending Tools ---
    sections.append("## 📈 Tools Gaining Traction")
    sections.append("")
    if trending_tools:
        for rank, idea in enumerate(trending_tools[:5], 1):
            sections.append(format_idea(idea, rank))
    else:
        sections.append("*No significant tool momentum detected this cycle.*\n")

    # --- Section 3: Unsolved Problems ---
    sections.append("## 🔍 Unsolved Problems (Gap Patterns)")
    sections.append("")
    if gap_ideas:
        for rank, idea in enumerate(gap_ideas[:5], 1):
            sections.append(format_idea(idea, rank))
    else:
        if high_urgency:
            sections.append("*No cross-validated gap patterns, but high-urgency problems detected:*\n")
            for rank, idea in enumerate(high_urgency[:3], 1):
                sections.append(format_idea(idea, rank))
        else:
            sections.append("*No gap patterns detected this cycle.*\n")

    # --- Section 4: Product Opportunities ---
    sections.append("## 💡 Product Opportunities")
    sections.append("")
    if product_opps:
        for rank, idea in enumerate(product_opps[:5], 1):
            sections.append(format_idea(idea, rank))
    else:
        sections.append("*No high-scoring product opportunities this cycle.*\n")

    # --- Section 5: Signal Analysis ---
    sections.append("## 📊 Signal Analysis")
    sections.append("")

    # Meta stats
    type_counts = {}
    insights = db.get_insights(days=7)
    for ins in insights:
        t = ins["insight_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    sections.append("**Insight Breakdown:**")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        sections.append(f"- {t.capitalize()}s: {count}")
    sections.append("")

    # Subreddit activity
    sub_counts = {}
    for ins in insights:
        s = ins["source_name"]
        sub_counts[s] = sub_counts.get(s, 0) + 1

    sections.append("**Most Active Subreddits:**")
    for s, count in sorted(sub_counts.items(), key=lambda x: -x[1])[:5]:
        sections.append(f"- {s}: {count} insights")
    sections.append("")

    # Average scores
    if all_ideas:
        avg_momentum = sum(i["momentum_score"] for i in all_ideas) / len(all_ideas)
        avg_build = sum(i["buildability_score"] for i in all_ideas) / len(all_ideas)
        avg_urgency = sum(i["urgency_score"] for i in all_ideas) / len(all_ideas)
        gap_count = sum(1 for i in all_ideas if i["gap_pattern"])

        sections.append("**Score Averages:**")
        sections.append(f"- Avg Momentum: {avg_momentum:.1f}")
        sections.append(f"- Avg Buildability: {avg_build:.1f}")
        sections.append(f"- Avg Urgency: {avg_urgency:.1f}")
        sections.append(f"- Gap Patterns Found: {gap_count}")
        sections.append("")

    sections.append("---")
    sections.append("*This briefing was auto-generated by the AI Intelligence System.*")

    briefing = "\n".join(sections)

    # Save to file
    ensure_briefings_dir()
    filename = f"briefing_{date_str}.md"
    filepath = os.path.join(BRIEFINGS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(briefing)

    print(f"Briefing saved to: {filepath}")
    print(f"  - {len(weekend_projects)} weekend projects")
    print(f"  - {len(trending_tools)} trending tools")
    print(f"  - {len(gap_ideas)} gap patterns")
    print(f"  - {len(product_opps)} product opportunities")

    db.close()
    return filepath


if __name__ == "__main__":
    generate_briefing()
