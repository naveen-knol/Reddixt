"""
Reddit Collector for the AI Intelligence System.
Uses Reddit's public JSON endpoints — no API key required.
Pulls posts from target subreddits, calculates engagement scores, and stores them.
"""

import math
import time
from datetime import datetime, timezone

import requests

from database import Database

USER_AGENT = "Reddixt/1.0 (AI Intelligence System; personal use)"
BASE_URL = "https://www.reddit.com"
REQUEST_TIMEOUT = 15

MIN_BODY_LENGTH = 30
MIN_SCORE = 2


def calculate_engagement_score(score, num_comments, posted_utc):
    """
    Engagement = log(score+1) * (1 + comment_ratio) * recency_weight

    - comment_ratio: comments relative to score, capped at 2.0
    - recency_weight: decays from 1.0 to 0.1 over 14 days
    """
    score_component = math.log(max(score, 1) + 1)
    comment_ratio = min(num_comments / max(score, 1), 2.0)

    age_hours = (datetime.now(timezone.utc) - datetime.fromtimestamp(posted_utc, tz=timezone.utc)).total_seconds() / 3600
    recency_weight = max(0.1, 1.0 - (age_hours / (14 * 24)))

    return round(score_component * (1 + comment_ratio) * recency_weight, 3)


def fetch_subreddit_posts(subreddit_name, limit=100, sort="hot", max_age_hours=None):
    """Fetch posts from a subreddit using the public JSON endpoint.

    Args:
        sort: "hot" for trending posts, "new" for chronological (daily mode)
        max_age_hours: if set, only return posts younger than this many hours
    """
    url = f"{BASE_URL}/r/{subreddit_name}/{sort}.json"
    params = {"limit": min(limit, 100), "raw_json": 1}
    headers = {"User-Agent": USER_AGENT}

    cutoff = None
    if max_age_hours:
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)

    all_posts = []
    after = None

    while len(all_posts) < limit:
        if after:
            params["after"] = after

        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        hit_cutoff = False
        for child in children:
            created = child.get("data", {}).get("created_utc", 0)
            if cutoff and created < cutoff:
                hit_cutoff = True
                break
            all_posts.append(child)

        if hit_cutoff:
            break

        after = data.get("data", {}).get("after")
        if not after:
            break

        time.sleep(1)

    return all_posts[:limit]


def fetch_post_comments(post_id, limit=5):
    """Fetch top comments for a post using the public JSON endpoint."""
    url = f"{BASE_URL}/comments/{post_id}.json"
    params = {"limit": limit, "depth": 1, "raw_json": 1}
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if len(data) < 2:
            return []

        comments = []
        for child in data[1].get("data", {}).get("children", []):
            if child.get("kind") != "t1":
                continue
            body = child.get("data", {}).get("body", "")
            if len(body) > 20:
                comments.append(body)

        return comments[:limit]
    except Exception:
        return []


def collect_subreddit(db, source, limit=100, sort="hot", max_age_hours=None):
    """Collect posts from a single subreddit."""
    subreddit_name = source["name"].replace("r/", "")
    collected = 0
    skipped = 0

    try:
        posts = fetch_subreddit_posts(subreddit_name, limit, sort=sort, max_age_hours=max_age_hours)

        for item in posts:
            post = item.get("data", {})

            # Skip stickied posts
            if post.get("stickied", False):
                continue

            body = post.get("selftext", "") or ""
            is_self = post.get("is_self", True)
            score = post.get("score", 0)
            num_comments = post.get("num_comments", 0)
            created_utc = post.get("created_utc", 0)

            # Filter low-quality posts
            if is_self and len(body) < MIN_BODY_LENGTH:
                continue
            if score < MIN_SCORE:
                continue

            post_id = post.get("id", "")
            external_id = f"reddit_{post_id}"

            if db.content_exists(external_id):
                skipped += 1
                continue

            engagement = calculate_engagement_score(score, num_comments, created_utc)

            posted_at = datetime.fromtimestamp(
                created_utc, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")

            # Build full body
            full_body = body
            link_url = post.get("url", "")
            if not is_self and link_url:
                full_body = f"[Link post: {link_url}]\n\n{body}"

            # Fetch top comments for additional signal
            top_comments = fetch_post_comments(post_id, limit=5)
            if top_comments:
                full_body += "\n\n--- Top Comments ---\n" + "\n---\n".join(top_comments)

            permalink = post.get("permalink", "")
            author = post.get("author", "[deleted]") or "[deleted]"

            db.add_content(
                source_id=source["id"],
                external_id=external_id,
                title=post.get("title", ""),
                body=full_body,
                url=f"https://reddit.com{permalink}",
                author=author,
                score=score,
                num_comments=num_comments,
                engagement_score=engagement,
                posted_at=posted_at,
            )
            collected += 1

            # Small delay between comment fetches
            if top_comments:
                time.sleep(0.5)

        db.update_source_collected(source["id"])

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            print(f"  Rate limited on {source['name']}, waiting 10s...", end=" ", flush=True)
            time.sleep(10)
        else:
            print(f"  HTTP error collecting {source['name']}: {e}")
    except Exception as e:
        print(f"  Error collecting {source['name']}: {e}")

    return collected, skipped


def collect_all(limit=100, sort="hot", max_age_hours=None):
    """Collect from all tracked subreddits.

    Args:
        sort: "hot" for trending, "new" for chronological (daily mode)
        max_age_hours: if set, only collect posts from the last N hours
    """
    db = Database()
    sources = db.get_sources(source_type="reddit")

    total_collected = 0
    total_skipped = 0

    mode = f"{sort}, last {max_age_hours}h" if max_age_hours else sort
    print(f"Collecting from {len(sources)} subreddits (limit: {limit}, mode: {mode})...")

    for source in sources:
        print(f"  {source['name']}...", end=" ", flush=True)
        collected, skipped = collect_subreddit(db, source, limit, sort=sort, max_age_hours=max_age_hours)
        total_collected += collected
        total_skipped += skipped
        print(f"{collected} new, {skipped} duplicates")

        # 2s delay between subreddits for public endpoint rate limits
        time.sleep(2)

    print(f"\nDone. Collected {total_collected} new posts, skipped {total_skipped} duplicates.")
    db.close()
    return total_collected


if __name__ == "__main__":
    collect_all()
