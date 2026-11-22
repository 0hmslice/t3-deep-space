# Installing Deep Space (instructions for coding agents)

A user asked you to install this theme in T3 Code. These steps install it and switch to it. Only do that: don't commit, push, or change any other setting.

## 1. Find the themes folder

If you have T3's `t3_theme_read` tool (load it through tool search if needed), call it with no arguments. Its `themesDir` field is the folder to use.

Otherwise, use `~/.t3/userdata/themes`. If `~/.t3/userdata` doesn't exist, ask the user where T3 Code keeps its data.

## 2. Install the two files

The theme is `themes/deep-space.json` plus its starfield, `themes/deep-space.webp`. Both go in the themes folder.

```sh
# Without a clone:
curl -fsSL https://raw.githubusercontent.com/0hmslice/t3-deep-space/main/install.sh | T3_THEMES_DIR="<themesDir>" sh

# From a clone of this repo:
T3_THEMES_DIR="<themesDir>" sh install.sh
```

You can leave out `T3_THEMES_DIR` when the folder is `~/.t3/userdata/themes`. If a different `deep-space.json` or `.webp` is already there, the script keeps it as `<file>.previous`, so local edits aren't lost. If you can't run shell commands, download both files from `https://raw.githubusercontent.com/0hmslice/t3-deep-space/main/themes/` into the themes folder yourself.

## 3. Switch to it

- **If you have `t3_theme_set`:** call it with `themeId: "t3-chat"`, then with `themeId: "deep-space"`. Switching away first makes T3 re-read the file if Deep Space was already selected. Don't pass a `theme` object, because that would replace the installed file. Each call returns `"published": false`, which is expected: it means the call only switched themes and didn't publish anything.
- **Otherwise:** tell the user to pick **Deep Space** in T3 Code's theme settings.

## 4. Check

Call `t3_theme_read` again. Its `published` list should include `{"id": "deep-space", "name": "Deep Space", "hasCss": true, "hasBackground": true}`, and `current` should be `deep-space`.

Tell the user that visitors arrive on a schedule. The first ship appears within a minute, and the Millennium Falcon after about 2 minutes. The full schedule is in [README.md](README.md#the-visitors).

## Requirements

- **T3 Code Nightly `0.1.12-nightly.20261121` or later.** The date at the end of the version string is the build date. The theme's CSS is about 93,000 characters and T3's limit is 100,000. Older builds may reject it or leave out the animated scene; if so, ask the user to update.
- You don't need to build anything. The files in `themes/` are ready to use, and "Build from source" in the README is only for editing the theme.
