- `message_grade_recorded.json`: a real `claude-sonnet-5-5` response, recorded 2026-11-01
  with rubric v1 at effort `low`.
- The other files are hand-built in the documented Messages / Batches response shapes, to
  cover cases that are hard to trigger live (refusals, invalid grades, batch errors). Tests
  parse them with the SDK's own models, so shape drift fails loudly.
