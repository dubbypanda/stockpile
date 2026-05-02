# input/

Drop your brokerage CSV exports here.

Both tools (`positions` and `cost-basis-charts`) resolve CSV paths in
`config.toml` relative to the repo root, so a path like:

```toml
csv = "input/schwab.csv"
```

refers to this directory regardless of which tool you're running.

CSV files are gitignored and will never be committed.
