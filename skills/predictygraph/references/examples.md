# Example diagrams to start from

Each one is a complete `.pdg` file in the predictygraph repo, with its rendered picture
in the [gallery](https://predictygraph.github.io/gallery/). Copy the closest one and edit it.

- **Every annotation feature in one small diagram** (second lines, steps, `align-x`,
  bracket, legend, caption, side titles):
  [examples/annotations.pdg](https://github.com/predictygraph/predictygraph/blob/master/examples/annotations.pdg)
- **Two panels side by side with numbered steps** (a Pod's path to a GPU):
  [examples/hami/pod_to_gpu.pdg](https://github.com/predictygraph/predictygraph/blob/master/examples/hami/pod_to_gpu.pdg)
- **A layer stack with equal-width tiers and a legend** (the GPU software stack):
  [examples/hami/gpu_stack.pdg](https://github.com/predictygraph/predictygraph/blob/master/examples/hami/gpu_stack.pdg)
- **Stacked panels with brackets, sideways titles and an edge routed around boxes**
  (NVIDIA kernel modules):
  [examples/hami/kernel_modules.pdg](https://github.com/predictygraph/predictygraph/blob/master/examples/hami/kernel_modules.pdg)
- **Three layouts in one file** (step-by-step flow, a grid of nodes, a column):
  [examples/hami_flow.pdg](https://github.com/predictygraph/predictygraph/blob/master/examples/hami_flow.pdg)
- **Flowchart, state machine, ER, class diagram** (Mermaid equivalents):
  [examples/mermaid/](https://github.com/predictygraph/predictygraph/tree/master/examples/mermaid)
- **Animated edges and borders:**
  [examples/animation/](https://github.com/predictygraph/predictygraph/tree/master/examples/animation)

## The smallest useful file

Declare boxes first, then connect them (labels can't go inside an arrow line):

```pdg
graph dir=LR
user "User"
api "API"
db "Database" shape=cylinder
user -> api -> db
```
