# World in Words

Daily English-learning notes generated from BBC World Service's **What in the World** podcast.

## How it works

On weekdays, GitHub Actions reads the official BBC RSS feed, processes the newest unseen episode,
uses Gemini to transcribe its audio and generate Traditional Chinese learning notes, then deploys the
static site to GitHub Pages. Audio and full transcripts are not committed to the repository.

## Setup

1. In the GitHub repository, open **Settings → Secrets and variables → Actions**.
2. Create repository secrets named `GEMINI_FREE_API_KEY` and `GEMINI_PAID_API_KEY`.
   Each AI operation tries the free key up to three times, then the paid key up to three times.
   Failed attempts wait 30 seconds before the next attempt, including when switching keys.
   Exception: an explicit free-quota exhaustion error skips remaining free attempts and switches
   to the paid key immediately, without sleeping. A bare 429 still uses the normal retry delay.
   Paid attempts retain the three-attempt limit and 30-second retry delay. If no paid key is
   configured, free-quota exhaustion raises an error immediately.
   Retries stop as soon as an attempt succeeds; if all six fail, the update raises an error.
   This adds at most 150 seconds of retry waiting per operation, excluding request duration.
   For local runs without a paid key, it raises an error after three failed free attempts.
   Actions streams timestamped progress immediately: each AI operation logs its model, key tier,
   attempt number, duration, and errors, with a waiting message every 30 seconds while blocked.
   Audio download, Gemini upload/cleanup, validation, and saving are timed separately.
   Retry waits are explicitly logged; waiting messages do not impose a request timeout.
3. Open **Settings → Pages** and select **GitHub Actions** as the deployment source.
4. Run **Actions → Update daily podcast → Run workflow** once.

The default feed is `https://podcasts.files.bbci.co.uk/w13xtvrv.rss`. The update runs at 08:00
Asia/Taipei, Tuesday through Saturday. Both can be changed in the workflow or with the
`PODCAST_FEED_URL` environment variable.

The workflow transcribes the complete episode. Manual runs reprocess the latest episode; scheduled
runs only process newly published episodes. Pushing code does not trigger podcast processing.

## Local feed check

```powershell
python -m pip install -r requirements.txt
python scripts/update_podcast.py --dry-run
```

To run the complete process locally, put the following in a local `.env` file and omit `--dry-run`:

```dotenv
GEMINI_FREE_API_KEY=your-free-key
GEMINI_PAID_API_KEY=your-paid-key
```

To deliberately rebuild a particular RSS item, pass its zero-based position, for example
`--episode-offset 0` for the newest episode.

## Attribution

This is an independent educational project and is not affiliated with the BBC. Podcast content
belongs to the BBC. The site links listeners to the official BBC episode pages and does not host
podcast audio or publish full transcripts.
