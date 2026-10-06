# IPHS 400 Mini-Project 2 report

Davelle Ampofo-Twumasi  
Kenyon Office of Institutional Research CMS  
October 5, 2026

## What I built and the decisions I made

I built a CMS for Kenyon College's Office of Institutional Research. The Console runs locally with FastAPI, Jinja, and SQLite. It publishes a static public website to GitHub Pages.

I chose the IR office because its content has a real difference in stakes. A short enrollment update is not the same as the Common Data Set or Factbook. Someone may cite a Report years later. A Data Bite is quicker and less permanent. That distinction became the center of the CMS.

The system has two roles. The Director manages users and controls published Reports. Analysts can publish Data Bites without waiting for the Director. They can prepare draft Reports, but the Director decides when those Reports become public. Published Reports also appear in the site's navigation.

My first answer during the grill was that interns could share one account. I changed that after using WordPress Playground. A named account made it possible to see who wrote an item. It also meant the Director could deactivate one person's access without changing the password for everyone. ADR-003 records the switch to individual Analyst accounts.

I also changed the original idea of what writing inside the CMS should feel like. The first working version used Markdown. That was technically fine, but it was not the kind of interface I wanted someone in the IR office to use every day. I stopped and gave this direction

> "so, now update about the project. I want to add proper UI on top to make this usable. But before that, I want to change the way a person uses the CMS. Tthey should be able to use it in plain language ans dnot markdwon, insert tables / charts (or build them, whichever is easier) and be able to see what it will look like on the sample weboage."

That prompt changed a large part of the project. The CMS gained a document-style Editor, editable tables, Charts, uploaded Chart images, and a Site preview. Writers no longer have to work directly in Markdown. The database still stores Markdown because it is portable and easy to render safely.

I cared about what happened to content the Editor could not understand. Dropping an unknown block would be worse than showing it read-only. The final design turns unsupported source into a locked block. The writer can see its rendered result, while the original bytes remain on the server. Saving changes around the block does not rewrite it.

The internal-link design also received more thought than I expected. A link cannot safely depend on a title or slug because both can change. A normal database ID was not enough either because SQLite may reuse a deleted ID. The final version assigns an immutable reference to each item and keeps a tombstone after deletion. A reference to a draft or deleted item becomes plain text on the public site. It can become a link again if the same item is republished.

I also pushed back on the stale-save design before approving the authoring specification

> "Replace `body_base` with an item-level base hash covering at least `title`, `slug`, and `body`. The form saves all three, so a body-only hash could let a stale tab overwrite someone else's newer title or slug. Add a test for that conflict."

That correction expanded the concurrency check to cover the full editable item. If two people open the same content and one saves first, the older form cannot quietly overwrite the newer title, slug, or body.

The public design went through several rounds. I rejected one of the early versions with this response

> "its a bit too juvinile and AI-ey. lets be more creative and not dfall on the defaults."

Another proposal relied on the newspaper-style serif look that appears on many generated websites. I asked for something less familiar while keeping it readable and appropriate for a college office. The final design treats the public site more like a dataset. It uses Atkinson Hyperlegible, numbered sections, a restrained grid, and a limited accent color.

I changed my mind about the Charts after seeing them

> "so actually, i do not like the green in the charts. I think my direction was for the neon green to pop up in other places but i dont like it in the charts tbh."

The bright green worked better as an accent around the site. Inside the Charts, it pulled attention away from the data. I asked for it to be removed from the chart palette.

After the public redesign, I noticed another problem. The visitor-facing site looked finished while the Director and Analysts still had a plain Console. I stopped the process again

> "before we go, my main conern wasnt fully adreessed. we visually rehauled the public site but the sitte the directer ansd admin uses is still barebones. i wasnt it usable and pretty too"

That led to the Console redesign. The final Console has navigation on every signed-in page, clearer lists, separate creation pages, a save bar, and a dashboard that shows what needs attention. The public site and Console share a visual family without using the same stylesheet.

## Where the AI went wrong and how I caught it

The clearest AI mistake concerned individual Analyst accounts.

The first version of the spec described a shared intern account. After the WordPress field trip, I changed the decision to individual named accounts. ADR-003 and the implementation reflected the new decision. One sentence in the spec's Out of Scope section still claimed that individual accounts had been rejected.

The spec contradicted itself for eleven tickets. I found the stale sentence during submission review on September 29. I corrected the issue and posted a comment explaining the change. I did not quietly erase the mistake because the contradiction is part of what happened.

