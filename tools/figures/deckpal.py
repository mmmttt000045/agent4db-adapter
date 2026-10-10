"""Colours of the report deck's three figures, after the Nature (NPG) palette common in research figures.

Each responsibility keeps one hue in all three figures and on the slides: publish green, use navy, maintain and
optimize cyan; pending is salmon, a failed check and invalidation red, the running example brown. Strokes, badges
and fills use the palette's hues (cyan one step darker so white step numbers stay legible); text set in a hue uses
a darker shade so it reads on white. A passed check is a green tick. The paper's figures keep their own colours
(style.py, parts.py).
"""
PUBLISH, PUBLISH_TEXT, PUBLISH_PALE = '#00A087', '#00826D', '#E3F4EF'
USE, USE_TEXT, USE_PALE = '#3C5488', '#3C5488', '#E9EDF5'
MAINT, MAINT_TEXT, MAINT_PALE = '#2E93AF', '#24809A', '#E2F3F7'
PENDING, PENDING_TEXT, PENDING_PALE = '#F39B7F', '#C4603F', '#FDECE6'
FAIL, FAIL_TEXT = '#E64B35', '#D23F29'
EXAMPLE = '#7E6148'
OK = '#00A087'
FIELD = '#F3F5F9'                                 # MAVRA's area
PANEL = '#AEB8D3'                                 # edges of the responsibility boxes
