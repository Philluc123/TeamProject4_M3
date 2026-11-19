# SignalBrief M4 User Testing: Sessions 1-3 (run by Paul)

Three real sessions run by Paul on Nov 16–18, 2026, written in the M4 session template. Sessions 4 and 5 were run by Phil and are in the M4 report.

## Session 1: Nvidia tester

- **Tester:** Follows tech news, especially Nvidia and Jensen Huang. Not on the team or in CEN 4930.
- **Date and format:** Nov 16, 2026, 5:38–5:43 pm, in person, recorded and transcribed with Granola. About 5 minutes, with two other people in the room.
- **Task given:** after a short pitch, enter a topic they care about in the web UI and run it.
- **What they did:** Entered one topic, Nvidia (news, 7 days, why: "Interested in Jensen"). While it ran, the facilitator explained the Scout, Editor and Fact-checker agents. When the edition came back they read the top bullet (a CNBC story) out loud and reacted to its content.
- **Where they got stuck:** The topic form. They didn't know what each field was for and the facilitator had to explain them: "these columns should be a little bit more obvious... you had to tell me." The facilitator also noted the live terminal output reads like "a ticker of numbers" that doesn't explain much.
- **What surprised you:** Instead of a form, they wanted one text box they could "spill off my brain" into, with another agent splitting it into topics (their example: Nvidia, the Jensen Huang story, and updates on China in one sentence). They also wanted the output to look like an actual digital newspaper, with pictures from the sources.
- **Would they use this agent again? What would make them more likely to?** Positive: "this is something I do. This is a really good idea." More likely with a single free-text input and a newspaper-style output with images.
- **Best quote:** "I really like how this looks, the UI of it, because it looks like a newspaper... what I would like to see is... one text box I can just spill off my brain."

## Session 2: Jon

- **Tester:** "Jon", senior, finance major. Not on the team or in CEN 4930.
- **Date and format:** Nov 18, 2026, in person. First time using the tool.
- **Task given:** set up three interests in the web UI and run it, find something worth acting on, check a bullet against its source, and compare the cited and uncited versions.
- **What they did:** Entered Terraria, Gym (5-day window) and Fashion and ran it. He got the core idea quickly: it fetches recent news per topic within a day range. Processing was slow enough that the session paused to wait. His standout result was a Terraria master-mode melee gameplay video (1 day old, 9 views, channel with 157 subscribers). He opened it in about 10 seconds and it matched the bullet. He'd click through on 2 items: the Terraria video and an embroidered-coats item under Fashion.
- **Where they got stuck:** Setup. The build he used (M3 commit 906feb1) opens with the facilitator's 3 topics already filled in. He didn't know where to put his own or what the fields and day-range numbers meant, and had to ask the facilitator. Later, the slow run.
- **What surprised you:** "No notable updates" made him trust it slightly more, not less. He said he'd recommend it to a friend "because it's a new tool," even though he wouldn't use it or pay for it himself. He gets his news from TikTok.
- **Would they use this agent again? What would make them more likely to?** Not in its current state; he'd "probably just use the internet instead." He'd reconsider if it were faster and gave more detail per result (bigger links, more context on what each article is about).
- **Measures:** links opened 1 · bullet matched source: yes · preferred the cited version (with links) · trust 4/5 · daily or weekly: no · recommend: yes · price $0 · worst part and top fix: speed · would switch: no · channel: app.
- **Best quote:** "probably just use the internet instead"

## Session 3: Frankie

- **Tester:** "Frankie", junior, software engineering major. Not on the team or in CEN 4930.
- **Date and format:** Nov 18, 2026, 6:51–7:00 pm, in person, recorded with consent.
- **Task given:** set up three interests himself in the web UI and run it, find something worth acting on, check a bullet against its source, look at the verification footer, and compare two versions of an edition.
- **What they did:** Said he keeps up through Instagram and friends, and that the algorithm keeps showing him the same things. The form opened with the facilitator's topics preloaded. He went to the optional "why" box first, then replaced the topics with his own: sports (news, 5 days), new music (news, 15 days), food (news, 7 days). While it ran he guessed it was "building me an algorithm... like a little For You page" and said it "kind of looks like a newspaper." He picked 2 items he'd act on: an MLB salary cap story and an indie new-music item, nothing from Food. He opened the MLB link and confirmed it matched the bullet. The facilitator then showed the verification footer.
- **Where they got stuck:** Setup. He started in the optional box instead of the topic, and didn't know what the number field was until the facilitator explained it means how many days back to look. Later, the wait.
- **What surprised you:** He assumed it was a personalization algorithm building him a feed, not a fact-checked brief. He asked for guidance on how to word topics ("what describing words to use") to get better results, and wanted it as a daily text "like those Bible apps."
- **Would they use this agent again? What would make them more likely to?** "If it was updated, yeah." Mainly faster, plus tips on describing topics and more links and detail.
- **Measures:** links opened 1 · bullet matched source: yes · cited vs uncited: preferred the cited version because it "looks more professional" and the other "looked like it was whipped up"; asked which he'd use, he said "I already used this one," meaning the linked edition he'd just clicked through · trust 4/5 · relevance 2/5 ("because I wasn't given enough") · time saved: could see it if it were fast, not as is · daily or weekly: "probably not, just because it takes like 15 minutes" · recommend: "in its current state, no" · price: wouldn't pay · worst part and top fix: waiting · would stop daily use: "the time for sure" · channel: text.
- **Best quote:** "Maybe building me an algorithm. Like building me a little For You page maybe."

## Patterns so far (3 sessions)

Setup confusion is the one pattern all three testers showed, so it qualifies for the synthesis. Add Sessions 4 and 5 to each row before writing it.

| Pattern | Sessions | Evidence |
|---|---|---|
| Couldn't set up topics without help | 1, 2, 3 | Didn't know what fields or day numbers meant; facilitator had to explain |
| Too slow; worst part and top fix | 2, 3 | Jon paused mid-session; Frankie: "takes like 15 minutes" |
| Wants more detail per result | 2, 3 | Bigger links and context (Jon); more links and detail (Frankie) |
| Bullet matched its source when checked | 2, 3 | Terraria video; MLB salary cap story |
| Found 2 items they'd act on | 2, 3 | Terraria + coats; MLB + indie music |
| Trust 4/5 | 2, 3 | |
| Won't pay | 2, 3 | $0 / "no" |
| Would not use daily or weekly as is | 2, 3 | Both blamed speed |
| Current source is social media | 2, 3 | TikTok; Instagram |
| Likes the newspaper look | 1, 3 | |
| Wants easier topic input | 1, 3 | One free-text box (1); wording tips (3) |

Against M3's rebuild triggers so far: "can't set up topics without help" fired (3 of 3), and the price ceiling is under $2 for both testers asked. Testers did open and value sources, and no one reported an overstated bullet.
