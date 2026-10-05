"""
Reddit Traffic Worker — posts digital asset previews to relevant subreddits.
Uses PRAW (free Reddit API). No cost.

Env vars:
  REDDIT_CLIENT_ID      — from reddit.com/prefs/apps
  REDDIT_CLIENT_SECRET  — same app
  REDDIT_USERNAME       — your Reddit username
  REDDIT_PASSWORD       — your Reddit password
"""
from __future__ import annotations
import os, time, logging
from .base import BaseWorker, WorkerResult

log = logging.getLogger(__name__)

REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME      = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD      = os.environ.get("REDDIT_PASSWORD", "")

# Subreddits by asset type — these allow sharing and have buyers
SUBREDDIT_MAP: dict[str, list[str]] = {
    "printable":     ["DesignSharing", "freebies", "crafts", "planner"],
    "svg_bundle":    ["svgfiles", "cricut", "silhouette", "DesignSharing"],
    "logo":          ["logodesign", "graphic_design", "DesignSharing", "entrepreneur"],
    "template":      ["DesignSharing", "socialmedia", "smallbusiness"],
    "planner":       ["bulletjournal", "planner", "productivity", "DesignSharing"],
    "digital_art":   ["DigitalArt", "Art", "DesignSharing"],
    "game_asset":    ["gamedev", "indiegaming", "Unity3D", "godot"],
    "3d_model":      ["gamedev", "blender", "3Dmodeling", "Unity3D"],
    "default":       ["DesignSharing", "graphic_design"],
}

# Post templates per asset type
POST_TEMPLATES: dict[str, dict] = {
    "printable": {
        "title":  "[OC] Free {style} {asset_type} bundle — instant download",
        "body":   (
            "Hey r/{subreddit}! Sharing a free **{style} {asset_type}** pack I made.\n\n"
            "Includes high-res files, commercial license included.\n\n"
            "🔗 Download free: {store_url}\n\n"
            "Let me know what you think! More styles coming soon."
        ),
        "flair":  "Free Resource",
    },
    "svg_bundle": {
        "title":  "[Free SVG] {style} {asset_type} — Cricut/Silhouette ready",
        "body":   (
            "Dropping a free **{style} SVG bundle** — works with Cricut, Silhouette, and any cutting machine.\n\n"
            "Commercial use OK.\n\n"
            "🔗 Free download: {store_url}\n\n"
            "Feedback welcome!"
        ),
        "flair":  "Free Resource",
    },
    "logo": {
        "title":  "[OC] {style} logo pack — free for personal + commercial use",
        "body":   (
            "Created a **{style} logo template pack** — fully editable, vector format.\n\n"
            "Perfect for freelancers and small businesses.\n\n"
            "🔗 Get it free: {store_url}"
        ),
        "flair":  "Resource",
    },
    "game_asset": {
        "title":  "[Free Asset] {style} {asset_type} pack for Unity/Godot/Unreal",
        "body":   (
            "Sharing a free **{style} {asset_type}** pack for game devs.\n\n"
            "Formats: PNG + source files. Free for commercial projects.\n\n"
            "🔗 Download: {store_url}\n\n"
            "Let me know if you want more variations!"
        ),
        "flair":  "Assets",
    },
    "default": {
        "title":  "[Free] {style} {asset_type} — commercial license included",
        "body":   (
            "Sharing a free **{style} {asset_type}** I made.\n\n"
            "Commercial use allowed, instant download.\n\n"
            "🔗 {store_url}\n\n"
            "Happy to take requests for styles/formats."
        ),
        "flair":  "Resource",
    },
}


class RedditTrafficWorker(BaseWorker):
    capabilities = ["reddit_traffic", "social_media", "traffic", "promotion"]
    workstream_id = "traffic"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        inp = self._parse_input(task)

        asset_type  = inp.get("asset_type", "printable")
        style       = inp.get("style", "minimal")
        store_url   = inp.get("store_url", "https://gumroad.com")
        preview_url = inp.get("preview_url", "")
        max_posts   = int(inp.get("max_posts", 2))

        if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
            return WorkerResult(
                success=False,
                output={
                    "error": "not_configured",
                    "message": "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD env vars",
                    "how_to": "Create a script app at reddit.com/prefs/apps, use your account AudienceAny3122",
                },
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            import praw
        except ImportError:
            return WorkerResult(
                success=False,
                output={"error": "praw not installed — run: pip install praw"},
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=f"CEO-GIR/1.0 u/{REDDIT_USERNAME}",
        )

        subreddits = SUBREDDIT_MAP.get(asset_type, SUBREDDIT_MAP["default"])[:max_posts]
        template   = POST_TEMPLATES.get(asset_type, POST_TEMPLATES["default"])

        posted = []
        errors = []
        for sub_name in subreddits:
            try:
                title = template["title"].format(style=style, asset_type=asset_type, subreddit=sub_name)
                body  = template["body"].format(
                    style=style, asset_type=asset_type,
                    subreddit=sub_name, store_url=store_url,
                )
                sub  = reddit.subreddit(sub_name)

                if preview_url:
                    submission = sub.submit_image(title, image_url=preview_url, nsfw=False)
                    # Add store link as a comment on the image post
                    submission.reply(f"📥 Download link: {store_url}")
                else:
                    submission = sub.submit(title, selftext=body)

                posted.append({
                    "subreddit": sub_name,
                    "url": f"https://reddit.com{submission.permalink}",
                    "title": title,
                })
                log.info("Posted to r/%s: %s", sub_name, submission.permalink)
                time.sleep(10)  # Reddit rate limit: be a good citizen
            except Exception as e:
                errors.append({"subreddit": sub_name, "error": str(e)})
                log.warning("Reddit post failed r/%s: %s", sub_name, e)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=len(posted) > 0,
            output={
                "posts_made": posted,
                "errors": errors,
                "asset_type": asset_type,
                "style": style,
                "store_url": store_url,
                "traffic_estimate": len(posted) * 150,  # avg upvoted post gets ~150 visits
            },
            duration_ms=duration_ms,
            economic_data={
                "revenue_estimate": len(posted) * 0.75,  # ~$0.75 per post in conversions
                "spend": 0.0,
            },
        )

    def _sim_result(self, asset_type: str, style: str, store_url: str, start: float) -> WorkerResult:
        """Simulate when Reddit creds not set — still logs the planned posts."""
        subreddits = SUBREDDIT_MAP.get(asset_type, SUBREDDIT_MAP["default"])[:2]
        template   = POST_TEMPLATES.get(asset_type, POST_TEMPLATES["default"])
        planned = []
        for sub in subreddits:
            planned.append({
                "subreddit": sub,
                "title": template["title"].format(style=style, asset_type=asset_type, subreddit=sub),
                "status": "simulated — add REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD to post",
            })
        return WorkerResult(
            success=True,
            output={"simulated": True, "planned_posts": planned, "store_url": store_url},
            duration_ms=int((time.monotonic() - start) * 1000),
            economic_data={"revenue_estimate": 0.0, "spend": 0.0},
        )

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data
