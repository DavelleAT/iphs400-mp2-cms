# Field notes

I used WordPress Playground to try the same kinds of jobs the Institutional
Research office would need to do in this project. I made an Update, a Report
page, and a separate account for an intern.

1. The admin dashboard is a lot. I counted 44 links in the main menu before I
   even started editing anything. WordPress has sections for plugins, themes,
   media, comments, tools, and a bunch of settings. An IR intern should not have
   to dig through all of that just to post a deadline or survey Update.

2. Draft and published really are two different states. I saved a post called
   "Fall 2026 Survey Update: First Look" as a draft and could not find it on the
   public site. As soon as I published it, the post was public. That made the
   risk feel more real. A half-checked number cannot be allowed to slip from a
   draft into a public Update.

3. WordPress made the slug automatically:
   `fall-2026-survey-update-first-look`. It worked, but I can see these getting
   long when a Report has an official title. I would rather have the CMS make a
   sensible slug automatically and still let the author shorten it before
   publishing.

4. I created a page called "Institutional Research Reports," and it showed up
   in the public navigation. That felt right for Reports because things like the
   Factbook, Common Data Set, and Survey Policy should have a permanent place.
   Updates make more sense in a dated list instead of taking over the main menu.

5. The separate intern account worked the way I hoped for Updates. The intern
   could publish an Update directly, and the content list showed "Research
   Intern" as the author instead of making everything look like it came from a
   shared office account.

6. WordPress stopped the intern from opening the Users screen. The exact message
   was, "Sorry, you are not allowed to list users." That is better than only
   hiding the Users link because the restriction still worked when I went
   straight to the page.

7. One permission surprised me: the WordPress Editor could still edit the
   "Institutional Research Reports" page. That does not match what I want for
   this project. Interns should be able to publish routine Updates, but only the
   Director should be able to edit or publish Reports. We will need to enforce
   that rule ourselves instead of copying WordPress's Editor role exactly.

8. The content filters were simple and useful. After making a few items, the
   list showed `All (4)`, `Mine (1)`, `Published (3)`, and `Draft (1)`. "Mine"
   seems especially useful when several interns have accounts and each person
   wants to find the Update they were working on.

9. The Permalinks screen offered seven choices, including date-based URLs,
   numeric URLs, post names, and a custom structure. That is more choice than
   this small CMS needs. A readable title-based slug is enough, and fewer
   settings would make it harder for someone to accidentally break the URLs.