This showed me how an AI can update the section directly in front of it while missing an older sentence elsewhere. A decision can change cleanly in the code and still remain wrong in the documentation.

The reviews caught implementation problems too. During T01, the reviewer found that importing the application could initialize the real `cms.db`. Tests import the app, so a test run could touch the working database. Database initialization moved into FastAPI's lifespan handling.

T05 had a different failure. If a Report's database row named a file that had disappeared from disk, downloading it caused a server error. The route now returns a 404, and a regression test covers the missing-file case.

The table sanitizer also needed a correction. Its first alignment filter allowed more CSS than intended. Values containing `url(...)`, `expression(...)`, or `var(...)` could get through. The review narrowed that rule to the exact values `left`, `right`, and `center`.

The workflow made these mistakes visible because each ticket had an issue, acceptance criteria, tests, and a review comment before closing. I could trace a finding to the code that caused it and the commit that fixed it.

The tests became much larger than I expected. The final suite has 1,540 passing tests. That number is useful, but it does not mean I manually checked every possible environment. Most browser work happened in Chrome. Some ticket comments openly say that I did not repeat the same checks in Safari or with every real spreadsheet application. I would rather state that plainly than imply broader testing than I completed.

## How I used AI, skills, prompts, and other resources

Claude Code handled most of the project work. Sonnet 5 at medium effort supported the first grill, the original specification, and the first set of tickets. Opus 5.5 at high effort handled implementation, TDD, code review, and the later design sessions.

The mattpocock workflow shaped the project. `/grill-with-docs` helped turn a general client idea into decisions. `/to-spec` moved those decisions into a GitHub issue. `/to-tickets` divided the work into smaller pieces with dependencies. Each `/implement` session worked from one ticket. `/tdd` connected the acceptance criteria to tests. `/code-review` checked the result against the ticket and the repository rules.

Some of my strongest prompts came during the later authoring grill. I approved parts of the recommendation while correcting details that could lose data or create security problems. One prompt challenged the proposed internal links, locked blocks, chart storage, SVG generation, external-link rules, and browser evidence.

The stale-save correction quoted earlier came from the same grill. It is a good example of how I used the model. I did not only ask it to produce a feature. I read the proposed behavior and looked for places where it could overwrite someone else's work.

I used WordPress Playground before settling the permissions and content model. I created a post, changed it from draft to published, made a page, and logged in with an Editor account. The WordPress Editor could reach content I wanted to reserve for the Director. That experience influenced the Report lockdown in this CMS.

I also used OpenAI Codex for research support and for the final rubric audit. The audit ran the tests, examined the GitHub issues, checked commit authorship, verified the Pages deployment, and compared the repository with each grading item. Codex did not change the project during that audit.

My token planning was late. The assignment asked for the plan before the first implementation ticket. I completed it after T11. I am leaving that history alone.

My original estimate was about one percent of weekly usage for implementation and another one percent for review on each ticket, so about two percent. The ledger says the Stage 1 tickets, T01 to T11, averaged 1.1 percent each, under the estimate. The Stage 2 tickets, T12 to T24, averaged 3.2 percent, about 60 percent over it. Across all 24 tickets that is about 2.2 percent. The costliest were the Chart builder (T17, 5 percent) and the Editor, Links, Chart rendering, homepage, and Lists tickets (T13, T14, T16, T20, and T22, 4 percent each). `notes/token-budget-plan.md` has the figures, with a per-ticket table for Stage 2. The Editor and chart work cost more than the first set of CMS tickets. The design and Console work also expanded the project after the original core was complete.

Most tickets started in a fresh session. The project recorded one automatic compaction across the saved sessions. The largest sessions involved the Editor, Chart builder, public redesign, and final dashboard. Clearing context between tickets kept unrelated decisions from piling up in one conversation.

## What I would change or build next

Revision history would be my next feature. Reports are meant to last, and the current permissions protect them from Analyst changes after publication. The Director still cannot compare an old version with a new one or restore an earlier copy. That ability fits the client better than adding another editing tool.

I would also make the browser testing easier to repeat. The repository already has strong route and rendering tests, along with screenshots at the required widths. A Playwright walkthrough could repeat the most important actions in Chrome and Safari before each release. I would include login, editing, user deactivation, publishing, and the public export.

I would plan the token budget before writing code next time. I kept finding additions that made the CMS better, and I am glad I built many of them. The late plan meant I had no honest baseline for deciding when the project had grown enough.

The part I would show someone first is the Editor beside the Site preview. That screen contains most of what I wanted the project to become. Someone can write normally, insert a table or Chart, and see the public result while it is still a draft.