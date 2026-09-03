# Findings

One claim per file. **The directory is the status**, and the directory above it
is the machine.

```
findings/
  spark/     DGX Spark (GB10), 121 GB unified LPDDR5X
    verified/ unverified/ refuted/
  mira/      RTX 5070 Ti (16 GB GDDR7) + Ryzen 9 7950X3D + 124 GB DDR5
    verified/ unverified/ refuted/
```

Both trees run llama.cpp pinned at `687e778`, so numbers are comparable across
them. A claim that compares the two machines lives with the machine it was taken
to characterise.

## Why the machine is part of the path

Every file under `spark/` was measured on one box, and many of them are *about*
that box. [00](spark/verified/00-capacity-for-bandwidth.md) is the clearest case:
"a DGX Spark buys capacity and pays with bandwidth" is not a fact about
llama.cpp, it is a fact about GB10, and most of the tree follows from it.

While there was only one machine, that was implicit and harmless. With a second
one it stops being harmless, because the two disagree on hardware questions and
agree on software ones — and nothing in a flat tree told you which kind of claim
you were reading.

So: **a claim is claimed only for the machine whose directory it sits in.** A
finding that turns out to hold everywhere earns that by being measured
elsewhere, not by being filed at the top.

## Reading a claim from another machine

Some claims are hardware-independent and travel intact — a chat template that
drops system messages does so on any GPU. Others invert. The frontmatter says
what was measured, not what generalises; check the mechanism before assuming a
number carries over.
