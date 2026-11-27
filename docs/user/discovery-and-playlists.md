# Discover videos and plan a playlist

In Windows Codex, open the project checkout and connect the local MCP server using the [fixture setup](../developer/codex-fixture.md). Use the repository's `$video-to-playlist` skill for a playlist based on a seed YouTube video. You can also ask for similar videos or channels, or for recommendations based on an authorised library snapshot, without asking to create a playlist.

## What you will see

- Similarity uses available video metadata, such as titles, descriptions and tags. Seed summaries describe title and description evidence. Missing metadata and incomplete candidate coverage are reported. Recommended videos may use likes, subscriptions or playlist evidence from an authorised snapshot.
- For a playlist, give a seed, topic, maximum total time, maximum time per video and spoken language. A request for exactly two hours needs clarification. An upper limit of two hours can produce a shorter playlist. Videos with unknown durations or unverified spoken language are excluded when those are hard constraints.
- The preview shows the destination, privacy, expiry, ordered videos, exact time and unused time. Check the complete preview before choosing in the native dialog. Close or Reject ends the creation attempt with zero playlist writes. If a write is partial or uncertain, follow the [playlist recovery steps](recovery.md).

## Walk through the fixture today

Ask Codex to read `yt-intel://fixture/previews/create` from `yt-intel-fixture`. It shows the synthetic **Database indexing practice** playlist, with two items totalling **22:00 (1,320 seconds)** and **8:00 (480 seconds)** unused. You can also read `yt-intel://skills/video-to-playlist` to inspect the skill instructions through the same connection.

For recommendations, ask Codex to call `get_library` for likes, then use its snapshot ID with `recommend_videos` to find English videos within 22 minutes total. The result shows which preferences supported the ranking and how much time remains. You can also run `recommend_videos` by itself to use the bundled example. A full seed-to-playlist request will report any missing workflow tools. For repeatable cases, see the [evaluation record](../evidence/skills/video-to-playlist.md).

Once the product handlers are available, try a request with this shape:

> Use $video-to-playlist with my seed YouTube link. Make a private English playlist on database indexing, up to two hours with each video at most 20 minutes. Show me the proposal first.
