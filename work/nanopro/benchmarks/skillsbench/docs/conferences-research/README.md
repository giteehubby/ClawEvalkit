# ML Conference Paper Rankings

Paper rankings fetched from OpenReview API, sorted by average reviewer rating.

## Data Summary

| Conference | Total Papers | With Scores | Rating Scale | Top Score |
|------------|--------------|-------------|--------------|-----------|
| ICLR 2026  | 15,734       | 13,920      | 0-10         | 8.50      |
| ICML 2025  | 3,257        | 3,257       | 1-5          | 4.75      |

## Files

### Reports (Markdown)
- `iclr2026_top_papers.md` - Top 100 ICLR 2026 papers by rating
- `icml2025_top_papers.md` - Top 100 ICML 2025 papers by rating

### Raw Data (JSON)
- `iclr2026_ranked.json` - All 13,920 ICLR 2026 papers with scores
- `icml2025_ranked.json` - All 3,257 ICML 2025 accepted papers

### Reference
- `OPENREVIEW_API_GUIDE.md` - OpenReview API documentation
- `scripts/` - Python scripts used to fetch data

## Data Format

Each JSON file contains:
```json
{
  "total_papers": 15734,
  "papers_with_scores": 13920,
  "top_100": [...],
  "all_papers": [
    {
      "id": "paper_forum_id",
      "title": "Paper Title",
      "avg_rating": 8.0,
      "ratings": [8, 8, 8, 8],
      "num_reviews": 4,
      "url": "https://openreview.net/forum?id=..."
    }
  ]
}
```

## Last Updated
2025-12-30
