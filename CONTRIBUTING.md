# Contributing

Thanks for looking. This tool is meant to stay small: one area of the Moon or
Mars in, one watertight STL out. Bug reports, clearer docs and fixes are very
welcome; large features (texture, text, multi-part prints) are out of scope.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[test,preview]"
pytest -q              # offline tests
pytest -q --network    # also fetches a few MB of real Moon data
```

## Ground rules

- Only data that is public domain or CC0, read at runtime. No bundled data, and
  no share-alike sources (for example the HRSC/MOLA blend for Mars).
  A new world needs its licence quoted in `DATA.md` with URL and date.
- Every mesh change keeps the tests green: watertight, outward normals, exact
  millimetre size, true scale at 1x.
- Keep the runtime dependency list at numpy.

By contributing you agree your work is released under the MIT licence.
