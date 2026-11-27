# predictygraph syntax, short version

The full language spec: <https://predictygraph.github.io/reference/spec/>.

## Statements (one per line, or separated by `;`)

```
graph [attrs]                     # header: layout, theme, caption, steps=auto, target=...
ID ["Label"] [.class...] [attrs]  # a box (node); the label defaults to the ID
A -> B ["label"] [.class] [attrs] # an arrow; chains (A -> B -> C) and fans (A, B -> C) work
group ID ["Title"] [attrs] {      # a panel; everything up to "}" is inside it
}
default node|edge|group [attrs]   # defaults for everything after it in this panel
legend "Key"                      # names the key box
legend .class "text"              # a key entry, drawn like a box with that class
bracket A, B ["note"]             # curly bracket beside A..B with a note
css { ... }  /  css "file.css"    # styles
# a comment                       (# then a space; "#fff" and "issue #42" are not comments)
```

## Arrows

`->` arrow, `<-` reversed, `<->` both ends, `--` no heads; `=>` thick, `..>` dashed.

Arrow attributes: `route=curve|bend|ortho|straight`, `exit=` / `enter=`
`top|bottom|left|right`, `step=N`, `head=triangle|open|diamond|dot|bar`,
`flow=forward|reverse|both|auto` (moving dots in SVG), `via="x,y x,y"` (fixed bend
points in the root's `at=` frame, straight segments).

## Box attributes

`sub="second line"`, `shape=box|square|round|pill|circle|ellipse|diamond|hexagon|cylinder|note|none`,
`image=icon.svg`, `width=` / `height=` (minimum), `layer=back` (draw under the edges), `align-x=ID` (line up with ID),
`rank=N` (layered), `row=R col=C` (grid), `border=pulse|march|glow` (animated outline in SVG).

## Panel (group) attributes

`layout=layered|row|column|grid|radial|fixed`, `gap=`, `align=center|start|end|stretch`,
`dir=TB|LR|BT|RL` (layered), `cols=N` (grid), `sub="subtitle"`, `align-x=ID`.

## CSS

Selectors: `node`, `edge`, `group`, `graph`, `.class`, `#id`, `group.x node`, and the text
parts `label`, `sub`, `step`, `legend`, `caption`, `bracket`.

Properties: `fill`, `stroke`, `stroke-width`, `stroke-dasharray`, `border-radius`,
`padding`, `color`, `font-family`, `font-size`, `font-weight`, `font-style`,
`text-align`, `accent-bar` (`4px #16a34a`), `accent-side`, `title-fill`,
`label-position: top|bottom|left`, `border: pulse|march|glow`.

Theme colours as variables: `var(--green)`, `var(--blue)`, `var(--muted)`, `var(--border)` ...
Each theme also has classes `.red .orange .yellow .green .cyan .blue .purple`, and
generic ones that say what an item is, so the diagram needs no colours of its own:
`.label` (text, no box), `.plain .strong .quiet` (text weight/colour), `.chip .card .frame
.placeholder .ghost .outline` (boxes), `.band .open` (groups with/without a fill), and
`.on-<colour>` (filled box with readable text, e.g. `.on-blue`). Colour roles name a
meaning, so a brand theme decides the colour: `.on-primary .on-highlight .on-secondary
.on-positive`, and `.series-1` `.series-2` ... for categories (jobs, clusters). Themes with
`utilities = true` add `.fill-<colour> .stroke-<colour> .text-<colour> .sub-<colour>
.regular .bold .heavy` for one-off colours.

## Command line

```
pdg file.pdg                          # -> file.svg
pdg file.pdg -o out.png --width 900 --colors 64
pdg file.pdg --check                  # errors only
pdg file.pdg --theme nord             # or graph theme=nord
pdg file.pdg --target web             # size boxes for any browser's font
pdg --list-themes
```
