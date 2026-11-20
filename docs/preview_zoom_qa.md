# Preview zoom review and QA

The branch introduces a shared control bar and adapts existing preview renderers.
It preserves their processing pipelines and current control locations. Moving
all bars to a common position and sharing before/after preview behavior are
separate changes.

## Automated checks

Run from the repository root with the application dependencies and pytest:

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_preview_zoom_core.py tests/test_preview_zoom.py tests/test_preview_zoom_migration.py tests/test_preview_zoom_native.py
```

Use the native `windows` Qt platform instead of `offscreen` on Windows to run
SendInput tests. Repeat with `QT_SCALE_FACTOR=2` for display scaling coverage.
The Preview zoom QA workflow runs on Windows, Linux and macOS using Python 3.13
and the application's exported dependencies, including its pinned Qt version.

Coverage includes:

- Fit, 100%, plus/minus, equals, shifted plus and keypad variants. Unmodified
  text remains editable. Window and embedded-pane routing do not intercept the
  main viewer's shortcuts; detached Curves controls explicitly share the preview.
- Manual zoom survives resizing. Fit follows viewport resizing, including linked
  previews. Scrolling without zoom and zero-delta wheel events preserve Fit.
- Existing button connections and disabled/busy states remain effective.
  Deleting bars, hosts or viewports leaves no stale shortcut actions or refits.
- Source-relative zoom for reduced renders, Curves' full-resolution detail cache,
  before/after transitions, and Statistical Stretch preview resolution changes.
- Real processing dialogs, masks, comparisons, planetary output, SER keeper
  previews, paired frequency previews and generated script wiring. Source arrays
  are checked for unintended changes. This is representative integration coverage,
  not a processing-quality test of every migrated tool.
- Tiny 8×8 images and Fit scales above the manual zoom ceiling. Zoom In must not
  shrink an image and Zoom Out must take a proportional step.
- Native Windows SendInput dispatch for Ctrl+0/1, equals, shifted equals, minus,
  keypad plus/minus under US and Polish (Programmers) keyboard layouts.

## Findings fixed during review

1. Shortcut actions were owned by the host rather than the bar and survived
   deletion of the controls. Actions now share the bar's lifetime.
2. Holding Fit or 100% repeated expensive callbacks. Auto-repeat is retained only
   for incremental zoom actions, including the event-filter dispatch path.
3. A Fit scale above a renderer's manual ceiling could make Zoom In shrink the
   image or prevent Zoom Out. The shared graphics view and affected renderers
   now permit proportional descent from an existing larger fit scale.
4. Invalid legacy adapters could remove buttons before reporting missing
   callbacks. Required callbacks and layouts are validated before mutation.
5. A pending refit could access a deleted viewport. Linked live viewports are
   checked, and a callback may safely destroy its host.
6. The detached Curves editor was outside the shortcut scope. It now opts in
   explicitly without extending shortcuts to unrelated child dialogs.
7. Ctrl-wheel previews other than CLAHE did not declare their wheel policy;
   ordinary scrolling could exit Fit. These adapters now declare that policy.
8. Native macOS testing exposed a Curves transition bug: restoring the old 100%
   scale while switching to a reduced Fit render could re-enable full-resolution
   detail and its cache. Fit now replaces the bitmap without restoring that
   intermediate scale; the regression checks both mode and cache release.

## Manual validation and limits

Before merging, exercise a packaged build on each target OS: control readability
at normal and high display scaling, Cmd shortcuts on macOS, panning, cursor and
center anchoring, scrollbars, repeated opening/closing, and interaction with
processing workers. Test real large RGB and monochrome images and several open
tools. Automated offscreen runs cannot establish native visual layout or the
behavior of every mouse/trackpad driver. Windows native key tests cover shortcut
translation, not a complete Windows application session.

This change retains renderer-specific zoom limits and allocation strategies.
The tests do not establish a memory bound for arbitrarily large images or
unlimited repeated zoom in renderers that previously had no upper limit.

A full local repository run is compared against the unchanged main baseline.
The baseline already has 36 failing tests and an HDR-composition collection
error; these must be reported separately from the focused zoom suite.
