# Package 10: Domain integrity

Release gate: run the competition integrity service against every active division before upgrade acceptance. Played or published history must never be removed by a cascade operation. Stage, gameday, match, participant and progression scopes must remain inside their division.

Rollback trigger: any blocking integrity result, orphaned planning reference, duplicate participant, or incorrect published schedule.
