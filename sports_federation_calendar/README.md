
## Match-day slot generation

Open a draft or capacity-ready match day in **Calendar Planner** and select **Generate Match Slots**. The wizard requests:

- the active venue playing areas to use;
- the local game-day start and end time;
- one total slot duration per match;
- whether a noon pause begins at 12:00 and its duration;
- whether an existing slot plan may be replaced.

The total slot duration is the complete playing-area occupancy and must include normal play, possible overtime, post-match clearance, and setup for the next match. There is no separate hidden buffer that could make the published times misleading.

The preview reports playable slots, explicit noon-break rows, and candidates rejected by active venue or playing-area constraint windows. Start, end, and pause times are interpreted in the user timezone and stored as the corresponding UTC instants. Generation preserves those planned times when it creates the rows, including explicit break rows; it does not rebase generated rows onto a playing area's existing timeline. Generation creates only slots that finish inside the requested game-day window. Venue-wide constraints affect every selected playing area; area-specific constraints affect only that area. Existing slots are never overwritten unless the operator explicitly enables replacement. Slot generation is unavailable once scheduling has started.
## User-facing slot labels

Schedule slots are displayed as their local start and end time plus court, for
example `09:00–09:40 · Court 1`. The same label is used by the backend schedule
assignment picker and by portal/public match-day views, so internal model names
such as `federation.schedule.slot,42` are never shown to users.

