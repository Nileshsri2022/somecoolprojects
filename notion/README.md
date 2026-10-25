# Notion (local-only clone)

A local-only, Notion-like workspace/docs app — pages, blocks, nesting,
reordering, duplication, and search — in Python 3 standard library only.
No real Notion account, API, or cloud sync: everything lives in one local
JSON file. See `docs/SPEC.md` for the full spec, divergences, and what is
NOT built (no AI generation, no collaboration, no real Notion UI).

## Quick start

```bash
python3 notion.py register --user alice --password secret
python3 notion.py create-page --user alice --password secret --title "My notes"
# prints a page id, e.g. 3f8a...; use it below as PAGE_ID
python3 notion.py add-block --user alice --password secret --page PAGE_ID \
    --type heading_1 --text "Hello"
python3 notion.py add-block --user alice --password secret --page PAGE_ID \
    --type bulleted_list_item --text "First **bold** and *italic* point"
python3 notion.py show-page --user alice --password secret --page PAGE_ID
python3 notion.py list-pages --user alice --password secret
python3 notion.py duplicate-page --user alice --password secret --page PAGE_ID
python3 notion.py search --user alice --password secret hello
```

Block types: `heading_1`, `heading_2`, `heading_3`, `paragraph`,
`bulleted_list_item`. Bold/italic use `**bold**` / `*italic*` markers.

## More commands

```bash
python3 notion.py edit-block   --user alice --password secret --page PAGE_ID --block BLOCK_ID --text "New text"
python3 notion.py delete-block --user alice --password secret --page PAGE_ID --block BLOCK_ID
python3 notion.py move-block   --user alice --password secret --page PAGE_ID --block BLOCK_ID --to 0
python3 notion.py move-page    --user alice --password secret --page PAGE_ID --parent OTHER_ID --position 0
python3 notion.py move-page    --user alice --password secret --page PAGE_ID --top
python3 notion.py reorder      --user alice --password secret --parent top --order ID1,ID2
python3 notion.py serve --port 8000   # local HTML view at http://127.0.0.1:8000/
```

Use `--data PATH` before the subcommand
(`python3 notion.py --data my.json <command> ...`) to pick a different
store file; the default is `notion_workspace.json` in the working directory.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Docs: `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md`.
