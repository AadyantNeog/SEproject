# Draft: D-02 question for the instructor

Status: **draft, not sent.** Aadyant should edit it and send it himself.
Then record the reply in [d02-status.json](d02-status.json) through a
reviewed PR, with a link to the evidence.

---

**Subject:** YouTube MCP project: live data policy (D-02) and Stage 4 demo format

Dear [Instructor],

Our team (Random Stuff) is building the YouTube Video Intelligence MCP
Server. Our submitted SRS records one open dependency, D-02. I would like
your direction on it before the Stage 4 review.

The project brief asks for similarity rankings, recommendations and
aggregated analysis of a user's YouTube library (FR-1 to FR-4). The
playlist workflow (FR-5) builds on FR-1. The YouTube API Services
Developer Policies restrict creating derived metrics and data from API
content. We are not sure this restriction applies to a course project
that runs locally for one authorised test account.

Current state:
- **Fixture data.** All five features work end to end on synthetic data,
  including the real human-approval dialog. This is covered by automated
  tests and was demonstrated in a real MCP client.
- **Live mode.** It can read official metadata and an authorised user's
  library with our own OAuth client. It refuses all derived processing,
  making zero API calls, until we have your direction.

Questions:
1. Is derived processing of live YouTube data acceptable for this project:
   similarity, recommendations and library analysis for one authorised
   test account, run locally and never published?
2. For Stage 4, is a demonstration on synthetic data acceptable for the
   derived features, alongside live reads? Or do you require a live demo of
   FR-1 to FR-5?

Under our SRS, if live use is not permitted, those cases are reported as
*blocked* rather than passed. We will not scrape, use unofficial APIs or
create extra Cloud projects.

Thank you,
Aadyant Neog (BT2024186), for Jeswin Jose and Paul T Mathew
