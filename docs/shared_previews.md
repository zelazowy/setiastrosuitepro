# Shared image previews

PreviewZoomBar now places an existing image renderer in PreviewPane. Image
margins use the same opaque neutral background (`#181818`) in light and dark app
themes. Zoom controls sit below the image, aligned left: minus, plus, 100%, Fit,
percentage, followed by a comparison hint when available. Legacy callbacks, busy states,
source-scale tracking and image-processing ownership remain with each tool.

PreviewPane preserves a view's grid or splitter position. Linked frequency
previews share one pane and one control bar. Graphics views nested in outer
scroll areas retain their scrolling arrangement. Legacy button objects remain
available to their owners, while common QToolButtons provide the visible UI.

## Before/after interaction

Hold unmodified Space to show Before. A muted Hold Space to compare hint beside
the zoom readout explains the gesture without adding another button.
Release it to restore the result or the selected Split/Side by side mode.
Text fields, spin boxes and editable combos retain normal space input. Modified
Space retains existing behavior. Focus loss, window deactivation, hiding and
closing restore the preview, even if no physical key release reaches the tool.
Auto-repeat does not rerun comparison callbacks.

Temporary comparison only changes display state. It does not invoke Preview,
Apply or the processing algorithm. Cached image adapters retain a finished worker
result while Before is held and display it on release. Original renders are
converted lazily and reused for that hold. Zoom and source-coordinate geometry
remain stable when original/result render resolutions differ.

Comparison is connected in these 24 preview contexts:

- Curves, CLAHE, Statistical Stretch, ADBE and Background Neutralization.
- Morphology, Halo-B-Gon, WaveScale HDR and WaveScale Dark Enhancer.
- GHS, Levels/Histogram Transform, Star Stretch and Remove Pedestal.
- Texture and Clarity, FX, Convolution/Deconvolution and Multiscale Decomposition.
- Saturation/Chroma, Layers Preview and Flat Strength Preview.
- History Compare with Current, Signature/Insert, AstroSpike and Pixel Math.

Background Neutralization now prepares a non-destructive result after a sample
is selected, found automatically or restored from a preset. The existing Apply
operation remains responsible for updating the document. This makes comparison
meaningful in a tool that previously showed only the sample selector.

History comparison uses Space for Before; Shift+Space+left-drag or middle-drag
still pans. The SER keeper/browser and Blink selection shortcuts retain their
existing Space functions. Combination tools with several independent input
images retain their processing UI: this change does not invent a single Before
reference for those tools. Their backgrounds and zoom layout are standardized.
Graphs, histograms and 3D navigation are outside the image-preview styling scope.

## Reusable API

`PreviewZoomBar` automatically mounts the presentation on the next event-loop
turn, after the caller finishes constructing its layout. Owners keep their
original view, viewport and renderer references. `preview_pane` exposes the
mounted pane. Set `preview_content` before mounting to group linked views.

- `enable_comparison(show_before)` attaches the focus-safe Space
  controller and a text hint to an existing cached renderer.
- `enable_image_comparison(before_image, redraw, source_key)` selects a cached
  QImage or QPixmap at display time. Feed the existing result to its `image()`
  method; it never replaces the processing result with the original.
- `enable_pixmap_comparison(before_image, item, source_key)` adapts a graphics
  pixmap item without replacing its transform.
- `enable_canvas_comparison(canvas)` toggles `sasShowBefore` for a custom painter.
- `enable_overlay_comparison(scene, base_item)` temporarily hides overlays above
  an original base image, preserving existing visibility and handling deleted or
  newly created items.

BeforeAfterCompare continues to own split rendering and display stretches for
Convolution/Deconvolution and Multiscale Decomposition. Its `use_shared_hold()`
method delegates keyboard scope and the text hint to the common controller.
One application dispatcher holds weak references to controllers, so closing or
garbage-collecting dialogs does not leave native event filters on dying wrappers.

## Review and QA

Launch a full source application with isolated preferences and a synthetic RGB
image using the repository's normal environment:

```sh
PYTHONPATH=src python tools/review_previews.py
```

The selector opens real tools rather than replacing their image algorithms.
On Windows, set `PYTHONPATH` using PowerShell before running the same Python file.

The image-preview CI workflow tests Windows with its native Qt backend and Linux
and macOS offscreen, then repeats shared layout/interaction tests at 200% scaling.
The native Windows SendInput checks include Space typing in a field and actual
Space press/release comparison, under US and Polish (Programmers) layouts.

Tests cover source/result pixel differences in 16 real tools, exact restoration
of result pixels and source scale, unmodified source arrays, source changes and
worker results while held, focus changes, hidden/deleted widgets, repeated
closing/garbage collection, splitter ordering, overlay visibility, uint16 data,
Unicode input and CLAHE Side by side geometry. The existing zoom suites also
assert that migrated previews mount their common pane.

Manual checks should include large real RGB/monochrome files, panning, overlays,
Split/Side by side, display stretching and platform theme/display scaling. A
passing automated suite does not validate every processing configuration or
packaged release. Renderer-specific zoom limits and allocations are retained.
