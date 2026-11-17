# Translations

Owner: Federation Platform Team
Last reviewed: 2026-11-09
Review cadence: Every release

How the platform is translated, and how to add a language. The setup is built
so that a new language costs only its translation work: one registry entry,
one command, and translators in Weblate. Code, templates and checks do not
change per language.

## Contents

- [How it fits together](#how-it-fits-together)
- [Adding a language](#adding-a-language)
- [Changing user-facing text](#changing-user-facing-text)
- [Writing translatable code](#writing-translatable-code)
- [Weblate setup](#weblate-setup)
- [Checks](#checks)
- [Known gaps](#known-gaps)

## How it fits together

| Piece | Where | Role |
| --- | --- | --- |
| Language registry | [`i18n/languages.json`](../../i18n/languages.json) | The only list of languages, their Odoo codes and status. Also groups modules by audience for progress reports. |
| Templates | `<module>/i18n/<module>.pot` | Every translatable text of a module, exported by Odoo itself. |
| Language files | `<module>/i18n/<code>.po` | One per language, for example `nl.po`. Odoo loads `nl.po` for every Dutch variant (`nl_BE`, `nl_NL`); an optional `nl_BE.po` only overrides Belgian differences. |
| Glossary | `i18n/glossary/` | Fixed terms (roster, line-up, game day…) with a definition, translated once per language and shown to translators in Weblate. |
| Tooling | `scripts/i18n/` | `export_pot.sh` rebuilds templates with Odoo; `sync_po.py` creates and updates language files; `pofile.py` is the shared PO reader. |
| Check | `ci/check_translations.py` | Registry, file validity, placeholders and markup, completeness, untranslatable messages. |
| Translators | Weblate | Translates in the browser; commits back to the repository. |

Language status in the registry:

| Status | Meaning |
| --- | --- |
| `draft` | Being translated; not offered to users. Missing texts are only reported. |
| `active` | Offered to users. Missing texts are reported as warnings. |
| `required` | Offered to users. A missing translation fails CI, so no release ships untranslated text. |

## Adding a language

Example: Spanish.

1. Add an entry to `i18n/languages.json` with `"code": "es"`, its Odoo codes
   (for example `es_ES`) and `"status": "draft"`.
2. Run `python3 scripts/i18n/sync_po.py --language es`. This creates `es.po`
   from the template of every module and of the glossary.
3. Commit and push. Weblate discovers the new files on its next update; no
   Weblate configuration changes.
4. Translators start with the glossary, then follow the module groups in the
   registry: clubs and public, match day, federation staff. `python3
   ci/check_translations.py` shows progress per group.
5. After native speakers have reviewed the translation on a staging database,
   set the status to `active`, and to `required` once it is complete.
6. On each database: Settings > Languages > activate the language, and add it
   to the website languages. Odoo loads the `.po` files on activation and on
   every module upgrade.

## Changing user-facing text

1. Change the English text in code, views or templates.
2. Run `scripts/i18n/export_pot.sh` (needs Docker; it uses the CI stack). It
   installs the addons in a throw-away database, exports one template per
   module with Odoo's own exporter, and runs `sync_po.py`.
3. Commit the changed `.pot` and `.po` files with the code change.
4. Weblate shows the new texts to translators. For languages with status
   `required`, CI fails until they are translated, so plan text changes ahead
   of a release.

Keep wording changes small once a screen is translated: every changed English
sentence becomes untranslated in every language. Use glossary terms instead of
synonyms.

## Writing translatable code

- Python: wrap user-facing text in `_()` in models, and in
  `request.env._()` in controllers. Use named placeholders,
  `_("%(team)s plays on %(date)s", team=..., date=...)`, never string
  concatenation or f-strings: translators need the whole sentence and may
  reorder it.
- Messages passed to a page in the URL (`success=`, `error=`,
  `error_hint=`) must be translated before the redirect. CI rejects plain
  literals.
- Templates and views: plain text is translated automatically. Keep a sentence
  in one element; text split around `t-esc` becomes fragments that are hard to
  translate.
- Field labels, help texts and selection values are translated automatically.
- Emails to people without an account use their stored language, for example
  `player._communication_lang()`, rendered with `with_context(lang=...)`.
- Leave dates, numbers and currency to Odoo's formatting widgets.
- Leave room in layouts: German and French texts are often 30% longer than
  English.

## Weblate setup

One Weblate project with component discovery, so new modules and languages
appear without manual setup.

Project:

- Repository: this Git repository, branch `main`.
- Push branch: `weblate-translations`; open pull requests from it. Translations
  go through review and CI like any other change.
- Add a repository webhook to Weblate so it updates on every push.

Component discovery add-on, with these values:

| Setting | Value |
| --- | --- |
| Regular expression | `(?P<component>sports_federation_[a-z_]+)/i18n/(?P<language>[^/.]+)\.po` |
| Component name | `{{ component }}` |
| Base file for new translations | `{{ component }}/i18n/{{ component }}.pot` |
| File format | gettext PO file |
| Language filter | `^[a-z]{2,3}(_[A-Z]{2})?$` |

A separate component for the glossary:

| Setting | Value |
| --- | --- |
| File mask | `i18n/glossary/*.po` |
| Base file for new translations | `i18n/glossary/glossary.pot` |
| File format | gettext PO file |
| Use as a glossary | On |

Project add-ons:

- Update PO files to match POT (msgmerge).
- Customize gettext output: line length `-1` (no wrapping), so files match the
  output of `sync_po.py` and diffs stay small.
- Squash Git commits, per language.

Translation flags on all components: `xml-text`, so Weblate warns when markup
in a translation differs from the source. Odoo's `python-format` flag comes
from the templates.

## Checks

`ci/check_translations.py` runs in CI with its tests
(`ci/test_check_translations.py`). It fails on:

- a `.po` file for a language that is not in the registry;
- an unreadable file, a missing `Language` header or duplicate texts;
- a translation whose placeholders or markup differ from the source;
- an untranslated text in a language with status `required`;
- a plain English `success=`, `error=` or `error_hint=` in a controller.

It warns when a language file is out of step with its template, and prints
completeness per language and module group.

## Known gaps

- **Templates not yet exported.** Run `scripts/i18n/export_pot.sh` once to
  create the `.pot` files. Until then, completeness covers the glossary only.
  The Dutch and French portal files written earlier were extracted the same
  way Odoo does, so their translations carry over into the synced files.
- **Court app.** The offline court app has its own JavaScript texts outside
  Odoo's translation system. It needs a message catalog that is cached with
  the app.
- **PDF language.** Score sheets and game-day schedules print in the language
  of the user who prints them.
- **Mail templates and data records.** Shipped records such as role types and
  fee types are translated through the templates once their name fields are
  translatable; check each model before relying on it.
