# Software Teleprompter — TEST_PLAN

Suite: `tests/test_teleprompter.py`, run with:

```sh
python3 -m unittest discover -s tests -v
```

All tests are headless: they exercise `Script`, `render_lines`,
`TeleprompterSettings`, and `Player` directly. The curses UI is
NOT unit-tested (it requires a real terminal); it is a thin loop
over the tested core, and its key bindings are documented in
SPEC.md. No test starts a server except the URL-import tests, which
bind a local `http.server` on an ephemeral port (`port 0`) on
127.0.0.1 and shut it down in `tearDown`.

## Coverage map

| Area | Tests |
|---|---|
| Loading text, empty text, paragraph breaks / newlines preserved | `test_load_text`, `test_empty_script`, `test_newlines_and_paragraph_breaks_preserved` |
| Markdown: headings upper-cased, bold/italic/code markers stripped, link text kept | `test_markdown_heading`, `test_markdown_emphasis_stripped`, `test_markdown_link_kept_as_text` |
| Margins (left prefix, right narrowing) and invalid margins rejected | `test_left_margin_prefix`, `test_right_margin_narrows_lines`, `test_negative_margin_rejected` |
| Line spacing inserts blank lines; invalid spacing rejected | `test_line_spacing_inserts_blanks`, `test_line_spacing_out_of_range_rejected` |
| Font face stored; font size scales wrap width; invalid size rejected | `test_font_face_stored`, `test_font_size_scales_wrap_width`, `test_font_size_out_of_range_rejected` |
| WPM validation, lines-per-second derivation, speed change mid-play | `test_wpm_out_of_range_rejected`, `test_lines_per_second_from_wpm`, `test_set_wpm_changes_rate` |
| Play/pause: step advances only while playing, toggle works, pause keeps offset | `test_step_advances_while_playing`, `test_step_does_not_advance_when_paused`, `test_toggle_pause_resume`, `test_pause_keeps_offset` |
| End clamping, at_end, reset, seek clamping, progress | `test_clamps_at_end`, `test_reset_returns_to_top`, `test_seek_clamps`, `test_progress_fraction` |
| Viewport slicing at an offset | `test_visible_lines_window` |
| Mirroring: horizontal reverses lines, vertical reverses order, both, invalid mode, scrolling still works when mirrored | `test_mirror_horizontal`, `test_mirror_vertical`, `test_mirror_both`, `test_mirror_invalid_rejected`, `test_scrolling_works_when_mirrored` |
| File import, missing file raises, URL import via local ephemeral server, failed URL raises ImportError | `test_load_file`, `test_load_missing_file_raises`, `test_load_url_local_server`, `test_load_url_failure_raises_import_error` |
| Render width respects margins + minimum width | `test_render_respects_width_and_margins` |

## Manual checks (not automated)

1. `python3 teleprompter.py --file example_script.txt --dump` prints
   the formatted script.
2. `python3 teleprompter.py --file example_script.txt` opens the
   curses UI; Space pauses/resumes, `+`/`-` change speed, `m`
   cycles mirror, `q` quits. (Requires a real terminal; not run in
   the sandbox test pass.)
3. `python3 teleprompter.py --file example_script.txt --play
   --seconds 5` prints successive viewports and exits on its own.
