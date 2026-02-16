# Reddit Intelligence Pipeline

## Objective
Collect posts from 12 target subreddits, extract actionable insights using Claude, score and cluster them into product ideas, and generate a weekly briefing report.

## Required Inputs
- Anthropic API key (ANTHROPIC_API_KEY) in `.env`
- No Reddit API key needed — collector uses public JSON endpoints

## Pipeline Sequence

### Phase 1: Collection
**Tool:** `tools/reddit_collector.py`
- Pulls hot posts from each tracked subreddit
- Calculates engagement scores
- Deduplicates by external ID
- Filters out stickied, short, and low-score posts
- Grabs top 5 comments for additional signal

**Run:** `python tools/orchestrator.py collect --limit 100`

### Phase 2: LLM Processing
**Tool:** `tools/llm_processor.py`
- Sends unprocessed posts to Claude (Sonnet)
- Extracts structured insights: problems, tools, ideas, trends
- Each insight gets: type, summary, entities, sentiment, urgency signals, confidence
- Marks posts as processed after extraction

**Run:** `python tools/orchestrator.py process --batch 50`

### Phase 3: Scoring & Clustering
**Tool:** `tools/scoring_engine.py`
- Clusters related insights by entity/keyword overlap
- Calculates per-cluster scores:
  - **Momentum** (0-10): mention count, recency, engagement, cross-subreddit spread
  - **Buildability** (0-10): API mentions, project complexity → effort estimate
  - **Urgency** (0-10): negative sentiment, urgency keywords, problem age
- Detects **gap patterns**: problems in 2+ subreddits with no solution
- Creates scored ideas in the database

**Run:** `python tools/orchestrator.py score --days 7`

### Phase 4: Briefing
**Tool:** `tools/briefing_generator.py`
- Queries top ideas by category
- Generates markdown report with 5 sections:
  1. Quick Wins (weekend projects)
  2. Trending Tools
  3. Unsolved Problems (gap patterns)
  4. Product Opportunities
  5. Signal Analysis
- Saves to `.tmp/briefings/briefing_YYYY-MM-DD.md`

**Run:** `python tools/orchestrator.py brief`

## Full Pipeline
`python tools/orchestrator.py full --limit 100 --batch 50 --days 7`

## Expected Outputs
- `intelligence.db` — SQLite database with all data
- `.tmp/briefings/briefing_YYYY-MM-DD.md` — Weekly briefing report

## Edge Cases & Notes
- **Reddit rate limits:** ~30 requests/min (public endpoints). The collector adds 2s delay between subreddits and handles 429 rate-limit responses.
- **Claude API costs:** Each post costs ~1K-2K tokens. A batch of 50 posts ≈ 50K-100K tokens.
- **Duplicate runs:** Collection deduplicates by post ID. Re-running is safe.
- **Empty results:** If no insights are extracted, check that content meets minimum quality thresholds.
- **Database locked:** Only run one pipeline instance at a time (SQLite single-writer).

## Tracked Subreddits
| Subreddit | Authority Score |
|-----------|----------------|
| r/AI_Agents | 8.0 |
| r/artificialintelligence | 7.0 |
| r/automation | 6.5 |
| r/cofounder | 6.0 |
| r/founder | 6.5 |
| r/microsaas | 8.5 |
| r/producthunt | 7.0 |
| r/producthuntlaunches | 6.5 |
| r/smallbusiness | 6.0 |
| r/upwork | 5.5 |
| r/entrepreneur | 7.0 |
| r/freelance | 5.5 |
