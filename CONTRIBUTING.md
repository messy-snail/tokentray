# Contributing to tokentray

Thanks for helping out. Issues and pull requests are welcome in English or
Korean (한국어로 작성해도 됩니다).

## Bugs, ideas and security reports

- **Bug** - open a
  [bug report](https://github.com/messy-snail/tokentray/issues/new?template=bug_report.yml).
  Include `tokentray --version`, your operating system and the output of
  `tokentray doctor`. Remove tokens, webhook URLs and email addresses first.
- **Idea** - open a
  [feature request](https://github.com/messy-snail/tokentray/issues/new?template=feature_request.yml)
  that describes what you are trying to do.
- **Security problem** - please do not open a public issue; follow
  [SECURITY.md](SECURITY.md).

## Development setup

You need [uv](https://docs.astral.sh/uv/); it fetches a suitable Python.

```bash
git clone https://github.com/messy-snail/tokentray
cd tokentray
uv sync
uv run tokentray        # run the tray app from the checkout
uv run pytest           # widget tests use Qt's offscreen platform
uv run ruff check .
```

## Pull requests

1. Branch from `dev` and open the pull request against `dev`. Releases are cut
   from `main`.
2. Add or update tests when you change behaviour.
3. If you change something users see, update both `README.md` and
   `README.ko.md`. A short English note is fine; the maintainer can fill in the
   Korean.
4. If you change the panel, alert cards, tray icon or integrations window,
   regenerate the README screenshots:

   ```bash
   uv run python scripts/render_screenshots.py
   ```

5. Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/),
   for example `fix(ui): keep the panel inside the screen`. English is
   preferred; Korean is fine too.

## Packaging and desktop checks

Build and smoke-test a bundle the same way CI and the release workflow do:

```bash
uv run pyinstaller --noconfirm --distpath dist --workpath build packaging/tokentray.spec
./packaging/smoke.sh
```

After changing the icon design, regenerate and commit the icon files:

```bash
QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py
```

Automated tests cannot see a real desktop. [MANUAL_TEST.md](MANUAL_TEST.md)
lists what to check by hand, and on Linux `./scripts/verify-linux.sh` runs every
desktop check that does not need a person watching.
