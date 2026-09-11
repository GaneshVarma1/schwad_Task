"""Synthetic demo data shared by local and hosted interview environments."""

from datetime import UTC, datetime, timedelta

from app.models import CreateLink


def seed_demo(store, now):
    examples = [
        ("product-launch", "https://example.com/products/new-experience", 1),
        ("engineering-blog", "https://example.org/blog/building-better-connections", 2),
        ("design-system", "https://example.com/design/foundations", 4),
        ("team-handbook", "https://example.org/team/handbook", 5),
        ("fall-newsletter", "https://example.com/newsletter/september", 7),
        ("api-quickstart", "https://example.org/developers/quickstart", 8),
        ("launch-webinar", "https://example.com/events/launch", 10),
        ("customer-stories", "https://example.org/stories", 12),
        ("summer-campaign", "https://example.com/campaigns/summer", 16),
        ("brand-assets", "https://example.org/brand", 20),
        ("early-access", "https://example.com/early-access", 24),
        ("release-notes", "https://example.org/releases", 29),
    ]
    today = datetime.fromtimestamp(now, UTC).date()
    for index, (code, url, age) in enumerate(examples):
        created = now - age * 86400
        expiry = datetime.fromtimestamp(now - 86400, UTC) if index == 8 else None
        store.create(CreateLink(url=url, custom_alias=code, expires_at=expiry), created)
        if index in {6, 10}:
            store.disable(code)
        with store.connection() as db:
            total = 0
            for days_ago in range(min(age, 29), -1, -1):
                if (index == 8 and days_ago <= 1) or (index in {6, 10} and days_ago == 0):
                    continue
                # Deterministic synthetic history; never presented as visitor activity.
                clicks = max(2, (70 - index * 4) + ((30 - days_ago) * 13 + index * 7) % 63)
                day = (today - timedelta(days=days_ago)).isoformat()
                db.execute("INSERT INTO daily_clicks VALUES (?, ?, ?)", (code, day, clicks))
                total += clicks
            db.execute("UPDATE links SET total_clicks = ? WHERE code = ?", (total, code))
